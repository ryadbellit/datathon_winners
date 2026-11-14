import pytest

from alphaforge.config import Settings
from alphaforge.evaluation.dataset import EvalCase, load_dataset
from alphaforge.evaluation.judge import LLMJudge, parse_verdict
from alphaforge.evaluation.runner import Baseline, check_rules, detect_regression, run_evaluation, to_baseline
from alphaforge.llm.base import LLMProvider, ThrottledError
from alphaforge.llm.mock import MockProvider
from alphaforge.llm.router import ModelRouter
from alphaforge.orchestrator import Orchestrator
from alphaforge.storage import LocalStorage


def router_with(responses: dict[str, str], provider_cls=MockProvider) -> ModelRouter:
    return ModelRouter({"default": ["mock:m"]}, {"mock": lambda: provider_cls(responses)})


CASE = EvalCase(case_id="c1", question="Ton ?", must_include=["négatif"], must_not_include=["garanti"])


# --- Juge ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text,score,valid",
    [
        ('{"score": 5, "rationale": "parfait"}', 5, True),
        ('Voici : {"score": 2, "rationale": "faible"} merci', 2, True),
        ('{"score": 9, "rationale": "hors échelle"}', None, False),
        ("pas du json", None, False),
        ('{"rationale": "pas de score"}', None, False),
    ],
)
def test_parse_verdict(text, score, valid):
    verdict = parse_verdict(text)
    assert (verdict.score, verdict.valid) == (score, valid)


def test_judge_uses_evaluation_task_and_returns_score():
    provider = MockProvider({"evaluation": '{"score": 3, "rationale": "moyen"}'})
    router = ModelRouter({"default": ["mock:m"]}, {"mock": lambda: provider})
    verdict = LLMJudge(router).judge(CASE, "réponse")
    assert verdict.score == 3
    assert provider.calls[0].task == "evaluation" and "réponse" in provider.calls[0].prompt


def test_judge_failure_is_contained():
    class Down(LLMProvider):
        name = "down"

        def complete(self, request, model_id):
            raise ThrottledError("x")

    router = ModelRouter({"default": ["down:m"]}, {"down": Down})
    verdict = LLMJudge(router).judge(CASE, "réponse")
    assert verdict.score is None and not verdict.valid


# --- Règles -------------------------------------------------------------------------------------------
def test_rules_pass_and_fail():
    assert check_rules(CASE, "Le ton est négatif.", []) == []
    failures = check_rules(CASE, "Rendement garanti, très positif", [])
    assert any("négatif" in f for f in failures) and any("garanti" in f for f in failures)
    assert check_rules(CASE, "", []) and check_rules(CASE, "négatif", ["sentiment"])


def test_forbidden_promises_apply_to_every_case():
    case = EvalCase(case_id="x", question="q")
    assert check_rules(case, "Ce placement est sans aucun risque", [])


# --- Évaluation de bout en bout (mock) ----------------------------------------------------------------
def test_run_evaluation_aggregates_scores_rules_usage_cost():
    cases = [CASE, EvalCase(case_id="c2", question="Autre", must_include=["introuvable"])]
    router = router_with({"orchestration": "Ton négatif.", "evaluation": '{"score": 4, "rationale": "ok"}'})
    report = run_evaluation(Orchestrator(router), LLMJudge(router), cases, "demo")
    assert report.n_cases == 2
    assert report.rule_pass_rate == 0.5  # c1 passe, c2 manque « introuvable »
    assert report.mean_judge_score == 4.0 and report.judge_failures == 0
    assert report.usage.total_tokens > 0 and report.estimated_cost_usd == 0.0


def test_golden_dataset_loads_and_pipeline_runs_on_every_case():
    cases = load_dataset(LocalStorage("data"), "golden_v1")
    assert len(cases) >= 4 and len({c.case_id for c in cases}) == len(cases)
    router = ModelRouter.from_settings(Settings(_env_file=None))  # mock par défaut
    report = run_evaluation(Orchestrator(router), LLMJudge(router), cases, "golden_v1")
    assert report.n_cases == len(cases) and report.judge_failures == 0
    assert all(c.degraded_agents == [] for c in report.cases)


# --- Régression ---------------------------------------------------------------------------------------
def make_report(score, rules_ok=True):
    responses = {"orchestration": "Ton négatif." if rules_ok else "Aucune idée.", "evaluation": f'{{"score": {score}, "rationale": "x"}}'}
    router = router_with(responses)
    return run_evaluation(Orchestrator(router), LLMJudge(router), [CASE], "demo")


def test_no_regression_when_equal_or_better():
    baseline = to_baseline(make_report(4))
    assert detect_regression(make_report(4), baseline) == []
    assert detect_regression(make_report(5), baseline) == []


def test_regression_detected_on_judge_score_drop():
    problems = detect_regression(make_report(2), to_baseline(make_report(4)))
    assert len(problems) == 1 and "juge" in problems[0]


def test_regression_detected_on_rule_failures():
    problems = detect_regression(make_report(4, rules_ok=False), to_baseline(make_report(4)))
    assert any("règles" in p for p in problems)


def test_regression_when_judge_stops_producing_valid_scores():
    broken = make_report(4)
    broken.mean_judge_score = None
    assert detect_regression(broken, Baseline(mean_judge_score=4.0, rule_pass_rate=1.0))
