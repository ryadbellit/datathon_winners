"""Deterministic profile checks: does the portfolio (and the asset asked about) fit the investor's profile?

The rules and thresholds below are documented assumptions (README, « Contrôles de profil »), not market facts. They are
computed by code, shown to the user and passed to the agents as evidence: the governance agent cannot declare a
profile "consistent" when a check fails. Portfolio volatility ceilings match the interface (COMFORT_RULES in engine.ts).
"""

from __future__ import annotations

from alphaforge.contracts import AnalysisRequest, Persona
from alphaforge.starter import StarterData
from alphaforge.team.interfaces import Check

from .metrics import portfolio_metrics
from .universe import asset_stats

SOURCE = "Contrôles de profil AlphaForge (seuils documentés dans le README) sur le jeu de départ PolyFinances"
LIMITS = {  # percent ; asset_vol=None: no ceiling for a single asset, only diversification rules
    Persona.PRUDENT: {"label": "prudent", "vol": 8, "line": 20, "crypto": 0, "sector": 40, "asset_vol": 25},
    Persona.BALANCED: {"label": "équilibré", "vol": 12, "line": 25, "crypto": 5, "sector": 50, "asset_vol": 35},
    Persona.BOLD: {"label": "audacieux", "vol": 18, "line": 35, "crypto": 10, "sector": 60, "asset_vol": None},
}
SHORT_HORIZON_YEARS = 5
SHORT_HORIZON_MAX_VOL = 30  # percent: above this, a single asset can lose a lot within a short horizon
MIN_EFFECTIVE_POSITIONS = 3  # "risque élevé ne veut pas dire tout est acceptable": diversification is checked for everyone
FOSSIL_SECTORS = {"Energy"}  # starter sector labels; a sector exposure, NOT an ESG rating (the data has none)
SINGLE_NAME_CLASSES = {"equity", "crypto"}  # diversified ETFs are not "single lines" for concentration purposes


def _fmt(x: float) -> str:
    return f"{x:.1f}".rstrip("0").rstrip(".")


class ProfileRules:
    def __init__(self, starter: StarterData):
        self._starter = starter
        self._stats = asset_stats(starter)
        self._universe = starter.universe

    def _info(self, ticker: str) -> dict | None:
        return self._universe.loc[ticker].to_dict() if ticker in self._universe.index else None

    def checks(self, request: AnalysisRequest) -> list[Check]:
        limits = LIMITS[request.persona]
        profile = f"profil {limits['label']}"
        holdings = {h.ticker: h.weight_pct for h in (request.portfolio.holdings if request.portfolio else []) if h.weight_pct > 0}
        total = sum(holdings.values())
        weights = {t: w / total * 100 for t, w in holdings.items()} if total else {}
        known = {t: w for t, w in weights.items() if self._info(t)}
        candidates = [t for t in request.tickers if t not in weights and self._info(t)]
        out: list[Check] = []

        def check(rule: str, status: str, detail: str) -> None:
            out.append(Check(rule=rule, status=status, detail=detail, source=SOURCE))

        if known:
            m = portfolio_metrics(self._starter.prices_usd(list(known)), known)
            vol = 100 * m.vol_annual
            status = "ok" if vol <= limits["vol"] else "fail" if vol > 1.5 * limits["vol"] else "warn"
            check("Volatilité du portefeuille (1 an)", status, f"{_fmt(vol)} % pour un plafond de {limits['vol']} % ({profile})")
            n_eff = m.effective_positions
            check("Diversification (nombre effectif de lignes)", "ok" if n_eff >= MIN_EFFECTIVE_POSITIONS else "warn",
                  f"{_fmt(n_eff)} lignes effectives pour un minimum de {MIN_EFFECTIVE_POSITIONS}")

            singles = {t: w for t, w in known.items() if self._info(t)["asset_class"] in SINGLE_NAME_CLASSES}
            if singles:
                top, w = max(singles.items(), key=lambda kv: kv[1])
                check("Poids d'une seule ligne (action ou crypto)", "ok" if w <= limits["line"] else "warn",
                      f"{top} pèse {_fmt(w)} % pour un maximum de {limits['line']} % ({profile})")
            sectors: dict[str, float] = {}
            for t, w in known.items():
                if self._info(t)["asset_class"] == "equity":
                    sectors[self._info(t)["sector"]] = sectors.get(self._info(t)["sector"], 0) + w
            if sectors:
                sector, w = max(sectors.items(), key=lambda kv: kv[1])
                check("Concentration sectorielle (actions individuelles)", "ok" if w <= limits["sector"] else "warn",
                      f"{sector} : {_fmt(w)} % du portefeuille pour un maximum de {limits['sector']} %")

        crypto = sum(w for t, w in known.items() if self._info(t)["asset_class"] == "crypto")
        crypto_candidates = [t for t in candidates if self._info(t)["asset_class"] == "crypto"]
        if crypto or crypto_candidates:
            limit = limits["crypto"]
            status = "fail" if limit == 0 else "ok" if crypto <= limit else "warn"
            asked = f" ; demande portant sur {', '.join(crypto_candidates)}" if crypto_candidates else ""
            check("Cryptoactifs", status, f"{_fmt(crypto)} % du portefeuille pour un maximum de {limit} % ({profile}){asked}")

        horizon = request.horizon_years
        for t in candidates:
            vol = 100 * self._stats.loc[t, "vol_1y"]
            ceiling = limits["asset_vol"]
            if ceiling is not None:
                check(f"Adéquation de {t} au profil", "ok" if vol <= ceiling else "warn",
                      f"volatilité de {t} sur 1 an : {_fmt(vol)} % pour un plafond de {ceiling} % par actif ({profile})")
            if horizon is not None and horizon <= SHORT_HORIZON_YEARS:
                check(f"Horizon de placement et {t}", "ok" if vol <= SHORT_HORIZON_MAX_VOL else "warn",
                      f"horizon de {horizon} ans ; volatilité de {t} : {_fmt(vol)} % (seuil {SHORT_HORIZON_MAX_VOL} % pour un horizon de "
                      f"{SHORT_HORIZON_YEARS} ans ou moins)")

        lines = [*known, *candidates]
        if request.esg_preference != "none":
            fossil = [t for t in lines if self._info(t)["sector"] in FOSSIL_SECTORS]
            status = "ok" if not fossil else "fail" if request.esg_preference == "strong" else "warn"
            detail = (f"exposition au secteur Énergie (combustibles fossiles) : {', '.join(fossil)}" if fossil
                      else "aucune ligne du secteur Énergie") + " ; classement par secteur, le jeu de données ne contient aucune note ESG"
            check("Préférence ESG", status, detail)
        for term in request.exclusions:
            term_l = term.strip().lower()
            if not term_l:
                continue
            hit = [t for t in lines if term_l in " ".join([t, str(self._info(t)["name"]), str(self._info(t)["sector"])]).lower()]
            check(f"Exclusion « {term.strip()} »", "fail" if hit else "ok",
                  f"lignes concernées : {', '.join(hit)}" if hit else "aucune ligne concernée")
        return out
