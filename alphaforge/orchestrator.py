"""Orchestrateur LangGraph : agents en parallèle, puis synthèse."""
from __future__ import annotations

import logging
import time

from langgraph.graph import END, START, StateGraph

from alphaforge.agents import SPECS, Agent
from alphaforge.contracts import AgentResult, AnalysisRequest, FinalReport, GraphState, TokenUsage
from alphaforge.llm import LLMError, LLMRequest
from alphaforge.observability import bind_request_id
from alphaforge.retrieval import KnowledgeBase

logger = logging.getLogger("alphaforge.orchestrator")


class Orchestrator:
    def __init__(self, llm, kb: KnowledgeBase | None = None):
        self._llm = llm
        agents = [Agent(spec, llm, kb) for spec in SPECS]
        graph = StateGraph(GraphState)
        for agent in agents:
            graph.add_node(agent.name, self._agent_node(agent))
            graph.add_edge(START, agent.name)  # exécution en parallèle
        graph.add_node("synthesize", self._synthesize)
        graph.add_edge([a.name for a in agents], "synthesize")  # attend tous les agents
        graph.add_edge("synthesize", END)
        self._graph = graph.compile()

    @staticmethod
    def _agent_node(agent: Agent):
        def node(state: GraphState) -> dict:
            try:
                result = agent.run(state["request"])
            except LLMError as exc:  # un agent en panne ne fait pas échouer la requête : résultat dégradé
                logger.error("agent_error", extra={"event": "agent_error", "agent": agent.name, "error_type": type(exc).__name__})
                result = AgentResult(
                    agent=agent.name,
                    summary=f"Agent indisponible ({type(exc).__name__}).",
                    confidence=0.0,
                    error=type(exc).__name__,
                    estimated_cost_usd=0.0,
                )
            return {"agent_results": [result]}

        return node

    def _synthesize(self, state: GraphState) -> dict:
        request = state["request"]
        results = sorted(state["agent_results"], key=lambda r: r.agent)  # ordre stable malgré le parallélisme
        findings = "\n".join(
            f"- [{r.agent}] {r.summary}" + (f" (sources : {', '.join(r.sources)})" if r.sources else "") for r in results
        )
        response = self._llm.complete(
            LLMRequest(
                task="orchestration",
                system="Tu synthétises le travail d'agents spécialisés en une réponse claire et prudente.",
                prompt=f"Profil : {request.persona.value}\nQuestion : {request.question}\nRésultats des agents :\n{findings}",
            )
        )
        costs = [r.estimated_cost_usd for r in results] + [response.estimated_cost_usd]
        return {
            "report": FinalReport(
                request_id=request.request_id,
                persona=request.persona,
                answer=response.text,
                sources=sorted({s for r in results for s in r.sources}),
                agent_results=results,
                usage=sum((r.usage for r in results), TokenUsage()) + response.usage,
                estimated_cost_usd=None if None in costs else sum(costs),  # None si un prix est inconnu
            )
        }

    def run(self, request: AnalysisRequest) -> FinalReport:
        with bind_request_id(request.request_id):
            started = time.perf_counter()
            report = self._graph.invoke({"request": request, "agent_results": []})["report"]
            logger.info(
                "request_end",
                extra={
                    "event": "request_end",
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                    "input_tokens": report.usage.input_tokens,
                    "output_tokens": report.usage.output_tokens,
                    "estimated_cost_usd": report.estimated_cost_usd,
                },
            )
            return report
