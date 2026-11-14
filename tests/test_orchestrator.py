from alphaforge.agents.base import parse_agent_json
from alphaforge.contracts import AnalysisRequest, Persona
from alphaforge.orchestrator import Orchestrator


def test_orchestrator_runs_all_agents_and_synthesizes(stub_router):
    request = AnalysisRequest(question="Ce FNB est-il risqué ?", persona=Persona.PRUDENT, documents=["texte"])
    report = Orchestrator(stub_router).run(request)

    assert report.request_id == request.request_id
    assert report.persona is Persona.PRUDENT
    assert {r.agent for r in report.agent_results} == {"document_analyst", "sentiment", "risk_explainer"}
    assert report.answer
    # 3 agents + 1 synthèse = 4 appels
    assert len(stub_router.provider.calls) == 4
    assert {c.task for c in stub_router.provider.calls} == {"agent", "orchestration"}


def test_usage_is_aggregated_over_all_calls(stub_router):
    report = Orchestrator(stub_router).run(AnalysisRequest(question="q"))
    assert report.usage.total_tokens > 0
    assert report.usage.input_tokens >= sum(r.usage.input_tokens for r in report.agent_results)


def test_risk_agent_prompt_contains_persona(stub_router):
    Orchestrator(stub_router).run(AnalysisRequest(question="q", persona=Persona.BOLD))
    assert any("audacieux" in c.prompt for c in stub_router.provider.calls)


def test_parse_agent_json_falls_back_on_invalid_output():
    parsed = parse_agent_json("pas du json du tout")
    assert parsed["summary"] == "pas du json du tout"
    assert parsed["confidence"] == 0.3


def test_parse_agent_json_extracts_object_inside_text():
    parsed = parse_agent_json('Voici : {"summary": "ok", "key_points": ["a"], "confidence": 0.9} fin')
    assert parsed["summary"] == "ok" and parsed["confidence"] == 0.9
