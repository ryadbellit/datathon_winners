"""Agents spécialisés (squelettes). Aucun calcul financier ici : seulement des appels au LLM."""
from __future__ import annotations

from alphaforge.agents.base import Agent
from alphaforge.contracts import AnalysisRequest


def _documents_block(request: AnalysisRequest) -> str:
    return "\n---\n".join(request.documents) if request.documents else "(aucun document fourni)"


class DocumentAnalystAgent(Agent):
    name = "document_analyst"
    role = "Tu résumes des documents financiers et en extrais les chiffres clés, sans rien inventer."

    def build_prompt(self, request: AnalysisRequest) -> str:
        return f"Question : {request.question}\nDocuments :\n{_documents_block(request)}"


class SentimentAgent(Agent):
    name = "sentiment"
    role = "Tu évalues le ton (positif, neutre, négatif) de nouvelles financières."

    def build_prompt(self, request: AnalysisRequest) -> str:
        return f"Question : {request.question}\nTextes :\n{_documents_block(request)}"


class RiskExplainerAgent(Agent):
    name = "risk_explainer"
    role = "Tu expliques un risque en langage simple, adapté au profil de l'investisseur."

    def build_prompt(self, request: AnalysisRequest) -> str:
        return (
            f"Profil de l'investisseur : {request.persona.value}\n"
            f"Question : {request.question}\nContexte :\n{_documents_block(request)}"
        )
