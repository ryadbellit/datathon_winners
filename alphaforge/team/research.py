"""Agent 1 — Recherche & Preuves : rassemble des preuves réelles, les date, les source, signale ce qui manque."""
from __future__ import annotations

import datetime as dt
import logging
import re
from collections import defaultdict

from alphaforge.contracts import AnalysisRequest
from alphaforge.llm import LLMError, LLMResponse
from alphaforge.retrieval import KnowledgeBase, RetrievalError
from alphaforge.team.interfaces import ProfileChecks, QuantMetrics
from alphaforge.team.base import (
    AgentOutput,
    Evidence,
    Fact,
    TeamAgent,
    brief,
    cited,
    dict_items,
    evidence_text,
    numbers_supported,
    str_items,
)

logger = logging.getLogger("alphaforge.team")
MAX_EVIDENCE = 32  # borne le coût en tokens des agents suivants (prix + métriques + contrôles + actualités)
CHECK_LABEL = {"ok": "respecté", "warn": "attention", "fail": "non respecté"}
# Sans ticker cité, les métriques ne sont calculées que si la question porte sur le portefeuille ou son risque :
# une question générale (« c'est quoi un ETF ? ») garde ainsi la réponse rapide en connaissances générales.
_PORTFOLIO_QUESTION = re.compile(
    r"portefeuille|portfolio|risqu|risk|diversif|volatil|concentr|perte|pire|worst|drawdown|allocation|répartition|corrél|bêta|beta",
    re.I,
)
SCHEMA = (
    '{"claims": {"E1": "observation en une phrase"}, "key_facts": [{"text": str, "evidence_ids": ["E1"]}], '
    '"missing_information": [str], "confidence": nombre entre 0 et 1}'
)


class ResearchOutput(AgentOutput):
    key_facts: list[Fact] = []
    evidence: list[Evidence] = []
    sources: list[str] = []
    data_as_of: dt.date | None = None  # date de la preuve la plus récente
    missing_information: list[str] = []

    def short(self) -> str:
        return f"{self.status} : {len(self.evidence)} preuve(s), {len(self.key_facts)} fait(s) clé(s)"


class ResearchAgent(TeamAgent):
    name = "research"
    role = (
        "Tu es l'agent Recherche & Preuves d'une équipe d'analyse financière. Tu relis des éléments déjà collectés "
        "(jamais inventés) et tu en tires des faits chiffrés et datés, en distinguant ce qui est vérifié de ce qui manque. "
        "Recopie les chiffres tels quels."
    )
    Output = ResearchOutput

    def __init__(self, llm, kb: KnowledgeBase | None = None, market=None, quant: QuantMetrics | None = None,
                 checker: ProfileChecks | None = None):
        super().__init__(llm)
        self._kb, self._market, self._quant, self._checker = kb, market, quant, checker

    def gather(self, request: AnalysisRequest) -> tuple[list[Evidence], list[str]]:
        """Collecte déterministe (sans LLM) : KB, documents, actualités, prix. Chaque preuve reçoit son ID ici."""
        missing: list[str] = []
        news, prices = list(request.news), list(request.prices)
        if self._market:
            try:
                news += self._market.news(request.question, request.tickers)
                for ticker in request.tickers:
                    prices += self._market.prices(ticker)
            except Exception as exc:  # interface externe (autre équipe) : sa panne ne doit pas faire échouer l'analyse
                logger.warning("market_data_error", extra={"event": "market_data_error", "error_type": type(exc).__name__})
                missing.append(f"Données de marché indisponibles ({type(exc).__name__}).")
        metrics, checks = [], []
        wants_metrics = request.tickers or _PORTFOLIO_QUESTION.search(request.question)
        has_portfolio = bool(request.portfolio and request.portfolio.holdings)
        if self._quant and has_portfolio and wants_metrics:
            try:
                metrics = self._quant.observations(request.portfolio, request.tickers)
            except Exception as exc:  # module externe : sa panne ne doit pas faire échouer l'analyse
                logger.warning("quant_error", extra={"event": "quant_error", "error_type": type(exc).__name__})
                missing.append(f"Métriques de risque indisponibles ({type(exc).__name__}).")
        if self._checker and (has_portfolio or request.tickers) and wants_metrics:
            try:
                checks = self._checker.checks(request)
            except Exception as exc:
                logger.warning("checks_error", extra={"event": "checks_error", "error_type": type(exc).__name__})
                missing.append(f"Contrôles de profil indisponibles ({type(exc).__name__}).")
        passages = []
        if self._kb:
            try:
                passages = self._kb.retrieve(request.question)
            except RetrievalError as exc:
                logger.warning("retrieval_error", extra={"event": "retrieval_error", "agent": self.name, "error": str(exc)[:200]})
                missing.append("Knowledge Base indisponible.")
        else:
            missing.append("Knowledge Base non configurée.")

        raw: list[dict] = []
        by_ticker = defaultdict(list)
        for p in prices:
            by_ticker[p.ticker].append(p)
        for ticker, points in sorted(by_ticker.items()):
            points = sorted((p for p in points if not (request.as_of and p.date > request.as_of)), key=lambda p: p.date)
            if not points:
                continue
            first, last = points[0], points[-1]
            if len(points) >= 2 and first.close:
                pct = (last.close - first.close) / first.close * 100
                text = (
                    f"{ticker} : {first.close:g} {first.currency} le {first.date} -> "
                    f"{last.close:g} {last.currency} le {last.date} ({pct:+.2f} %)"
                )
                value, unit = round(pct, 2), "%"
            else:
                text = f"{ticker} : clôture {last.close:g} {last.currency} le {last.date}"
                value, unit = last.close, last.currency
            raw.append(
                dict(kind="price", claim=text, source=last.source, reference=ticker, date=last.date, excerpt=text, value=value, unit=unit)
            )
        for o in metrics:  # chiffres calculés par le code : citables comme preuves, jamais résumés par le LLM
            text = f"{o.name} : {o.value:g}{' ' + o.unit if o.unit else ''}"
            date = dt.date.fromisoformat(o.as_of) if o.as_of else None
            raw.append(dict(kind="metric", claim=text, source=o.source, reference=o.name, date=date, excerpt=text, value=o.value, unit=o.unit))
        today = request.as_of or dt.date.today()
        for c in checks:  # contrôles déterministes du profil : citables et opposables à la gouvernance
            text = f"Contrôle « {c.rule} » : {CHECK_LABEL[c.status]} — {c.detail}"
            raw.append(dict(kind="check", claim=text, source=c.source, reference=c.rule, date=today, excerpt=text, check_status=c.status))
        for n in sorted(news, key=lambda n: n.date, reverse=True):
            raw.append(
                dict(kind="news", claim=n.title, source=n.source, reference=n.url or n.title, date=n.date, excerpt=f"{n.title}. {n.text}"[:600])
            )
        for i, d in enumerate(request.documents, 1):
            raw.append(
                dict(kind="document", claim=d[:200], source=f"document fourni n°{i}", reference=f"documents[{i}]", date=None, excerpt=d[:600])
            )
        for p in passages:
            raw.append(dict(kind="knowledge_base", claim=p.text[:200], source=p.source, reference=p.source, date=None, excerpt=p.text[:600]))

        future = [r for r in raw if request.as_of and r["date"] and r["date"] > request.as_of]
        if future:
            missing.append(f"{len(future)} élément(s) postérieur(s) à {request.as_of} ignoré(s) (pas de look-ahead).")
        raw = [r for r in raw if r not in future]
        if len(raw) > MAX_EVIDENCE:
            missing.append(f"{len(raw) - MAX_EVIDENCE} élément(s) non analysé(s) (limite de {MAX_EVIDENCE} preuves).")
            raw = raw[:MAX_EVIDENCE]
        evidence = [
            Evidence(id=f"E{i}", validation="verified" if r["date"] and r["source"] else "undated", **r) for i, r in enumerate(raw, 1)
        ]
        return evidence, missing

    def run(self, request: AnalysisRequest) -> tuple[ResearchOutput, list[LLMResponse]]:
        evidence, missing = self.gather(request)
        if not evidence:  # rien à analyser : pas d'appel LLM
            return ResearchOutput(status="no_evidence", missing_information=missing + ["Aucune preuve disponible."]), []
        dated = [e.date for e in evidence if e.date]
        base = dict(evidence=evidence, sources=sorted({e.source for e in evidence}), data_as_of=max(dated) if dated else None)
        try:
            data, response = self.ask(SCHEMA, {"question": request.question, "evidence": [brief(e, excerpt=True) for e in evidence]})
        except LLMError as exc:  # les preuves collectées restent réelles et utilisables ; l'échec reste visible
            return ResearchOutput(status="failed", error=type(exc).__name__, missing_information=missing, **base), []

        claims = data.get("claims") if isinstance(data.get("claims"), dict) else {}
        for e in evidence:
            if e.kind not in ("price", "metric", "check") and isinstance(claims.get(e.id), str) and claims[e.id].strip():
                e.claim = claims[e.id].strip()[:300]
        by_id, facts, dropped = {e.id: e for e in evidence}, [], 0
        for item in dict_items(data, "key_facts"):
            ids, text = cited(item.get("evidence_ids"), by_id), str(item.get("text", "")).strip()
            if text and ids and numbers_supported(text, [evidence_text(by_id[i]) for i in ids]):
                facts.append(Fact(text=text, evidence_ids=ids))
            else:
                dropped += 1
        if dropped:
            missing.append(f"{dropped} fait(s) retiré(s) : sans preuve valide ou avec un chiffre non étayé.")
        verified = any(e.validation == "verified" for e in evidence)
        output = ResearchOutput(
            status="ok" if verified else "partial",
            confidence=min(AgentOutput(confidence=data.get("confidence", 0.3)).confidence, 1.0 if verified else 0.4),
            key_facts=facts,
            missing_information=missing + str_items(data, "missing_information"),
            **base,
        )
        return output, [response]
