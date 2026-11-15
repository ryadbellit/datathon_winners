"""Logs JSON (CloudWatch), métriques EMF et suivi des tokens et du coût.

On ne journalise que des métadonnées : jamais d'identifiants, de prompts ni de questions.
"""
from __future__ import annotations

import contextlib
import json
import logging
import sys
import threading
import uuid
from collections import defaultdict
from contextvars import ContextVar
from datetime import datetime, timezone

import boto3
import watchtower

from alphaforge.config import Settings
from alphaforge.llm import LLMRequest, LLMResponse

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
            **{k: v for k, v in record.__dict__.items() if k not in _STANDARD_ATTRS},
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(settings: Settings) -> None:
    """Logs sur stderr, et vers CloudWatch Logs si CLOUDWATCH_LOG_GROUP est défini. Idempotent."""
    logger = logging.getLogger("alphaforge")
    if logger.handlers:
        return
    logger.setLevel(settings.log_level.upper())
    logger.propagate = False
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if settings.cloudwatch_log_group:
        try:
            handlers.append(
                watchtower.CloudWatchLogHandler(
                    log_group_name=settings.cloudwatch_log_group,
                    log_stream_name=f"alphaforge-{datetime.now(timezone.utc):%Y-%m-%d}-{uuid.uuid4().hex[:8]}",
                    boto3_client=boto3.Session(
                        profile_name=settings.aws_profile, region_name=settings.aws_region
                    ).client("logs"),
                    create_log_group=True,
                    log_group_retention_days=settings.cloudwatch_retention_days,
                    send_interval=5,
                )
            )
        except Exception as exc:  # l'observabilité ne doit jamais empêcher l'application de tourner
            print(f"CloudWatch indisponible, logs locaux uniquement : {type(exc).__name__}: {exc}", file=sys.stderr)
    for handler in handlers:
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)


def model_call_logger(emf: bool):
    """Observateur du ModelRouter : un événement `model_call` par appel réussi (+ métriques CloudWatch si `emf`)."""
    logger = logging.getLogger("alphaforge.model_calls")

    def observe(request: LLMRequest, response: LLMResponse) -> None:
        extra = {
            "event": "model_call",
            "task": request.task,
            "model_id": response.model_id,
            "latency_ms": round(response.latency_ms, 1),
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "estimated_cost_usd": response.estimated_cost_usd,
            "stop_reason": response.stop_reason,
        }
        if emf:  # Embedded Metric Format : CloudWatch en tire des métriques sans appel d'API
            names = ["latency_ms", "input_tokens", "output_tokens"]
            if response.estimated_cost_usd is not None:  # None est invalide en EMF
                names.append("estimated_cost_usd")
            extra["_aws"] = {
                "Timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
                "CloudWatchMetrics": [
                    {
                        "Namespace": "AlphaForge",
                        "Dimensions": [["task", "model_id"]],
                        "Metrics": [{"Name": n, "Unit": "Milliseconds" if n == "latency_ms" else "Count"} for n in names],
                    }
                ],
            }
        logger.info("model_call", extra=extra)

    return observe


class UsageTracker:
    """Cumule tokens et coût par tâche et par modèle. Thread-safe (agents en parallèle)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._rows = defaultdict(lambda: {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "unpriced_calls": 0})

    def __call__(self, request: LLMRequest, response: LLMResponse) -> None:
        with self._lock:
            row = self._rows[(request.task, response.model_id)]
            row["calls"] += 1
            row["input_tokens"] += response.usage.input_tokens
            row["output_tokens"] += response.usage.output_tokens
            if response.estimated_cost_usd is None:
                row["unpriced_calls"] += 1
            else:
                row["cost_usd"] += response.estimated_cost_usd

    def summary(self) -> dict:
        with self._lock:
            rows = [{"task": t, "model_id": m, **r} for (t, m), r in sorted(self._rows.items())]
        unpriced = sum(r["unpriced_calls"] for r in rows)
        return {
            "calls": sum(r["calls"] for r in rows),
            "input_tokens": sum(r["input_tokens"] for r in rows),
            "output_tokens": sum(r["output_tokens"] for r in rows),
            "estimated_cost_usd": None if unpriced else sum(r["cost_usd"] for r in rows),  # connu si tous les prix le sont
            "unpriced_calls": unpriced,
            "by_task_model": rows,
        }
