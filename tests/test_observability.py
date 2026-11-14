import json
import logging

from alphaforge.contracts import AnalysisRequest
from alphaforge.llm.base import LLMProvider, ThrottledError
from alphaforge.llm.mock import MockProvider
from alphaforge.llm.pricing import PricingTable
from alphaforge.llm.router import ModelRouter
from alphaforge.observability.logging import JsonFormatter, make_model_call_logger
from alphaforge.observability.usage import UsageTracker
from alphaforge.orchestrator import Orchestrator


class CapturingHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.setFormatter(JsonFormatter())
        self.lines: list[dict] = []

    def emit(self, record):
        self.lines.append(json.loads(self.format(record)))


def capture():
    handler = CapturingHandler()
    logger = logging.getLogger("alphaforge")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger, handler


def test_tracker_aggregates_tokens_and_cost_by_task_and_model():
    tracker = UsageTracker()
    router = ModelRouter({"default": ["mock:m"]}, {"mock": MockProvider}, observers=[tracker])
    Orchestrator(router).run(AnalysisRequest(question="q"))
    summary = tracker.summary()
    assert summary["calls"] == 4
    assert summary["input_tokens"] > 0 and summary["output_tokens"] > 0
    assert summary["estimated_cost_usd"] == 0.0
    assert {r["task"] for r in summary["by_task_model"]} == {"agent", "orchestration"}


def test_tracker_reports_unknown_cost_when_a_model_has_no_price():
    class Paid(MockProvider):
        name = "paid"

    tracker = UsageTracker()
    router = ModelRouter({"default": ["paid:inconnu"]}, {"paid": Paid}, pricing=PricingTable(), observers=[tracker])
    Orchestrator(router).run(AnalysisRequest(question="q"))
    assert tracker.summary()["estimated_cost_usd"] is None
    assert tracker.summary()["unpriced_calls"] == 4


def test_final_report_cost_is_none_when_price_unknown():
    class Paid(MockProvider):
        name = "paid"

    router = ModelRouter({"default": ["paid:inconnu"]}, {"paid": Paid})
    assert Orchestrator(router).run(AnalysisRequest(question="q")).estimated_cost_usd is None


def test_logs_are_json_with_request_id_and_no_prompt_by_default():
    logger, handler = capture()
    try:
        router = ModelRouter({"default": ["mock:m"]}, {"mock": MockProvider}, observers=[make_model_call_logger()])
        request = AnalysisRequest(question="question confidentielle", documents=["document privé"])
        Orchestrator(router).run(request)
    finally:
        logger.removeHandler(handler)

    events = {line.get("event") for line in handler.lines}
    assert {"request_start", "agent_run", "model_call", "request_end"} <= events
    assert all(line["request_id"] == request.request_id for line in handler.lines)  # y compris dans les threads d'agents
    raw = json.dumps(handler.lines)
    assert "question confidentielle" not in raw and "document privé" not in raw
    model_call = next(line for line in handler.lines if line.get("event") == "model_call")
    assert {"latency_ms", "input_tokens", "output_tokens", "estimated_cost_usd", "model_id", "task"} <= model_call.keys()


def test_failing_agent_degrades_instead_of_failing_the_request():
    class FlakyProvider(LLMProvider):
        name = "flaky"

        def __init__(self):
            self._ok = MockProvider()

        def complete(self, request, model_id):
            if request.task == "agent" and "Profil de l'investisseur" in request.prompt:  # l'agent de risque
                raise ThrottledError("trop vite")
            return self._ok.complete(request, model_id)

    logger, handler = capture()
    try:
        router = ModelRouter({"default": ["flaky:m"]}, {"flaky": FlakyProvider})  # pas de 2e modèle : l'agent échoue
        report = Orchestrator(router).run(AnalysisRequest(question="q"))
    finally:
        logger.removeHandler(handler)

    by_agent = {r.agent: r for r in report.agent_results}
    assert by_agent["risk_explainer"].error == "AllModelsFailedError"
    assert by_agent["risk_explainer"].confidence == 0.0
    assert by_agent["document_analyst"].error is None
    assert report.answer
    assert any(line.get("event") == "agent_error" and line["agent"] == "risk_explainer" for line in handler.lines)
