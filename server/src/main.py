"""API Flask : le front envoie question + profil + lignes du portefeuille, l'équipe de 5 agents répond.

Lancer : `flask --app server.src.main run --port 5000` (le front Vite proxifie /api vers ce port).
"""
from __future__ import annotations

import re
import threading
import time
from collections import defaultdict, deque

from flask import Flask, jsonify, request
from flask_cors import CORS
from pydantic import ValidationError

from alphaforge.config import get_settings
from alphaforge.contracts import AnalysisRequest, Holding, Persona, Portfolio
from alphaforge.llm import LLMError, ModelRouter
from alphaforge.observability import UsageTracker, model_call_logger, setup_logging
from alphaforge.retrieval import KnowledgeBase
from alphaforge.team import TeamOrchestrator

PERSONAS = {"preservation": Persona.PRUDENT, "income": Persona.PRUDENT, "balanced": Persona.BALANCED, "growth": Persona.BOLD}
HORIZON_YEARS = {"short": 2, "medium": 5, "long": 10}
RATE_LIMIT = (10, 60)  # 10 analyses par minute et par IP : chaque analyse coûte environ 0,1 $ avec Bedrock


def to_request(body: dict) -> AnalysisRequest:
    """Traduit le payload du front (profil + lignes) en AnalysisRequest. Le ticker n'est jamais deviné."""
    profile = body.get("profile") or {}
    persona = Persona.PRUDENT if profile.get("comfort") == "stability" else PERSONAS.get(profile.get("objective"), Persona.BALANCED)
    holdings = [Holding.model_validate(h) for h in body.get("holdings") or []]
    question = str(body.get("question", "")).strip()
    mentioned = [h.ticker for h in holdings if re.search(rf"\b{re.escape(h.ticker)}\b", question, re.I) or (h.name and h.name.lower() in question.lower())]
    return AnalysisRequest(
        question=question,
        persona=persona,
        tickers=[str(t).upper() for t in body.get("tickers") or mentioned],
        portfolio=Portfolio(holdings=holdings) if holdings else None,
        horizon_years=body.get("horizon_years") or HORIZON_YEARS.get(profile.get("horizon")),
    )


def build_orchestrator() -> TeamOrchestrator:
    settings = get_settings()
    setup_logging(settings)
    router = ModelRouter.from_settings(settings, [UsageTracker(), model_call_logger(settings.cloudwatch_metrics)])
    market = None
    if settings.market_data == "yahoo":
        from alphaforge.team.market import YahooMarketData

        market = YahooMarketData()
    return TeamOrchestrator(router, KnowledgeBase(settings) if settings.knowledge_base_id else None, market)


def create_app(orchestrator: TeamOrchestrator | None = None) -> Flask:
    app = Flask(__name__)
    CORS(app, origins=[r"http://localhost:\d+", r"http://127\.0\.0\.1:\d+"])
    state = {"orchestrator": orchestrator}
    lock, hits = threading.Lock(), defaultdict(deque)

    def limited(ip: str) -> bool:
        now, (limit, window) = time.monotonic(), RATE_LIMIT
        with lock:
            recent = hits[ip]
            while recent and now - recent[0] > window:
                recent.popleft()
            if len(recent) >= limit:
                return True
            recent.append(now)
            return False

    @app.get("/api/health")
    def health():
        return jsonify(status="ok")

    @app.post("/api/analyze")
    def analyze():
        if limited(request.remote_addr or "?"):
            return jsonify(error="Trop de requêtes : réessayez dans une minute."), 429
        try:
            analysis = to_request(request.get_json(silent=True) or {})
        except (ValidationError, ValueError) as exc:
            return jsonify(error="Requête invalide", detail=str(exc)[:300]), 400
        with lock:
            if state["orchestrator"] is None:
                state["orchestrator"] = build_orchestrator()
        try:
            report = state["orchestrator"].run(analysis)
        except LLMError as exc:  # la synthèse et les agents gèrent leurs pannes ; ceci ne couvre que le reste
            return jsonify(error="Analyse indisponible", detail=type(exc).__name__), 503
        return jsonify(report.model_dump(mode="json"))

    return app


app = create_app()
