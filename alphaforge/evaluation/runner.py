"""Exécution d'une évaluation : règles déterministes + juge LLM, agrégation et détection de régression."""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from alphaforge.contracts import AnalysisRequest, TokenUsage
from alphaforge.evaluation.dataset import EvalCase
from alphaforge.evaluation.judge import JudgeVerdict, LLMJudge
from alphaforge.orchestrator import Orchestrator

# Promesses interdites dans toute réponse, quel que soit le cas.
FORBIDDEN_PHRASES = ("gain garanti", "rendement garanti", "sans aucun risque", "aucun risque")


class CaseResult(BaseModel):
    case_id: str
    answer: str
    rule_failures: list[str]
    judge: JudgeVerdict
    degraded_agents: list[str]
    usage: TokenUsage
    estimated_cost_usd: float | None
    duration_s: float

    @property
    def passed_rules(self) -> bool:
        return not self.rule_failures


class EvalReport(BaseModel):
    run_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    dataset: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    n_cases: int
    rule_pass_rate: float
    mean_judge_score: float | None
    judge_failures: int
    usage: TokenUsage
    estimated_cost_usd: float | None
    cases: list[CaseResult]


class Baseline(BaseModel):
    mean_judge_score: float | None
    rule_pass_rate: float


def check_rules(case: EvalCase, answer: str, degraded_agents: list[str]) -> list[str]:
    text = answer.lower()
    failures = []
    if not answer.strip():
        failures.append("réponse vide")
    failures += [f"manque « {kw} »" for kw in case.must_include if kw.lower() not in text]
    failures += [f"contient « {kw} » (interdit)" for kw in [*case.must_not_include, *FORBIDDEN_PHRASES] if kw.lower() in text]
    if degraded_agents:
        failures.append(f"agents en échec : {', '.join(degraded_agents)}")
    return failures


def run_evaluation(orchestrator: Orchestrator, judge: LLMJudge, cases: list[EvalCase], dataset: str) -> EvalReport:
    results: list[CaseResult] = []
    for case in cases:
        started = time.perf_counter()
        report = orchestrator.run(
            AnalysisRequest(question=case.question, persona=case.persona, documents=case.documents)
        )
        verdict = judge.judge(case, report.answer)
        degraded = [r.agent for r in report.agent_results if r.error]
        results.append(
            CaseResult(
                case_id=case.case_id,
                answer=report.answer,
                rule_failures=check_rules(case, report.answer, degraded),
                judge=verdict,
                degraded_agents=degraded,
                usage=report.usage,
                estimated_cost_usd=report.estimated_cost_usd,
                duration_s=round(time.perf_counter() - started, 3),
            )
        )
    scores = [r.judge.score for r in results if r.judge.score is not None]
    costs = [r.estimated_cost_usd for r in results]
    return EvalReport(
        dataset=dataset,
        n_cases=len(results),
        rule_pass_rate=sum(r.passed_rules for r in results) / len(results) if results else 0.0,
        mean_judge_score=sum(scores) / len(scores) if scores else None,
        judge_failures=sum(not r.judge.valid for r in results),
        usage=sum((r.usage for r in results), TokenUsage()),
        estimated_cost_usd=None if any(c is None for c in costs) else sum(costs),
        cases=results,
    )


def detect_regression(report: EvalReport, baseline: Baseline, score_tolerance: float = 0.3) -> list[str]:
    """Liste des régressions par rapport à la baseline (liste vide = OK)."""
    problems = []
    if report.rule_pass_rate < baseline.rule_pass_rate:
        problems.append(f"taux de règles respectées : {report.rule_pass_rate:.2f} < baseline {baseline.rule_pass_rate:.2f}")
    if baseline.mean_judge_score is not None:
        if report.mean_judge_score is None:
            problems.append("aucune note de juge valide alors que la baseline en avait")
        elif report.mean_judge_score < baseline.mean_judge_score - score_tolerance:
            problems.append(
                f"note moyenne du juge : {report.mean_judge_score:.2f} < baseline {baseline.mean_judge_score:.2f} "
                f"(tolérance {score_tolerance})"
            )
    return problems


def to_baseline(report: EvalReport) -> Baseline:
    return Baseline(mean_judge_score=report.mean_judge_score, rule_pass_rate=report.rule_pass_rate)
