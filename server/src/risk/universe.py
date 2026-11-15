"""The 31-asset starter universe: per-asset historical statistics and detection of the assets named in a question."""

from __future__ import annotations

import math
import re

import numpy as np
import pandas as pd

from alphaforge.starter import StarterData

TRADING_DAYS = 252
CRYPTO_DAYS = 365
# Usual names that are not the official name of the asset (the official name and the ticker are always recognised).
ALIASES = {
    "BTC-USD": ["bitcoin", "btc"],
    "ETH-USD": ["ether", "ethereum", "eth"],
    "GOOGL": ["google", "alphabet"],
    "ATD.TO": ["couche-tard", "couche tard"],
    "JNJ": ["johnson & johnson", "johnson and johnson"],
    "PG": ["procter"],
    "XOM": ["exxon"],
    "JPM": ["jpmorgan", "jp morgan"],
    "RY.TO": ["royal bank", "rbc", "banque royale"],
    "TD.TO": ["toronto-dominion", "banque td"],
    "CNR.TO": ["cn rail", "canadien national"],
    "MFC.TO": ["manulife", "manuvie"],
    "CSU.TO": ["constellation software"],
    "SHOP.TO": ["shopify"],
    "QQQ": ["nasdaq-100", "nasdaq 100"],
}


def annualization(ticker: str) -> int:
    return CRYPTO_DAYS if ticker.endswith("-USD") else TRADING_DAYS


def asset_stats(starter: StarterData) -> pd.DataFrame:
    """Historical statistics per asset, in USD, each on its own trading calendar (crypto: 365 days a year).

    Columns: return_1y, return_ann (annualised over the whole window), vol_1y, vol (whole window), max_drawdown
    (whole window, positive), first_date, last_date.
    """
    prices = starter.prices_usd(list(starter.universe.index))
    rows = {}
    for t in prices:
        s = prices[t].dropna()
        r = s.pct_change().dropna()
        n = annualization(t)
        years = (s.index[-1] - s.index[0]).days / 365.25
        one_year = s[s.index >= s.index[-1] - pd.Timedelta(days=365)]
        rows[t] = {
            "return_1y": float(one_year.iloc[-1] / one_year.iloc[0] - 1),
            "return_ann": float((s.iloc[-1] / s.iloc[0]) ** (1 / years) - 1),
            "vol_1y": float(r.iloc[-n:].std() * math.sqrt(n)),
            "vol": float(r.std() * math.sqrt(n)),
            "max_drawdown": float((1 - s / s.cummax()).max()),
            "first_date": s.index[0].strftime("%Y-%m-%d"),
            "last_date": s.index[-1].strftime("%Y-%m-%d"),
        }
    return pd.DataFrame.from_dict(rows, orient="index")


def window_returns(starter: StarterData, start: str, end: str) -> dict[str, float]:
    """Return of each asset (USD, adjusted) between the last price on or before `start` and the last on or before `end`."""
    prices = starter.prices_usd(list(starter.universe.index))
    out = {}
    for t in prices:
        s = prices[t].dropna()
        a, b = s[: pd.Timestamp(start)], s[: pd.Timestamp(end)]
        if len(a) and len(b):
            out[t] = float(b.iloc[-1] / a.iloc[-1] - 1)
    return out


def correlations(starter: StarterData, window: int = TRADING_DAYS * 5) -> pd.DataFrame:
    """Pairwise correlations of daily USD returns on common trading days (crypto weekend moves roll into Monday)."""
    common = starter.prices_usd(list(starter.universe.index)).dropna(how="any")
    return common.pct_change().dropna().iloc[-window:].corr()


def _patterns(starter: StarterData) -> dict[str, re.Pattern]:
    pats = {}
    for ticker, row in starter.universe.iterrows():
        base = ticker.split(".")[0].split("-")[0]
        names = [str(row["name"]).split(" (")[0], *ALIASES.get(ticker, [])]
        name_part = "|".join(re.escape(n) for n in names)
        # Tickers must be written in capitals (avoids "pg", "td" inside words); names are case-insensitive.
        pats[ticker] = re.compile(rf"(?<![\w-])(?:{re.escape(ticker)}|{re.escape(base)})(?![\w-])|(?i:(?<!\w)(?:{name_part})(?!\w))")
    return pats


def find_tickers(question: str, starter: StarterData) -> list[str]:
    """Assets of the universe named in the question (ticker in capitals, official name or usual alias), in order."""
    hits = [(m.start(), t) for t, p in _patterns(starter).items() if (m := p.search(question))]
    return [t for _, t in sorted(hits)]


def is_crypto(asset_class: str) -> bool:
    return asset_class == "crypto"


def nan_to_none(x: float) -> float | None:
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else x
