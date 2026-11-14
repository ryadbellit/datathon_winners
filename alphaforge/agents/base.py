"""Classe de base des agents : prompt -> LLM -> AgentResult."""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod

from alphaforge.contracts import AgentResult, AnalysisRequest
from alphaforge.llm.base import LLMClient, LLMRequest

JSON_INSTRUCTION = (
    'Réponds uniquement avec un objet JSON : {"summary": str, "key_points": [str], "confidence": nombre entre 0 et 1}.'
)


def parse_agent_json(text: str) -> dict:
    """Extrait l'objet JSON d'une réponse de LLM. Retombe sur le texte brut si le JSON est invalide."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict) and "summary" in data:
                return data
        except json.JSONDecodeError:
            pass
    return {"summary": text.strip(), "key_points": [], "confidence": 0.3}


class Agent(ABC):
    name: str
    task: str = "agent"  # clé de routage dans le ModelRouter
    role: str

    def __init__(self, llm: LLMClient):
        self._llm = llm

    @abstractmethod
    def build_prompt(self, request: AnalysisRequest) -> str: ...

    def run(self, request: AnalysisRequest) -> AgentResult:
        response = self._llm.complete(
            LLMRequest(
                task=self.task,
                system=f"{self.role}\n{JSON_INSTRUCTION}",
                prompt=self.build_prompt(request),
            )
        )
        data = parse_agent_json(response.text)
        try:
            confidence = min(1.0, max(0.0, float(data.get("confidence", 0.3))))
        except (TypeError, ValueError):
            confidence = 0.3
        return AgentResult(
            agent=self.name,
            summary=str(data["summary"]),
            key_points=[str(p) for p in data.get("key_points", [])],
            confidence=confidence,
            model_id=response.model_id,
            usage=response.usage,
            estimated_cost_usd=response.estimated_cost_usd,
            latency_ms=response.latency_ms,
        )
