"""Ligne de commande : ask | analyze | evaluate | check-routes | upload-datasets."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from alphaforge.config import Settings, get_settings
from alphaforge.contracts import AnalysisRequest, NewsItem, Persona, Portfolio, PricePoint
from alphaforge.evaluation import Baseline, detect_regression, load_dataset, log_to_mlflow, run_evaluation
from alphaforge.llm import LLMError, LLMRequest, ModelRouter
from alphaforge.observability import UsageTracker, model_call_logger, setup_logging
from alphaforge.orchestrator import Orchestrator
from alphaforge.retrieval import KnowledgeBase
from alphaforge.storage import BASELINES, DATASETS, REPORTS, LocalStorage, StorageNotFoundError, get_storage
from alphaforge.team import TeamOrchestrator


def _build(settings: Settings, with_kb: bool = True, team: bool = False):
    setup_logging(settings)
    tracker = UsageTracker()
    router = ModelRouter.from_settings(settings, [tracker, model_call_logger(settings.cloudwatch_metrics)])
    kb = KnowledgeBase(settings) if with_kb and settings.knowledge_base_id else None
    return (TeamOrchestrator(router, kb) if team else Orchestrator(router, kb)), router, tracker


def cmd_ask(args, settings: Settings) -> int:
    orchestrator, _, tracker = _build(settings)
    documents = [Path(p).read_text(encoding="utf-8") for p in args.doc]
    report = orchestrator.run(AnalysisRequest(question=args.question, persona=Persona(args.persona), documents=documents))
    print(f"\n=== Réponse ({report.persona.value}) ===\n{report.answer}\n")
    for r in report.agent_results:
        print(f"- {r.agent} [{r.model_id}] confiance={r.confidence:.2f}" + (f" ERREUR={r.error}" if r.error else ""))
    if report.sources:
        print("\nSources : " + ", ".join(report.sources))
    print("\n=== Consommation ===")
    print(json.dumps(tracker.summary(), ensure_ascii=False, indent=2))
    return 0


def cmd_analyze(args, settings: Settings) -> int:
    """Workflow à 5 agents (preuves, événements, portefeuille, avocat du diable, gouvernance)."""
    orchestrator, _, tracker = _build(settings, team=True)

    def load(path, model):
        return [model.model_validate(x) for x in json.loads(Path(path).read_text(encoding="utf-8"))] if path else []

    request = AnalysisRequest(
        question=args.question,
        persona=Persona(args.persona),
        documents=[Path(p).read_text(encoding="utf-8") for p in args.doc],
        tickers=args.ticker,
        news=load(args.news, NewsItem),
        prices=load(args.prices, PricePoint),
        portfolio=Portfolio.model_validate_json(Path(args.portfolio).read_text(encoding="utf-8")) if args.portfolio else None,
        horizon_years=args.horizon_years,
        as_of=args.as_of,
    )
    report = orchestrator.run(request)
    print(f"\n{report.answer}\n")
    print(f"=== Verdict : {report.assessment} | tours de débat : {report.debate_rounds} | preuves : {len(report.evidence)} ===")
    for r in report.agent_results:
        print(f"- {r.agent:<28} {r.summary}" + (f" ERREUR={r.error}" if r.error else ""))
    print("\n=== Consommation ===")
    print(json.dumps(tracker.summary(), ensure_ascii=False, indent=2))
    return 0


def cmd_evaluate(args, settings: Settings) -> int:
    orchestrator, router, _ = _build(settings, with_kb=args.with_kb, team=args.team)  # sans KB par défaut : baseline reproductible
    storage = get_storage(settings)
    report = run_evaluation(orchestrator, router, load_dataset(storage, args.dataset), args.dataset)
    storage.put_json(f"{REPORTS}/{report.run_id}.json", report.model_dump(mode="json"))

    print(
        f"Run {report.run_id} : {report.n_cases} cas | règles OK {report.rule_pass_rate:.0%} | note juge {report.mean_judge_score} | "
        f"échecs juge {report.judge_failures} | tokens {report.usage.total_tokens} | coût {report.estimated_cost_usd}"
    )
    for c in report.cases:
        print(f"  {'OK ' if not c.rule_failures else 'KO '}{c.case_id:<24} juge={c.judge.score} {'; '.join(c.rule_failures)}")
    if args.mlflow:
        print(f"MLflow run : {log_to_mlflow(report, settings)} (voir : mlflow ui --backend-store-uri {settings.mlflow_tracking_uri})")

    baseline_key = f"{BASELINES}/{args.dataset}.json"
    if args.save_baseline:
        storage.put_json(baseline_key, Baseline(mean_judge_score=report.mean_judge_score, rule_pass_rate=report.rule_pass_rate).model_dump())
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
    """Teste chaque modèle de chaque route avec un appel minuscule (coût négligeable)."""
    setup_logging(settings)
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
    """Copie ./data/datasets vers le stockage configuré (ex. S3)."""
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

    an = sub.add_parser("analyze", help="Analyse à 5 agents avec débat (preuves, événements, portefeuille, gouvernance)")
    an.add_argument("question")
    an.add_argument("--persona", choices=[p.value for p in Persona], default=Persona.BALANCED.value)
    an.add_argument("--ticker", action="append", default=[], help="Valeur concernée, ex. NVDA (répétable)")
    an.add_argument("--doc", action="append", default=[], metavar="FICHIER")
    an.add_argument("--news", metavar="JSON", help="Fichier JSON : liste de NewsItem")
    an.add_argument("--prices", metavar="JSON", help="Fichier JSON : liste de PricePoint")
    an.add_argument("--portfolio", metavar="JSON", help="Fichier JSON : Portfolio")
    an.add_argument("--horizon-years", type=int)
    an.add_argument("--as-of", type=dt.date.fromisoformat, help="Ignore les preuves postérieures (AAAA-MM-JJ)")
    an.set_defaults(func=cmd_analyze)

    ev = sub.add_parser("evaluate", help="Évalue un dataset (règles + juge LLM)")
    ev.add_argument("--dataset", default="golden_v1")
    ev.add_argument("--mlflow", action="store_true", help="Enregistre le run dans MLflow")
    ev.add_argument("--baseline", action="store_true", help="Compare à la baseline ; code de sortie 1 si régression")
    ev.add_argument("--save-baseline", action="store_true", help="Enregistre ce run comme nouvelle baseline")
    ev.add_argument("--team", action="store_true", help="Évalue le workflow à 5 agents (ex. --dataset golden_team_v1)")
    ev.add_argument("--with-kb", action="store_true", help="Utilise aussi la Knowledge Base")
    ev.set_defaults(func=cmd_evaluate)

    sub.add_parser("check-routes", help="Teste chaque modèle configuré").set_defaults(func=cmd_check_routes)

    up = sub.add_parser("upload-datasets", help="Envoie ./data/datasets vers le stockage configuré")
    up.add_argument("--source", default="data", help="Dossier local source (défaut : data)")
    up.set_defaults(func=cmd_upload_datasets)

    args = parser.parse_args(argv)
    return args.func(args, get_settings())


if __name__ == "__main__":
    sys.exit(main())
