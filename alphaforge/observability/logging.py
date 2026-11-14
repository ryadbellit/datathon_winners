"""Logs JSON structurés (une ligne = un événement), lisibles par CloudWatch Logs Insights.

Sur ECS Fargate, stdout/stderr partent vers CloudWatch via le pilote de logs `awslogs`.
On ne journalise que des métadonnées : jamais d'identifiants ni de prompts complets.
"""
from __future__ import annotations

import contextlib
import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone

from alphaforge.llm.base import LLMRequest, LLMResponse

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

_STANDARD_ATTRS = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


@contextlib.contextmanager
def bind_request_id(request_id: str):
    token = request_id_var.set(request_id)
    try:
        yield
    finally:
        request_id_var.reset(token)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        payload.update({k: v for k, v in record.__dict__.items() if k not in _STANDARD_ATTRS})
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level: str = "INFO", stream=None) -> None:
    """Idempotent : peut être appelé plusieurs fois sans dupliquer les logs. stderr par défaut
    (le pilote `awslogs` d'ECS capture stdout et stderr)."""
    logger = logging.getLogger("alphaforge")
    logger.setLevel(level.upper())
    if not any(getattr(h, "_alphaforge", False) for h in logger.handlers):
        handler = logging.StreamHandler(stream or sys.stderr)
        handler.setFormatter(JsonFormatter())
        handler._alphaforge = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
        logger.propagate = False


def add_cloudwatch_handler(
    log_group: str,
    stream_prefix: str = "alphaforge",
    region: str | None = None,
    profile: str | None = None,
    retention_days: int = 14,
    client=None,
    use_queues: bool = True,
) -> logging.Handler:
    """Envoie les logs JSON vers CloudWatch Logs (groupe créé au besoin, durée de rétention limitée).

    Identifiants : chaîne par défaut de boto3. Permissions : logs:CreateLogGroup, CreateLogStream,
    PutLogEvents, PutRetentionPolicy. Un échec lève une exception : l'appelant décide de continuer sans.
    """
    import uuid

    import boto3
    import watchtower

    if client is None:
        client = boto3.Session(profile_name=profile, region_name=region).client("logs")
    handler = watchtower.CloudWatchLogHandler(
        log_group_name=log_group,
        log_stream_name=f"{stream_prefix}-{datetime.now(timezone.utc):%Y-%m-%d}-{uuid.uuid4().hex[:8]}",
        boto3_client=client,
        create_log_group=True,
        log_group_retention_days=retention_days,
        use_queues=use_queues,
        send_interval=5,
    )
    handler.setFormatter(JsonFormatter())
    handler._alphaforge = True  # type: ignore[attr-defined]
    logging.getLogger("alphaforge").addHandler(handler)
    return handler


def _emf_block(extra: dict) -> dict:
    """Format Embedded Metric Format : CloudWatch en tire des métriques sans appel d'API supplémentaire."""
    metrics = [
        {"Name": "latency_ms", "Unit": "Milliseconds"},
        {"Name": "input_tokens", "Unit": "Count"},
        {"Name": "output_tokens", "Unit": "Count"},
    ]
    if extra.get("estimated_cost_usd") is not None:  # une valeur None est invalide en EMF
        metrics.append({"Name": "estimated_cost_usd", "Unit": "None"})
    return {
        "Timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
        "CloudWatchMetrics": [
            {"Namespace": "AlphaForge", "Dimensions": [["task", "model_id"]], "Metrics": metrics}
        ],
    }


def make_model_call_logger(log_prompts: bool = False, emf: bool = False):
    """Observateur du ModelRouter : un événement `model_call` par appel LLM réussi."""
    logger = logging.getLogger("alphaforge.model_calls")

    def observer(request: LLMRequest, response: LLMResponse) -> None:
        extra = {
            "event": "model_call",
            "task": request.task,
            "provider": response.provider,
            "model_id": response.model_id,
            "latency_ms": round(response.latency_ms, 1),
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "estimated_cost_usd": response.estimated_cost_usd,
            "stop_reason": response.stop_reason,
        }
        if emf:
            extra["_aws"] = _emf_block(extra)
        if log_prompts:  # désactivé par défaut ; tronqué quand activé
            extra["prompt_preview"] = request.prompt[:200]
        logger.info("model_call", extra=extra)

    return observer
