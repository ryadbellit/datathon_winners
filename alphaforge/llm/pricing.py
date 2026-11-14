"""Estimation du coût à partir d'une table de prix fournie par la configuration."""
from __future__ import annotations

from alphaforge.contracts import TokenUsage

_PROFILE_PREFIXES = ("global.", "us.", "eu.", "apac.")


class PricingTable:
    def __init__(self, prices: dict[str, dict[str, float]] | None = None):
        self._prices = prices or {}

    def _lookup(self, model_id: str) -> dict[str, float] | None:
        if model_id in self._prices:
            return self._prices[model_id]
        for prefix in _PROFILE_PREFIXES:  # permet de ne déclarer le prix qu'une fois par modèle
            if model_id.startswith(prefix) and model_id[len(prefix):] in self._prices:
                return self._prices[model_id[len(prefix):]]
        return None

    def cost(self, model_id: str, usage: TokenUsage) -> float | None:
        """Coût en USD, ou None si le prix du modèle n'est pas configuré (on ne devine pas)."""
        price = self._lookup(model_id)
        if price is None:
            return None
        return (
            usage.input_tokens * price["input_per_1m"] + usage.output_tokens * price["output_per_1m"]
        ) / 1_000_000
