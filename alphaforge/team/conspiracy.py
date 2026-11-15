"""Agent 6 — Conspiracy Theorist : voit un complot derrière chaque mouvement (le gouvernement veut contrôler les marchés).

Il sert de « stress test » : ses théories sont TOUJOURS des hypothèses non prouvées. Il ne peut que réinterpréter les preuves
existantes (pas de source, de chiffre ni de date inventés) et la gouvernance les examine. Il ne plafonne jamais le verdict.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from alphaforge.llm import LLMResponse
from alphaforge.team.base import AgentOutput, Evidence, TeamAgent, brief, cited, dict_items, evidence_text, numbers_supported, str_items

SCHEMA = (
    '{"theories": [{"text": str, "suspected_actor": "gouvernement|banque centrale|régulateur|...", "alleged_motive": str, '
    '"evidence_ids": ["E1"], "would_prove_it": str}], "distrusted_official_explanations": [str], "confidence": nombre entre 0 et 1}'
)


class Theory(BaseModel):
    """Théorie du complot : hypothèse non prouvée par construction (le code fixe `validation`, pas le LLM)."""

    text: str
    suspected_actor: str = ""
    alleged_motive: str = ""
    evidence_ids: list[str] = []  # preuves existantes que l'agent réinterprète (elles ne prouvent pas la théorie)
    would_prove_it: str = ""  # quelle preuve la confirmerait ou l'infirmerait
    validation: Literal["unproven"] = "unproven"


class ConspiracyOutput(AgentOutput):
    theories: list[Theory] = []
    distrusted_official_explanations: list[str] = []
    dropped_theories: int = 0  # théories retirées par le code (chiffre non étayé)

    def short(self) -> str:
        return f"{self.status} : {len(self.theories)} théorie(s) non prouvée(s)"


class ConspiracyTheorist(TeamAgent):
    name = "conspiracy_theorist"
    role = (
        "Tu es l'agent complotiste de l'équipe. Tu es convaincu que rien n'arrive par hasard sur les marchés : derrière chaque "
        "mouvement tu soupçonnes une manœuvre, en particulier du gouvernement, des banques centrales ou des régulateurs qui "
        "chercheraient à contrôler les marchés. Propose des théories du complot à partir des preuves fournies, avec l'acteur "
        "soupçonné et le mobile supposé. Mais tu restes honnête sur les faits : tu ne peux que réinterpréter les preuves "
        "existantes, sans inventer de document, de source, de chiffre ni de date. Ne vise aucune personne nommée. Pour chaque "
        "théorie, indique précisément quelle preuve la confirmerait ou la réfuterait. Tes théories sont des hypothèses, jamais des faits. "
        "Au plus 3 théories, chaque champ en une ou deux phrases."
    )
    Output = ConspiracyOutput

    def run(self, question: str, evidence: list[Evidence]) -> tuple[ConspiracyOutput, list[LLMResponse]]:
        if not evidence:  # rien à réinterpréter : pas d'appel LLM
            return ConspiracyOutput(status="no_evidence"), []
        data, response = self.ask(SCHEMA, {"question": question, "evidence": [brief(e, excerpt=True) for e in evidence]})
        by_id = {e.id: e for e in evidence}
        theories, dropped = [], 0
        for t in dict_items(data, "theories"):
            text = str(t.get("text", "")).strip()
            if not text:
                continue
            ids = cited(t.get("evidence_ids"), by_id)
            if not numbers_supported(text, [evidence_text(by_id[i]) for i in ids]):  # même complotiste : aucun chiffre inventé
                dropped += 1
                continue
            theories.append(
                Theory(
                    text=text,
                    suspected_actor=str(t.get("suspected_actor", "")).strip(),
                    alleged_motive=str(t.get("alleged_motive", "")).strip(),
                    evidence_ids=ids,
                    would_prove_it=str(t.get("would_prove_it", "")).strip(),
                )
            )
        output = ConspiracyOutput(
            confidence=AgentOutput(confidence=data.get("confidence", 0.3)).confidence,
            theories=theories,
            distrusted_official_explanations=str_items(data, "distrusted_official_explanations"),
            dropped_theories=dropped,
        )
        return output, [response]
