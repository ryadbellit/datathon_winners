"""Implémentation de `MarketData` avec Yahoo Finance (yfinance) : actualités et prix récents. Sans clé d'API."""
from __future__ import annotations

import datetime as dt
from functools import lru_cache

from alphaforge.contracts import NewsItem, PricePoint

YAHOO = "Yahoo Finance"
EXCHANGE_SUFFIXES = (".TO",)  # symboles nus de l'interface (XIC, ZAG) cotés à Toronto chez Yahoo (XIC.TO, ZAG.TO)


def _yf():
    import yfinance  # import lourd : seulement si ce fournisseur est activé

    return yfinance


@lru_cache(maxsize=256)
def resolve_symbol(symbol: str) -> str:
    """Symbole Yahoo d'un ticker : tel quel s'il a des cotations, sinon avec un suffixe de place (XIC -> XIC.TO)."""
    if "." in symbol or "-" in symbol or "=" in symbol:
        return symbol
    for candidate in (symbol, *(symbol + suffix for suffix in EXCHANGE_SUFFIXES)):
        if not _yf().Ticker(candidate).history(period="5d").empty:
            return candidate
    return symbol  # inconnu : l'appelant obtiendra des données vides, sans substitution devinée


class YahooMarketData:
    def __init__(self, days: int = 10, max_news: int = 5):
        self._days, self._max_news = days, max_news

    def prices(self, ticker: str) -> list[PricePoint]:
        t = _yf().Ticker(resolve_symbol(ticker))
        currency = getattr(t.fast_info, "currency", None) or ""  # inconnue : on ne suppose pas USD
        history = t.history(period=f"{self._days}d")
        return [
            PricePoint(ticker=ticker, date=idx.date(), close=float(row["Close"]), currency=currency, source=YAHOO)
            for idx, row in history.iterrows()
        ]

    def news(self, query: str, tickers: list[str]) -> list[NewsItem]:
        items: dict[str, NewsItem] = {}
        for ticker in tickers[:3]:
            for raw in (_yf().Ticker(resolve_symbol(ticker)).news or [])[: self._max_news]:
                c = raw.get("content") or {}
                if not (c.get("title") and c.get("pubDate")):
                    continue
                publisher = (c.get("provider") or {}).get("displayName") or YAHOO
                items.setdefault(
                    c["title"],
                    NewsItem(
                        title=c["title"],
                        source=publisher if publisher == YAHOO else f"{publisher} (via {YAHOO})",  # éditeur réel + agrégateur
                        date=dt.date.fromisoformat(c["pubDate"][:10]),
                        text=c.get("summary") or c.get("description") or "",
                        url=(c.get("canonicalUrl") or {}).get("url"),
                    ),
                )
        return list(items.values())
