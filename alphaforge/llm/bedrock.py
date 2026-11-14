"""Fournisseur Amazon Bedrock via l'API Converse (compatible Claude, Nova et autres modèles)."""
from __future__ import annotations

import time

from alphaforge.contracts import TokenUsage
from alphaforge.llm.base import (
    LLMProvider,
    LLMRequest,
    LLMResponse,
    ModelUnavailableError,
    ProviderError,
    ProviderTimeoutError,
    ThrottledError,
)

_THROTTLE_CODES = {"ThrottlingException", "TooManyRequestsException", "ServiceQuotaExceededException"}
_UNAVAILABLE_CODES = {
    "AccessDeniedException",
    "ResourceNotFoundException",
    "ModelNotReadyException",
    "ServiceUnavailableException",
    "InternalServerException",
    # Identifiants absents, invalides ou expirés (fréquent avec des jetons d'atelier)
    "ExpiredTokenException",
    "UnrecognizedClientException",
    "InvalidSignatureException",
}
_TIMEOUT_CODES = {"ModelTimeoutException"}


class BedrockProvider(LLMProvider):
    name = "bedrock"

    def __init__(
        self,
        region: str,
        profile: str | None = None,
        timeout_seconds: float = 60.0,
        max_retries: int = 3,
        client=None,
    ):
        self._region, self._profile = region, profile
        self._timeout, self._max_retries = timeout_seconds, max_retries
        self._client = client  # injectable pour les tests ; sinon créé à la première utilisation

    def _get_client(self):
        if self._client is None:
            import boto3  # import tardif : l'appli reste utilisable sans boto3 configuré
            from botocore.config import Config

            session = boto3.Session(profile_name=self._profile, region_name=self._region)
            self._client = session.client(
                "bedrock-runtime",
                config=Config(
                    connect_timeout=min(10.0, self._timeout),
                    read_timeout=self._timeout,
                    retries={"max_attempts": self._max_retries, "mode": "adaptive"},
                ),
            )
        return self._client

    def complete(self, request: LLMRequest, model_id: str) -> LLMResponse:
        from botocore.exceptions import (
            BotoCoreError,
            ClientError,
            ConnectTimeoutError,
            EndpointConnectionError,
            NoCredentialsError,
            PartialCredentialsError,
            ReadTimeoutError,
        )

        params: dict = {
            "modelId": model_id,
            "messages": [{"role": "user", "content": [{"text": request.prompt}]}],
            "inferenceConfig": {"maxTokens": request.max_tokens or 1024},
        }
        if request.system:
            params["system"] = [{"text": request.system}]
        if request.temperature is not None:  # certains modèles refusent ce paramètre : on ne l'envoie que si demandé
            params["inferenceConfig"]["temperature"] = request.temperature

        started = time.perf_counter()
        try:
            raw = self._get_client().converse(**params)
        except ClientError as exc:
            raise self._map_client_error(exc, model_id) from exc
        except (ReadTimeoutError, ConnectTimeoutError, EndpointConnectionError) as exc:
            raise ProviderTimeoutError(f"Bedrock injoignable ou trop lent ({model_id}): {exc}") from exc
        except (NoCredentialsError, PartialCredentialsError) as exc:
            raise ModelUnavailableError(f"Identifiants AWS introuvables : {exc}") from exc
        except BotoCoreError as exc:
            raise ProviderError(f"Erreur botocore ({model_id}): {exc}") from exc
        latency_ms = (time.perf_counter() - started) * 1000

        blocks = raw.get("output", {}).get("message", {}).get("content", [])
        text = "".join(b["text"] for b in blocks if "text" in b)
        usage = raw.get("usage", {})
        return LLMResponse(
            text=text,
            provider=self.name,
            model_id=model_id,
            usage=TokenUsage(input_tokens=usage.get("inputTokens", 0), output_tokens=usage.get("outputTokens", 0)),
            latency_ms=latency_ms,
            stop_reason=raw.get("stopReason"),
        )

    @staticmethod
    def _map_client_error(exc, model_id: str) -> Exception:
        error = exc.response.get("Error", {})
        code, message = error.get("Code", ""), error.get("Message", "")
        detail = f"{code} ({model_id}): {message}"
        if code in _THROTTLE_CODES:
            return ThrottledError(detail)
        if code in _TIMEOUT_CODES:
            return ProviderTimeoutError(detail)
        if code in _UNAVAILABLE_CODES or (code == "ValidationException" and "model" in message.lower()):
            return ModelUnavailableError(detail)
        return ProviderError(detail)
