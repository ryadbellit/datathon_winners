"""Fournisseur simulé : déterministe, sans réseau, sans AWS. Pour le dev local et les tests."""
from __future__ import annotations

import hashlib
import json

from alphaforge.contracts import TokenUsage
from alphaforge.llm.base import LLMProvider, LLMRequest, LLMResponse


def _approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class MockProvider(LLMProvider):
    name = "mock"

    def __init__(self, responses: dict[str, str] | None = None):
        """`responses` : texte imposé par tâche (ex. {"evaluation": '{"score": 2}'})."""
        self._responses = responses or {}
        self.calls: list[LLMRequest] = []

    def complete(self, request: LLMRequest, model_id: str) -> LLMResponse:
        self.calls.append(request)
        text = self._responses.get(request.task) or self._default(request)
        return LLMResponse(
            text=text,
            provider=self.name,
            model_id=model_id,
            usage=TokenUsage(
                input_tokens=_approx_tokens((request.system or "") + request.prompt),
                output_tokens=_approx_tokens(text),
            ),
            latency_ms=1.0,
            estimated_cost_usd=0.0,
        )

    @staticmethod
    def _default(request: LLMRequest) -> str:
        digest = hashlib.sha256(request.prompt.encode()).hexdigest()[:8]
        if request.task == "evaluation":
            return json.dumps({"score": 4, "rationale": f"[mock {digest}] réponse jugée correcte"})
        return json.dumps(
            {
                "summary": f"[mock {digest}] synthèse simulée",
                "key_points": ["point simulé 1", "point simulé 2"],
                "confidence": 0.5,
            }
        )
