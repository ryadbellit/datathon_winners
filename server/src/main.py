"""API Flask : le front envoie question + profil + lignes du portefeuille, l'équipe de 5 agents répond.

Lancer : `flask --app server.src.main run --port 5000` (le front Vite proxifie /api vers ce port).
"""
from __future__ import annotations

import json
import logging
import os
import queue
import re
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Callable

from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_cors import CORS
from pydantic import ValidationError

from alphaforge.config import get_settings
from alphaforge.contracts import AnalysisRequest, Holding, Persona, Portfolio
from alphaforge.llm import LLMError, ModelRouter
from alphaforge.observability import UsageTracker, model_call_logger, setup_logging
from alphaforge.retrieval import KnowledgeBase
from alphaforge.starter import load_starter
from alphaforge.storage import REPORTS, LocalStorage, StorageError, get_storage
from alphaforge.team import TeamOrchestrator
from alphaforge.tracing import setup_tracing

logger = logging.getLogger("alphaforge.server")
PERSONAS = {"preservation": Persona.PRUDENT, "income": Persona.PRUDENT, "balanced": Persona.BALANCED, "growth": Persona.BOLD}
HORIZON_YEARS = {"short": 2, "medium": 5, "long": 10}
RATE_LIMIT = (10, 60)  # 10 analyses par minute et par IP : chaque analyse coûte environ 0,17 $ avec Bedrock
GLOBAL_LIMIT = (int(os.environ.get("ANALYSES_PER_HOUR", "0")), 3600)  # plafond de coût du site public (0 = aucun)
TRUSTED_PROXIES = int(os.environ.get("TRUSTED_PROXIES", "0"))  # en ligne : 2 (CloudFront puis load balancer)
FRONTEND_DIST = Path(os.environ.get("FRONTEND_DIST", "alphaforge-ai/dist"))  # interface compilée, servie si présente
HEARTBEAT_SECONDS = 15  # commentaire SSE pendant les étapes longues : CloudFront coupe après 60 s de silence


def to_request(body: dict, find_tickers: Callable[[str], list[str]] = lambda question: []) -> AnalysisRequest:
    """Traduit le payload du front (profil + lignes) en AnalysisRequest.

    Tickers : ceux envoyés explicitement, sinon ceux nommés dans la question (lignes du portefeuille, puis actifs de
    l'univers reconnus par `find_tickers`, ex. « Tesla » -> TSLA). Aucun ticker n'est deviné au-delà d'un nom explicite."""
    profile = body.get("profile") or {}
    persona = Persona.PRUDENT if profile.get("comfort") == "stability" else PERSONAS.get(profile.get("objective"), Persona.BALANCED)
    holdings = [Holding.model_validate(h) for h in body.get("holdings") or []]
    question = str(body.get("question", "")).strip()
    held = [h.ticker for h in holdings if re.search(rf"\b{re.escape(h.ticker)}\b", question, re.I) or (h.name and h.name.lower() in question.lower())]
    mentioned = list(dict.fromkeys([*held, *find_tickers(question)]))
    return AnalysisRequest(
        question=question,
        persona=persona,
        tickers=[str(t).upper() for t in body.get("tickers") or mentioned],
        portfolio=Portfolio(holdings=holdings) if holdings else None,
        horizon_years=body.get("horizon_years") or HORIZON_YEARS.get(profile.get("horizon")),
        esg_preference=profile.get("esg") if profile.get("esg") in ("none", "aware", "strong") else "none",
        exclusions=[t.strip() for t in re.split(r"[,;]", str(profile.get("exclusions") or "")) if t.strip() and t.strip().lower() != "none"],
    )


@dataclass
class Services:
    """Ce dont l'API a besoin : l'orchestrateur, la détection des actifs cités, l'archivage des rapports."""

    orchestrator: TeamOrchestrator
    find_tickers: Callable[[str], list[str]] = lambda question: []
    archive: Callable[[dict], None] = lambda report: None


def build_services() -> Services:
    settings = get_settings()
    setup_logging(settings)
    setup_tracing(settings)
    router = ModelRouter.from_settings(settings, [UsageTracker(), model_call_logger(settings.cloudwatch_metrics)])
    storage = get_storage(settings)
    # Jeu de départ PolyFinances : depuis le stockage configuré (S3), sinon depuis la copie locale ./data/starter
    starter = load_starter(storage, LocalStorage(settings.local_storage_dir))
    market = quant = checker = None
    find: Callable[[str], list[str]] = lambda question: []
    if starter is not None:
        from server.src.risk.checks import ProfileRules
        from server.src.risk.universe import find_tickers

        checker = ProfileRules(starter)
        find = lambda question: find_tickers(question, starter)  # noqa: E731
    if settings.market_data == "yahoo":
        from alphaforge.team.market import YahooMarketData

        market = YahooMarketData()  # actualités et prix des derniers jours
    if starter is not None or settings.market_data == "yahoo":
        from server.src.risk.quant import PortfolioQuantMetrics

        quant = PortfolioQuantMetrics(starter)  # jeu de départ d'abord, Yahoo en direct pour les autres actifs

    def archive(report: dict) -> None:  # trace d'exécution consultable après coup (S3 en production)
        try:
            storage.put_json(f"{REPORTS}/analyses/{report['request_id']}.json", report)
        except StorageError as exc:
            logger.warning("archive_error", extra={"event": "archive_error", "error": str(exc)[:200]})

    kb = KnowledgeBase(settings) if settings.knowledge_base_id else None
    return Services(TeamOrchestrator(router, kb, market, quant, checker=checker), find, archive)


def create_app(services: Services | TeamOrchestrator | None = None) -> Flask:
    app = Flask(__name__, static_folder=None)
    if TRUSTED_PROXIES:  # vraie IP du client derrière CloudFront + load balancer (sinon une seule limite pour tous)
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=TRUSTED_PROXIES, x_proto=TRUSTED_PROXIES)
    CORS(app, origins=[r"http://localhost:\d+", r"http://127\.0\.0\.1:\d+"])
    state = {"services": Services(services) if isinstance(services, TeamOrchestrator) else services}
    lock, hits = threading.Lock(), defaultdict(deque)

    def limited(ip: str) -> bool:
        now = time.monotonic()
        with lock:
            for key, (limit, window) in ((ip, RATE_LIMIT), ("*", GLOBAL_LIMIT)):
                recent = hits[key]
                while recent and now - recent[0] > window:
                    recent.popleft()
                if limit and len(recent) >= limit:
                    return True
            hits[ip].append(now)
            hits["*"].append(now)
            return False

    @app.get("/api/health")
    def health():
        return jsonify(status="ok")

    def prepare() -> tuple[AnalysisRequest | None, tuple | None]:
        """Limite de débit, services (créés au premier appel) et validation : communs aux deux routes d'analyse."""
        if limited(request.remote_addr or "?"):
            return None, (jsonify(error="Trop de requêtes : réessayez dans une minute."), 429)
        with lock:
            if state["services"] is None:
                state["services"] = build_services()
        try:
            analysis = to_request(request.get_json(silent=True) or {}, state["services"].find_tickers)
        except (ValidationError, ValueError) as exc:
            return None, (jsonify(error="Requête invalide", detail=str(exc)[:300]), 400)
        return analysis, None

    @app.post("/api/analyze")
    def analyze():
        analysis, error = prepare()
        if error:
            return error
        try:
            report = state["services"].orchestrator.run(analysis).model_dump(mode="json")
        except LLMError as exc:  # la synthèse et les agents gèrent leurs pannes ; ceci ne couvre que le reste
            return jsonify(error="Analyse indisponible", detail=type(exc).__name__), 503
        state["services"].archive(report)
        return jsonify(report)

    @app.post("/api/analyze/stream")
    def analyze_stream():
        """Même analyse, en Server-Sent Events : agent_start / agent_end au fil de l'eau, puis report (ou error)."""
        analysis, error = prepare()
        if error:
            return error
        events: queue.Queue[dict | None] = queue.Queue()

        def work() -> None:
            try:
                report = state["services"].orchestrator.run(analysis, on_event=events.put).model_dump(mode="json")
                events.put({"type": "report", "report": report})
                state["services"].archive(report)  # après l'envoi : n'allonge pas l'attente
            except LLMError as exc:
                events.put({"type": "error", "error": "Analyse indisponible", "detail": type(exc).__name__})
            except Exception:  # le flux doit toujours se terminer proprement côté front
                logger.exception("stream_error", extra={"event": "stream_error"})
                events.put({"type": "error", "error": "Erreur interne"})
            finally:
                events.put(None)

        threading.Thread(target=work, daemon=True).start()

        def stream():
            while True:
                try:
                    event = events.get(timeout=HEARTBEAT_SECONDS)
                except queue.Empty:
                    yield ": keep-alive\n\n"  # ignoré par le front, garde la connexion ouverte
                    continue
                if event is None:
                    break
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        return Response(stream(), mimetype="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    if (FRONTEND_DIST / "index.html").exists():  # en ligne : un seul service pour l'interface et l'API

        @app.get("/", defaults={"path": ""})
        @app.get("/<path:path>")
        def frontend(path: str):
            if path.startswith("api/"):
                return jsonify(error="Route inconnue"), 404
            if path and (FRONTEND_DIST / path).is_file():
                return send_from_directory(FRONTEND_DIST, path)
            return send_from_directory(FRONTEND_DIST, "index.html")  # routes de l'application React

    return app


app = create_app()
