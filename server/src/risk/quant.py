"""`QuantMetrics` implementation: portfolio statistics (metrics.py), GARCH forecast (portfolio.py), what-if and macro context.

Prices come from the PolyFinances starter dataset (adjusted closes, 5 years, CAD converted with the Bank of Canada
rate) when the asset is in it, otherwise from live Yahoo Finance. Every figure becomes an `Observation` whose `source`
says exactly where it comes from, so the agents can cite it as evidence.
"""

from __future__ import annotations

import datetime as dt
import logging
from functools import lru_cache

import pandas as pd

from alphaforge.contracts import Portfolio
from alphaforge.starter import SOURCE_FX, SOURCE_PRICES, StarterData
from alphaforge.team.interfaces import Observation
from alphaforge.team.market import resolve_symbol

from .metrics import portfolio_metrics
from .portfolio import garch_portfolio

logger = logging.getLogger("alphaforge.quant")
BENCHMARK = "SPY"  # S&P 500, for betas
FX_CADUSD = "CAD=X"  # Yahoo: CAD per 1 USD (live fallback only)
CAD_SUFFIXES = (".TO", ".V")
WHAT_IF_WEIGHT = 0.10  # weight given to an asset that is asked about but not held
MACRO_SERIES = {  # starter macro series shown as context when the portfolio holds bonds
    "V39079": "Taux directeur de la Banque du Canada",
    "BD.CDN.10YR.DQ.YLD": "Rendement des obligations du Canada à 10 ans",
    "STATIC_TOTALCPICHANGE": "Inflation au Canada (IPC, variation sur 1 an)",
    "DFF": "Taux des fonds fédéraux américains",
    "DGS10": "Rendement des obligations du Trésor américain à 10 ans",
}


@lru_cache(maxsize=32)
def _download(symbols: tuple[str, ...], period: str, day: str) -> pd.DataFrame:
    """Live adjusted closes, one column per Yahoo symbol; cached for the day (`day` is part of the cache key)."""
    import yfinance  # heavy import: only for assets outside the starter dataset

    closes = yfinance.download(list(symbols), period=period, auto_adjust=True, progress=False)["Close"]
    return closes if isinstance(closes, pd.DataFrame) else closes.to_frame(symbols[0])


def _pct(x: float) -> float:
    return round(100 * x, 1)


class PortfolioQuantMetrics:
    def __init__(self, starter: StarterData | None = None, period: str = "5y", horizon_days: int = 21, max_focus: int = 2):
        self._starter, self._period, self._horizon, self._max_focus = starter, period, horizon_days, max_focus

    def _yahoo_usd(self, tickers: list[str]) -> pd.DataFrame:
        yahoo = {t: resolve_symbol(t) for t in tickers}
        raw = _download(tuple(sorted({*yahoo.values(), FX_CADUSD})), self._period, dt.date.today().isoformat())
        out = pd.DataFrame(index=raw.index)
        for ticker, symbol in yahoo.items():
            if symbol in raw and not raw[symbol].dropna().empty:
                out[ticker] = raw[symbol] / raw[FX_CADUSD].ffill() if symbol.endswith(CAD_SUFFIXES) else raw[symbol]
        return out

    def _prices_usd(self, tickers: list[str]) -> tuple[pd.DataFrame, str]:
        """USD prices (app tickers as columns, benchmark included) and a description of where they come from."""
        wanted = sorted({*tickers, BENCHMARK})
        local = [t for t in wanted if self._starter and self._starter.has(t)]
        live = [t for t in wanted if t not in local]
        frames, sources = [], []
        if local:
            frames.append(self._starter.prices_usd(local))
            sources.append(f"{SOURCE_PRICES} ({self._starter.prices.index[0]:%Y-%m-%d} → {self._starter.as_of}), {SOURCE_FX}")
        if live:
            frames.append(self._yahoo_usd(live))
            sources.append(f"Yahoo Finance en direct pour {', '.join(t for t in live if t != BENCHMARK) or BENCHMARK}")
        return pd.concat(frames, axis=1).sort_index(), " ; ".join(sources)

    def observations(self, portfolio: Portfolio, tickers: list[str]) -> list[Observation]:
        weights = {h.ticker: h.weight_pct for h in portfolio.holdings if h.weight_pct > 0}
        if not weights:
            return []
        candidates = [t for t in tickers if t not in weights][: self._max_focus]  # asked about, not held
        prices, origin = self._prices_usd([*weights, *candidates])
        benchmark = prices.pop(BENCHMARK) if BENCHMARK not in weights else prices[BENCHMARK]
        covered = {t: w for t, w in weights.items() if t in prices and prices[t].notna().sum() >= 60}
        if not covered:
            return []
        m = portfolio_metrics(prices[list(covered)], covered, benchmark)
        source = f"Calcul AlphaForge sur 1 an ({m.n_obs} séances communes, en USD) — {origin}"

        def obs(name: str, value: float, unit: str | None = "%", src: str = source, as_of: str = m.as_of) -> Observation:
            return Observation(name=name, value=value, unit=unit, source=src, as_of=as_of)

        out = []
        coverage = sum(covered.values()) / sum(weights.values())
        if coverage < 0.999:
            out.append(obs("Part du portefeuille couverte par les calculs (cours disponibles)", _pct(coverage)))
        out += [
            obs("Volatilité annualisée du portefeuille (1 an)", _pct(m.vol_annual)),
            obs("Perte journalière dépassée seulement 1 jour sur 20 (VaR historique 95 %, 1 jour)", _pct(m.var_95_1d)),
            obs("Perte moyenne des 5 % pires jours (CVaR 95 %, 1 jour)", _pct(m.cvar_95_1d)),
            obs("Baisse maximale du portefeuille sur 1 an (d'un sommet au creux suivant)", _pct(m.max_drawdown)),
            obs(f"Nombre effectif de lignes (diversification réelle, sur {len(covered)} lignes)", round(m.effective_positions, 1), "lignes"),
        ]
        if len(covered) > 1:
            out.append(obs("Corrélation moyenne entre les lignes (1 an, de -1 à 1)", round(m.avg_correlation, 2), None))
        if m.beta is not None:
            out.append(obs(f"Bêta du portefeuille par rapport au S&P 500 ({BENCHMARK})", round(m.beta, 2), None))

        focus = [t for t in tickers if t in covered][: self._max_focus] or ([] if candidates else [max(m.risk_share, key=m.risk_share.get)])
        for t in focus:
            out.append(obs(f"Part du risque du portefeuille due à {t} (poids {_pct(m.weights[t]):g} %)", _pct(m.risk_share[t])))
            out.append(obs(f"Volatilité annualisée de {t} (1 an)", _pct(m.asset_vols[t])))
        out += self._what_if(prices, covered, candidates, benchmark, m, source)
        out += self._garch(prices, covered, origin)
        if self._starter and any(self._starter.has(t) and self._starter.universe.loc[t, "asset_class"] == "etf_bond" for t in covered):
            out += self._macro()
        return out

    def _what_if(self, prices, covered, candidates, benchmark, m, source) -> list[Observation]:
        """Asset asked about but not held: its own risk, and the portfolio if it took WHAT_IF_WEIGHT of it."""
        out = []
        for t in candidates:
            if t not in prices or prices[t].notna().sum() < 60:
                continue
            total = sum(covered.values())
            mixed = {**{s: (1 - WHAT_IF_WEIGHT) * w / total for s, w in covered.items()}, t: WHAT_IF_WEIGHT}
            aligned = prices[list(mixed)].dropna(how="any")  # même calendrier que le portefeuille (crypto : week-end reporté au lundi)
            alone = portfolio_metrics(aligned[[t]], {t: 1}, benchmark)
            after = portfolio_metrics(aligned, mixed, benchmark)
            share = _pct(WHAT_IF_WEIGHT)
            out += [
                Observation(name=f"Volatilité annualisée de {t} (1 an, actif non détenu)", value=_pct(alone.vol_annual), unit="%", source=source, as_of=alone.as_of),
                Observation(name=f"Baisse maximale de {t} sur 1 an (actif non détenu)", value=_pct(alone.max_drawdown), unit="%", source=source, as_of=alone.as_of),
                Observation(name=f"Volatilité du portefeuille si {t} y pesait {share:g} % (simulation, contre {_pct(m.vol_annual):g} % aujourd'hui)",
                            value=_pct(after.vol_annual), unit="%", source=source, as_of=after.as_of),
                Observation(name=f"Part du risque du portefeuille qui viendrait de {t} à {share:g} % du poids (simulation)",
                            value=_pct(after.risk_share[t]), unit="%", source=source, as_of=after.as_of),
            ]
        return out

    def _garch(self, prices, covered, origin) -> list[Observation]:
        """GARCH + Monte Carlo (risk/portfolio.py) on the full common history: a forecast, unlike the other figures."""
        try:
            total = sum(covered.values())
            g = garch_portfolio(prices[list(covered)].dropna(how="any"), {t: w / total for t, w in covered.items()},
                                horizon=self._horizon, n_paths=1000)
        except Exception as exc:  # too little history, no convergence...: the other figures stay valid
            logger.warning("garch_unavailable", extra={"event": "garch_unavailable", "error_type": type(exc).__name__})
            return []
        src = f"Modèle {g.model}, {g.n_obs} séances depuis {g.history_start} — {origin}"
        return [
            Observation(name=f"Volatilité prévue du portefeuille sur {self._horizon} séances (GARCH, annualisée)", value=_pct(g.vol_portfolio), unit="%", source=src, as_of=g.as_of),
            Observation(name=f"Perte non dépassée dans 95 % des scénarios simulés sur {self._horizon} séances (GARCH + Monte Carlo)", value=_pct(g.var_95), unit="%", source=src, as_of=g.as_of),
        ]

    def _macro(self) -> list[Observation]:
        """Rates and inflation context (dated to the observation, not the publication: CPI comes out weeks later)."""
        rows = {r["series_id"]: r for r in self._starter.macro_latest()}
        return [
            Observation(name=f"{label} (observation du {rows[sid]['date']:%Y-%m-%d})", value=round(float(rows[sid]["value"]), 2), unit="%",
                        source=f"Jeu de départ PolyFinances : {rows[sid]['source']} (série {sid})", as_of=f"{rows[sid]['date']:%Y-%m-%d}")
            for sid, label in MACRO_SERIES.items() if sid in rows
        ]
