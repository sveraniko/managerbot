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


def get_settings() -> Settings:
    return Settings()
