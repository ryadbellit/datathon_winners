"""Configuration par variables d'environnement (.env) : aucun secret ni ID de modèle dans le code."""
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Routage : {"tâche": ["fournisseur:model_id", ...]}, dans l'ordre de fallback. Défaut : mock (sans AWS).
    llm_routes: dict[str, list[str]] = {"default": ["mock:mock-model"]}
    llm_max_tokens: dict[str, int] = {"default": 2048, "orchestration": 4096, "agent": 2048, "evaluation": 600}
    # {"model_id": {"input_per_1m": x, "output_per_1m": y}} en USD ; absent = coût inconnu (jamais deviné)
    llm_pricing: dict[str, dict[str, float]] = {}

    # AWS : chaîne d'identifiants par défaut de boto3 (rôle IAM, profil, variables d'environnement)
    aws_region: str = Field("us-east-1", validation_alias=AliasChoices("AWS_REGION", "AWS_DEFAULT_REGION"))
    aws_profile: str | None = None
    bedrock_timeout_seconds: float = 60.0
    bedrock_max_retries: int = 3
    guardrail_id: str | None = None
    guardrail_version: str = "DRAFT"
    guardrail_tasks: list[str] = ["orchestration"]  # jamais "evaluation" : le juge doit lire les réponses brutes
    knowledge_base_id: str | None = None

    storage_backend: str = "local"  # local | s3
    local_storage_dir: str = "./data"
    s3_bucket: str | None = None
    s3_prefix: str = "alphaforge"

    log_level: str = "INFO"
    cloudwatch_log_group: str | None = None  # vide = logs sur stderr uniquement (sur ECS : pilote awslogs)
    cloudwatch_retention_days: int = 14
    cloudwatch_metrics: bool = False  # métriques EMF sur chaque appel de modèle
    mlflow_tracking_uri: str = "sqlite:///mlflow.db"
    mlflow_experiment: str = "alphaforge"


@lru_cache
def get_settings() -> Settings:
    load_dotenv(".env", override=False)  # expose aussi le .env à boto3 (qui lit os.environ)
    return Settings()
