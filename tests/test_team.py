"""Tests de l'équipe de 5 agents. Fournisseur scripté : aucun appel réseau, aucun coût AWS."""
import datetime as dt
import json

import pytest

from alphaforge.contracts import AnalysisRequest, Holding, NewsItem, Persona, Portfolio, PricePoint, TokenUsage
from alphaforge.evaluation import EvalCase, check_rules
from alphaforge.llm import LLMProvider, LLMResponse, ModelRouter, ModelUnavailableError
from alphaforge.retrieval import RetrievalError
from alphaforge.team import TeamOrchestrator
from alphaforge.team.base import Rebuttal, cited, numbers_supported
from alphaforge.team.devil import DevilOutput
from alphaforge.team.events import EventHunter
from alphaforge.team.governance import GovernanceAgent
from alphaforge.team.research import ResearchAgent

PRICES = [PricePoint(ticker="NVDA", date=dt.date(2025, 1, 24), close=140.0), PricePoint(ticker="NVDA", date=dt.date(2025, 1, 27), close=118.42)]
NEWS = [
    NewsItem(title="Un modèle d'IA chinois à faible coût fait trembler le secteur", source="Reuters", date=dt.date(2025, 1, 27), text="Annonce d'un modèle open source."),
    NewsItem(title="La demande de puces IA reste forte", source="Bloomberg", date=dt.date(2024, 12, 2)),
    NewsItem(title="Article postérieur à la date d'analyse", source="Futur", date=dt.date(2025, 2, 10)),
]
PORTFOLIO = Portfolio(
    holdings=[
        Holding(ticker="NVDA", name="NVIDIA", weight_pct=20, sector="Semi-conducteurs"),
        Holding(ticker="AMD", name="AMD", weight_pct=10, sector="Semi-conducteurs"),
        Holding(ticker="BND", name="Obligations", weight_pct=70, sector="Obligations"),
    ]
)
REQUEST = AnalysisRequest(
    question="Pourquoi l'action NVIDIA a-t-elle baissé et quel impact sur mon portefeuille ?",
    persona=Persona.PRUDENT, tickers=["NVDA"], news=NEWS, prices=PRICES, portfolio=PORTFOLIO, horizon_years=5, as_of=dt.date(2025, 1, 28),
)
FACT_PRICE = "NVDA a varié de -15.41 % entre le 2025-01-24 et le 2025-01-27"
FACT_NEWS = "Une annonce de modèle d'IA à faible coût a eu lieu le 2025-01-27"

SCRIPT = {
    "research": {
        "claims": {"E2": "Un modèle d'IA à faible coût est annoncé", "E3": "Demande de puces IA forte"},
        "key_facts": [
            {"text": FACT_PRICE, "evidence_ids": ["E1"]},
            {"text": FACT_NEWS, "evidence_ids": ["E2"]},
            {"text": "Le cours a perdu 42 %", "evidence_ids": ["E1"]},  # chiffre non étayé
            {"text": "Fait sans preuve", "evidence_ids": ["E99"]},  # preuve inexistante
        ],
        "confidence": 0.8,
    },
    "event_hunter": {
        "events": [
            {"description": "Annonce d'un modèle d'IA chinois à faible coût", "category": "technological", "signal": "negative", "evidence_ids": ["E2"]},
            {"description": "Rumeur de ralentissement macro", "category": "macro", "evidence_ids": []},
        ],
        "affected_entities": ["NVIDIA", "semi-conducteurs"],
        "mechanisms": [{"text": "Les investisseurs pourraient revoir la demande future de puces", "evidence_ids": ["E2"]}],
        "alternative_explanations": [{"text": "Prises de bénéfices après une forte hausse", "evidence_ids": []}],
        "uncertainties": ["Cause exacte non établie"],
        "confidence": 0.6,
    },
    "portfolio_storyteller": {
        "relevant_financial_concepts": ["volatilité", "concentration"],
        "potential_impacts": [
            {"text": "NVDA pèse 20 % du portefeuille : sa baisse pèse sur l'ensemble", "evidence_ids": ["E1"]},
            {"text": "Le portefeuille perdrait 35 %", "evidence_ids": []},  # chiffre inventé
        ],
        "educational_explanation": "La volatilité mesure l'ampleur des variations ; une baisse d'un jour n'annonce pas une tendance.",
        "confidence": 0.7,
    },
    "devils_advocate": {
        "challenged_claims": [
            {"target": "event_hunter", "claim": "Annonce d'un modèle d'IA chinois", "objection": "La coïncidence de date ne prouve pas la cause", "severity": "high", "evidence_ids": ["E2"]},
            {"target": "agent_inconnu", "claim": "x", "objection": "cible invalide", "severity": "high"},
            {"target": "research", "claim": FACT_PRICE, "objection": "détail mineur", "severity": "low"},
        ],
        "counterarguments": ["La baisse peut refléter des anticipations de croissance dégradées."],
        "alternative_hypotheses": [{"text": "Anticipations de croissance déjà intégrées au prix", "evidence_ids": []}],
        "unsupported_assumptions": ["La baisse serait temporaire"],
        "missing_evidence": ["Volumes d'échange"],
        "risk_scenarios": [{"text": "Si le cycle d'investissement IA ralentit, plusieurs lignes sont touchées", "evidence_ids": []}],
        "evidence_needed": ["Prévisions de la direction"],
        "confidence": 0.6,
    },
    "event_hunter:rebuttal": {"rebuttals": [{"index": 0, "response": "Seule la date coïncide.", "evidence_ids": ["E2", "E77"], "concedes": False}]},
    "governance": {
        "validated_claims": [
            {"text": FACT_PRICE, "kind": "fact", "evidence_ids": ["E1"]},
            {"text": FACT_NEWS, "kind": "fact", "evidence_ids": ["E2"]},
            {"text": "La baisse est due à cette annonce", "kind": "fact", "evidence_ids": ["E2"]},
            {"text": "Affirmation sans preuve", "kind": "interpretation", "evidence_ids": []},
        ],
        "evidence_gaps": ["Volumes d'échange"],
        "profile_consistency": {"status": "partly", "note": "Profil prudent : exposition de 20 % à une valeur."},
        "final_assessment": "supported",
        "confidence": 0.7,
    },
    "synthesis": "\n".join(f"## {t}\nTexte [E1] [E9]." for t in (
        "1. Que s'est-il passé ?", "2. Pourquoi cela a-t-il pu arriver ?", "3. Qu'est-ce que cela signifie pour votre portefeuille ?",
        "4. Le débat", "5. Le verdict", "6. Sources et limites")),
}


class ScriptedProvider(LLMProvider):
    name = "scripted"

    def __init__(self, script):
        self.script, self.calls = script, []

    def complete(self, request, model_id):
        key = f"{request.agent}:rebuttal" if '"rebuttals"' in (request.system or "") else request.agent
        self.calls.append(key)
        reply = self.script.get(key, {})
        if isinstance(reply, Exception):
            raise reply
        text = reply if isinstance(reply, str) else json.dumps(reply)
        return LLMResponse(text=text, provider=self.name, model_id=model_id, usage=TokenUsage(input_tokens=100, output_tokens=50))


def build(script=None, **kwargs):
    provider = ScriptedProvider({**SCRIPT, **(script or {})})
    router = ModelRouter({"default": ["scripted:test-model"]}, {"scripted": lambda: provider}, {"test-model": {"input_per_1m": 1.0, "output_per_1m": 2.0}})
    return TeamOrchestrator(router, **kwargs), provider, router


def run(script=None, request=REQUEST, **kwargs):
    orchestrator, provider, _ = build(script, **kwargs)
    return orchestrator.run(request), provider


# --- Agent 1 : preuves -------------------------------------------------------------------------------------------------
def test_research_evidence_ids_sources_dates_and_lookahead():
    _, provider, router = build()
    output, _ = ResearchAgent(router).run(REQUEST)
    ids = [e.id for e in output.evidence]
    assert ids == ["E1", "E2", "E3"] and len(set(ids)) == 3  # article postérieur à as_of ignoré
    assert all(e.source and e.reference and e.excerpt for e in output.evidence)
    assert output.data_as_of == dt.date(2025, 1, 27) and output.status == "ok"
    assert "-15.41" in output.evidence[0].claim and output.evidence[0].unit == "%"
    assert any("postérieur" in m for m in output.missing_information)
    assert any("Knowledge Base non configurée" in m for m in output.missing_information)


def test_research_drops_unsupported_numbers_and_unknown_evidence():
    _, _, router = build()
    output, _ = ResearchAgent(router).run(REQUEST)
    assert [f.text for f in output.key_facts] == [FACT_PRICE, FACT_NEWS]
    known = {e.id for e in output.evidence}
    assert all(set(f.evidence_ids) <= known for f in output.key_facts)
    assert any("2 fait(s) retiré(s)" in m for m in output.missing_information)


def test_research_without_any_data_makes_no_llm_call():
    _, provider, router = build()
    output, responses = ResearchAgent(router).run(AnalysisRequest(question="Et NVIDIA ?"))
    assert output.status == "no_evidence" and responses == [] and provider.calls == []


def test_research_survives_knowledge_base_failure():
    class BrokenKB:
        def retrieve(self, query):
            raise RetrievalError("AccessDenied")

    _, _, router = build()
    output, _ = ResearchAgent(router, kb=BrokenKB()).run(REQUEST)
    assert output.status == "ok" and "Knowledge Base indisponible." in output.missing_information


# --- Agent 2 : événements ----------------------------------------------------------------------------------------------
def test_events_dates_come_from_evidence_and_unproven_events_are_flagged():
    _, _, router = build()
    research, _ = ResearchAgent(router).run(REQUEST)
    output, _ = EventHunter(router).run(REQUEST.question, research.evidence)
    first, second = output.identified_events
    assert first.verified and first.date == dt.date(2025, 1, 27) and first.category == "technological"
    assert not second.verified and second.date is None
    assert "non vérifié" in output.event_timeline[-1]
    assert all(h.evidence_ids or h.text for h in output.potential_market_mechanisms)
    assert any("causalité" in u for u in output.uncertainties)


def test_events_without_news_says_so_and_skips_llm():
    _, provider, router = build()
    research, _ = ResearchAgent(router).run(REQUEST.model_copy(update={"news": []}))
    calls_before = len(provider.calls)
    output, responses = EventHunter(router).run(REQUEST.question, research.evidence)
    assert output.status == "no_evidence" and responses == [] and len(provider.calls) == calls_before
    assert "Aucune actualité" in output.uncertainties[0]


# --- Agent 3 : portefeuille --------------------------------------------------------------------------------------------
def test_portfolio_exposures_use_given_weights_and_drop_invented_numbers():
    report, _ = run()
    p = report.portfolio
    assert p.personalized and [(e.ticker, e.weight_pct) for e in p.direct_exposure] == [("NVDA", 20)]
    assert [e.ticker for e in p.indirect_exposure] == ["AMD"]
    assert len(p.potential_impacts) == 1 and "35" not in p.potential_impacts[0].text
    assert any("Aucune métrique quantitative" in x for x in p.limitations)  # module quantitatif non branché


def test_missing_portfolio_gives_general_explanation_only():
    report, _ = run(request=REQUEST.model_copy(update={"portfolio": None}))
    p = report.portfolio
    assert not p.personalized and p.potential_impacts == [] and p.direct_exposure == []
    assert any("Portefeuille indisponible" in x for x in p.limitations) and p.educational_explanation
    assert report.assessment != "supported"  # agent partiel : verdict plafonné


# --- Agent 4 : avocat du diable ----------------------------------------------------------------------------------------
def test_devil_challenges_are_structured_and_invalid_targets_dropped():
    report, _ = run()
    devil = report.devil
    assert [c.target for c in devil.challenged_claims] == ["event_hunter", "research"]
    assert [c.target for c in devil.objections_for("event_hunter")] == ["event_hunter"]
    assert devil.objections_for("research") == []  # sévérité low : pas de réponse requise
    assert devil.alternative_hypotheses and devil.unsupported_assumptions and devil.evidence_needed and devil.risk_scenarios


# --- Agent 5 : gouvernance ---------------------------------------------------------------------------------------------
def test_governance_rejects_unsupported_and_downgrades_causal_facts():
    report, _ = run()
    gov = report.governance
    assert [c.text for c in gov.facts] == [FACT_PRICE, FACT_NEWS]
    assert [c.text for c in gov.interpretations] == ["La baisse est due à cette annonce"]  # une cause n'est pas un fait
    assert [c.text for c in gov.rejected_claims] == ["Affirmation sans preuve"]
    assert all(set(c.evidence_ids) <= {e.id for e in report.evidence} for c in gov.validated_claims)


def test_governance_cannot_exceed_what_rules_allow():
    research, _ = ResearchAgent(build()[2]).run(REQUEST)
    data = {"validated_claims": [{"text": "Interprétation", "kind": "interpretation", "evidence_ids": ["E2"]}], "final_assessment": "supported"}
    out = GovernanceAgent._enforce(data, research.evidence, research, DevilOutput(), [], {"research": "ok"})
    assert out.final_assessment == "insufficient_evidence"  # aucun fait validé
    assert any("plafonné" in x for x in out.limitations)
    assert GovernanceAgent._enforce({"final_assessment": "supported"}, research.evidence, research, DevilOutput(), [], {}).final_assessment == "insufficient_evidence"


# --- Workflow complet ----------------------------------------------------------------------------------------------------
def test_full_workflow_two_debate_rounds():
    report, provider = run()
    calls = provider.calls
    assert calls[0] == "research" and sorted(calls[1:3]) == ["event_hunter", "portfolio_storyteller"]  # les deux agents sont indépendants
    assert calls[3:] == ["devils_advocate", "event_hunter:rebuttal", "governance", "synthesis"]  # 7 appels au total
    assert report.debate_rounds == 2 and report.assessment == "supported" and not report.failures
    assert report.rebuttals[0].evidence_ids == ["E2"]  # E77 (inexistante) retirée
    assert [r.agent for r in report.agent_results] == ["research", "event_hunter", "portfolio_storyteller", "devils_advocate", "governance", "event_hunter:rebuttal"]
    assert report.usage.total_tokens == 150 * 7 and report.estimated_cost_usd is not None
    assert report.sources == ["Reuters", "données de prix fournies"]


def test_final_answer_has_six_sections_and_no_unknown_citation():
    report, _ = run()
    for title in ("1. Que s'est-il passé ?", "4. Le débat", "5. Le verdict", "6. Sources et limites"):
        assert f"## {title}" in report.answer
    assert "[E9]" not in report.answer and "[E1]" in report.answer


def test_synthesis_without_sources_section_gets_one_appended():
    report, _ = run({"synthesis": "Réponse libre [E1]."})
    assert "## 6. Sources et limites" in report.answer and "[E1] données de prix fournies" in report.answer


def test_debate_skipped_when_no_serious_objection():
    low = {"challenged_claims": [{"target": "research", "claim": "c", "objection": "détail", "severity": "low"}], "counterarguments": ["x"]}
    report, provider = run({"devils_advocate": low})
    assert report.debate_rounds == 1 and report.rebuttals == []
    assert not any(c.endswith(":rebuttal") for c in provider.calls) and len(provider.calls) == 6


def test_rebuttal_without_evidence_keeps_disagreement_open():
    weak = {"rebuttals": [{"index": 0, "response": "Je maintiens.", "evidence_ids": ["E404"]}]}
    report, _ = run({"event_hunter:rebuttal": weak})
    assert report.rebuttals[0].evidence_ids == [] and report.rebuttals[0].missing_evidence
    assert any("Objection non levée" in d for d in report.governance.unresolved_disagreements)
    assert report.assessment == "partially_supported"  # le LLM disait « supported » : plafonné
    assert any("plafonné" in x for x in report.governance.limitations)


def test_one_agent_failure_is_recorded_not_replaced():
    report, _ = run({"event_hunter": ModelUnavailableError("AccessDenied")})
    assert report.failures == ["event_hunter"] and report.events.status == "failed" and report.events.identified_events == []
    assert report.assessment != "supported" and report.answer
    assert next(r for r in report.agent_results if r.agent == "event_hunter").error == "AllModelsFailedError"  # le routeur a épuisé ses modèles


def test_governance_failure_returns_incomplete_answer_without_fabrication():
    report, provider = run({"governance": ModelUnavailableError("down")})
    assert report.assessment == "insufficient_evidence" and "governance" in report.failures
    assert "Analyse incomplète" in report.answer and "synthesis" not in provider.calls


def test_missing_news_still_reports_price_move_without_causal_claim():
    report, _ = run(request=REQUEST.model_copy(update={"news": []}))
    assert report.events.status == "no_evidence" and report.events.identified_events == []
    assert report.rebuttals == [] and report.assessment != "supported"


def test_insufficient_evidence_stops_early_and_stays_inconclusive():
    report, provider = run(request=AnalysisRequest(question="Pourquoi NVIDIA baisse-t-elle ?", persona=Persona.BALANCED))
    assert provider.calls == []  # aucun appel LLM : rien à analyser
    assert report.assessment == "insufficient_evidence" and report.debate_rounds == 0 and report.evidence == []
    assert "Analyse incomplète" in report.answer and "## 5. Le verdict" in report.answer
    assert report.estimated_cost_usd == 0.0


def test_conflicting_sources_are_preserved_as_uncertainty():
    conflict = {"validated_claims": [{"text": FACT_PRICE, "kind": "fact", "evidence_ids": ["E1"]}],
                "unresolved_disagreements": ["Reuters et Bloomberg divergent sur la cause"], "final_assessment": "supported"}
    report, _ = run({"governance": conflict})
    assert report.assessment == "partially_supported"
    assert "Reuters et Bloomberg divergent sur la cause" in report.governance.unresolved_disagreements


# --- Intégrité financière / utilitaires ------------------------------------------------------------------------------------
def test_numbers_supported_and_cited_helpers():
    assert numbers_supported("hausse de 12,5 % le 2025-01-27", ["12.5 % 2025-01-27"])
    assert not numbers_supported("hausse de 99 %", ["12.5 %"])
    assert cited(["E1", "E1", "E9", 3], {"E1"}) == ["E1"]


def test_no_causal_fact_and_no_unsourced_number_in_validated_claims():
    report, _ = run()
    for claim in report.governance.facts:
        assert "due à" not in claim.text
        evidence = {e.id: e for e in report.evidence}
        assert numbers_supported(claim.text, [f"{evidence[i].claim} {evidence[i].excerpt} {evidence[i].value} {evidence[i].date}" for i in claim.evidence_ids])


def test_evaluation_case_builds_request_and_checks_expected_assessment():
    case = EvalCase(case_id="c", question="Q", tickers=["NVDA"], news=NEWS[:1], portfolio=PORTFOLIO, expected_assessment="insufficient_evidence")
    request = case.to_request()
    assert request.tickers == ["NVDA"] and request.portfolio == PORTFOLIO and request.news == NEWS[:1]
    assert check_rules(case, "réponse", [], "insufficient_evidence") == []
    assert any("verdict" in f for f in check_rules(case, "réponse", [], "supported"))


def test_rebuttal_model_requires_agent_and_objection():
    with pytest.raises(Exception):
        Rebuttal(agent="x")
