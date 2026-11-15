"""API Flask : traduction front -> AnalysisRequest et réponse du workflow (fournisseur scripté, sans AWS)."""
from test_team import REQUEST, build

from alphaforge.contracts import Persona
from server.src.main import create_app, to_request

BODY = {
    "question": "Pourquoi NVDA baisse-t-elle ?",
    "profile": {"objective": "preservation", "horizon": "long", "comfort": "ups-downs"},
    "holdings": [{"ticker": "NVDA", "name": "NVIDIA", "weight_pct": 20, "sector": "Technology"}, {"ticker": "BND", "weight_pct": 80}],
}


def test_to_request_maps_profile_and_only_named_tickers():
    request = to_request(BODY)
    assert request.persona == Persona.PRUDENT and request.horizon_years == 10
    assert request.tickers == ["NVDA"] and [h.ticker for h in request.portfolio.holdings] == ["NVDA", "BND"]
    assert to_request({**BODY, "question": "Mon portefeuille est-il risqué ?"}).tickers == []  # jamais deviné
    assert to_request({**BODY, "profile": {"objective": "growth", "comfort": "stability"}}).persona == Persona.PRUDENT


def test_analyze_endpoint_returns_report_and_rejects_bad_input():
    orchestrator, _, _ = build()
    client = create_app(orchestrator).test_client()
    assert client.get("/api/health").json == {"status": "ok"}
    response = client.post("/api/analyze", json={**BODY, "question": REQUEST.question})
    assert response.status_code == 200 and response.json["assessment"] == "insufficient_evidence"  # aucune donnée de marché
    assert "## 5. Le verdict" in response.json["answer"]
    assert client.post("/api/analyze", json={"question": ""}).status_code == 400
