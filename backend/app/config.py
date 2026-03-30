from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite:///data/flashcards.db"

    # JWT Auth — auto-generated if not set via .env
    secret_key: str = ""
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080  # 7 days

    # AI Provider (OpenAI-compatible)
    ai_enabled: bool = False
    ai_api_base_url: str = "https://api.openai.com/v1"
    ai_api_key: str = ""
    ai_model: str = "gpt-4o-mini"
    ai_max_daily_calls: int = 50

    # AI Import batching (tune per model context window)
    ai_import_batch_chars: int = 128 * 1024
    ai_import_batch_rows: int = 30

    # Debug: log full AI response body (success & failure) to file and DB
    ai_debug_response: bool = False

    # Ingestion
    ingestion_enabled: bool = False
    ingestion_cron_hour: int = 6
    ingestion_cron_minute: int = 0

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
