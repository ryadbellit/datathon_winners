"""Jeu de cas d'évaluation (golden set), stocké via l'adaptateur Storage (local ou S3)."""
from __future__ import annotations

from pydantic import BaseModel, Field

from alphaforge.contracts import Persona
from alphaforge.storage import DATASETS, Storage


class EvalCase(BaseModel):
    case_id: str
    question: str
    persona: Persona = Persona.BALANCED
    documents: list[str] = Field(default_factory=list)
    must_include: list[str] = Field(default_factory=list, description="Mots/chiffres attendus dans la réponse")
    must_not_include: list[str] = Field(default_factory=list)
    reference: str | None = Field(default=None, description="Réponse de référence facultative pour le juge")


def load_dataset(storage: Storage, name: str) -> list[EvalCase]:
    return [EvalCase.model_validate(c) for c in storage.get_json(f"{DATASETS}/{name}.json")]
