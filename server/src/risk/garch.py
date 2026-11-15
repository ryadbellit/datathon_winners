"""GARCH volatility forecasting for a single asset.

Usage:
    from risk import garch_volatility

    result = garch_volatility(prices)          # prices: pd.Series of adjusted closes, DatetimeIndex
    result.vol_forecast                         # annualized vol expected over the next `horizon` days
    result.to_dict()                            # JSON-ready, for agent tool outputs

    mc = garch_monte_carlo(prices)              # simulated paths → vol p10/p50/p90, P(drawdown > 10%), VaR, CVaR

    garch_price_ranges(wide_df)                 # several assets: low (p5) / median / mean / high (p95) price

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
MAX_HORIZON = 63  # trading days (≈ 3 months). Beyond that GARCH just reverts to its long-run
# vol, and 5 years of data cannot validate the forecast. Crypto: 63 trading days ≈ 91 crypto days.


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


@dataclass(frozen=True)
class MonteCarloResult:
    as_of: str
    horizon_days: int
    n_paths: int
    method: str  # "bootstrap" (resampled historical shocks) or "simulation" (Student-t shocks)
    vol_p10: float  # annualized realized vol over the horizon, across simulated paths
    vol_p50: float
    vol_p90: float
    vol_forecast_analytic: float  # closed-form GARCH forecast, for comparison
    drawdown_threshold: float
    prob_drawdown_exceeds: float  # share of paths whose max drawdown > drawdown_threshold
    max_drawdown_p50: float
    max_drawdown_p90: float
    var_95: float  # loss over the horizon not exceeded in 95% of paths (positive = loss)
    cvar_95: float  # average loss in the worst 5% of paths
    last_price: float  # price at as_of (same currency as the input)
    price_p05: float  # price at the end of the horizon: 5th percentile of paths ("low")
    price_p50: float  # median final price
    price_mean: float  # mean final price (≈ last_price: drift is removed by design)
    price_p95: float  # 95th percentile ("high")
    model: str

    def to_dict(self) -> dict:
        return asdict(self)


def _check_horizon(horizon: int, annualization: int) -> None:
    """Reject horizons longer than ~3 months (same calendar period for stocks and crypto)."""
    limit = round(MAX_HORIZON * annualization / TRADING_DAYS)
    if not 1 <= horizon <= limit:
        raise ValueError(
            f"horizon must be between 1 and {limit} days (≈ 3 months) for annualization={annualization}, "
            f"got {horizon}."
        )


def _fit(prices, as_of, asymmetric, min_obs):
    """Clean prices, compute % log returns and fit the GARCH model."""
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
    name = ("GJR-GARCH(1,1)" if asymmetric else "GARCH(1,1)") + ", Student-t"
    return s, returns, res, name


def _annualize(daily_var_pct: float, annualization: int) -> float:
    return math.sqrt(daily_var_pct * annualization) / 100


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
    _check_horizon(horizon, annualization)
    s, returns, res, name = _fit(prices, as_of, asymmetric, min_obs)

    p = res.params
    gamma = p.get("gamma[1]", 0.0)
    persistence = float(p["alpha[1]"] + p["beta[1]"] + gamma / 2)  # gamma/2 valid for a symmetric dist (Student-t)

    var_path = res.forecast(horizon=horizon, reindex=False).variance.iloc[-1].to_numpy()
    if persistence < 1:
        vol_long_run = _annualize(p["omega"] / (1 - persistence), annualization)
        half_life = math.log(0.5) / math.log(persistence) if persistence > 0 else 0.0
    else:
        vol_long_run, half_life = float("nan"), float("inf")

    return GarchResult(
        as_of=s.index[-1].strftime("%Y-%m-%d"),
        horizon_days=horizon,
        vol_forecast=_annualize(var_path.mean(), annualization),
        vol_current=float(res.conditional_volatility.iloc[-1]) * math.sqrt(annualization) / 100,
        vol_long_run=vol_long_run,
        vol_historical_1y=float(returns.iloc[-252:].std()) * math.sqrt(annualization) / 100,
        persistence=persistence,
        shock_half_life_days=half_life,
        n_obs=len(returns),
        converged=res.convergence_flag == 0,
        model=name,
        params={k: float(v) for k, v in p.items()},
    )


def garch_monte_carlo(
    prices: pd.Series,
    horizon: int = 21,
    n_paths: int = 2000,
    method: str = "bootstrap",
    drawdown_threshold: float = 0.10,
    annualization: int = TRADING_DAYS,
    as_of: str | pd.Timestamp | None = None,
    asymmetric: bool = True,
    min_obs: int = 250,
    seed: int | None = 42,
) -> MonteCarloResult:
    """Simulate `n_paths` future return paths from a fitted GARCH and measure risk on each.

    Args:
        method: "bootstrap" resamples the model's own historical standardized shocks
            (filtered historical simulation, no distribution assumption — recommended);
            "simulation" draws shocks from the fitted Student-t.
        drawdown_threshold: e.g. 0.10 → probability that the max drawdown exceeds 10%.
        seed: fixes the random draws so results are reproducible (None = random).
        Other args: see `garch_volatility`.

    The fitted mean return is removed from the paths: results describe dispersion and
    downside risk only, never an expected return.
    """
    if method not in ("bootstrap", "simulation"):
        raise ValueError("method must be 'bootstrap' or 'simulation'.")
    _check_horizon(horizon, annualization)
    s, _, res, name = _fit(prices, as_of, asymmetric, min_obs)

    rs = np.random.RandomState(seed)
    kwargs = {"random_state": rs}
    if method == "simulation":
        nu = float(res.params["nu"])  # standardized Student-t shocks (unit variance)
        kwargs = {"rng": lambda size: rs.standard_t(nu, size) * math.sqrt((nu - 2) / nu)}

    fc = res.forecast(horizon=horizon, method=method, simulations=n_paths, reindex=False, **kwargs)
    paths = fc.simulations.values[-1] - res.params["mu"]  # (n_paths, horizon), % log returns, drift removed
    r = paths / 100

    vol = np.sqrt((r**2).mean(axis=1) * annualization)  # zero-mean realized vol per path
    wealth = np.exp(np.hstack([np.zeros((n_paths, 1)), np.cumsum(r, axis=1)]))
    max_dd = 1 - (wealth / np.maximum.accumulate(wealth, axis=1)).min(axis=1)
    total = wealth[:, -1] - 1
    q05 = np.quantile(total, 0.05)
    last_price = float(s.iloc[-1])
    final_price = last_price * wealth[:, -1]

    return MonteCarloResult(
        as_of=s.index[-1].strftime("%Y-%m-%d"),
        horizon_days=horizon,
        n_paths=n_paths,
        method=method,
        vol_p10=float(np.quantile(vol, 0.10)),
        vol_p50=float(np.median(vol)),
        vol_p90=float(np.quantile(vol, 0.90)),
        vol_forecast_analytic=_annualize(
            res.forecast(horizon=horizon, reindex=False).variance.values[-1].mean(), annualization
        ),
        drawdown_threshold=drawdown_threshold,
        prob_drawdown_exceeds=float((max_dd > drawdown_threshold).mean()),
        max_drawdown_p50=float(np.median(max_dd)),
        max_drawdown_p90=float(np.quantile(max_dd, 0.90)),
        var_95=float(-q05),
        cvar_95=float(-total[total <= q05].mean()),
        last_price=last_price,
        price_p05=float(np.quantile(final_price, 0.05)),
        price_p50=float(np.median(final_price)),
        price_mean=float(final_price.mean()),
        price_p95=float(np.quantile(final_price, 0.95)),
        model=name,
    )


def is_crypto(symbol: str) -> bool:
    """Crypto pairs in the starter universe are quoted like 'BTC-USD'."""
    return symbol.upper().endswith(("-USD", "-CAD"))


def garch_price_ranges(
    prices: pd.DataFrame | dict[str, pd.Series],
    horizon: int = 21,
    n_paths: int = 2000,
    method: str = "bootstrap",
    as_of: str | pd.Timestamp | None = None,
    seed: int | None = 42,
) -> pd.DataFrame:
    """Probable price range at the end of the horizon, for several assets at once.

    Args:
        prices: wide DataFrame (one column per symbol, DatetimeIndex) or {symbol: price Series}.
        horizon: in trading days. Crypto (7 days/week) is simulated over the same calendar
            period (21 trading days → 30 crypto days) so ranges are comparable.
        horizon: max MAX_HORIZON (63 trading days ≈ 3 months).
        method: see `garch_monte_carlo`.

    Returns one row per symbol: last price, low (p5), median, mean, high (p95), plus vol and
    drawdown risk. 90% of simulated scenarios end between `price_low` and `price_high`.
    Symbols that fail (e.g. too little history) get an `error` instead of numbers.
    """
    rows = []
    for sym, px in prices.items():  # works for both a dict and a wide DataFrame
        crypto = is_crypto(str(sym))
        h = round(horizon * CRYPTO_DAYS / TRADING_DAYS) if crypto else horizon
        try:
            mc = garch_monte_carlo(
                px, horizon=h, n_paths=n_paths, method=method, as_of=as_of, seed=seed,
                annualization=CRYPTO_DAYS if crypto else TRADING_DAYS,
            )
        except ValueError as e:
            rows.append({"symbol": sym, "error": str(e)})
            continue
        rows.append({
            "symbol": sym,
            "as_of": mc.as_of,
            "horizon_days": h,
            "last_price": mc.last_price,
            "price_low": mc.price_p05,
            "price_median": mc.price_p50,
            "price_mean": mc.price_mean,
            "price_high": mc.price_p95,
            "range_pct": (mc.price_p95 - mc.price_p05) / mc.last_price,
            "vol_p50": mc.vol_p50,
            "prob_drawdown_gt_10pct": mc.prob_drawdown_exceeds,
            "error": None,
        })
    return pd.DataFrame(rows).set_index("symbol")
