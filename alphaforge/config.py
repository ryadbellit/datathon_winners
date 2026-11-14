"""Configuration par variables d'environnement (jamais de secret ni d'ID de modèle dans le code)."""
from __future__ import annotations

from functools import lru_cache

from dotenv import load_dotenv
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Routage des modèles : {"tâche": ["fournisseur:model_id", ...]}, dans l'ordre de fallback ---
    # Par défaut tout passe par le mock : l'appli fonctionne sans AWS.
    llm_routes: dict[str, list[str]] = {"default": ["mock:mock-model"]}
    # Limite de tokens de sortie par tâche (une limite trop basse tronque les réponses).
    llm_max_tokens: dict[str, int] = {"default": 2048, "orchestration": 4096, "agent": 2048, "evaluation": 600}
    # {"model_id": {"input_per_1m": float, "output_per_1m": float}} en USD. Absent => coût inconnu (None).
    llm_pricing: dict[str, dict[str, float]] = {}

    # --- AWS (chaîne d'identifiants par défaut de boto3 : rôle IAM, profil, variables d'environnement) ---
    aws_region: str = Field(
        default="us-east-1", validation_alias=AliasChoices("AWS_REGION", "AWS_DEFAULT_REGION")
    )
    aws_profile: str | None = None
    bedrock_timeout_seconds: float = 60.0
    bedrock_max_retries: int = 3

    # --- Stockage ---
    storage_backend: str = "local"  # local | s3
    local_storage_dir: str = "./data"
    s3_bucket: str | None = None
    s3_prefix: str = "alphaforge"

    # --- Observabilité ---
    log_level: str = "INFO"
    log_prompts: bool = False  # Ne jamais activer en production : prompts potentiellement privés
    # CloudWatch : vide = désactivé (logs sur stderr uniquement). Sur ECS, laisser vide et utiliser le pilote awslogs.
    cloudwatch_log_group: str | None = None
    cloudwatch_log_stream_prefix: str = "alphaforge"
    cloudwatch_retention_days: int = 14
    cloudwatch_metrics: bool = False  # ajoute le format EMF aux événements model_call (métriques CloudWatch)
    mlflow_tracking_uri: str = "sqlite:///mlflow.db"  # le backend fichiers de MLflow est en mode maintenance
    mlflow_experiment: str = "alphaforge"


@lru_cache
def get_settings() -> Settings:
    # Expose le .env à boto3 (qui lit os.environ). Sans effet sur ECS où il n'y a pas de .env.
    load_dotenv(".env", override=False)
    return Settings()
