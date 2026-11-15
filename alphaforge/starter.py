"""Jeu de données de départ PolyFinances (31 actifs, 5 ans) : lecture depuis le stockage configuré (S3 ou local).

Fichiers sous la clé `starter/` (envoyés par `python -m alphaforge upload-datasets`) :
- assets_universe.csv : ticker, nom, classe d'actif, marché, devise, secteur ;
- prices_daily.csv : cours quotidiens (Yahoo Finance), `adj_close` ajusté des dividendes et fractionnements ;
- fx_usdcad_daily.csv : taux USD/CAD de la Banque du Canada (pas de ligne les jours fériés canadiens) ;
- macro_rates.csv : taux directeurs, rendements 2 et 10 ans, IPC, chômage (Banque du Canada, FRED).

Règles appliquées (énoncé et README du jeu) : rendements sur `adj_close` ; conversion en USD au taux de la Banque du
Canada (dernier taux connu reporté les jours fériés) ; aucun alignement de calendrier implicite (l'appelant choisit).
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from functools import cached_property

import pandas as pd

from alphaforge.storage import Storage, StorageError

logger = logging.getLogger("alphaforge.starter")
STARTER = "starter"  # préfixe des clés dans le stockage
SOURCE_PRICES = "Jeu de départ PolyFinances : cours ajustés Yahoo Finance"
SOURCE_FX = "taux USD/CAD Banque du Canada"


@dataclass
class StarterData:
    universe: pd.DataFrame  # index = ticker
    prices: pd.DataFrame  # adj_close, une colonne par ticker, devise de cotation
    cadusd: pd.Series  # USD par 1 CAD, Banque du Canada
    macro: pd.DataFrame  # format long : date, series_id, value, unit, frequency, label, source

    @classmethod
    def from_storage(cls, storage: Storage) -> StarterData:
        def csv(name: str, **kwargs) -> pd.DataFrame:
            return pd.read_csv(io.BytesIO(storage.get_bytes(f"{STARTER}/{name}")), **kwargs)

        prices = csv("prices_daily.csv", parse_dates=["date"]).pivot(index="date", columns="ticker", values="adj_close")
        fx = csv("fx_usdcad_daily.csv", parse_dates=["date"]).set_index("date")["cadusd"]
        return cls(
            universe=csv("assets_universe.csv").set_index("ticker"),
            prices=prices.sort_index(),
            cadusd=fx.sort_index(),
            macro=csv("macro_rates.csv", parse_dates=["date"]),
        )

    @property
    def as_of(self) -> str:
        return self.prices.index[-1].strftime("%Y-%m-%d")

    def has(self, ticker: str) -> bool:
        return ticker in self.universe.index and ticker in self.prices

    @cached_property
    def _cadusd_daily(self) -> pd.Series:
        return self.cadusd.reindex(self.prices.index.union(self.cadusd.index)).ffill()

    def prices_usd(self, tickers: list[str]) -> pd.DataFrame:
        """Cours ajustés en USD (CAD convertis au taux du jour de la Banque du Canada), sans alignement de calendrier."""
        out = pd.DataFrame(index=self.prices.index)
        for t in tickers:
            if not self.has(t):
                continue
            series = self.prices[t]
            if self.universe.loc[t, "currency"] == "CAD":
                series = series * self._cadusd_daily.reindex(series.index)
            out[t] = series
        return out

    def macro_latest(self) -> list[dict]:
        """Dernière valeur de chaque série macro, avec sa date d'observation (pas sa date de publication)."""
        last = self.macro.sort_values("date").groupby("series_id").tail(1)
        return last.to_dict("records")


def load_starter(storage: Storage, fallback: Storage | None = None) -> StarterData | None:
    """Jeu de départ depuis le stockage configuré (ex. S3), sinon depuis `fallback` (copie locale) ; None si absent.

    Envoi vers S3 : `python -m alphaforge upload-datasets`."""
    for source in (storage, fallback):
        if source is None:
            continue
        try:
            return StarterData.from_storage(source)
        except StorageError as exc:
            logger.warning("starter_unavailable", extra={"event": "starter_unavailable", "error": str(exc)[:200]})
    return None
