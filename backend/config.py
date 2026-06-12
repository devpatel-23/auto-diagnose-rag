"""
backend/config.py
-----------------
Central configuration loaded from environment variables.

WHY THIS EXISTS:
Instead of doing os.getenv("OPENAI_API_KEY") in every file,
we load all settings here ONCE and import `settings` everywhere.
Pydantic validates types automatically — if DATABASE_URL is missing,
the app crashes immediately with a clear error instead of silently
failing later.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # OpenAI
    groq_api_key: str
    embedding_model: str = "text-embedding-3-small"

    # Database
    database_url: str

    # App
    app_env: str = "development"
    secret_key: str = "change-me-in-production"

    # Chunking — controls how we split documents for embedding
    chunk_size: int = 1000       # characters per chunk
    chunk_overlap: int = 200     # overlap between chunks (preserves context)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """
    lru_cache means this function only runs ONCE.
    Every subsequent call returns the cached Settings object.
    This prevents re-reading the .env file on every request.
    """
    return Settings()


# Export a singleton so we can do: from backend.config import settings
settings = get_settings()
