from functools import lru_cache
import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "LeadScore AI API"
    environment: str = "development"
    database_url: str = "postgresql://postgres:postgres@localhost:5432/leadscore"
    default_scoring_profile: str = "default_b2b"
    internal_alert_email: str = "sales@leadscore.ai"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str | None = None
    llm_enabled: bool = True
    redis_url: str | None = None
    workspace_memory_ttl_seconds: int = 3600
    langsmith_api_key: str = ""
    langsmith_project: str = "leadscore-ai"
    langsmith_tracing: bool = False

    # Zoho CRM OAuth (optional defaults; UI can override). Use env: ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET, etc.
    zoho_client_id: str = ""
    zoho_client_secret: str = ""
    zoho_accounts_host: str = "accounts.zoho.com"
    zoho_redirect_uri: str = ""

    # monday.com (optional defaults; Connect form overrides when non-empty)
    monday_api_token: str = ""
    monday_board_ids: str = "5093637072"
    monday_graphql_query: str = ""

    # Local / default database connector settings (Connect form overrides when non-empty)
    postgres_source_url: str = ""
    postgres_source_query: str = ""
    supabase_source_url: str = ""
    supabase_source_query: str = ""
    mysql_source_url: str = ""
    mysql_source_query: str = ""
    mongodb_source_url: str = ""
    mongodb_source_database: str = ""
    mongodb_source_collection: str = ""
    mongodb_source_filter: str = "{}"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.langsmith_api_key:
        os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    os.environ["LANGSMITH_TRACING"] = "true" if settings.langsmith_tracing else "false"
    return settings
