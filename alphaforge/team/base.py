"""Briques communes aux 5 agents : preuves, sortie typée, appel LLM en JSON, citations vérifiables."""
from __future__ import annotations

import datetime as dt
import json
import re
from typing import Iterable, Literal

from pydantic import BaseModel, field_validator

from alphaforge.contracts import AgentResult, TokenUsage
from alphaforge.llm import LLMError, LLMRequest, LLMResponse

PROMPT_VERSION = "team-v1"
Status = Literal["ok", "partial", "no_evidence", "skipped", "failed"]

RULES = (
    "Règles : réponds uniquement en JSON valide. Tu ne disposes que des éléments fournis : n'invente ni source, ni chiffre, "
    "ni date. Cite uniquement les identifiants de preuves fournis (E1, E2...). Une coïncidence dans le temps ne prouve pas "
    "une cause. Distingue faits vérifiés, interprétations et scénarios hypothétiques. Aucun conseil d'achat ou de vente. "
    "Arguments concis : pas de raisonnement interne."
)


class InvalidOutputError(LLMError):
    """Le modèle n'a pas renvoyé de JSON exploitable (souvent : réponse tronquée)."""


class Evidence(BaseModel):
    """Preuve : créée par le code à partir de données réelles (jamais par le LLM). Le LLM ne fait que la citer."""

    id: str
    kind: Literal["news", "price", "document", "knowledge_base"]
    claim: str  # observation résumée (par le LLM ; calculée par le code pour les prix)
    source: str
    reference: str  # URL, fichier S3, ticker...
    date: dt.date | None = None
    excerpt: str
    value: float | None = None
    unit: str | None = None
    validation: Literal["verified", "undated"]  # verified = source + date présentes et non postérieures à as_of


class Fact(BaseModel):
    text: str
    evidence_ids: list[str] = []


class Hypothesis(BaseModel):
    """Explication ou scénario possible, jamais présenté comme un fait."""

    text: str
    evidence_ids: list[str] = []


class AgentOutput(BaseModel):
    schema_version: str = "1"
    confidence: float = 0.0
    status: Status = "ok"
    error: str | None = None

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp(cls, value):
        try:
            return min(1.0, max(0.0, float(value)))
        except (TypeError, ValueError):
            return 0.3

    def short(self) -> str:
        return self.status


class Challenge(BaseModel):
    target: Literal["research", "event_hunter", "portfolio_storyteller"]
    claim: str
    objection: str
    severity: Literal["high", "medium", "low"] = "medium"
    evidence_ids: list[str] = []


class Rebuttal(BaseModel):
    agent: str
    objection: str
    response: str
    evidence_ids: list[str] = []  # preuves existantes uniquement
    missing_evidence: str | None = None  # à défaut de preuve : ce qui manque, ou aveu de faiblesse
    concedes: bool = False


# --- Utilitaires -----------------------------------------------------------------------------------------------------
_ANY_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_NUMBER = re.compile(r"\d{2,}(?:[.,]\d+)?|\d+[.,]\d+")


def extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    try:
        data = json.loads(match.group(0)) if match else {}
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def dict_items(data: dict, key: str) -> list[dict]:
    value = data.get(key)
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def str_items(data: dict, key: str) -> list[str]:
    value = data.get(key)
    return [str(v).strip() for v in value if str(v).strip()] if isinstance(value, list) else []


def cited(ids, known: Iterable[str]) -> list[str]:
    """Identifiants valides uniquement, sans doublon, dans l'ordre : une citation inconnue est supprimée."""
    known = set(known)
    return list(dict.fromkeys(i for i in ids if isinstance(i, str) and i in known)) if isinstance(ids, list) else []


def evidence_text(e: Evidence) -> str:
    return f"{e.claim} {e.excerpt} {'' if e.value is None else f'{e.value:g}'} {e.date or ''}"


def numbers_supported(text: str, sources: Iterable[str]) -> bool:
    """Chaque chiffre de `text` doit figurer (comme nombre entier) dans les preuves citées : pas de chiffre non étayé."""
    known = {float(n.replace(",", ".")) for n in _ANY_NUMBER.findall(" ".join(sources))}
    return all(float(n.replace(",", ".")) in known for n in _NUMBER.findall(re.sub(r"\bE\d+\b", "", text)))


def brief(e: Evidence, excerpt: bool = False) -> dict:
    """Forme compacte échangée entre agents (JSON court plutôt que de longs prompts)."""
    data = {"id": e.id, "kind": e.kind, "claim": e.claim, "source": e.source, "date": str(e.date or ""), "validation": e.validation}
    return {**data, "excerpt": e.excerpt} if excerpt else data


def to_result(name: str, output: AgentOutput, responses: list[LLMResponse], sources: list[str] | None = None) -> AgentResult:
    costs = [r.estimated_cost_usd for r in responses]
    return AgentResult(
        agent=name,
        summary=output.short(),
        confidence=output.confidence,
        model_id=responses[-1].model_id if responses else None,
        usage=sum((r.usage for r in responses), TokenUsage()),
        estimated_cost_usd=None if None in costs else sum(costs),
        sources=sources or [],
        error=output.error if output.status == "failed" else None,
    )


class TeamAgent:
    """Base d'un agent : `role` (identité), `task` (route du ModelRouter : jamais d'ID de modèle ici) et `ask`."""

    name: str
    role: str
    task = "agent"  # modèle économique ; "arbitration" = modèle fort
    max_tokens: int | None = None
    Output: type[AgentOutput] = AgentOutput

    def __init__(self, llm):
        self._llm = llm

    def failed(self, error: str) -> AgentOutput:
        return self.Output(status="failed", error=error)

    def ask(self, schema: str, payload: dict) -> tuple[dict, LLMResponse]:
        response = self._llm.complete(
            LLMRequest(
                task=self.task,
                agent=self.name,
                max_tokens=self.max_tokens,
                system=f"{self.role}\n{RULES}\nFormat de réponse : {schema}",
                prompt=json.dumps(payload, ensure_ascii=False),
            )
        )
        data = extract_json(response.text)
        if not data:
            raise InvalidOutputError(f"{self.name} : sortie JSON illisible (stop_reason={response.stop_reason})")
        return data, response

    def respond(self, view: dict, objections: list[Challenge], evidence: list[Evidence]) -> tuple[list[Rebuttal], LLMResponse]:
        """Tour 2 du débat : répond aux objections avec des preuves EXISTANTES, ou reconnaît la faiblesse."""
        schema = (
            '{"rebuttals": [{"index": numéro de l\'objection, "response": str, "evidence_ids": ["E1"], '
            '"missing_evidence": str ou null, "concedes": bool}]}'
        )
        payload = {
            "ton_analyse": view,
            "objections": [{"index": i, "claim": c.claim, "objection": c.objection} for i, c in enumerate(objections)],
            "preuves_disponibles": [brief(e) for e in evidence],
            "consigne": "Réponds à chaque objection. Cite des preuves existantes ; sinon indique ce qui manque ou reconnais la faiblesse. Ne crée aucune preuve.",
        }
        data, response = self.ask(schema, payload)
        known, by_index = {e.id for e in evidence}, {}
        for item in dict_items(data, "rebuttals"):
            if isinstance(item.get("index"), int):
                by_index[item["index"]] = item
        rebuttals = []
        for i, challenge in enumerate(objections):
            item = by_index.get(i, {})
            ids = cited(item.get("evidence_ids"), known)
            missing = str(item["missing_evidence"]).strip() if item.get("missing_evidence") else None
            concedes = bool(item.get("concedes"))
            if not ids and not missing and not concedes:  # une réponse sans preuve doit le dire
                missing = "Aucune preuve existante citée pour répondre à cette objection."
            rebuttals.append(
                Rebuttal(
                    agent=self.name,
                    objection=challenge.objection,
                    response=str(item.get("response", "")).strip() or "(pas de réponse)",
                    evidence_ids=ids,
                    missing_evidence=missing,
                    concedes=concedes,
                )
            )
        return rebuttals, response
