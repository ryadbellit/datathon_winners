"""Writes alphaforge-ai/src/data/universe.json: the 31 starter assets with their real historical statistics, the
correlation matrix and historical scenario replays used by the interface (Discover, Compare, Scenarios, Report).

    python -m server.src.risk.build_front_data            # reads ./data/starter (or S3 if STORAGE_BACKEND=s3)

Only aggregated statistics are written (no raw price series). Re-run after updating the starter dataset.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from alphaforge.config import get_settings
from alphaforge.starter import SOURCE_FX, SOURCE_PRICES, StarterData, load_starter
from alphaforge.storage import LocalStorage, get_storage

from .universe import asset_stats, correlations, window_returns

OUT = Path("alphaforge-ai/src/data/universe.json")
BENCH, BONDS = "SPY", "AGG"


def _pct(x: float) -> float:
    return round(100 * x, 1)


def _month_extremes(starter: StarterData) -> tuple[tuple[str, str], tuple[str, str]]:
    """Worst and best 21-trading-day windows of the S&P 500 (SPY) over the dataset."""
    spy = starter.prices[BENCH].dropna()
    move = spy / spy.shift(21) - 1
    worst_end, best_end = move.idxmin(), move.idxmax()
    start = lambda end: spy.index[spy.index.get_loc(end) - 21]  # noqa: E731
    return ((f"{start(worst_end):%Y-%m-%d}", f"{worst_end:%Y-%m-%d}"), (f"{start(best_end):%Y-%m-%d}", f"{best_end:%Y-%m-%d}"))


def scenarios(starter: StarterData) -> list[dict]:
    """Historical replays: what each asset actually did (USD, adjusted) over well-identified past windows."""
    worst, best = _month_extremes(starter)
    last = pd.Timestamp(starter.as_of)
    windows = [
        ("year-2022", "2022: stocks and bonds fell together", "Calendar year 2022, when rates rose quickly.", "2021-12-31", "2022-12-30"),
        ("worst-month", "Worst month of the S&P 500 in the data", "The 21 trading days with the largest S&P 500 fall.", *worst),
        ("year-2023", "2023 rebound", "Calendar year 2023, after the 2022 decline.", "2022-12-30", "2023-12-29"),
        ("best-month", "Best month of the S&P 500 in the data", "The 21 trading days with the largest S&P 500 rise.", *best),
        ("last-12m", "Last 12 months", "The most recent year of the dataset.", f"{last - pd.Timedelta(days=365):%Y-%m-%d}", starter.as_of),
    ]
    out = []
    for sid, name, description, start, end in windows:
        moves = {t: _pct(r) for t, r in window_returns(starter, start, end).items()}
        out.append({
            "id": sid, "name": name, "description": description, "start": start, "end": end, "moves": moves,
            "explanation": f"Historical replay from {start} to {end}: S&P 500 (SPY) {moves[BENCH]:+.1f}%, "
                           f"U.S. bonds (AGG) {moves[BONDS]:+.1f}%. Past moves, not a forecast.",
        })
    return out


def build(starter: StarterData) -> dict:
    stats = asset_stats(starter)
    corr = correlations(starter)
    assets = []
    for ticker, row in starter.universe.iterrows():
        s = stats.loc[ticker]
        assets.append({
            "ticker": ticker, "name": row["name"], "asset_class": row["asset_class"], "market": row["market"],
            "currency": row["currency"], "sector": row["sector"],
            "return_ann": _pct(s["return_ann"]), "return_1y": _pct(s["return_1y"]), "vol": _pct(s["vol"]),
            "vol_1y": _pct(s["vol_1y"]), "max_drawdown": _pct(s["max_drawdown"]), "first_date": s["first_date"],
        })
    return {
        "as_of": starter.as_of,
        "start": f"{starter.prices.index[0]:%Y-%m-%d}",
        "source": f"{SOURCE_PRICES}, {SOURCE_FX}. Returns and risk in USD, computed by AlphaForge (server/src/risk).",
        "assets": assets,
        "correlations": {t: {u: round(float(corr.loc[t, u]), 2) for u in corr.columns} for t in corr.index},
        "scenarios": scenarios(starter),
    }


def main() -> None:
    settings = get_settings()
    starter = load_starter(get_storage(settings), LocalStorage(settings.local_storage_dir))
    if starter is None:
        raise SystemExit("Starter dataset not found: copy it to ./data/starter or run `python -m alphaforge upload-datasets`.")
    OUT.write_text(json.dumps(build(starter), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"written: {OUT} ({len(starter.universe)} assets, as of {starter.as_of})")


if __name__ == "__main__":
    main()
