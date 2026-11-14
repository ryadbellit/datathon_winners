"""Ligne de commande : ask | evaluate | check-routes."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from alphaforge.config import Settings, get_settings
from alphaforge.contracts import AnalysisRequest, Persona
from alphaforge.evaluation.dataset import load_dataset
from alphaforge.evaluation.judge import LLMJudge
from alphaforge.evaluation.runner import Baseline, detect_regression, run_evaluation, to_baseline
from alphaforge.llm.base import LLMError, LLMRequest
from alphaforge.llm.router import ModelRouter
from alphaforge.observability.logging import add_cloudwatch_handler, make_model_call_logger, setup_logging
from alphaforge.observability.usage import UsageTracker
from alphaforge.orchestrator import Orchestrator
from alphaforge.storage import BASELINES, DATASETS, REPORTS, LocalStorage, StorageNotFoundError, get_storage


def _setup_logging(settings: Settings) -> None:
    setup_logging(settings.log_level)
    if settings.cloudwatch_log_group:
        try:
            add_cloudwatch_handler(
                settings.cloudwatch_log_group,
                settings.cloudwatch_log_stream_prefix,
                region=settings.aws_region,
                profile=settings.aws_profile,
                retention_days=settings.cloudwatch_retention_days,
            )
        except Exception as exc:  # l'observabilité ne doit jamais empêcher l'application de tourner
            print(f"CloudWatch indisponible, logs locaux uniquement : {type(exc).__name__}: {exc}", file=sys.stderr)


def _build(settings: Settings):
    _setup_logging(settings)
    tracker = UsageTracker()
    router = ModelRouter.from_settings(
        settings,
        observers=[tracker, make_model_call_logger(settings.log_prompts, emf=settings.cloudwatch_metrics)],
    )
    return router, tracker


def cmd_ask(args, settings: Settings) -> int:
    router, tracker = _build(settings)
    documents = [Path(p).read_text(encoding="utf-8") for p in args.doc]
    request = AnalysisRequest(question=args.question, persona=Persona(args.persona), documents=documents)
    report = Orchestrator(router).run(request)
    print(f"\n=== Réponse ({report.persona.value}) ===\n{report.answer}\n")
    for r in report.agent_results:
        print(f"- {r.agent} [{r.model_id}] confiance={r.confidence:.2f}" + (f" ERREUR={r.error}" if r.error else ""))
    print("\n=== Consommation ===")
    print(json.dumps(tracker.summary(), ensure_ascii=False, indent=2))
    return 0


def cmd_evaluate(args, settings: Settings) -> int:
    router, tracker = _build(settings)
    storage = get_storage(settings)
    cases = load_dataset(storage, args.dataset)
    report = run_evaluation(Orchestrator(router), LLMJudge(router), cases, args.dataset)
    storage.put_json(f"{REPORTS}/{report.run_id}.json", report.model_dump(mode="json"))

    print(f"Run {report.run_id} : {report.n_cases} cas | règles OK {report.rule_pass_rate:.0%} | "
          f"note juge {report.mean_judge_score} | échecs juge {report.judge_failures} | "
          f"tokens {report.usage.total_tokens} | coût {report.estimated_cost_usd}")
    for c in report.cases:
        status = "OK " if c.passed_rules else "KO "
        print(f"  {status}{c.case_id:<24} juge={c.judge.score} {'; '.join(c.rule_failures)}")

    if args.mlflow:
        from alphaforge.evaluation.tracking import log_to_mlflow

        print(f"MLflow run : {log_to_mlflow(report, settings)} (voir : mlflow ui --backend-store-uri {settings.mlflow_tracking_uri})")

    baseline_key = f"{BASELINES}/{args.dataset}.json"
    if args.save_baseline:
        storage.put_json(baseline_key, to_baseline(report).model_dump())
        print(f"Baseline enregistrée : {baseline_key}")
    elif args.baseline:
        try:
            problems = detect_regression(report, Baseline.model_validate(storage.get_json(baseline_key)))
        except StorageNotFoundError:
            print(f"Pas de baseline ({baseline_key}) : lancez avec --save-baseline d'abord.", file=sys.stderr)
            return 2
        for p in problems:
            print(f"RÉGRESSION : {p}")
        return 1 if problems else 0
    return 0


def cmd_check_routes(args, settings: Settings) -> int:
    """Vérifie chaque modèle de chaque route avec un appel minuscule (coût négligeable)."""
    setup_logging(settings.log_level)
    failures = 0
    for task, entries in settings.llm_routes.items():
        for entry in entries:
            single = ModelRouter.from_settings(settings.model_copy(update={"llm_routes": {task: [entry]}}))
            try:
                r = single.complete(LLMRequest(task=task, prompt="Réponds par le mot OK.", max_tokens=20))
                print(f"OK    {task:<14} {entry}  ({r.usage.total_tokens} tokens, {r.latency_ms:.0f} ms)")
            except LLMError as exc:
                failures += 1
                print(f"ECHEC {task:<14} {entry}  -> {exc}")
    return 1 if failures else 0


def cmd_upload_datasets(args, settings: Settings) -> int:
    """Copie les datasets locaux (./data/datasets) vers le stockage configuré (ex. S3)."""
    source, target = LocalStorage(args.source), get_storage(settings)
    keys = source.list(f"{DATASETS}/")
    for key in keys:
        target.put_bytes(key, source.get_bytes(key))
        print(f"envoyé : {key}")
    print(f"{len(keys)} fichier(s) envoyé(s) vers le backend '{settings.storage_backend}'")
    return 0 if keys else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="alphaforge")
    sub = parser.add_subparsers(dest="command", required=True)

    ask = sub.add_parser("ask", help="Pose une question à l'orchestrateur")
    ask.add_argument("question")
    ask.add_argument("--persona", choices=[p.value for p in Persona], default=Persona.BALANCED.value)
    ask.add_argument("--doc", action="append", default=[], metavar="FICHIER", help="Fichier texte à analyser (répétable)")
    ask.set_defaults(func=cmd_ask)

    ev = sub.add_parser("evaluate", help="Évalue un dataset (règles + juge LLM)")
    ev.add_argument("--dataset", default="golden_v1")
    ev.add_argument("--mlflow", action="store_true", help="Enregistre le run dans MLflow")
    ev.add_argument("--baseline", action="store_true", help="Compare à la baseline ; code de sortie 1 si régression")
    ev.add_argument("--save-baseline", action="store_true", help="Enregistre ce run comme nouvelle baseline")
    ev.set_defaults(func=cmd_evaluate)

    chk = sub.add_parser("check-routes", help="Teste chaque modèle configuré (appel réel si Bedrock)")
    chk.set_defaults(func=cmd_check_routes)

    up = sub.add_parser("upload-datasets", help="Envoie ./data/datasets vers le stockage configuré (STORAGE_BACKEND)")
    up.add_argument("--source", default="data", help="Dossier local source (défaut : data)")
    up.set_defaults(func=cmd_upload_datasets)

    args = parser.parse_args(argv)
    return args.func(args, get_settings())


if __name__ == "__main__":
    sys.exit(main())
