"""Agent 2 — Event Hunter : identifie ce qui s'est passé sur le marché, sans attribuer de cause sans preuve."""
from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel

from alphaforge.llm import LLMResponse
from alphaforge.team.base import (
    AgentOutput,
    Evidence,
    Hypothesis,
    TeamAgent,
    brief,
    cited,
    dict_items,
    str_items,
)

Category = Literal["earnings", "guidance", "macro", "geopolitical", "regulatory", "technological", "supply_chain", "analyst", "other"]
SCHEMA = (
    '{"events": [{"description": str, "category": "earnings|guidance|macro|geopolitical|regulatory|technological|supply_chain|analyst|other", '
    '"signal": "positive|negative|neutral", "evidence_ids": ["E2"]}], "affected_entities": [str], '
    '"mechanisms": [{"text": str, "evidence_ids": []}], "alternative_explanations": [{"text": str, "evidence_ids": []}], '
    '"uncertainties": [str], "confidence": nombre entre 0 et 1}'
)
CATEGORIES = set(Category.__args__)


class Event(BaseModel):
    id: str
    description: str
    category: Category = "other"
    date: dt.date | None = None  # déduite des preuves citées par le code, jamais par le LLM
    signal: Literal["positive", "negative", "neutral"] = "neutral"
    evidence_ids: list[str] = []
    verified: bool = False  # vrai seulement si appuyé par une preuve datée et sourcée


class EventsOutput(AgentOutput):
    identified_events: list[Event] = []
    event_timeline: list[str] = []
    affected_entities: list[str] = []
    potential_market_mechanisms: list[Hypothesis] = []  # toujours des hypothèses
    supporting_evidence_ids: list[str] = []
    alternative_explanations: list[Hypothesis] = []
    uncertainties: list[str] = []

    def short(self) -> str:
        return f"{self.status} : {len(self.identified_events)} événement(s), {sum(e.verified for e in self.identified_events)} vérifié(s)"


class EventHunter(TeamAgent):
    name = "event_hunter"
    role = (
        "Tu es l'Event Hunter : tu identifies les événements (résultats, prévisions, macro, géopolitique, réglementation, "
        "technologie, chaîne d'approvisionnement...) liés au mouvement étudié. N'attribue JAMAIS le mouvement d'un cours à "
        "l'article le plus proche : présente les mécanismes comme des hypothèses et propose des explications alternatives. "
        "Si aucune actualité ne l'explique, dis-le dans uncertainties."
    )
    Output = EventsOutput

    def run(self, question: str, evidence: list[Evidence]) -> tuple[EventsOutput, list[LLMResponse]]:
        sources = [e for e in evidence if e.kind not in ("price", "metric", "check")]  # des événements, pas des chiffres calculés
        if not sources:  # pas d'actualité ni de document : on le dit, sans appel LLM
            return (
                EventsOutput(
                    status="no_evidence",
                    uncertainties=["Aucune actualité ni document disponible : aucun événement ne peut être identifié ni relié au mouvement observé."],
                ),
                [],
            )
        data, response = self.ask(SCHEMA, {"question": question, "evidence": [brief(e, excerpt=True) for e in evidence]})
        by_id = {e.id: e for e in evidence}
        events = []
        for i, item in enumerate(dict_items(data, "events"), 1):
            ids = cited(item.get("evidence_ids"), by_id)
            dates = [by_id[j].date for j in ids if by_id[j].date]
            category = item.get("category") if item.get("category") in CATEGORIES else "other"
            signal = item.get("signal") if item.get("signal") in ("positive", "negative", "neutral") else "neutral"
            events.append(
                Event(
                    id=f"V{i}",
                    description=str(item.get("description", "")).strip(),
                    category=category,
                    signal=signal,
                    date=min(dates) if dates else None,
                    evidence_ids=ids,
                    verified=any(by_id[j].validation == "verified" for j in ids),
                )
            )
        events = [e for e in events if e.description]
        ordered = sorted(events, key=lambda e: (e.date is None, e.date or dt.date.max))
        timeline = [
            f"{e.date or 'date inconnue'} — {e.description} [{', '.join(e.evidence_ids) or 'sans preuve'}]"
            f"{'' if e.verified else ' (non vérifié)'}"
            for e in ordered
        ]

        def hypotheses(key: str) -> list[Hypothesis]:
            return [
                Hypothesis(text=str(h["text"]).strip(), evidence_ids=cited(h.get("evidence_ids"), by_id))
                for h in dict_items(data, key)
                if str(h.get("text", "")).strip()
            ]

        uncertainties = str_items(data, "uncertainties")
        if events:
            uncertainties.append("Le lien de causalité entre ces événements et la variation de prix n'est pas démontré.")
        output = EventsOutput(
            status="ok" if any(e.verified for e in events) else "partial",
            confidence=AgentOutput(confidence=data.get("confidence", 0.3)).confidence,
            identified_events=events,
            event_timeline=timeline,
            affected_entities=str_items(data, "affected_entities"),
            potential_market_mechanisms=hypotheses("mechanisms"),
            supporting_evidence_ids=sorted({j for e in events for j in e.evidence_ids}),
            alternative_explanations=hypotheses("alternative_explanations"),
            uncertainties=uncertainties,
        )
        return output, [response]
