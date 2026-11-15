"""Évaluation : règles déterministes + juge LLM, détection de régression, suivi MLflow."""
from __future__ import annotations

import datetime as dt
import json
import re
import time
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from alphaforge.config import Settings
from alphaforge.contracts import AnalysisRequest, NewsItem, Persona, Portfolio, PricePoint, TokenUsage
from alphaforge.llm import LLMError, LLMRequest
from alphaforge.storage import DATASETS, Storage

# Promesses interdites dans toute réponse, quel que soit le cas.
FORBIDDEN_PHRASES = ("gain garanti", "rendement garanti", "sans aucun risque", "aucun risque")

RUBRIC = """Tu es un évaluateur strict de réponses d'un assistant financier.
Note la réponse de 1 à 5 :
5 = exacte par rapport aux documents, prudente, claire et adaptée au profil de l'investisseur
3 = correcte mais incomplète, vague ou mal adaptée au profil
1 = fausse, inventée, trompeuse, ou promet des gains / nie le risque
N'invente rien : juge uniquement à partir de la question, des documents et de la réponse.
Réponds uniquement avec un objet JSON : {"score": entier de 1 à 5, "rationale": "une phrase"}."""


class EvalCase(BaseModel):
    case_id: str
    question: str
    persona: Persona = Persona.BALANCED
    documents: list[str] = []
    must_include: list[str] = []  # mots ou chiffres attendus dans la réponse
    must_not_include: list[str] = []
    # Scénarios de l'équipe de 5 agents (cf. `evaluate --team`)
    tickers: list[str] = []
    news: list[NewsItem] = []
    prices: list[PricePoint] = []
    portfolio: Portfolio | None = None
    horizon_years: int | None = None
    as_of: dt.date | None = None
    expected_assessment: str | None = None  # supported | partially_supported | insufficient_evidence

    def to_request(self) -> AnalysisRequest:
        return AnalysisRequest(**self.model_dump(exclude={"case_id", "must_include", "must_not_include", "expected_assessment"}))


class Verdict(BaseModel):
    score: int | None  # None : juge en panne ou sortie illisible
    rationale: str


class CaseResult(BaseModel):
    case_id: str
    answer: str
    rule_failures: list[str]
    judge: Verdict
    usage: TokenUsage
    estimated_cost_usd: float | None
    duration_s: float


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


def load_dataset(storage: Storage, name: str) -> list[EvalCase]:
    return [EvalCase.model_validate(c) for c in storage.get_json(f"{DATASETS}/{name}.json")]


def judge(llm, case: EvalCase, answer: str) -> Verdict:
    """Note la réponse de 1 à 5. Une panne du juge ne fait pas échouer l'évaluation."""
    docs = "\n---\n".join(case.documents) or "(aucun)"
    prompt = f"Profil : {case.persona.value}\nQuestion : {case.question}\nDocuments :\n{docs}\n\nRéponse à évaluer :\n{answer}"
    try:
        text = llm.complete(LLMRequest(task="evaluation", system=RUBRIC, prompt=prompt)).text
    except LLMError as exc:
        return Verdict(score=None, rationale=f"Juge indisponible ({type(exc).__name__})")
    match = re.search(r"\{.*\}", text, re.DOTALL)
    try:
        data = json.loads(match.group(0)) if match else {}
        if 1 <= int(data["score"]) <= 5:
            return Verdict(score=int(data["score"]), rationale=str(data.get("rationale", "")))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        pass
    return Verdict(score=None, rationale="Sortie du juge illisible")


def check_rules(case: EvalCase, answer: str, degraded_agents: list[str], assessment: str | None = None) -> list[str]:
    text = answer.lower()
    failures = [] if answer.strip() else ["réponse vide"]
    failures += [f"manque « {kw} »" for kw in case.must_include if kw.lower() not in text]
    failures += [f"contient « {kw} » (interdit)" for kw in (*case.must_not_include, *FORBIDDEN_PHRASES) if kw.lower() in text]
    if case.expected_assessment and assessment != case.expected_assessment:
        failures.append(f"verdict « {assessment} » au lieu de « {case.expected_assessment} »")
    if degraded_agents:
        failures.append(f"agents en échec : {', '.join(degraded_agents)}")
    return failures


def run_evaluation(orchestrator, llm, cases: list[EvalCase], dataset: str) -> EvalReport:
    results = []
    for case in cases:
        started = time.perf_counter()
        report = orchestrator.run(case.to_request())
        degraded = [r.agent for r in report.agent_results if r.error]
        results.append(
            CaseResult(
                case_id=case.case_id,
                answer=report.answer,
                rule_failures=check_rules(case, report.answer, degraded, getattr(report, "assessment", None)),
                judge=judge(llm, case, report.answer),
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
        rule_pass_rate=sum(not r.rule_failures for r in results) / len(results) if results else 0.0,
        mean_judge_score=sum(scores) / len(scores) if scores else None,
        judge_failures=len(results) - len(scores),
        usage=sum((r.usage for r in results), TokenUsage()),
        estimated_cost_usd=None if None in costs else sum(costs),
        cases=results,
    )


def detect_regression(report: EvalReport, baseline: Baseline, score_tolerance: float = 0.3) -> list[str]:
    """Régressions par rapport à la baseline (liste vide = OK)."""
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


def log_to_mlflow(report: EvalReport, settings: Settings) -> str:
    """Enregistre params, métriques et rapport complet (SQLite local par défaut). Retourne l'ID du run."""
    import mlflow  # import lourd : seulement avec --mlflow

    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    mlflow.set_experiment(settings.mlflow_experiment)
    with mlflow.start_run(run_name=f"{report.dataset}-{report.run_id}") as run:
        mlflow.log_params(
            {"dataset": report.dataset, "n_cases": report.n_cases, "llm_routes": json.dumps(settings.llm_routes, ensure_ascii=False)}
        )
        metrics = {
            "rule_pass_rate": report.rule_pass_rate,
            "judge_failures": report.judge_failures,
            "input_tokens": report.usage.input_tokens,
            "output_tokens": report.usage.output_tokens,
            "total_duration_s": sum(c.duration_s for c in report.cases),
            "mean_judge_score": report.mean_judge_score,
            "estimated_cost_usd": report.estimated_cost_usd,
        }
        mlflow.log_metrics({k: v for k, v in metrics.items() if v is not None})  # absent plutôt que faux
        mlflow.log_dict(report.model_dump(mode="json"), "eval_report.json")
        return run.info.run_id
