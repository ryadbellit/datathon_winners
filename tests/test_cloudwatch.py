import json
import logging

import boto3
from moto import mock_aws

from alphaforge.contracts import AnalysisRequest
from alphaforge.llm.mock import MockProvider
from alphaforge.llm.router import ModelRouter
from alphaforge.observability.logging import add_cloudwatch_handler, make_model_call_logger
from alphaforge.orchestrator import Orchestrator


def _events(client, group):
    stream = client.describe_log_streams(logGroupName=group)["logStreams"][0]["logStreamName"]
    messages = [e["message"] for e in client.get_log_events(logGroupName=group, logStreamName=stream)["events"]]
    return [json.loads(m) for m in messages]


@mock_aws
def test_logs_reach_cloudwatch_with_retention_and_emf(monkeypatch):
    for var in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(var, "fake")
    client = boto3.client("logs", region_name="us-east-1")
    logger = logging.getLogger("alphaforge")
    logger.setLevel(logging.INFO)
    handler = add_cloudwatch_handler("/test/alphaforge", region="us-east-1", retention_days=7, client=client, use_queues=False)
    try:
        router = ModelRouter({"default": ["mock:m"]}, {"mock": MockProvider}, observers=[make_model_call_logger(emf=True)])
        request = AnalysisRequest(question="question confidentielle")
        Orchestrator(router).run(request)
        handler.flush()
    finally:
        logger.removeHandler(handler)
        handler.close()

    group = client.describe_log_groups(logGroupNamePrefix="/test/alphaforge")["logGroups"][0]
    assert group["retentionInDays"] == 7
    events = _events(client, "/test/alphaforge")
    assert {"request_start", "agent_run", "model_call", "request_end"} <= {e.get("event") for e in events}
    assert all(e["request_id"] == request.request_id for e in events)
    model_call = next(e for e in events if e.get("event") == "model_call")
    emf = model_call["_aws"]["CloudWatchMetrics"][0]
    assert emf["Namespace"] == "AlphaForge" and {"latency_ms", "input_tokens", "output_tokens"} <= {m["Name"] for m in emf["Metrics"]}
    assert "question confidentielle" not in json.dumps(events)
