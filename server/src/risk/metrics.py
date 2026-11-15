"""Portfolio construction & risk statistics from historical prices: pure math (numpy / pandas), no I/O.

Usage:
    from risk.metrics import portfolio_metrics

    m = portfolio_metrics(prices, {"NVDA": 0.4, "MSFT": 0.3, "AGG": 0.3}, benchmark=spy)
    m.vol_annual, m.risk_share["NVDA"], m.effective_positions

All figures describe the PAST window (default: last 252 trading days, i.e. about 1 year). They are
measurements, not forecasts: a calm year can understate the risk of the next one.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

TRADING_DAYS = 252


@dataclass(frozen=True)
class PortfolioMetrics:
    as_of: str  # last date of the window
    n_obs: int  # daily returns used
    weights: dict[str, float]  # normalised to 1 over the assets that have prices
    vol_annual: float  # annualised volatility of the portfolio: sqrt(w' Σ w * 252)
    asset_vols: dict[str, float]  # annualised volatility of each asset
    risk_share: dict[str, float]  # share of portfolio variance due to each asset (sums to 1)
    var_95_1d: float  # historical 1-day loss not exceeded on 95% of days (positive = loss)
    cvar_95_1d: float  # average loss on the worst 5% of days
    max_drawdown: float  # worst peak-to-trough fall of the portfolio over the window (positive)
    total_return: float  # portfolio return over the window (daily rebalanced)
    effective_positions: float  # 1 / sum(w²): how many equal-weight lines the portfolio "behaves like"
    diversification_ratio: float  # sum(w σ) / σ_p ; 1 = no diversification benefit
    avg_correlation: float  # mean pairwise correlation of daily returns (nan if a single asset)
    beta: float | None  # portfolio beta vs the benchmark (None without benchmark)
    asset_betas: dict[str, float]

    def to_dict(self) -> dict:
        return asdict(self)


def portfolio_metrics(
    prices: pd.DataFrame,
    weights: dict[str, float],
    benchmark: pd.Series | None = None,
    window: int = TRADING_DAYS,
) -> PortfolioMetrics:
    """Risk and construction statistics of a constant-weight (daily rebalanced) portfolio.

    Args:
        prices: wide DataFrame of adjusted closes, one column per symbol, all in the SAME currency.
        weights: {symbol: weight >= 0}; renormalised to 1 over the given symbols.
        benchmark: adjusted closes of a market index (e.g. SPY) for betas.
        window: number of most recent daily returns used.
    """
    if any(w < 0 for w in weights.values()) or sum(weights.values()) <= 0:
        raise ValueError("Weights must be non-negative with a positive sum.")
    missing = [s for s in weights if s not in prices.columns]
    if missing:
        raise ValueError(f"No prices for: {missing}")
    symbols = list(weights)
    returns = prices[symbols].sort_index().dropna(how="any").pct_change().dropna().iloc[-window:]
    if len(returns) < 60:
        raise ValueError(f"Need at least 60 common daily returns, got {len(returns)}.")

    w = np.array([weights[s] for s in symbols], dtype=float)
    w /= w.sum()
    cov = returns.cov().to_numpy() * TRADING_DAYS
    variance = float(w @ cov @ w)
    vol = math.sqrt(variance)
    asset_vols = np.sqrt(np.diag(cov))
    contributions = w * (cov @ w) / variance if variance > 0 else np.full(len(w), 1 / len(w))

    port = returns.to_numpy() @ w
    tail = np.sort(port)[: max(1, int(math.ceil(0.05 * len(port))))]
    index = np.cumprod(1 + port)
    drawdown = 1 - index / np.maximum.accumulate(index)

    corr = returns.corr().to_numpy()
    n = len(symbols)
    avg_corr = float((corr.sum() - n) / (n * (n - 1))) if n > 1 else float("nan")

    beta, asset_betas = None, {}
    if benchmark is not None:
        bench = benchmark.dropna().sort_index().pct_change().reindex(returns.index)  # trous (week-ends crypto) retirés
        ok = bench.notna().to_numpy()
        if ok.sum() >= 60 and bench[ok].var() > 0:
            b = bench[ok].to_numpy()
            var_b = float(np.var(b, ddof=1))
            beta = float(np.cov(port[ok], b)[0, 1] / var_b)
            asset_betas = {s: float(np.cov(returns[s].to_numpy()[ok], b)[0, 1] / var_b) for s in symbols}

    return PortfolioMetrics(
        as_of=returns.index[-1].strftime("%Y-%m-%d"),
        n_obs=len(returns),
        weights={s: float(x) for s, x in zip(symbols, w)},
        vol_annual=vol,
        asset_vols={s: float(v) for s, v in zip(symbols, asset_vols)},
        risk_share={s: float(c) for s, c in zip(symbols, contributions)},
        var_95_1d=float(-np.quantile(port, 0.05)),
        cvar_95_1d=float(-tail.mean()),
        max_drawdown=float(drawdown.max()),
        total_return=float(index[-1] - 1),
        effective_positions=float(1 / np.sum(w**2)),
        diversification_ratio=float(w @ asset_vols / vol) if vol > 0 else 1.0,
        avg_correlation=avg_corr,
        beta=beta,
        asset_betas=asset_betas,
    )
