from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    gcp_project_id: str = Field(min_length=1)
    gcp_location: str = "us-central1"
    gcs_bucket: str = "indian_supreme_court"
    gcs_prefix: str = "indian_supreme_court_judgement/pdfs"
    gemini_model: str = "gemini-2.5-pro"
    gemini_fallback_model: str = "gemini-2.5-flash"
    embedding_model: str = "text-embedding-005"
    holdout_count: int = 20
    chunk_size: int = 1400
    chunk_overlap: int = 180
    embedding_batch_size: int = 100
    embedding_retry_attempts: int = 6
    embedding_retry_delay_seconds: float = 10.0
    retrieval_k: int = 8
    backend_cors_origins: str = "http://localhost:5173"
    data_dir: Path = Path("data")

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.backend_cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
