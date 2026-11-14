"""ModelRouter : choisit le modèle selon la tâche, gère le fallback et estime le coût."""
from __future__ import annotations

import logging
from typing import Callable

from alphaforge.config import Settings
from alphaforge.llm.base import (
    FALLBACK_ERRORS,
    LLMClient,
    LLMError,
    LLMProvider,
    LLMRequest,
    LLMResponse,
)
from alphaforge.llm.mock import MockProvider
from alphaforge.llm.pricing import PricingTable

logger = logging.getLogger("alphaforge.router")


class NoRouteError(LLMError):
    """Aucune route configurée pour cette tâche (et pas de route 'default')."""


class AllModelsFailedError(LLMError):
    def __init__(self, task: str, attempts: list[str]):
        super().__init__(f"Tous les modèles de la tâche '{task}' ont échoué : " + " | ".join(attempts))
        self.attempts = attempts


def parse_route(entry: str) -> tuple[str, str]:
    """'bedrock:global.anthropic.claude-sonnet-5-5' -> ('bedrock', 'global.anthropic.claude-sonnet-5-5')."""
    provider, sep, model_id = entry.partition(":")  # les model_id peuvent contenir ':' (ex. ...-v1:0)
    if not sep or not provider or not model_id:
        raise ValueError(f"Route invalide '{entry}' : format attendu 'fournisseur:model_id'")
    return provider, model_id


class ModelRouter(LLMClient):
    def __init__(
        self,
        routes: dict[str, list[str]],
        provider_factories: dict[str, Callable[[], LLMProvider]],
        pricing: PricingTable | None = None,
        observers: list[Callable[[LLMRequest, LLMResponse], None]] | None = None,
        max_tokens: dict[str, int] | None = None,
    ):
        for entries in routes.values():
            for entry in entries:
                parse_route(entry)  # échoue tôt si la config est mal formée
        self._routes = routes
        self._factories = provider_factories
        self._providers: dict[str, LLMProvider] = {}
        self._pricing = pricing or PricingTable()
        self._observers = observers or []
        self._max_tokens = max_tokens or {}

    @classmethod
    def from_settings(cls, settings: Settings, observers=None) -> ModelRouter:
        def bedrock() -> LLMProvider:
            from alphaforge.llm.bedrock import BedrockProvider  # boto3 n'est chargé que si Bedrock est utilisé

            return BedrockProvider(
                region=settings.aws_region,
                profile=settings.aws_profile,
                timeout_seconds=settings.bedrock_timeout_seconds,
                max_retries=settings.bedrock_max_retries,
            )

        return cls(
            routes=settings.llm_routes,
            provider_factories={"mock": MockProvider, "bedrock": bedrock},
            pricing=PricingTable(settings.llm_pricing),
            observers=observers,
            max_tokens=settings.llm_max_tokens,
        )

    def _provider(self, name: str) -> LLMProvider:
        if name not in self._providers:
            if name not in self._factories:
                raise LLMError(f"Fournisseur inconnu '{name}' (disponibles : {sorted(self._factories)})")
            self._providers[name] = self._factories[name]()
        return self._providers[name]

    def route_for(self, task: str) -> list[str]:
        entries = self._routes.get(task) or self._routes.get("default")
        if not entries:
            raise NoRouteError(f"Aucune route pour la tâche '{task}' et pas de route 'default'")
        return entries

    def complete(self, request: LLMRequest) -> LLMResponse:
        if request.max_tokens is None:
            limit = self._max_tokens.get(request.task, self._max_tokens.get("default", 1024))
            request = request.model_copy(update={"max_tokens": limit})
        attempts: list[str] = []
        for entry in self.route_for(request.task):
            provider_name, model_id = parse_route(entry)
            try:
                response = self._provider(provider_name).complete(request, model_id)
            except FALLBACK_ERRORS as exc:
                attempts.append(f"{entry}: {type(exc).__name__}: {exc}")
                logger.warning("Fallback de modèle", extra={"task": request.task, "model": entry, "error": type(exc).__name__})
                continue
            response.estimated_cost_usd = (
                0.0 if provider_name == "mock" else self._pricing.cost(response.model_id, response.usage)
            )
            if response.stop_reason == "max_tokens":
                logger.warning(
                    "Réponse tronquée : augmenter LLM_MAX_TOKENS pour cette tâche",
                    extra={"event": "truncated", "task": request.task, "model_id": response.model_id, "max_tokens": request.max_tokens},
                )
            for observer in self._observers:
                observer(request, response)
            return response
        raise AllModelsFailedError(request.task, attempts)
