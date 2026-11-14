"""Contrats de données partagés entre l'orchestrateur, les agents et l'évaluation."""
from __future__ import annotations

import uuid
from enum import Enum

from pydantic import BaseModel, Field


class Persona(str, Enum):
    PRUDENT = "prudent"
    BALANCED = "equilibre"
    BOLD = "audacieux"


class TokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )


class AnalysisRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    question: str = Field(min_length=1)
    persona: Persona = Persona.BALANCED
    documents: list[str] = Field(default_factory=list, description="Extraits de texte fournis par l'utilisateur")


class AgentResult(BaseModel):
    agent: str
    summary: str
    key_points: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    model_id: str | None = None
    usage: TokenUsage = Field(default_factory=TokenUsage)
    estimated_cost_usd: float | None = None
    latency_ms: float = 0.0
    error: str | None = Field(default=None, description="Type d'erreur si l'agent a échoué (résultat dégradé)")


class FinalReport(BaseModel):
    request_id: str
    persona: Persona
    answer: str
    agent_results: list[AgentResult]
    usage: TokenUsage = Field(default_factory=TokenUsage)
    estimated_cost_usd: float | None = Field(
        default=None, description="None si le prix d'un des modèles utilisés est inconnu"
    )
