"""Agent 4 — Devil's Advocate : conteste l'interprétation (objections ciblées, pas du désaccord gratuit)."""
from __future__ import annotations

from alphaforge.llm import LLMResponse
from alphaforge.team.base import (
    AgentOutput,
    Challenge,
    Evidence,
    Hypothesis,
    TeamAgent,
    brief,
    cited,
    dict_items,
    str_items,
)
from alphaforge.team.events import EventsOutput
from alphaforge.team.portfolio import PortfolioOutput
from alphaforge.team.research import ResearchOutput

TARGETS = ("research", "event_hunter", "portfolio_storyteller")
SCHEMA = (
    '{"challenged_claims": [{"target": "research|event_hunter|portfolio_storyteller", "claim": "affirmation contestée, citée", '
    '"objection": str, "severity": "high|medium|low", "evidence_ids": []}], "counterarguments": [str], '
    '"alternative_hypotheses": [{"text": str, "evidence_ids": []}], "unsupported_assumptions": [str], "missing_evidence": [str], '
    '"risk_scenarios": [{"text": str, "evidence_ids": []}], "evidence_needed": [str], "confidence": nombre entre 0 et 1}'
)


class DevilOutput(AgentOutput):
    challenged_claims: list[Challenge] = []
    counterarguments: list[str] = []
    alternative_hypotheses: list[Hypothesis] = []
    unsupported_assumptions: list[str] = []
    missing_evidence: list[str] = []
    risk_scenarios: list[Hypothesis] = []  # scénarios hypothétiques, pas des prévisions
    evidence_needed: list[str] = []  # ce qui confirmerait ou infirmerait chaque interprétation

    def objections_for(self, target: str) -> list[Challenge]:
        """Objections qui justifient une réponse (sévérité haute ou moyenne)."""
        return [c for c in self.challenged_claims if c.target == target and c.severity in ("high", "medium")]

    def short(self) -> str:
        return f"{self.status} : {len(self.challenged_claims)} objection(s), {len(self.alternative_hypotheses)} hypothèse(s) alternative(s)"


class DevilsAdvocate(TeamAgent):
    name = "devils_advocate"
    role = (
        "Tu es l'avocat du diable. Tu examines les conclusions de l'équipe et tu cherches pourquoi elles pourraient être "
        "fausses : hypothèses non étayées, causalité affirmée sans preuve, explications alternatives, informations ou risques "
        "oubliés. Construis le meilleur contre-argument raisonnable. Conteste des affirmations précises ; n'invente pas "
        "d'objection pour le principe : si une affirmation est solide, ne la conteste pas (ou en sévérité low). Indique quelles "
        "preuves confirmeraient ou infirmeraient chaque interprétation."
    )
    task = "arbitration"
    max_tokens = 3000
    Output = DevilOutput

    @staticmethod
    def has_claims(research: ResearchOutput, events: EventsOutput, portfolio: PortfolioOutput) -> bool:
        return bool(research.key_facts or events.identified_events or events.potential_market_mechanisms or portfolio.potential_impacts)

    def run(
        self, question: str, evidence: list[Evidence], research: ResearchOutput, events: EventsOutput, portfolio: PortfolioOutput
    ) -> tuple[DevilOutput, list[LLMResponse]]:
        if not self.has_claims(research, events, portfolio):  # rien à contester : pas d'appel LLM
            return DevilOutput(status="skipped"), []
        payload = {
            "question": question,
            "evidence": [brief(e) for e in evidence],
            "research": {"key_facts": [f.model_dump() for f in research.key_facts], "missing_information": research.missing_information},
            "event_hunter": events.model_dump(mode="json", include={"identified_events", "potential_market_mechanisms", "alternative_explanations", "uncertainties"}),
            "portfolio_storyteller": portfolio.model_dump(
                mode="json", include={"personalized", "direct_exposure", "indirect_exposure", "potential_impacts", "limitations"}
            ),
        }
        data, response = self.ask(SCHEMA, payload)
        known = {e.id for e in evidence}
        challenges = [
            Challenge(
                target=c["target"],
                claim=str(c.get("claim", "")).strip(),
                objection=str(c["objection"]).strip(),
                severity=c.get("severity") if c.get("severity") in ("high", "medium", "low") else "medium",
                evidence_ids=cited(c.get("evidence_ids"), known),
            )
            for c in dict_items(data, "challenged_claims")
            if c.get("target") in TARGETS and str(c.get("objection", "")).strip()
        ]

        def hypotheses(key: str) -> list[Hypothesis]:
            return [
                Hypothesis(text=str(h["text"]).strip(), evidence_ids=cited(h.get("evidence_ids"), known))
                for h in dict_items(data, key)
                if str(h.get("text", "")).strip()
            ]

        output = DevilOutput(
            confidence=AgentOutput(confidence=data.get("confidence", 0.3)).confidence,
            challenged_claims=challenges,
            counterarguments=str_items(data, "counterarguments"),
            alternative_hypotheses=hypotheses("alternative_hypotheses"),
            unsupported_assumptions=str_items(data, "unsupported_assumptions"),
            missing_evidence=str_items(data, "missing_evidence"),
            risk_scenarios=hypotheses("risk_scenarios"),
            evidence_needed=str_items(data, "evidence_needed"),
        )
        return output, [response]
