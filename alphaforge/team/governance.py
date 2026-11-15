"""Agent 5 — Explainability & Governance : relecteur et arbitre. Les preuves priment sur l'éloquence."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, model_validator

from alphaforge.contracts import AnalysisRequest
from alphaforge.llm import LLMResponse
from alphaforge.team.base import AgentOutput, Evidence, Rebuttal, TeamAgent, brief, cited, dict_items, evidence_text, numbers_supported, str_items
from alphaforge.team.conspiracy import ConspiracyOutput
from alphaforge.team.devil import DevilOutput
from alphaforge.team.events import EventsOutput
from alphaforge.team.portfolio import PortfolioOutput
from alphaforge.team.research import ResearchOutput

Assessment = Literal["supported", "partially_supported", "insufficient_evidence"]
_RANK = {"insufficient_evidence": 0, "partially_supported": 1, "supported": 2}
_CAUSAL = re.compile(r"\b(à cause de|causé|causée|provoqué|provoquée|en raison de|dû à|due à|because of|caused by|due to)\b", re.I)
SCHEMA = (
    '{"validated_claims": [{"text": str, "kind": "fact|interpretation|hypothesis", "evidence_ids": ["E1"], "reason": str}], '
    '"rejected_claims": [{"text": str, "kind": "fact|interpretation|hypothesis", "evidence_ids": [], "reason": str}], '
    '"unresolved_disagreements": [str], "evidence_gaps": [str], '
    '"profile_consistency": {"status": "yes|partly|no|unknown", "note": str}, "limitations": [str], '
    '"conspiracy_review": [{"index": numéro de la théorie, "verdict": "rejected|unproven", "reason": str}], '
    '"final_assessment": "supported|partially_supported|insufficient_evidence", "confidence": nombre entre 0 et 1}'
)


def _norm(text: str) -> str:
    return re.sub(r"\W+", " ", text).strip().lower()


class Claim(BaseModel):
    text: str
    kind: Literal["fact", "interpretation", "hypothesis"] = "interpretation"
    evidence_ids: list[str] = []
    reason: str = ""


class ProfileCheck(BaseModel):
    status: Literal["yes", "partly", "no", "unknown"] = "unknown"
    note: str = ""


class TheoryReview(BaseModel):
    """Avis de la gouvernance sur une théorie de l'agent complotiste : jamais validée (au mieux « non prouvée »)."""

    theory: str
    verdict: Literal["rejected", "unproven"] = "unproven"
    reason: str = ""


class GovernanceOutput(AgentOutput):
    validated_claims: list[Claim] = []
    rejected_claims: list[Claim] = []
    unresolved_disagreements: list[str] = []
    evidence_gaps: list[str] = []
    profile_consistency: ProfileCheck = ProfileCheck()
    facts: list[Claim] = []  # dérivés de validated_claims, par type
    interpretations: list[Claim] = []
    hypothetical_scenarios: list[Claim] = []
    limitations: list[str] = []
    conspiracy_review: list[TheoryReview] = []
    final_assessment: Assessment = "insufficient_evidence"

    @model_validator(mode="after")
    def _split_by_kind(self):
        self.facts = [c for c in self.validated_claims if c.kind == "fact"]
        self.interpretations = [c for c in self.validated_claims if c.kind == "interpretation"]
        self.hypothetical_scenarios = [c for c in self.validated_claims if c.kind == "hypothesis"]
        return self

    def short(self) -> str:
        return f"{self.final_assessment} : {len(self.validated_claims)} validée(s), {len(self.rejected_claims)} rejetée(s)"


class GovernanceAgent(TeamAgent):
    name = "governance"
    role = (
        "Tu es l'agent Explainability & Governance : relecteur et arbitre final. Tu reçois les résultats compacts des agents, "
        "les objections de l'avocat du diable et les réponses. Vérifie que chaque affirmation importante cite des preuves, "
        "relève les contradictions, sépare faits vérifiés, interprétations et scénarios hypothétiques, vérifie la cohérence "
        "avec le profil et l'horizon de l'investisseur. Ne choisis PAS l'agent le plus convaincant : la qualité des preuves "
        "prime sur l'assurance du ton. Ne déclare jamais un désaccord résolu si les preuves restent insuffisantes. "
        "Chaque affirmation validée doit citer des preuves existantes ; ce qui n'est pas étayé va dans rejected_claims. "
        "Examine chaque théorie de l'agent complotiste dans conspiracy_review (rejected si les preuves la contredisent, unproven "
        "sinon) et ne la reprends jamais dans validated_claims."
    )
    task = "arbitration"
    max_tokens = 6000  # Sonnet 5.5 dépassait 3000 sur des données réelles (JSON tronqué)
    Output = GovernanceOutput

    def failed(self, error: str) -> GovernanceOutput:
        return GovernanceOutput(status="failed", error=error, limitations=["Gouvernance indisponible : aucune validation des affirmations."])

    def run(
        self,
        request: AnalysisRequest,
        evidence: list[Evidence],
        research: ResearchOutput,
        events: EventsOutput,
        portfolio: PortfolioOutput,
        devil: DevilOutput,
        rebuttals: list[Rebuttal],
        statuses: dict[str, str],
        conspiracy: ConspiracyOutput | None = None,
    ) -> tuple[GovernanceOutput, list[LLMResponse]]:
        conspiracy = conspiracy or ConspiracyOutput(status="skipped")
        if not evidence:  # rien à arbitrer : pas d'appel LLM
            return (
                GovernanceOutput(
                    evidence_gaps=research.missing_information,
                    limitations=["Aucune preuve disponible : aucune conclusion ne peut être tirée."],
                ),
                [],
            )
        payload = {
            "persona": request.persona.value,
            "horizon_years": request.horizon_years,
            "statuts_des_agents": statuses,
            "evidence": [brief(e) for e in evidence],
            "research": {"key_facts": [f.model_dump() for f in research.key_facts], "missing_information": research.missing_information},
            "event_hunter": events.model_dump(
                mode="json", include={"identified_events", "potential_market_mechanisms", "alternative_explanations", "uncertainties"}
            ),
            "portfolio_storyteller": portfolio.model_dump(
                mode="json", include={"personalized", "direct_exposure", "indirect_exposure", "potential_impacts", "limitations"}
            ),
            "devils_advocate": devil.model_dump(mode="json", exclude={"schema_version", "status", "error", "confidence"}),
            "rebuttals": [r.model_dump(mode="json") for r in rebuttals],
            "conspiracy_theorist": [
                {"index": i, **t.model_dump(mode="json", include={"text", "suspected_actor", "alleged_motive", "evidence_ids"})}
                for i, t in enumerate(conspiracy.theories)
            ],
        }
        data, response = self.ask(SCHEMA, payload)
        return self._enforce(data, evidence, research, devil, rebuttals, statuses, conspiracy), [response]

    @staticmethod
    def _enforce(
        data: dict,
        evidence: list[Evidence],
        research: ResearchOutput,
        devil: DevilOutput,
        rebuttals: list[Rebuttal],
        statuses: dict[str, str],
        conspiracy: ConspiracyOutput | None = None,
    ) -> GovernanceOutput:
        """Règles déterministes appliquées APRÈS le LLM : il peut durcir le verdict, jamais l'adoucir."""
        by_id = {e.id: e for e in evidence}

        def claims(key: str) -> list[Claim]:
            return [
                Claim(
                    text=str(c["text"]).strip(),
                    kind=c.get("kind") if c.get("kind") in ("fact", "interpretation", "hypothesis") else "interpretation",
                    evidence_ids=cited(c.get("evidence_ids"), by_id),
                    reason=str(c.get("reason", "")).strip(),
                )
                for c in dict_items(data, key)
                if str(c.get("text", "")).strip()
            ]

        theories = conspiracy.theories if conspiracy else []
        theory_texts = {_norm(t.text) for t in theories}
        validated, rejected = [], claims("rejected_claims")
        for c in claims("validated_claims"):
            if _norm(c.text) in theory_texts:  # une théorie du complot n'est jamais validée
                rejected.append(c.model_copy(update={"kind": "hypothesis", "reason": "Théorie de l'agent complotiste : non prouvée."}))
            elif c.kind != "hypothesis" and not c.evidence_ids:
                rejected.append(c.model_copy(update={"reason": "Aucune preuve référencée."}))
            elif c.kind == "fact" and not numbers_supported(c.text, [evidence_text(by_id[i]) for i in c.evidence_ids]):
                rejected.append(c.model_copy(update={"reason": "Chiffre non présent dans les preuves citées."}))
            elif c.kind == "fact" and _CAUSAL.search(c.text):  # une cause n'est jamais un fait vérifié
                validated.append(c.model_copy(update={"kind": "interpretation", "reason": c.reason or "Lien causal : interprétation, pas un fait."}))
            else:
                validated.append(c)

        unresolved = str_items(data, "unresolved_disagreements")
        for challenge in devil.challenged_claims:  # une objection grave sans réponse étayée reste ouverte
            answer = next((r for r in rebuttals if r.objection == challenge.objection), None)
            if challenge.severity == "high" and not (answer and answer.evidence_ids and not answer.concedes):
                unresolved.append(f"Objection non levée : {challenge.objection}")
        unresolved = list(dict.fromkeys(unresolved))

        limitations = str_items(data, "limitations")
        degraded = [n for n, s in statuses.items() if s in ("failed", "partial", "no_evidence")]
        facts = [c for c in validated if c.kind == "fact"]
        verified_support = any(by_id[i].validation == "verified" for c in facts for i in c.evidence_ids)
        proposed = data.get("final_assessment") if data.get("final_assessment") in _RANK else "insufficient_evidence"
        ceiling = "supported"
        if not validated or not facts:
            ceiling = "insufficient_evidence"
        elif unresolved or degraded or not verified_support:
            ceiling = "partially_supported"
        if _RANK[proposed] > _RANK[ceiling]:
            reasons = []
            if not facts:
                reasons.append("aucun fait validé par des preuves")
            if unresolved:
                reasons.append("désaccords non résolus")
            if degraded:
                reasons.append("agents en échec ou partiels : " + ", ".join(degraded))
            if facts and not verified_support:
                reasons.append("aucune preuve datée et sourcée à l'appui des faits")
            limitations.append("Verdict plafonné par les règles de gouvernance : " + "; ".join(reasons) + ".")
        reviews = {r["index"]: r for r in dict_items(data, "conspiracy_review") if isinstance(r.get("index"), int)}
        conspiracy_review = [
            TheoryReview(
                theory=t.text,
                verdict="rejected" if reviews.get(i, {}).get("verdict") == "rejected" else "unproven",
                reason=str(reviews.get(i, {}).get("reason", "")).strip() or "Aucune preuve fournie ne confirme cette théorie.",
            )
            for i, t in enumerate(theories)
        ]
        profile = data.get("profile_consistency") if isinstance(data.get("profile_consistency"), dict) else {}
        status = profile.get("status") if profile.get("status") in ("yes", "partly", "no", "unknown") else "unknown"
        return GovernanceOutput(
            confidence=AgentOutput(confidence=data.get("confidence", 0.3)).confidence,
            validated_claims=validated,
            rejected_claims=rejected,
            unresolved_disagreements=unresolved,
            evidence_gaps=list(dict.fromkeys(str_items(data, "evidence_gaps") + research.missing_information)),
            profile_consistency=ProfileCheck(status=status, note=str(profile.get("note", "")).strip()),
            limitations=limitations,
            conspiracy_review=conspiracy_review,
            final_assessment=proposed if _RANK[proposed] <= _RANK[ceiling] else ceiling,
        )
