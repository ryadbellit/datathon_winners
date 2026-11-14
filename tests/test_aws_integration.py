"""Tests qui appellent RÉELLEMENT AWS (coût minime). Ignorés par défaut : pytest -m aws"""
import pytest

from alphaforge.config import get_settings
from alphaforge.llm.base import LLMRequest
from alphaforge.llm.router import ModelRouter

pytestmark = pytest.mark.aws


def test_every_configured_task_answers_on_real_bedrock():
    settings = get_settings()
    router = ModelRouter.from_settings(settings)
    for task in settings.llm_routes:
        response = router.complete(LLMRequest(task=task, prompt="Réponds par le mot OK.", max_tokens=20))
        assert response.text.strip(), f"réponse vide pour la tâche {task}"
        assert response.usage.total_tokens > 0
        print(f"{task}: {response.provider}:{response.model_id} -> {response.text.strip()[:40]!r}")


def test_golden_regression_against_baseline_on_real_models():
    """Régression réelle : compare au baseline enregistré (python -m alphaforge evaluate --save-baseline)."""
    from alphaforge.evaluation.dataset import load_dataset
    from alphaforge.evaluation.judge import LLMJudge
    from alphaforge.evaluation.runner import Baseline, detect_regression, run_evaluation
    from alphaforge.orchestrator import Orchestrator
    from alphaforge.storage import BASELINES, get_storage

    settings = get_settings()
    storage, router = get_storage(settings), ModelRouter.from_settings(settings)
    report = run_evaluation(Orchestrator(router), LLMJudge(router), load_dataset(storage, "golden_v1"), "golden_v1")
    baseline = Baseline.model_validate(storage.get_json(f"{BASELINES}/golden_v1.json"))
    # Tolérance large : le juge est stochastique et le jeu est petit (4 cas)
    assert detect_regression(report, baseline, score_tolerance=0.75) == []
