"""Risk of a fictitious portfolio, via GARCH + Monte Carlo on the portfolio's own history.

Usage:
    from risk import garch_portfolio

    r = garch_portfolio(wide_prices, {"AAPL": 0.3, "JNJ": 0.2, "RY.TO": 0.2, "BND": 0.2, "GLD": 0.1},
                        capital=10_000, horizon=63)
    r.return_low, r.return_high       # 90% of scenarios end between these two returns
    r.to_dict()                       # JSON for the agent tool

Why not combine per-asset simulations? They are independent, so they ignore that assets fall
together in a crisis and would understate the loss. Rebuilding the portfolio's historical daily
returns keeps the real co-movements (including 2022) inside the series that GARCH is fitted on.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .garch import TRADING_DAYS, garch_monte_carlo, garch_volatility


@dataclass(frozen=True)
class PortfolioResult:
    as_of: str
    horizon_days: int  # trading days
    weights: dict[str, float]
    capital: float
    history_start: str  # first common date of all assets (the youngest asset limits the history)
    n_obs: int
    # Distribution of the portfolio return at the end of the horizon (drift removed by design)
    return_low: float  # 5th percentile → "perte probable maximale" in 90% of scenarios
    return_median: float
    return_mean: float  # ≈ 0: no expected return is assumed
    return_high: float  # 95th percentile
    value_low: float  # same, in capital terms
    value_median: float
    value_mean: float
    value_high: float
    var_95: float  # loss not exceeded in 95% of scenarios (positive = loss)
    cvar_95: float  # average loss in the worst 5% of scenarios
    prob_drawdown_exceeds: float
    drawdown_threshold: float
    max_drawdown_p90: float
    # Diversification
    vol_portfolio: float  # annualized GARCH forecast for the portfolio
    vol_weighted_assets: float  # weighted average of each asset's own GARCH forecast
    diversification_benefit: float  # 1 - vol_portfolio / vol_weighted_assets (0 = none)
    avg_correlation_1y: float  # mean pairwise correlation of daily returns, last 252 days
    avg_correlation_full: float  # same over the whole history (includes 2022): compare both,
    # a calm year can show much lower correlations than a crisis
    asset_vols: dict[str, float]
    model: str

    def to_dict(self) -> dict:
        return asdict(self)


def portfolio_index(
    prices: pd.DataFrame, weights: dict[str, float], as_of: str | pd.Timestamp | None = None
) -> pd.DataFrame:
    """Align the assets on common dates and build a daily-rebalanced portfolio index (base 100).

    Returns the aligned prices with an extra "PORTFOLIO" column.
    """
    _check_weights(prices, weights)
    df = prices[list(weights)].copy()
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    if as_of is not None:
        df = df.loc[: pd.Timestamp(as_of)]
    # Keep dates where every asset has a price. Crypto weekend moves roll into Monday's return;
    # a holiday on one exchange makes the next return cover two days. Both are minor effects.
    df = df.dropna(how="any")
    w = pd.Series(weights, dtype=float)
    port_ret = df.pct_change().dropna() @ w[df.columns]
    df["PORTFOLIO"] = 100 * pd.concat([pd.Series([1.0], index=df.index[:1]), 1 + port_ret]).cumprod()
    return df


def garch_portfolio(
    prices: pd.DataFrame,
    weights: dict[str, float],
    capital: float = 10_000,
    horizon: int = 21,
    n_paths: int = 2000,
    drawdown_threshold: float = 0.10,
    as_of: str | pd.Timestamp | None = None,
    seed: int | None = 42,
) -> PortfolioResult:
    """Range of outcomes for a fictitious portfolio over `horizon` trading days (max 63).

    Args:
        prices: wide DataFrame, one column of adjusted closes per symbol. All columns must be in
            the SAME currency (convert CAD/USD first, e.g. with fx_usdcad_daily.csv).
        weights: {symbol: weight}, non-negative, summing to 1. Rebalanced daily (constant weights).
        capital: fictitious amount, to express results in money as well as in %.
    """
    df = portfolio_index(prices, weights, as_of)
    index = df.pop("PORTFOLIO")

    mc = garch_monte_carlo(
        index, horizon=horizon, n_paths=n_paths, drawdown_threshold=drawdown_threshold,
        annualization=TRADING_DAYS, seed=seed,
    )
    vol_portfolio = garch_volatility(index, horizon=horizon).vol_forecast
    asset_vols = {s: garch_volatility(df[s], horizon=horizon).vol_forecast for s in df.columns}
    vol_weighted = sum(weights[s] * v for s, v in asset_vols.items())

    daily = df.pct_change().dropna()
    avg_corr_1y, avg_corr_full = _avg_corr(daily.iloc[-252:]), _avg_corr(daily)

    ret = lambda p: p / mc.last_price - 1  # noqa: E731
    r_low, r_med, r_mean, r_high = ret(mc.price_p05), ret(mc.price_p50), ret(mc.price_mean), ret(mc.price_p95)

    return PortfolioResult(
        as_of=mc.as_of,
        horizon_days=horizon,
        weights=dict(weights),
        capital=capital,
        history_start=df.index[0].strftime("%Y-%m-%d"),
        n_obs=len(df) - 1,
        return_low=r_low,
        return_median=r_med,
        return_mean=r_mean,
        return_high=r_high,
        value_low=capital * (1 + r_low),
        value_median=capital * (1 + r_med),
        value_mean=capital * (1 + r_mean),
        value_high=capital * (1 + r_high),
        var_95=mc.var_95,
        cvar_95=mc.cvar_95,
        prob_drawdown_exceeds=mc.prob_drawdown_exceeds,
        drawdown_threshold=drawdown_threshold,
        max_drawdown_p90=mc.max_drawdown_p90,
        vol_portfolio=vol_portfolio,
        vol_weighted_assets=vol_weighted,
        diversification_benefit=1 - vol_portfolio / vol_weighted,
        avg_correlation_1y=avg_corr_1y,
        avg_correlation_full=avg_corr_full,
        asset_vols=asset_vols,
        model=mc.model + " on portfolio returns, Monte Carlo " + mc.method,
    )


def _avg_corr(returns: pd.DataFrame) -> float:
    """Mean of the off-diagonal pairwise correlations."""
    corr = returns.corr().to_numpy()
    n = len(corr)
    return float((corr.sum() - n) / (n * (n - 1))) if n > 1 else float("nan")


def _check_weights(prices: pd.DataFrame, weights: dict[str, float]) -> None:
    missing = [s for s in weights if s not in prices.columns]
    if missing:
        raise ValueError(f"No prices for: {missing}")
    if any(w < 0 for w in weights.values()):
        raise ValueError("Weights must be non-negative (no short selling in the simulation).")
    total = sum(weights.values())
    if not math.isclose(total, 1.0, abs_tol=1e-6):
        raise ValueError(f"Weights must sum to 1, got {total:.4f}.")
