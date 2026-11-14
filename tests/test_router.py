import pytest

from alphaforge.config import Settings
from alphaforge.contracts import TokenUsage
from alphaforge.llm.base import (
    LLMProvider,
    LLMRequest,
    LLMResponse,
    ModelUnavailableError,
    ProviderError,
    ThrottledError,
)
from alphaforge.llm.mock import MockProvider
from alphaforge.llm.pricing import PricingTable
from alphaforge.llm.router import AllModelsFailedError, ModelRouter, NoRouteError, parse_route


class FakeProvider(LLMProvider):
    """Provider de test : échoue avec `error` s'il est fourni, sinon répond avec 1M tokens d'entrée."""

    def __init__(self, name="fake", error: Exception | None = None):
        self.name, self.error, self.calls = name, error, []

    def complete(self, request, model_id):
        self.calls.append(model_id)
        if self.error:
            raise self.error
        return LLMResponse(
            text="ok", provider=self.name, model_id=model_id, usage=TokenUsage(input_tokens=1_000_000, output_tokens=0)
        )


REQ = LLMRequest(task="agent", prompt="bonjour")


def make_router(routes, **factories):
    return ModelRouter(routes, {k: (lambda p=p: p) for k, p in factories.items()}, pricing=PricingTable({"m1": {"input_per_1m": 2.0, "output_per_1m": 10.0}}))


def test_parse_route_keeps_colons_inside_model_id():
    assert parse_route("bedrock:anthropic.claude-x-v1:0") == ("bedrock", "anthropic.claude-x-v1:0")
    with pytest.raises(ValueError):
        parse_route("sans-fournisseur")


def test_routes_by_task_with_default_fallback_route():
    a, b = FakeProvider("a"), FakeProvider("b")
    router = make_router({"agent": ["a:m1"], "default": ["b:m2"]}, a=a, b=b)
    router.complete(REQ)
    router.complete(LLMRequest(task="autre", prompt="x"))
    assert a.calls == ["m1"] and b.calls == ["m2"]


def test_no_route_raises():
    with pytest.raises(NoRouteError):
        make_router({"agent": ["a:m1"]}, a=FakeProvider()).complete(LLMRequest(task="inconnue", prompt="x"))


@pytest.mark.parametrize("error", [ModelUnavailableError("non activé"), ThrottledError("trop vite")])
def test_falls_back_to_next_model_on_recoverable_errors(error):
    failing, healthy = FakeProvider("bad", error=error), FakeProvider("good")
    router = make_router({"agent": ["bad:m1", "good:m2"]}, bad=failing, good=healthy)
    response = router.complete(REQ)
    assert response.model_id == "m2" and failing.calls == ["m1"]


def test_non_recoverable_error_does_not_fall_back():
    failing, healthy = FakeProvider("bad", error=ProviderError("requête invalide")), FakeProvider("good")
    router = make_router({"agent": ["bad:m1", "good:m2"]}, bad=failing, good=healthy)
    with pytest.raises(ProviderError):
        router.complete(REQ)
    assert healthy.calls == []


def test_all_models_failing_reports_every_attempt():
    router = make_router(
        {"agent": ["a:m1", "b:m2"]},
        a=FakeProvider("a", error=ThrottledError("x")),
        b=FakeProvider("b", error=ModelUnavailableError("y")),
    )
    with pytest.raises(AllModelsFailedError) as info:
        router.complete(REQ)
    assert len(info.value.attempts) == 2


def test_cost_estimation_known_unknown_and_mock():
    router = make_router({"known": ["f:m1"], "unknown": ["f:m-sans-prix"], "local": ["mock:x"]}, f=FakeProvider("f"), mock=MockProvider())
    assert router.complete(LLMRequest(task="known", prompt="x")).estimated_cost_usd == pytest.approx(2.0)
    assert router.complete(LLMRequest(task="unknown", prompt="x")).estimated_cost_usd is None
    assert router.complete(LLMRequest(task="local", prompt="x")).estimated_cost_usd == 0.0


def test_pricing_resolves_inference_profile_prefix():
    table = PricingTable({"anthropic.claude-x": {"input_per_1m": 1.0, "output_per_1m": 5.0}})
    assert table.cost("global.anthropic.claude-x", TokenUsage(input_tokens=1_000_000)) == pytest.approx(1.0)


def test_providers_are_created_lazily():
    created = []
    router = ModelRouter({"default": ["mock:x"]}, {"mock": lambda: created.append(1) or MockProvider(), "bedrock": lambda: 1 / 0})
    router.complete(REQ)
    assert created == [1]  # bedrock (qui échouerait à la création) n'est jamais instancié


def test_observers_are_notified():
    seen = []
    router = ModelRouter({"default": ["mock:x"]}, {"mock": MockProvider}, observers=[lambda req, resp: seen.append(resp.model_id)])
    router.complete(REQ)
    assert seen == ["x"]


def test_default_settings_work_locally_without_aws():
    router = ModelRouter.from_settings(Settings(_env_file=None))
    assert router.complete(REQ).provider == "mock"


def test_settings_parse_routes_from_env(monkeypatch):
    monkeypatch.setenv("LLM_ROUTES", '{"agent": ["bedrock:global.x", "mock:m"], "evaluation": ["bedrock:global.y"]}')
    settings = Settings(_env_file=None)
    assert settings.llm_routes["agent"] == ["bedrock:global.x", "mock:m"]


def test_env_example_is_valid_and_defaults_to_local_mock():
    settings = Settings(_env_file=".env.example")
    assert settings.llm_routes == {"default": ["mock:mock-model"]}
    assert settings.storage_backend == "local" and settings.log_prompts is False


def test_router_applies_per_task_max_tokens_and_respects_explicit_value():
    provider = MockProvider()
    router = ModelRouter({"default": ["mock:m"]}, {"mock": lambda: provider}, max_tokens={"default": 100, "orchestration": 900})
    router.complete(LLMRequest(task="orchestration", prompt="x"))
    router.complete(LLMRequest(task="agent", prompt="x"))
    router.complete(LLMRequest(task="agent", prompt="x", max_tokens=7))
    assert [c.max_tokens for c in provider.calls] == [900, 100, 7]


def test_truncated_response_is_logged_as_warning(caplog):
    class Cut(FakeProvider):
        def complete(self, request, model_id):
            response = super().complete(request, model_id)
            response.stop_reason = "max_tokens"
            return response

    router = make_router({"agent": ["f:m1"]}, f=Cut("f"))
    with caplog.at_level("WARNING", logger="alphaforge.router"):
        router.complete(REQ)
    assert any(getattr(r, "event", None) == "truncated" for r in caplog.records)
