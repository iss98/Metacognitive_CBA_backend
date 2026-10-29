from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_DIR = Path(__file__).resolve().parents[1]
RESOURCE_DIR = PROJECT_DIR / "resources"
DATA_DIR = PROJECT_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    app_name: str = "MCCBA API"
    api_prefix: str = "/api"
    web_origin: str = "http://localhost:3000"
    data_backend: Literal["json", "firestore"] = "json"
    llm_provider: Literal["mock", "openai", "google"] = "mock"

    openai_api_key: str = ""
    openai_chat_model: str = ""
    openai_reasoning_effort: Literal["none", "low", "medium", "high", "xhigh", "max"] = "none"
    openai_realtime_transcribe_model: str = "gpt-live-transcribe"
    openai_file_transcribe_model: str = "gpt-transcribe"
    gemini_model: str = ""

    google_cloud_project: str = ""
    google_cloud_location: str = "asia-northeast3"
    google_genai_use_vertexai: bool = True
    firebase_project_id: str = ""
    audio_bucket: str = ""

    max_followups_per_question: int = 2
    rubric_version: str = "draft-3"


@lru_cache
def get_settings() -> Settings:
    return Settings()

