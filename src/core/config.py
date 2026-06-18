"""Application configuration."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/memory.db"
    log_level: str = "INFO"
    max_turn_payload_bytes: int = 1_048_576
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    recency_weight: float = 0.10


@lru_cache
def get_settings() -> Settings:
    return Settings()
