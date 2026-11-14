"""Suivi cumulé des tokens et du coût par tâche et par modèle."""
from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass

from alphaforge.llm.base import LLMRequest, LLMResponse


@dataclass
class _Bucket:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    unpriced_calls: int = 0  # appels dont le prix du modèle n'est pas configuré


class UsageTracker:
    """S'enregistre comme observateur du ModelRouter. Thread-safe (agents en parallèle)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._buckets: dict[tuple[str, str], _Bucket] = defaultdict(_Bucket)

    def __call__(self, request: LLMRequest, response: LLMResponse) -> None:
        with self._lock:
            bucket = self._buckets[(request.task, response.model_id)]
            bucket.calls += 1
            bucket.input_tokens += response.usage.input_tokens
            bucket.output_tokens += response.usage.output_tokens
            if response.estimated_cost_usd is None:
                bucket.unpriced_calls += 1
            else:
                bucket.cost_usd += response.estimated_cost_usd

    def summary(self) -> dict:
        with self._lock:
            rows = [
                {"task": task, "model_id": model, **vars(b)} for (task, model), b in sorted(self._buckets.items())
            ]
        unpriced = sum(r["unpriced_calls"] for r in rows)
        return {
            "calls": sum(r["calls"] for r in rows),
            "input_tokens": sum(r["input_tokens"] for r in rows),
            "output_tokens": sum(r["output_tokens"] for r in rows),
            # Coût connu uniquement si tous les modèles utilisés ont un prix configuré
            "estimated_cost_usd": None if unpriced else sum(r["cost_usd"] for r in rows),
            "unpriced_calls": unpriced,
            "by_task_model": rows,
        }
