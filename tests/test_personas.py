"""Les trois personas de l'énoncé, sur les données réelles du jeu de départ (data/starter, non versionné : test ignoré sans)."""
from pathlib import Path

import pytest

from alphaforge.contracts import AnalysisRequest, Holding, Persona, Portfolio
from alphaforge.storage import LocalStorage
from alphaforge.starter import load_starter
from server.src.main import to_request
from server.src.risk.checks import ProfileRules
from server.src.risk.universe import find_tickers
from test_team import build

pytestmark = pytest.mark.skipif(not Path("data/starter/prices_daily.csv").exists(), reason="jeu de départ absent (data/starter)")


@pytest.fixture(scope="module")
def starter():
    return load_starter(LocalStorage("data"))


@pytest.fixture(scope="module")
def rules(starter):
    return ProfileRules(starter)


def portfolio(**weights):
    return Portfolio(holdings=[Holding(ticker=t.replace("_", "."), weight_pct=w) for t, w in weights.items()])


def statuses(checks):
    return {c.rule: c.status for c in checks}


def test_robert_is_warned_that_tesla_does_not_fit_a_cautious_short_horizon(starter, rules):
    """Robert, 59 ans, prudent, 3 à 5 ans, tenté par une action très médiatisée."""
    body = {"question": "Je pense acheter du Tesla, bonne idée ?", "profile": {"objective": "preservation", "horizon": "short", "comfort": "stability"},
            "holdings": [{"ticker": "AGG", "weight_pct": 50}, {"ticker": "XBB.TO", "weight_pct": 30}, {"ticker": "JNJ", "weight_pct": 20}]}
    request = to_request(body, lambda q: find_tickers(q, starter))
    assert request.persona == Persona.PRUDENT and request.tickers == ["TSLA"]
    s = statuses(rules.checks(request))
    assert s["Adéquation de TSLA au profil"] == "warn" and s["Horizon de placement et TSLA"] == "warn"
    assert s["Volatilité du portefeuille (1 an)"] == "ok"  # son portefeuille actuel, lui, respecte le profil


def test_mateo_strong_esg_preference_flags_fossil_energy(rules):
    """Mateo, 41 ans, modéré, ESG important : Exxon dans le portefeuille est un conflit."""
    request = AnalysisRequest(question="Mon portefeuille respecte-t-il mes critères ?", persona=Persona.BALANCED, esg_preference="strong",
                              portfolio=portfolio(ESGV=40, XOM=15, AGG=45))
    checks = {c.rule: c for c in rules.checks(request)}
    assert checks["Préférence ESG"].status == "fail" and "XOM" in checks["Préférence ESG"].detail
    assert "aucune note ESG" in checks["Préférence ESG"].detail  # limite des données dite honnêtement
    aware = rules.checks(request.model_copy(update={"esg_preference": "aware", "exclusions": ["Energy"]}))
    assert statuses(aware)["Préférence ESG"] == "warn" and statuses(aware)["Exclusion « Energy »"] == "fail"


def test_amira_high_risk_still_requires_diversification(rules):
    """Amira, 26 ans, risque élevé : crypto et tech acceptées, mais pas sans limite."""
    request = AnalysisRequest(question="Mon portefeuille est-il assez diversifié ?", persona=Persona.BOLD,
                              portfolio=portfolio(**{"BTC-USD": 25, "NVDA": 45, "SHOP_TO": 20, "QQQ": 10}))
    s = statuses(rules.checks(request))
    assert s["Cryptoactifs"] == "warn"  # 25 % pour un maximum de 10 %
    assert s["Poids d'une seule ligne (action ou crypto)"] == "warn"  # NVDA à 45 % pour un maximum de 35 %
    assert s["Concentration sectorielle (actions individuelles)"] == "warn"  # technologie à 65 % pour un maximum de 60 %


def test_cautious_profile_cannot_hold_crypto(rules):
    request = AnalysisRequest(question="Et si j'ajoutais du Bitcoin ?", persona=Persona.PRUDENT, tickers=["BTC-USD"], portfolio=portfolio(AGG=100))
    assert statuses(rules.checks(request))["Cryptoactifs"] == "fail"


def test_failed_check_forbids_a_consistent_profile_verdict(rules):
    orchestrator, _, _ = build(checker=rules, script={"governance": {"profile_consistency": {"status": "yes", "note": "ok"}}})
    report = orchestrator.run(AnalysisRequest(question="Mon portefeuille respecte-t-il mes critères ?", persona=Persona.BALANCED,
                                              esg_preference="strong", portfolio=portfolio(XOM=50, AGG=50)))
    check = next(e for e in report.evidence if e.kind == "check" and e.reference == "Préférence ESG")
    assert check.check_status == "fail" and "non respecté" in check.claim
    assert report.governance.profile_consistency.status == "no"  # le LLM disait "yes" : la règle l'emporte


def test_question_detection_and_profile_fields_from_the_front(starter):
    body = {"question": "Bitcoin ou Shopify ?", "profile": {"objective": "growth", "comfort": "fluctuations", "esg": "aware",
                                                          "exclusions": "tabac; Energy"}}
    request = to_request(body, lambda q: find_tickers(q, starter))
    assert request.tickers == ["BTC-USD", "SHOP.TO"] and request.persona == Persona.BOLD
    assert request.esg_preference == "aware" and request.exclusions == ["tabac", "Energy"]
    assert find_tickers("c'est quoi un ETF ?", starter) == []
