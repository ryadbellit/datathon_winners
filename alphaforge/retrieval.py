"""Recherche dans une Knowledge Base Amazon Bedrock (RAG)."""
from __future__ import annotations

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from pydantic import BaseModel

from alphaforge.config import Settings


class RetrievalError(Exception):
    """Recherche impossible (droits, base introuvable, réseau) : les agents répondent sans documents."""


class Passage(BaseModel):
    text: str
    source: str  # nom du fichier d'origine, pour citer


class KnowledgeBase:
    def __init__(self, settings: Settings):
        self._id = settings.knowledge_base_id
        self._mode = "managed"  # KB managée ; bascule automatiquement sur "vector" (KB classique) si refusé
        self._client = boto3.Session(profile_name=settings.aws_profile, region_name=settings.aws_region).client(
            "bedrock-agent-runtime",
            config=Config(
                connect_timeout=min(10.0, settings.bedrock_timeout_seconds),
                read_timeout=settings.bedrock_timeout_seconds,
                retries={"max_attempts": settings.bedrock_max_retries, "mode": "adaptive"},
            ),
        )

    def retrieve(self, query: str, k: int = 5) -> list[Passage]:
        for mode in (self._mode, "vector" if self._mode == "managed" else "managed"):
            key = "managedSearchConfiguration" if mode == "managed" else "vectorSearchConfiguration"
            try:
                raw = self._client.retrieve(
                    knowledgeBaseId=self._id,
                    retrievalQuery={"text": query},
                    retrievalConfiguration={key: {"numberOfResults": k}},
                )
            except ClientError as exc:
                error = exc.response.get("Error", {})
                if error.get("Code") == "ValidationException" and "SearchConfiguration" in error.get("Message", ""):
                    continue  # mauvais type de configuration pour cette base : on essaie l'autre
                raise RetrievalError(f"{error.get('Code')}: {error.get('Message')}") from exc
            except BotoCoreError as exc:
                raise RetrievalError(f"Erreur botocore : {exc}") from exc
            self._mode = mode  # mémorise la configuration acceptée
            return [
                Passage(
                    text=r["content"]["text"],
                    source=(r.get("location", {}).get("s3Location", {}).get("uri") or "inconnu").rsplit("/", 1)[-1],
                )
                for r in raw.get("retrievalResults", [])
                if r.get("content", {}).get("text")
            ]
        raise RetrievalError("Aucune configuration de recherche acceptée par cette Knowledge Base")
