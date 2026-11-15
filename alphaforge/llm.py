"""Appels de modèles : interface commune, fournisseurs (mock, Amazon Bedrock) et ModelRouter."""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Callable

import boto3
from botocore.config import Config
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    ConnectTimeoutError,
    EndpointConnectionError,
    NoCredentialsError,
    PartialCredentialsError,
    ReadTimeoutError,
)
from pydantic import BaseModel, Field

from alphaforge.config import Settings
from alphaforge.contracts import TokenUsage
from alphaforge.tracing import span

logger = logging.getLogger("alphaforge.router")


class LLMRequest(BaseModel):
    task: str  # orchestration | arbitration | agent | evaluation : sert au routage
    prompt: str
    system: str | None = None
    max_tokens: int | None = None  # None : limite configurée pour la tâche
    agent: str | None = None  # nom de l'agent appelant : attribution des logs et du coût


class LLMResponse(BaseModel):
    text: str
    provider: str
    model_id: str
    usage: TokenUsage = Field(default_factory=TokenUsage)
    latency_ms: float = 0.0
    estimated_cost_usd: float | None = None
    stop_reason: str | None = None  # 'max_tokens' = tronquée ; 'guardrail_intervened' = bloquée


class LLMError(Exception):
    pass


class ModelUnavailableError(LLMError):
    """Modèle absent, non activé, accès refusé ou identifiants invalides/expirés."""


class ThrottledError(LLMError):
    pass


class ProviderTimeoutError(LLMError):
    pass


class ProviderError(LLMError):
    """Autre erreur du fournisseur (requête invalide...) : pas de fallback, ce serait masquer un bug."""


class NoRouteError(LLMError):
    pass


class AllModelsFailedError(LLMError):
    def __init__(self, task: str, attempts: list[str]):
        super().__init__(f"Tous les modèles de la tâche '{task}' ont échoué : " + " | ".join(attempts))


# Tâche sans route propre -> route d'une tâche voisine (puis "default") : « arbitration » = modèle fort, sans guardrail.
TASK_FALLBACKS = {"arbitration": "orchestration"}
FALLBACK_ERRORS = (ModelUnavailableError, ThrottledError, ProviderTimeoutError)


class LLMProvider(ABC):
    name: str

    @abstractmethod
    def complete(self, request: LLMRequest, model_id: str) -> LLMResponse:
        """Exécute la requête. Lève une LLMError typée en cas d'échec."""


class MockProvider(LLMProvider):
    """Déterministe, sans réseau : développement local."""

    name = "mock"

    def complete(self, request: LLMRequest, model_id: str) -> LLMResponse:
        digest = hashlib.sha256(request.prompt.encode()).hexdigest()[:8]
        if request.task == "evaluation":
            payload = {"score": 4, "rationale": f"[mock {digest}] réponse jugée correcte"}
        else:
            payload = {"summary": f"[mock {digest}] synthèse simulée", "confidence": 0.5}
        text = json.dumps(payload)
        usage = TokenUsage(
            input_tokens=max(1, len((request.system or "") + request.prompt) // 4), output_tokens=max(1, len(text) // 4)
        )
        return LLMResponse(text=text, provider=self.name, model_id=model_id, usage=usage, latency_ms=1.0)


_THROTTLE_CODES = {"ThrottlingException", "TooManyRequestsException", "ServiceQuotaExceededException"}
_UNAVAILABLE_CODES = {
    "AccessDeniedException", "ResourceNotFoundException", "ModelNotReadyException", "ServiceUnavailableException",
    "InternalServerException", "ExpiredTokenException", "UnrecognizedClientException", "InvalidSignatureException",
}


class BedrockProvider(LLMProvider):
    """Amazon Bedrock via l'API Converse : un seul code pour Claude, Nova, etc."""

    name = "bedrock"

    def __init__(self, settings: Settings):
        self._guardrail = (settings.guardrail_id, settings.guardrail_version, set(settings.guardrail_tasks))
        self._client = boto3.Session(profile_name=settings.aws_profile, region_name=settings.aws_region).client(
            "bedrock-runtime",
            config=Config(
                connect_timeout=min(10.0, settings.bedrock_timeout_seconds),
                read_timeout=settings.bedrock_timeout_seconds,
                retries={"max_attempts": settings.bedrock_max_retries, "mode": "adaptive"},
            ),
        )

    def complete(self, request: LLMRequest, model_id: str) -> LLMResponse:
        params: dict = {
            "modelId": model_id,
            "messages": [{"role": "user", "content": [{"text": request.prompt}]}],
            "inferenceConfig": {"maxTokens": request.max_tokens or 1024},
        }
        if request.system:
            params["system"] = [{"text": request.system}]
        guardrail_id, guardrail_version, guardrail_tasks = self._guardrail
        if guardrail_id and request.task in guardrail_tasks:
            params["guardrailConfig"] = {"guardrailIdentifier": guardrail_id, "guardrailVersion": guardrail_version}

        started = time.perf_counter()
        try:
            raw = self._client.converse(**params)
        except ClientError as exc:
            code, message = (exc.response.get("Error", {}).get(k, "") for k in ("Code", "Message"))
            detail = f"{code} ({model_id}): {message}"
            if code in _THROTTLE_CODES:
                raise ThrottledError(detail) from exc
            if code == "ModelTimeoutException":
                raise ProviderTimeoutError(detail) from exc
            if code in _UNAVAILABLE_CODES or (code == "ValidationException" and "model" in message.lower()):
                raise ModelUnavailableError(detail) from exc
            raise ProviderError(detail) from exc
        except (ReadTimeoutError, ConnectTimeoutError, EndpointConnectionError) as exc:
            raise ProviderTimeoutError(f"Bedrock injoignable ou trop lent ({model_id}): {exc}") from exc
        except (NoCredentialsError, PartialCredentialsError) as exc:
            raise ModelUnavailableError(f"Identifiants AWS introuvables : {exc}") from exc
        except BotoCoreError as exc:
            raise ProviderError(f"Erreur botocore ({model_id}): {exc}") from exc

        blocks = raw.get("output", {}).get("message", {}).get("content", [])
        usage = raw.get("usage", {})
        return LLMResponse(
            text="".join(b["text"] for b in blocks if "text" in b),
            provider=self.name,
            model_id=model_id,
            usage=TokenUsage(input_tokens=usage.get("inputTokens", 0), output_tokens=usage.get("outputTokens", 0)),
            latency_ms=(time.perf_counter() - started) * 1000,
            stop_reason=raw.get("stopReason"),
        )


def _parse_route(entry: str) -> tuple[str, str]:
    """'bedrock:global.anthropic.claude-x' -> ('bedrock', 'global.anthropic.claude-x')."""
    provider, sep, model_id = entry.partition(":")  # les model_id peuvent contenir ':' (ex. ...-v1:0)
    if not (sep and provider and model_id):
        raise ValueError(f"Route invalide '{entry}' : format attendu 'fournisseur:model_id'")
    return provider, model_id


class ModelRouter:
    """Choisit le modèle selon la tâche, bascule sur le suivant en cas d'indisponibilité, estime le coût."""

    def __init__(
        self,
        routes: dict[str, list[str]],
        factories: dict[str, Callable[[], LLMProvider]],
        prices: dict[str, dict[str, float]] | None = None,
        max_tokens: dict[str, int] | None = None,
        observers: list[Callable[[LLMRequest, LLMResponse], None]] | None = None,
    ):
        for entries in routes.values():
            for entry in entries:
                _parse_route(entry)  # échoue tôt si la config est mal formée
        self._routes, self._factories, self._providers = routes, factories, {}
        self._prices, self._max_tokens, self._observers = prices or {}, max_tokens or {}, observers or []

    @classmethod
    def from_settings(cls, settings: Settings, observers=None) -> ModelRouter:
        return cls(
            settings.llm_routes,
            {"mock": MockProvider, "bedrock": lambda: BedrockProvider(settings)},  # Bedrock créé à la 1re utilisation
            settings.llm_pricing,
            settings.llm_max_tokens,
            observers,
        )

    def _cost(self, response: LLMResponse) -> float | None:
        price = self._prices.get(response.model_id) or self._prices.get(
            re.sub(r"^(global|us|eu|apac)\.", "", response.model_id)  # prix déclaré une fois par modèle
        )
        if price is None:
            return None
        usage = response.usage
        return (usage.input_tokens * price["input_per_1m"] + usage.output_tokens * price["output_per_1m"]) / 1e6

    def complete(self, request: LLMRequest) -> LLMResponse:
        with span(f"llm:{request.agent or request.task}", "LLM", {"system": request.system, "prompt": request.prompt}, task=request.task) as current:
            response = self._complete(request)
            current.outputs(response.text)
            current.attributes(
                model_id=response.model_id, input_tokens=response.usage.input_tokens, output_tokens=response.usage.output_tokens,
                stop_reason=response.stop_reason, latency_ms=response.latency_ms, estimated_cost_usd=response.estimated_cost_usd,
            )
            return response

    def _complete(self, request: LLMRequest) -> LLMResponse:
        entries = self._routes.get(request.task) or self._routes.get(TASK_FALLBACKS.get(request.task, "")) or self._routes.get("default")
        if not entries:
            raise NoRouteError(f"Aucune route pour la tâche '{request.task}' et pas de route 'default'")
        if request.max_tokens is None:
            limit = self._max_tokens.get(request.task, self._max_tokens.get("default", 1024))
            request = request.model_copy(update={"max_tokens": limit})

        attempts: list[str] = []
        for entry in entries:
            provider_name, model_id = _parse_route(entry)
            if provider_name not in self._providers:
                if provider_name not in self._factories:
                    raise LLMError(f"Fournisseur inconnu '{provider_name}' (disponibles : {sorted(self._factories)})")
                self._providers[provider_name] = self._factories[provider_name]()
            try:
                response = self._providers[provider_name].complete(request, model_id)
            except FALLBACK_ERRORS as exc:
                attempts.append(f"{entry}: {type(exc).__name__}: {exc}")
                logger.warning(
                    "Fallback de modèle",
                    extra={"event": "fallback", "task": request.task, "model": entry, "error": type(exc).__name__},
                )
                continue
            response.estimated_cost_usd = 0.0 if provider_name == "mock" else self._cost(response)
            event = {"max_tokens": "truncated", "guardrail_intervened": "guardrail_intervened"}.get(response.stop_reason)
            if event:  # réponse coupée (augmenter LLM_MAX_TOKENS) ou remplacée par le message du guardrail
                logger.warning(
                    f"Réponse : {event}", extra={"event": event, "task": request.task, "model_id": response.model_id}
                )
            for observer in self._observers:
                observer(request, response)
            return response
        raise AllModelsFailedError(request.task, attempts)
