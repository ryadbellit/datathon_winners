import pytest

from alphaforge.llm.base import LLMClient, LLMRequest, LLMResponse
from alphaforge.llm.mock import MockProvider


class StubRouter(LLMClient):
    """Routeur minimal pour l'étape 1 : tout part vers le provider mock."""

    def __init__(self):
        self.provider = MockProvider()

    def complete(self, request: LLMRequest) -> LLMResponse:
        return self.provider.complete(request, model_id="mock-model")


@pytest.fixture
def stub_router() -> StubRouter:
    return StubRouter()
