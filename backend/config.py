"""Central configuration loaded from environment variables."""
from functools import lru_cache

from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM
    google_api_key: str = ""
    llm_model: str = "gemini-2.5-flash"
    embedding_model: str = "models/text-embedding-004"

    # PostgreSQL
    database_url: str = "postgresql://aegisops:aegisops@localhost:5432/aegisops"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "aegisops_knowledge"
    qdrant_logs_collection: str = "aegisops_logs"

    # App
    app_env: str = "development"
    log_level: str = "INFO"
    secret_key: str = "change-me"

    # Guardrails
    min_auto_action_confidence: float = 0.75

    # Observability
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "aegisops-api"

    model_config = ConfigDict(env_file=".env", case_sensitive=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
