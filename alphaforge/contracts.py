"""Contrats de données et State du graphe LangGraph."""
from __future__ import annotations

import operator
import uuid
from enum import Enum
from typing import Annotated, TypedDict

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
    documents: list[str] = []


class AgentResult(BaseModel):
    agent: str
    summary: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    model_id: str | None = None
    usage: TokenUsage = Field(default_factory=TokenUsage)
    estimated_cost_usd: float | None = None
    sources: list[str] = []  # fichiers cités (Knowledge Base)
    error: str | None = None  # type d'erreur si l'agent a échoué (résultat dégradé)


class FinalReport(BaseModel):
    request_id: str
    persona: Persona
    answer: str
    sources: list[str] = []
    agent_results: list[AgentResult]
    usage: TokenUsage = Field(default_factory=TokenUsage)
    estimated_cost_usd: float | None = None  # None si le prix d'un des modèles utilisés est inconnu


class GraphState(TypedDict, total=False):
    request: AnalysisRequest
    agent_results: Annotated[list[AgentResult], operator.add]  # fusionne les agents exécutés en parallèle
    report: FinalReport
