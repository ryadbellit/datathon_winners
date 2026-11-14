import pytest
from pydantic import ValidationError

from alphaforge.contracts import AgentResult, AnalysisRequest, Persona, TokenUsage


def test_request_defaults_generate_unique_ids():
    a, b = AnalysisRequest(question="q"), AnalysisRequest(question="q")
    assert a.request_id != b.request_id
    assert a.persona is Persona.BALANCED


def test_request_rejects_empty_question():
    with pytest.raises(ValidationError):
        AnalysisRequest(question="")


def test_confidence_must_be_between_0_and_1():
    with pytest.raises(ValidationError):
        AgentResult(agent="a", summary="s", confidence=1.5)


def test_token_usage_addition():
    total = TokenUsage(input_tokens=1, output_tokens=2) + TokenUsage(input_tokens=3, output_tokens=4)
    assert (total.input_tokens, total.output_tokens, total.total_tokens) == (4, 6, 10)
