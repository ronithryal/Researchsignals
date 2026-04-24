from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/defi_signal"

    # agentmail
    agentmail_api_key: str = ""

    # data providers
    apify_api_token: str = ""
    x_api_bearer_token: str = ""
    data_provider: str = "apify"  # "apify" or "xapi"

    # anthropic
    anthropic_api_key: str = ""

    # analytics (optional)
    dune_api_key: str = ""

    # app
    internal_api_token: str = ""
    ingestion_interval_seconds: int = 1800
    stale_data_threshold_minutes: int = 120
    ingestion_http_retries: int = 2
    ingestion_retry_backoff_seconds: float = 1.0
    enable_provider_fallback: bool = True
    copilot_model: str = "claude-sonnet-4-6"
    coverage_cache_ttl_seconds: int = 21600


settings = Settings()
