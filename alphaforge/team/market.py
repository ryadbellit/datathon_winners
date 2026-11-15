"""Implémentation de `MarketData` avec Yahoo Finance (yfinance) : actualités et prix récents. Sans clé d'API."""
from __future__ import annotations

import datetime as dt

from alphaforge.contracts import NewsItem, PricePoint


class YahooMarketData:
    def __init__(self, days: int = 10, max_news: int = 5):
        self._days, self._max_news = days, max_news

    @staticmethod
    def _ticker(symbol: str):
        import yfinance  # import lourd : seulement si ce fournisseur est activé

        return yfinance.Ticker(symbol)

    def prices(self, ticker: str) -> list[PricePoint]:
        t = self._ticker(ticker)
        currency = getattr(t.fast_info, "currency", None) or ""  # inconnue : on ne suppose pas USD
        history = t.history(period=f"{self._days}d")
        return [PricePoint(ticker=ticker, date=idx.date(), close=float(row["Close"]), currency=currency) for idx, row in history.iterrows()]

    def news(self, query: str, tickers: list[str]) -> list[NewsItem]:
        items: dict[str, NewsItem] = {}
        for ticker in tickers[:3]:
            for raw in (self._ticker(ticker).news or [])[: self._max_news]:
                c = raw.get("content") or {}
                if not (c.get("title") and c.get("pubDate")):
                    continue
                items.setdefault(
                    c["title"],
                    NewsItem(
                        title=c["title"],
                        source=(c.get("provider") or {}).get("displayName") or "Yahoo Finance",
                        date=dt.date.fromisoformat(c["pubDate"][:10]),
                        text=c.get("summary") or c.get("description") or "",
                        url=(c.get("canonicalUrl") or {}).get("url"),
                    ),
                )
        return list(items.values())
