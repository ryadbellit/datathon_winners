"""Le client boto3 est simulé avec botocore.Stubber : aucun appel réseau, aucun coût."""
import boto3
import pytest
from botocore.stub import Stubber

from alphaforge.llm.base import LLMRequest, ModelUnavailableError, ProviderError, ThrottledError
from alphaforge.llm.bedrock import BedrockProvider

MODEL = "global.anthropic.claude-sonnet-5-5"
REQ = LLMRequest(task="agent", prompt="bonjour", system="sois bref", max_tokens=100)


@pytest.fixture
def stubbed():
    client = boto3.client(
        "bedrock-runtime", region_name="us-east-1", aws_access_key_id="fake", aws_secret_access_key="fake"
    )
    with Stubber(client) as stubber:
        yield BedrockProvider(region="us-east-1", client=client), stubber


def test_converse_success_maps_text_and_usage(stubbed):
    provider, stubber = stubbed
    stubber.add_response(
        "converse",
        {
            "output": {"message": {"role": "assistant", "content": [{"text": "Salut !"}]}},
            "stopReason": "end_turn",
            "usage": {"inputTokens": 12, "outputTokens": 3, "totalTokens": 15},
            "metrics": {"latencyMs": 50},
        },
        expected_params={
            "modelId": MODEL,
            "messages": [{"role": "user", "content": [{"text": "bonjour"}]}],
            "system": [{"text": "sois bref"}],
            "inferenceConfig": {"maxTokens": 100},
        },
    )
    response = provider.complete(REQ, MODEL)
    assert response.text == "Salut !"
    assert (response.usage.input_tokens, response.usage.output_tokens) == (12, 3)
    assert response.model_id == MODEL and response.provider == "bedrock"
    assert response.stop_reason == "end_turn"


@pytest.mark.parametrize(
    "code,status,expected",
    [
        ("ThrottlingException", 429, ThrottledError),
        ("AccessDeniedException", 403, ModelUnavailableError),
        ("ResourceNotFoundException", 404, ModelUnavailableError),
        ("ExpiredTokenException", 400, ModelUnavailableError),
        ("ValidationException", 400, ProviderError),
    ],
)
def test_client_errors_are_mapped_to_typed_errors(stubbed, code, status, expected):
    provider, stubber = stubbed
    stubber.add_client_error("converse", service_error_code=code, service_message="détail", http_status_code=status)
    with pytest.raises(expected):
        provider.complete(REQ, MODEL)


def test_validation_error_about_model_means_unavailable(stubbed):
    provider, stubber = stubbed
    stubber.add_client_error(
        "converse", service_error_code="ValidationException", service_message="The provided model identifier is invalid."
    )
    with pytest.raises(ModelUnavailableError):
        provider.complete(REQ, "modele.inexistant")
