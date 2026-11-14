"""Orchestrateur LangGraph : agents en parallèle, puis synthèse."""
from __future__ import annotations

import logging
import time

from langgraph.graph import END, START, StateGraph

from alphaforge.agents import DEFAULT_AGENTS, Agent
from alphaforge.contracts import AgentResult, AnalysisRequest, FinalReport, TokenUsage
from alphaforge.llm.base import LLMClient, LLMError, LLMRequest
from alphaforge.observability.logging import bind_request_id
from alphaforge.state import GraphState

logger = logging.getLogger("alphaforge.orchestrator")


def _sum_costs(costs: list[float | None]) -> float | None:
    """Somme des coûts, ou None si l'un d'eux est inconnu (on ne sous-estime pas silencieusement)."""
    return None if any(c is None for c in costs) else sum(costs)  # type: ignore[arg-type]


class Orchestrator:
    def __init__(self, llm: LLMClient, agents: list[Agent] | None = None):
        self._llm = llm
        self._agents = agents if agents is not None else [cls(llm) for cls in DEFAULT_AGENTS]
        self._graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(GraphState)
        for agent in self._agents:
            graph.add_node(agent.name, self._agent_node(agent))
            graph.add_edge(START, agent.name)  # exécution en parallèle
        graph.add_node("synthesize", self._synthesize)
        graph.add_edge([a.name for a in self._agents], "synthesize")  # attend tous les agents
        graph.add_edge("synthesize", END)
        return graph.compile()

    @staticmethod
    def _agent_node(agent: Agent):
        def node(state: GraphState) -> dict:
            started = time.perf_counter()
            try:
                result = agent.run(state["request"])
            except LLMError as exc:
                # Un agent en panne ne doit pas faire échouer toute la requête : résultat dégradé, erreur journalisée.
                logger.error(
                    "agent_error",
                    extra={"event": "agent_error", "agent": agent.name, "error_type": type(exc).__name__},
                )
                result = AgentResult(
                    agent=agent.name,
                    summary=f"Agent indisponible ({type(exc).__name__}).",
                    confidence=0.0,
                    error=type(exc).__name__,
                    estimated_cost_usd=0.0,
                )
            else:
                logger.info(
                    "agent_run",
                    extra={
                        "event": "agent_run",
                        "agent": agent.name,
                        "model_id": result.model_id,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                        "input_tokens": result.usage.input_tokens,
                        "output_tokens": result.usage.output_tokens,
                    },
                )
            return {"agent_results": [result]}

        return node

    def _synthesize(self, state: GraphState) -> dict:
        request = state["request"]
        results = sorted(state["agent_results"], key=lambda r: r.agent)  # ordre stable malgré le parallélisme
        findings = "\n".join(f"- [{r.agent}] {r.summary}" for r in results)
        response = self._llm.complete(
            LLMRequest(
                task="orchestration",
                system="Tu synthétises le travail d'agents spécialisés en une réponse claire et prudente.",
                prompt=(
                    f"Profil : {request.persona.value}\nQuestion : {request.question}\n"
                    f"Résultats des agents :\n{findings}"
                ),
            )
        )
        usage = sum((r.usage for r in results), TokenUsage()) + response.usage
        cost = _sum_costs([r.estimated_cost_usd for r in results] + [response.estimated_cost_usd])
        return {
            "report": FinalReport(
                request_id=request.request_id,
                persona=request.persona,
                answer=response.text,
                agent_results=results,
                usage=usage,
                estimated_cost_usd=cost,
            )
        }

    def run(self, request: AnalysisRequest) -> FinalReport:
        with bind_request_id(request.request_id):
            started = time.perf_counter()
            logger.info("request_start", extra={"event": "request_start", "persona": request.persona.value})
            final_state = self._graph.invoke({"request": request, "agent_results": []})
            report = final_state["report"]
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
