from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "FICrime Balance Migration & Reconciliation Platform"
    database_url: str = "sqlite:///./fincrime_recon.db"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 480
    cors_origins: str = "http://localhost:3000"
    seed_demo_data: bool = True

    # AI providers (optional). Without keys the assistant uses the built-in deterministic engine.
    azure_openai_endpoint: str | None = None
    azure_openai_api_key: str | None = None
    azure_openai_deployment: str | None = None
    azure_openai_api_version: str = "2024-06-01"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-3-5-sonnet-latest"

    # Reconciliation tolerances
    numeric_tolerance: float = 0.0
    critical_variance_amount: float = 10000.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
