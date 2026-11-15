"""Interfaces à brancher par les autres équipes (données de marché, portefeuille, module quantitatif).

Aucune implémentation ici : sans elles, les agents le disent (« données indisponibles ») au lieu d'inventer.
"""
from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from alphaforge.contracts import NewsItem, Portfolio, PricePoint


class Observation(BaseModel):
    """Métrique calculée par le module quantitatif (volatilité, sensibilité, corrélation...)."""

    name: str
    value: float
    unit: str | None = None
    source: str  # module ou jeu de données d'origine
    as_of: str | None = None


class MarketData(Protocol):
    def news(self, query: str, tickers: list[str]) -> list[NewsItem]: ...

    def prices(self, ticker: str) -> list[PricePoint]: ...


class PortfolioProvider(Protocol):
    def get(self, user_id: str) -> Portfolio | None: ...


class QuantMetrics(Protocol):
    def observations(self, portfolio: Portfolio, tickers: list[str]) -> list[Observation]: ...
