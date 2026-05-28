from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_llm_api_key: str | None = None
    openai_whisper_api_key: str | None = None
    openai_api_key: str | None = None
    openai_model: str | None = None
    openai_resume_model: str = "gpt-5-mini"
    openai_jd_model: str = "gpt-5-mini"
    openai_question_model: str = "gpt-5-mini"
    openai_scoring_model: str = "gpt-5"
    openai_transcribe_model: str = "whisper-1"
    openai_timeout_seconds: float = 180.0
    supabase_database_url: str | None = None
    database_url: str | None = None
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def effective_database_url(self) -> str:
        url = self.supabase_database_url or self.database_url
        if not url:
            raise RuntimeError("Set DATABASE_URL or SUPABASE_DATABASE_URL to the Supabase Postgres connection string.")
        return url

    @property
    def resume_model(self) -> str:
        return self.openai_resume_model or self.openai_model or "gpt-5-mini"

    @property
    def jd_model(self) -> str:
        return self.openai_jd_model or self.openai_model or "gpt-5-mini"

    @property
    def question_model(self) -> str:
        return self.openai_question_model or self.openai_model or "gpt-5-mini"

    @property
    def scoring_model(self) -> str:
        return self.openai_scoring_model or self.openai_model or "gpt-5"


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
AUDIO_DIR = DATA_DIR / "audio"


@lru_cache
def get_settings() -> Settings:
    DATA_DIR.mkdir(exist_ok=True)
    AUDIO_DIR.mkdir(exist_ok=True)
    return Settings()
