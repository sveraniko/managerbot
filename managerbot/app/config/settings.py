from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MANAGERBOT_", extra="ignore")

    bot_token: str = Field(default="test-token")
    customer_bot_token: str = Field(default="test-customer-token")
    postgres_dsn: str = Field(default="postgresql+asyncpg://postgres:postgres@localhost:5432/postgres")
    redis_dsn: str = Field(default="redis://localhost:6379/0")
    log_level: str = Field(default="INFO")
    queue_page_size: int = Field(default=5)
    notification_poll_seconds: int = Field(default=20)
    notification_dedupe_ttl_seconds: int = Field(default=3600)
    ai_enabled: bool = Field(default=False)
    ai_reader_enabled: bool = Field(default=False)
    ai_api_key: str | None = Field(default=None)
    ai_base_url: str = Field(default="https://api.openai.com/v1")
    ai_model: str = Field(default="gpt-4.1-mini")
    ai_reader_prompt_version: str = Field(default="mb7c-reader-v1")
    ai_recommender_prompt_version: str = Field(default="mb7c-recommender-v1")
    ai_timeout_seconds: float = Field(default=12.0)
    ai_max_input_chars: int = Field(default=6000)
    ai_max_thread_entries: int = Field(default=6)
    ai_max_internal_notes: int = Field(default=3)
    ai_max_output_tokens: int = Field(default=500)
    ai_include_internal_notes: bool = Field(default=True)
    ai_recommender_enabled: bool = Field(default=False)
    ai_recommender_max_output_tokens: int = Field(default=700)
    ai_cache_ttl_seconds: int = Field(default=120)
    ai_min_confidence_for_draft_adoption_warning: float = Field(default=0.65)
    handoff_production_chat_id: int | None = Field(default=None)
    handoff_warehouse_chat_id: int | None = Field(default=None)
    handoff_accountant_chat_id: int | None = Field(default=None)


def get_settings() -> Settings:
    return Settings()
