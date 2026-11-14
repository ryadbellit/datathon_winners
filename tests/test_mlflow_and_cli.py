import mlflow

from alphaforge import cli
from alphaforge.config import Settings
from alphaforge.evaluation.judge import LLMJudge
from alphaforge.evaluation.runner import run_evaluation
from alphaforge.evaluation.tracking import log_to_mlflow
from alphaforge.evaluation.dataset import load_dataset
from alphaforge.llm.router import ModelRouter
from alphaforge.orchestrator import Orchestrator
from alphaforge.storage import LocalStorage


def test_log_to_mlflow_records_params_metrics_and_report(tmp_path):
    settings = Settings(_env_file=None, mlflow_tracking_uri=f"sqlite:///{(tmp_path / 'mlflow.db').as_posix()}")
    router = ModelRouter.from_settings(settings)
    report = run_evaluation(Orchestrator(router), LLMJudge(router), load_dataset(LocalStorage("data"), "golden_v1"), "golden_v1")

    run_id = log_to_mlflow(report, settings, tags={"git": "test"})

    run = mlflow.get_run(run_id)
    assert run.data.params["dataset"] == "golden_v1"
    assert run.data.metrics["rule_pass_rate"] == report.rule_pass_rate
    assert run.data.metrics["input_tokens"] == report.usage.input_tokens
    assert "estimated_cost_usd" in run.data.metrics  # mock : coût connu (0.0)
    assert run.data.tags["git"] == "test"


def test_mlflow_omits_cost_metric_when_cost_unknown(tmp_path):
    settings = Settings(_env_file=None, mlflow_tracking_uri=f"sqlite:///{(tmp_path / 'mlflow.db').as_posix()}")
    router = ModelRouter.from_settings(settings)
    report = run_evaluation(Orchestrator(router), LLMJudge(router), load_dataset(LocalStorage("data"), "golden_v1")[:1], "golden_v1")
    report.estimated_cost_usd = None
    run = mlflow.get_run(log_to_mlflow(report, settings))
    assert "estimated_cost_usd" not in run.data.metrics


def test_cli_ask_and_evaluate_work_locally_without_aws(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LOCAL_STORAGE_DIR", str(tmp_path))
    LocalStorage(tmp_path).put_json("datasets/mini.json", [{"case_id": "a", "question": "Bonjour ?"}])
    monkeypatch.setattr(cli, "get_settings", lambda: Settings(_env_file=None, local_storage_dir=str(tmp_path)))

    assert cli.main(["ask", "Qu'est-ce qu'une obligation ?", "--persona", "prudent"]) == 0
    assert "Consommation" in capsys.readouterr().out

    assert cli.main(["evaluate", "--dataset", "mini", "--save-baseline"]) == 0
    assert (tmp_path / "baselines" / "mini.json").exists()
    assert cli.main(["evaluate", "--dataset", "mini", "--baseline"]) == 0  # même résultat que la baseline
    assert list((tmp_path / "reports").glob("*.json"))  # rapports sauvegardés via Storage


def test_cli_baseline_check_fails_without_baseline(tmp_path, monkeypatch):
    LocalStorage(tmp_path).put_json("datasets/mini.json", [{"case_id": "a", "question": "Bonjour ?"}])
    monkeypatch.setattr(cli, "get_settings", lambda: Settings(_env_file=None, local_storage_dir=str(tmp_path)))
    assert cli.main(["evaluate", "--dataset", "mini", "--baseline"]) == 2


def test_cli_upload_datasets_copies_to_configured_storage(tmp_path, monkeypatch):
    target = tmp_path / "cible"
    monkeypatch.setattr(cli, "get_settings", lambda: Settings(_env_file=None, local_storage_dir=str(target)))
    assert cli.main(["upload-datasets", "--source", "data"]) == 0
    assert (target / "datasets" / "golden_v1.json").exists()
