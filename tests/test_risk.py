"""Module quantitatif : statistiques de portefeuille (valeurs connues par construction) et adaptateur Yahoo (sans réseau)."""
import math

import numpy as np
import pandas as pd
import pytest

from alphaforge.contracts import AnalysisRequest, Holding, Persona, Portfolio
from alphaforge.team.interfaces import Observation
from server.src.risk import quant
from server.src.risk.metrics import portfolio_metrics
from test_team import build

DATES = pd.bdate_range("2025-01-01", periods=300)


def prices_from(returns: dict[str, np.ndarray]) -> pd.DataFrame:
    return pd.DataFrame({s: 100 * np.cumprod(1 + r) for s, r in returns.items()}, index=DATES)


def test_two_uncorrelated_assets_with_equal_vol_halve_the_variance():
    rng = np.random.default_rng(0)
    a = rng.normal(0, 0.01, len(DATES))
    b = rng.normal(0, 0.01, len(DATES))
    b = b - np.dot(a, b - b.mean()) / np.dot(a - a.mean(), a - a.mean()) * (a - a.mean())  # corrélation ~0
    b = b / b.std() * a.std()  # même volatilité
    m = portfolio_metrics(prices_from({"A": a, "B": b}), {"A": 1, "B": 1}, window=299)
    assert m.weights == {"A": 0.5, "B": 0.5} and m.effective_positions == pytest.approx(2.0)
    assert abs(m.avg_correlation) < 0.02
    assert m.diversification_ratio == pytest.approx(math.sqrt(2), rel=0.03)
    assert m.risk_share["A"] == pytest.approx(0.5, abs=0.02) and sum(m.risk_share.values()) == pytest.approx(1.0)


def test_single_asset_has_no_diversification_and_beta_one_against_itself():
    r = np.random.default_rng(1).normal(0, 0.02, len(DATES))
    prices = prices_from({"X": r})
    m = portfolio_metrics(prices, {"X": 3}, benchmark=prices["X"])
    assert m.effective_positions == 1 and m.diversification_ratio == pytest.approx(1.0)
    assert m.vol_annual == pytest.approx(m.asset_vols["X"]) and m.beta == pytest.approx(1.0)
    assert math.isnan(m.avg_correlation) and m.risk_share == {"X": pytest.approx(1.0)}


def test_drawdown_var_and_return_on_a_known_path():
    r = np.zeros(len(DATES))
    r[100] = -0.20  # un seul choc de -20 %
    r[200:] = 0.001
    m = portfolio_metrics(prices_from({"X": r}), {"X": 1})
    assert m.max_drawdown == pytest.approx(0.20)
    assert m.cvar_95_1d >= m.var_95_1d >= 0  # la perte moyenne des pires jours dépasse le seuil VaR
    assert m.total_return == pytest.approx(0.8 * 1.001**100 - 1, rel=1e-6)


def test_metrics_reject_bad_inputs():
    prices = prices_from({"X": np.zeros(len(DATES))})
    with pytest.raises(ValueError):
        portfolio_metrics(prices, {"X": -1})
    with pytest.raises(ValueError):
        portfolio_metrics(prices, {"Y": 1})
    with pytest.raises(ValueError):
        portfolio_metrics(prices.iloc[:30], {"X": 1})


def test_yahoo_quant_converts_cad_to_usd_and_reports_coverage(monkeypatch):
    rng = np.random.default_rng(2)
    raw = prices_from({"NVDA": rng.normal(0, 0.03, len(DATES)), "XIC.TO": rng.normal(0, 0.01, len(DATES)),
                       "SPY": rng.normal(0, 0.01, len(DATES))})
    raw["CAD=X"] = np.linspace(1.30, 1.40, len(DATES))
    raw["XIC.TO"] = 100.0  # prix constant en CAD : en USD, il ne bouge qu'avec le change
    monkeypatch.setattr(quant, "_download", lambda symbols, period, day: raw)
    monkeypatch.setattr(quant, "resolve_symbol", lambda t: {"XIC": "XIC.TO"}.get(t, t))
    adapter = quant.PortfolioQuantMetrics()  # sans jeu de départ : repli sur Yahoo en direct
    prices, _ = adapter._prices_usd(["NVDA", "XIC"])
    assert prices["XIC"].iloc[0] == pytest.approx(100 / 1.30) and prices["XIC"].iloc[-1] == pytest.approx(100 / 1.40)

    portfolio = Portfolio(holdings=[Holding(ticker="NVDA", weight_pct=40), Holding(ticker="XIC", weight_pct=40), Holding(ticker="ZZZ", weight_pct=20)])
    obs = {o.name: o for o in adapter.observations(portfolio, ["NVDA"])}
    assert obs["Part du portefeuille couverte par les calculs (cours disponibles)"].value == 80.0  # ZZZ sans cours
    assert any(n.startswith("Part du risque du portefeuille due à NVDA") for n in obs)
    assert all("Yahoo Finance" in o.source and o.as_of for o in obs.values())


class FakeQuant:
    def __init__(self):
        self.calls = 0

    def observations(self, portfolio, tickers):
        self.calls += 1
        return [Observation(name="Part du risque du portefeuille due à NVDA (poids 40 %)", value=63.9, unit="%",
                            source="Calcul AlphaForge sur cours ajustés Yahoo Finance (test)", as_of="2026-11-13")]


PORTFOLIO = Portfolio(holdings=[Holding(ticker="NVDA", weight_pct=40, sector="Tech"), Holding(ticker="AGG", weight_pct=60)])


def test_metrics_become_cited_evidence_and_reach_the_storyteller():
    fake = FakeQuant()
    orchestrator, _, _ = build(quant=fake)
    report = orchestrator.run(AnalysisRequest(question="Mon portefeuille est-il trop risqué ?", persona=Persona.BALANCED, portfolio=PORTFOLIO))
    metric = next(e for e in report.evidence if e.kind == "metric")
    assert metric.claim == "Part du risque du portefeuille due à NVDA (poids 40 %) : 63.9 %" and metric.validation == "verified"
    assert metric.source.startswith("Calcul AlphaForge") and report.answer_mode == "evidence"
    assert report.portfolio.quantitative_observations[0].value == 63.9


def test_general_question_does_not_compute_metrics():
    fake = FakeQuant()
    orchestrator, _, _ = build(quant=fake)
    report = orchestrator.run(AnalysisRequest(question="C'est quoi un ETF ?", persona=Persona.BALANCED, portfolio=PORTFOLIO))
    assert fake.calls == 0 and report.answer_mode == "general_knowledge"
