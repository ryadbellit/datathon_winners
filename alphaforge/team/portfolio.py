"""Agent 3 — Portfolio Storyteller : explique ce que l'événement signifie pour le portefeuille réel de l'utilisateur."""
from __future__ import annotations

from pydantic import BaseModel

from alphaforge.contracts import AnalysisRequest, Holding
from alphaforge.llm import LLMResponse
from alphaforge.team.base import AgentOutput, Evidence, Hypothesis, TeamAgent, brief, cited, dict_items, numbers_supported, str_items
from alphaforge.team.interfaces import Observation

SCHEMA = (
    '{"relevant_financial_concepts": [str], "potential_impacts": [{"text": str, "evidence_ids": ["E1"]}], '
    '"educational_explanation": str, "limitations": [str], "confidence": nombre entre 0 et 1}'
)


DIRECT, INDIRECT = "ligne de la valeur concernée", "même secteur que la valeur concernée"


class Exposure(BaseModel):
    ticker: str
    name: str = ""
    weight_pct: float
    reason: str


class PortfolioOutput(AgentOutput):
    personalized: bool = False  # faux : pas de portefeuille, analyse générale seulement
    portfolio_context: str = ""
    direct_exposure: list[Exposure] = []
    indirect_exposure: list[Exposure] = []
    relevant_financial_concepts: list[str] = []
    quantitative_observations: list[Observation] = []
    potential_impacts: list[Hypothesis] = []
    educational_explanation: str = ""
    supporting_evidence_ids: list[str] = []
    limitations: list[str] = []

    def short(self) -> str:
        return f"{self.status} : {'personnalisé' if self.personalized else 'général'}, {len(self.direct_exposure)} exposition(s) directe(s)"


class PortfolioStoryteller(TeamAgent):
    name = "portfolio_storyteller"
    role = (
        "Tu es le Portfolio Storyteller : tu expliques à un investisseur non expert ce qu'un événement de marché signifie pour "
        "SON portefeuille et tu expliques les notions financières avec sa situation réelle (volatilité, concentration, "
        "diversification...). N'utilise que les poids et métriques fournis : n'invente ni poids, ni prix, ni impact chiffré, "
        "et ne fais aucun calcul. Pas de prédiction non étayée. Tu as tout le portefeuille (portfolio) : tiens compte des "
        "lignes qui amortissent ou amplifient le choc. Style : mots simples, phrases courtes, aucun jargon sans explication. "
        "potential_impacts : 3 au plus, une phrase chacun. educational_explanation : 2 à 3 phrases, une seule notion clé "
        "illustrée par SON portefeuille. relevant_financial_concepts : 3 au plus. limitations : 2 au plus, les plus utiles. "
        "Les métriques de risque (quantitative_observations, preuves de type metric) sont calculées sur des cours réels : "
        "cite-les par leur identifiant [E..], recopie leurs chiffres tels quels et traduis-les en mots simples "
        "(ex. une ligne qui pèse 40 % du capital mais 64 % du risque ; une perte journalière qui n'arrive qu'un jour sur 20). "
        "Ce sont des mesures du passé (ou une prévision GARCH), pas des promesses. Les contrôles de profil (preuves de type "
        "check) disent si le portefeuille ou l'actif demandé respectent le profil : un contrôle « attention » ou « non respecté » "
        "doit apparaître dans tes impacts, cité, sans être atténué ; n'acquiesce pas à une demande incohérente avec le profil."
    )
    Output = PortfolioOutput

    def run(self, request: AnalysisRequest, evidence: list[Evidence]) -> tuple[PortfolioOutput, list[LLMResponse]]:
        portfolio = request.portfolio
        personalized = bool(portfolio and portfolio.holdings)
        limitations: list[str] = []
        direct: list[Holding] = []
        indirect: list[Holding] = []
        observations: list[Observation] = []
        context = ""
        if personalized:
            tickers = {t.upper() for t in request.tickers}
            direct = [h for h in portfolio.holdings if h.ticker.upper() in tickers]
            sectors = {h.sector for h in direct if h.sector}
            indirect = [h for h in portfolio.holdings if h not in direct and h.sector in sectors]
            if not tickers:
                limitations.append("Aucun ticker précisé : les expositions ne peuvent pas être déterminées.")
            elif not direct:
                limitations.append("Le portefeuille ne contient pas la valeur concernée : pas d'exposition directe.")
            if direct and not sectors:
                limitations.append("Secteur non renseigné : exposition indirecte non évaluable.")
            context = (
                f"{len(portfolio.holdings)} ligne(s) ; poids direct {sum(h.weight_pct for h in direct):g} % ; "
                f"poids des lignes du même secteur {sum(h.weight_pct for h in indirect):g} % (poids fournis par l'utilisateur)."
            )
            # Métriques calculées une seule fois par l'agent Recherche (preuves « metric ») : citables par leur ID.
            observations = [
                Observation(name=e.reference, value=e.value, unit=e.unit, source=e.source, as_of=str(e.date) if e.date else None)
                for e in evidence if e.kind == "metric" and e.value is not None
            ]
            if not observations:
                limitations.append("Aucune métrique quantitative disponible (module quantitatif non branché ou sans résultat).")
        else:
            limitations.append("Portefeuille indisponible : l'analyse personnalisée est impossible ; explication générale seulement.")

        def expo(holdings: list[Holding], reason: str) -> list[Exposure]:
            return [Exposure(ticker=h.ticker, name=h.name, weight_pct=h.weight_pct, reason=reason) for h in holdings]

        payload = {
            **request.profile(),
            "personalized": personalized,
            "portfolio": [h.model_dump(mode="json") for h in portfolio.holdings] if personalized else [],
            "direct_exposure": [e.model_dump() for e in expo(direct, DIRECT)],
            "indirect_exposure": [e.model_dump() for e in expo(indirect, INDIRECT)],
            "quantitative_observations": [brief(e) for e in evidence if e.kind == "metric"],
            "evidence": [brief(e) for e in evidence],
            "limitations_connues": limitations,
        }
        data, response = self.ask(SCHEMA, payload)
        by_id = {e.id: e for e in evidence}
        allowed = [str(payload["portfolio"]), str(payload["quantitative_observations"])]
        impacts = []
        for item in dict_items(data, "potential_impacts") if personalized else []:  # sans portefeuille : aucun impact personnalisé
            text, ids = str(item.get("text", "")).strip(), cited(item.get("evidence_ids"), by_id)
            if text and numbers_supported(text, allowed + [by_id[i].claim + by_id[i].excerpt for i in ids]):
                impacts.append(Hypothesis(text=text, evidence_ids=ids))
        explanation = str(data.get("educational_explanation", "")).strip()
        if not numbers_supported(explanation, allowed + [str(request.horizon_years)] + [e.claim + e.excerpt for e in evidence]):
            explanation = ""  # même règle que les impacts : aucun chiffre calculé ou inventé par le modèle
            limitations.append("Explication pédagogique retirée : elle contenait un chiffre absent des données fournies.")
        output = PortfolioOutput(
            status="ok" if personalized else "partial",
            confidence=AgentOutput(confidence=data.get("confidence", 0.3)).confidence,
            personalized=personalized,
            portfolio_context=context,
            direct_exposure=expo(direct, DIRECT),
            indirect_exposure=expo(indirect, INDIRECT),
            relevant_financial_concepts=str_items(data, "relevant_financial_concepts"),
            quantitative_observations=observations,
            potential_impacts=impacts,
            educational_explanation=explanation,
            supporting_evidence_ids=sorted({i for h in impacts for i in h.evidence_ids}),
            limitations=limitations + str_items(data, "limitations"),
        )
        return output, [response]
