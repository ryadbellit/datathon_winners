"""Suivi des expériences avec MLflow (SQLite local par défaut : aucun serveur à lancer)."""
from __future__ import annotations

import json
from alphaforge.config import Settings
from alphaforge.evaluation.runner import EvalReport


def log_to_mlflow(report: EvalReport, settings: Settings, tags: dict[str, str] | None = None) -> str:
    """Enregistre params, métriques et rapport complet. Retourne l'ID du run MLflow."""
    import mlflow

    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    mlflow.set_experiment(settings.mlflow_experiment)
    with mlflow.start_run(run_name=f"{report.dataset}-{report.run_id}") as run:
        mlflow.log_params(
            {
                "dataset": report.dataset,
                "n_cases": report.n_cases,
                "llm_routes": json.dumps(settings.llm_routes, ensure_ascii=False),
            }
        )
        metrics = {
            "rule_pass_rate": report.rule_pass_rate,
            "judge_failures": report.judge_failures,
            "input_tokens": report.usage.input_tokens,
            "output_tokens": report.usage.output_tokens,
            "total_duration_s": sum(c.duration_s for c in report.cases),
        }
        if report.mean_judge_score is not None:
            metrics["mean_judge_score"] = report.mean_judge_score
        if report.estimated_cost_usd is not None:  # absent plutôt que faux si un prix est inconnu
            metrics["estimated_cost_usd"] = report.estimated_cost_usd
        mlflow.log_metrics(metrics)
        mlflow.set_tags(tags or {})
        mlflow.log_dict(report.model_dump(mode="json"), "eval_report.json")
        return run.info.run_id
