"""Agents spécialisés (squelettes) : prompt -> LLM -> AgentResult. Aucun calcul financier ici."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from alphaforge.contracts import AgentResult, AnalysisRequest
from alphaforge.llm import LLMRequest
from alphaforge.retrieval import KnowledgeBase, RetrievalError

logger = logging.getLogger("alphaforge.retrieval")

JSON_INSTRUCTION = 'Réponds uniquement avec un objet JSON : {"summary": str, "confidence": nombre entre 0 et 1}.'


@dataclass(frozen=True)
class AgentSpec:
    name: str
    role: str
    uses_kb: bool = False  # interroge la Knowledge Base si elle est configurée
    uses_persona: bool = False


SPECS = (
    AgentSpec(
        "document_analyst",
        "Tu résumes des documents financiers et en extrais les chiffres clés, sans rien inventer. Cite la source des chiffres.",
        uses_kb=True,
    ),
    AgentSpec("sentiment", "Tu évalues le ton (positif, neutre, négatif) de nouvelles financières."),
    AgentSpec(
        "risk_explainer",
        "Tu expliques un risque en langage simple, adapté au profil de l'investisseur. Appuie-toi sur les documents fournis.",
        uses_kb=True,
        uses_persona=True,
    ),
)


def parse_agent_json(text: str) -> dict:
    """Extrait l'objet JSON d'une réponse de LLM ; retombe sur le texte brut s'il est invalide."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict) and "summary" in data:
                return data
        except json.JSONDecodeError:
            pass
    return {"summary": text.strip(), "confidence": 0.3}


class Agent:
    def __init__(self, spec: AgentSpec, llm, kb: KnowledgeBase | None = None):
        self.name = spec.name
        self._spec, self._llm, self._kb = spec, llm, kb

    def run(self, request: AnalysisRequest) -> AgentResult:
        spec, parts = self._spec, list(request.documents)
        passages = []
        if spec.uses_kb and self._kb:
            try:
                passages = self._kb.retrieve(request.question)  # la requête n'est jamais journalisée
            except RetrievalError as exc:  # la base en panne n'empêche pas de répondre avec les documents fournis
                logger.warning(
                    "retrieval_error", extra={"event": "retrieval_error", "agent": self.name, "error": str(exc)[:200]}
                )
        parts += [f"[source : {p.source}]\n{p.text}" for p in passages]

        prompt = f"Question : {request.question}\nContexte :\n" + ("\n---\n".join(parts) or "(aucun document fourni)")
        if spec.uses_persona:
            prompt = f"Profil de l'investisseur : {request.persona.value}\n" + prompt
        response = self._llm.complete(
            LLMRequest(task="agent", system=f"{spec.role}\n{JSON_INSTRUCTION}", prompt=prompt)
        )

        data = parse_agent_json(response.text)
        try:
            confidence = min(1.0, max(0.0, float(data.get("confidence", 0.3))))
        except (TypeError, ValueError):
            confidence = 0.3
        return AgentResult(
            agent=self.name,
            summary=str(data["summary"]),
            confidence=confidence,
            model_id=response.model_id,
            usage=response.usage,
            estimated_cost_usd=response.estimated_cost_usd,
            sources=sorted({p.source for p in passages}),
        )
