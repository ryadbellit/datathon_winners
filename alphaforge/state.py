"""State du graphe LangGraph."""
from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from alphaforge.contracts import AgentResult, AnalysisRequest, FinalReport


class GraphState(TypedDict, total=False):
    request: AnalysisRequest
    # Les agents s'exécutent en parallèle : operator.add fusionne leurs résultats.
    agent_results: Annotated[list[AgentResult], operator.add]
    report: FinalReport
