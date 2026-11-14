"""LLM-as-a-Judge : un modèle (route `evaluation`) note la réponse finale de 1 à 5."""
from __future__ import annotations

import json
import re

from pydantic import BaseModel

from alphaforge.evaluation.dataset import EvalCase
from alphaforge.llm.base import LLMClient, LLMError, LLMRequest

RUBRIC = """Tu es un évaluateur strict de réponses d'un assistant financier.
Note la réponse de 1 à 5 :
5 = exacte par rapport aux documents, prudente, claire et adaptée au profil de l'investisseur
3 = correcte mais incomplète, vague ou mal adaptée au profil
1 = fausse, inventée, trompeuse, ou promet des gains / nie le risque
N'invente rien : juge uniquement à partir de la question, des documents et de la réponse.
Réponds uniquement avec un objet JSON : {"score": entier de 1 à 5, "rationale": "une phrase"}."""


class JudgeVerdict(BaseModel):
    score: int | None  # None si le juge a échoué ou renvoyé une sortie illisible
    rationale: str
    valid: bool


class LLMJudge:
    def __init__(self, llm: LLMClient):
        self._llm = llm

    def judge(self, case: EvalCase, answer: str) -> JudgeVerdict:
        docs = "\n---\n".join(case.documents) or "(aucun)"
        reference = f"\nRéponse de référence : {case.reference}" if case.reference else ""
        prompt = (
            f"Profil : {case.persona.value}\nQuestion : {case.question}\nDocuments :\n{docs}{reference}\n\n"
            f"Réponse à évaluer :\n{answer}"
        )
        try:
            response = self._llm.complete(LLMRequest(task="evaluation", system=RUBRIC, prompt=prompt, max_tokens=300))
        except LLMError as exc:  # une panne du juge ne doit pas faire échouer toute l'évaluation
            return JudgeVerdict(score=None, rationale=f"Juge indisponible ({type(exc).__name__})", valid=False)
        return parse_verdict(response.text)


def parse_verdict(text: str) -> JudgeVerdict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            score = int(data["score"])
            if 1 <= score <= 5:
                return JudgeVerdict(score=score, rationale=str(data.get("rationale", "")), valid=True)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            pass
    return JudgeVerdict(score=None, rationale="Sortie du juge illisible", valid=False)
