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
    ai_reader_enabled: bool = Field(default=False)
    ai_api_key: str | None = Field(default=None)
    ai_base_url: str = Field(default="https://api.openai.com/v1")
    ai_model: str = Field(default="gpt-4.1-mini")
    ai_timeout_seconds: float = Field(default=12.0)
    ai_max_input_chars: int = Field(default=6000)
    ai_max_output_tokens: int = Field(default=500)
    ai_include_internal_notes: bool = Field(default=True)
    ai_recommender_enabled: bool = Field(default=False)
    ai_recommender_max_output_tokens: int = Field(default=700)


def get_settings() -> Settings:
    return Settings()
