from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "LeadScore AI API"
    environment: str = "development"
    database_url: str = "postgresql://postgres:postgres@localhost:5432/leadscore"
    default_scoring_profile: str = "default_b2b"
    internal_alert_email: str = "sales@example.com"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str | None = None
    llm_enabled: bool = True
    redis_url: str | None = None
    workspace_memory_ttl_seconds: int = 3600

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
