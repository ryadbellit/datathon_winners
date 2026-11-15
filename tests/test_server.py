"""API Flask : traduction front -> AnalysisRequest et réponse du workflow (fournisseur scripté, sans AWS)."""
import json

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
    assert response.json["answer_mode"] == "general_knowledge"  # sans preuve, le LLM répond quand même (non vérifié)
    assert client.post("/api/analyze", json={"question": ""}).status_code == 400


class FakeMarket:
    """Actualités et prix du scénario de test, à la place de Yahoo."""

    def news(self, query, tickers):
        return list(REQUEST.news)

    def prices(self, ticker):
        return [p for p in REQUEST.prices if p.ticker == ticker]


def test_analyze_stream_emits_agent_events_then_report():
    orchestrator, _, _ = build(market=FakeMarket())
    client = create_app(orchestrator).test_client()
    response = client.post("/api/analyze/stream", json={"question": REQUEST.question, "tickers": REQUEST.tickers})
    assert response.status_code == 200 and response.mimetype == "text/event-stream"
    events = [json.loads(line[len("data: "):]) for line in response.get_data(as_text=True).split("\n\n") if line.startswith("data: ")]
    assert events[0] == {"type": "agent_start", "agent": "research"} and events[-1]["type"] == "report"
    ended = {e["agent"]: e["status"] for e in events if e["type"] == "agent_end"}
    assert {"research", "event_hunter", "portfolio_storyteller", "conspiracy_theorist", "devils_advocate", "governance", "synthesis"} <= set(ended)
    starts = [e["agent"] for e in events if e["type"] == "agent_start"]
    assert sorted(starts) == sorted(ended)  # chaque agent démarré se termine
    assert client.post("/api/analyze/stream", json={"question": ""}).status_code == 400


def test_global_hourly_cap_and_frontend_fallback(tmp_path, monkeypatch):
    import server.src.main as main

    (tmp_path / "index.html").write_text("<html>app</html>")
    monkeypatch.setattr(main, "FRONTEND_DIST", tmp_path)
    monkeypatch.setattr(main, "GLOBAL_LIMIT", (1, 3600))
    orchestrator, _, _ = build()
    client = create_app(orchestrator).test_client()
    assert client.get("/scenarios").data == b"<html>app</html>"  # route React -> index.html
    assert client.get("/api/inconnue").status_code == 404
    assert client.post("/api/analyze", json={"question": "Q ?"}).status_code == 200
    assert client.post("/api/analyze", json={"question": "Q ?"}, environ_base={"REMOTE_ADDR": "10.0.0.9"}).status_code == 429  # plafond global
