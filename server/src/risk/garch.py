"""GARCH volatility forecasting for a single asset.

Usage:
    from risk import garch_volatility

    result = garch_volatility(prices)          # prices: pd.Series of adjusted closes, DatetimeIndex
    result.vol_forecast                         # annualized vol expected over the next `horizon` days
    result.to_dict()                            # JSON-ready, for agent tool outputs

For many assets in a long-format DataFrame (date, symbol, adj_close, ...):
    {sym: garch_volatility(g.set_index("date")["adj_close"]) for sym, g in df.groupby("symbol")}
"""

from __future__ import annotations

import math
import warnings
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from arch import arch_model

TRADING_DAYS = 252  # equities / ETFs
CRYPTO_DAYS = 365  # crypto trades every day


@dataclass(frozen=True)
class GarchResult:
    as_of: str  # last date used (no data after it was seen)
    horizon_days: int
    vol_forecast: float  # annualized vol expected on average over the horizon
    vol_current: float  # annualized conditional vol today
    vol_long_run: float  # annualized level vol reverts to (nan if non-stationary)
    vol_historical_1y: float  # annualized realized vol, last 252 observations
    persistence: float  # alpha + beta + gamma/2; closer to 1 = shocks last longer
    shock_half_life_days: float  # days for a vol shock to lose half its effect
    n_obs: int
    converged: bool
    model: str
    params: dict[str, float]

    def to_dict(self) -> dict:
        return asdict(self)


def garch_volatility(
    prices: pd.Series,
    horizon: int = 21,
    annualization: int = TRADING_DAYS,
    as_of: str | pd.Timestamp | None = None,
    asymmetric: bool = True,
    min_obs: int = 250,
) -> GarchResult:
    """Fit a GARCH(1,1) on log returns and forecast volatility over `horizon` days.

    Args:
        prices: adjusted close prices indexed by date (dividends/splits adjusted).
        horizon: forecast horizon in trading days (21 ≈ 1 month, 63 ≈ 3 months).
        annualization: 252 for stocks/ETFs, 365 for crypto (use CRYPTO_DAYS).
        as_of: only use data up to this date (for walk-forward backtests, avoids look-ahead).
        asymmetric: GJR-GARCH (vol reacts more to drops than to rises). Recommended for equities.
        min_obs: minimum number of returns required to fit.
    """
    s = pd.Series(prices).dropna()
    s.index = pd.to_datetime(s.index)
    s = s.sort_index()
    if as_of is not None:
        s = s.loc[: pd.Timestamp(as_of)]
    s = s[s > 0]

    # Returns in percent: the optimizer is much more stable at this scale.
    returns = 100 * np.log(s).diff().dropna()
    if len(returns) < min_obs:
        raise ValueError(f"Need at least {min_obs} returns, got {len(returns)}.")

    model = arch_model(
        returns,
        mean="Constant",
        vol="GARCH",
        p=1,
        o=1 if asymmetric else 0,
        q=1,
        dist="t",
        rescale=False,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # convergence is reported via `converged`
        res = model.fit(disp="off", show_warning=False)

    p = res.params
    gamma = p.get("gamma[1]", 0.0)
    persistence = float(p["alpha[1]"] + p["beta[1]"] + gamma / 2)  # gamma/2 valid for a symmetric dist (Student-t)

    to_annual = lambda daily_var_pct: math.sqrt(daily_var_pct * annualization) / 100  # noqa: E731

    var_path = res.forecast(horizon=horizon, reindex=False).variance.iloc[-1].to_numpy()
    if persistence < 1:
        vol_long_run = to_annual(p["omega"] / (1 - persistence))
        half_life = math.log(0.5) / math.log(persistence) if persistence > 0 else 0.0
    else:
        vol_long_run, half_life = float("nan"), float("inf")

    return GarchResult(
        as_of=s.index[-1].strftime("%Y-%m-%d"),
        horizon_days=horizon,
        vol_forecast=to_annual(var_path.mean()),
        vol_current=float(res.conditional_volatility.iloc[-1]) * math.sqrt(annualization) / 100,
        vol_long_run=vol_long_run,
        vol_historical_1y=float(returns.iloc[-252:].std()) * math.sqrt(annualization) / 100,
        persistence=persistence,
        shock_half_life_days=half_life,
        n_obs=len(returns),
        converged=res.convergence_flag == 0,
        model=("GJR-GARCH(1,1)" if asymmetric else "GARCH(1,1)") + ", Student-t",
        params={k: float(v) for k, v in p.items()},
    )
