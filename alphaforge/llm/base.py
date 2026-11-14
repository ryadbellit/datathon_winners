"""Interface commune des fournisseurs de LLM et erreurs typées."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol

from pydantic import BaseModel, Field

from alphaforge.contracts import TokenUsage


class LLMRequest(BaseModel):
    task: str = Field(description="Tâche logique (orchestration, agent, evaluation...) : sert au routage")
    prompt: str
    system: str | None = None
    max_tokens: int | None = None  # None : le routeur applique la limite configurée pour la tâche
    temperature: float | None = None


class LLMResponse(BaseModel):
    text: str
    provider: str
    model_id: str
    usage: TokenUsage = Field(default_factory=TokenUsage)
    latency_ms: float = 0.0
    estimated_cost_usd: float | None = None
    stop_reason: str | None = None  # ex. 'end_turn' ; 'max_tokens' = réponse tronquée


class LLMError(Exception):
    """Erreur de base d'un fournisseur."""


class ModelUnavailableError(LLMError):
    """Modèle absent, non activé sur le compte ou accès refusé."""


class ThrottledError(LLMError):
    """Limite de débit atteinte."""


class ProviderTimeoutError(LLMError):
    """Délai dépassé ou erreur réseau."""


class ProviderError(LLMError):
    """Autre erreur du fournisseur (non rattrapable par un fallback de modèle)."""


# Erreurs pour lesquelles passer au modèle suivant a du sens.
FALLBACK_ERRORS = (ModelUnavailableError, ThrottledError, ProviderTimeoutError)


class LLMProvider(ABC):
    name: str

    @abstractmethod
    def complete(self, request: LLMRequest, model_id: str) -> LLMResponse:
        """Exécute la requête sur ce modèle. Lève une LLMError typée en cas d'échec."""


class LLMClient(Protocol):
    """Ce dont les agents ont besoin : le ModelRouter l'implémente."""

    def complete(self, request: LLMRequest) -> LLMResponse: ...
