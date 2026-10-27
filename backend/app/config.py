from functools import lru_cache
from pathlib import Path
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = f"sqlite:///{PROJECT_ROOT / 'storage' / 'contracts.db'}"
    storage_dir: Path = PROJECT_ROOT / "storage"
    cors_origins: list[str] = ["http://localhost:5173"]
    max_upload_bytes: int = 20 * 1024 * 1024
    max_pdf_pages: int = 100
    ocr_dpi: int = 150
    max_ocr_image_pixels: int = 25_000_000
    max_ocr_image_dimension: int = 6000
    min_pdf_text_chars: int = 80
    min_page_text_chars: int = 40
    ai_provider: str = "gemini"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-flash-lite-latest"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    ai_timeout_seconds: float = 120.0
    ai_max_concurrent_requests: int = 2
    max_ai_context_chars: int = 100_000
    chunk_words: int = 550
    chunk_overlap_words: int = 80

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("ai_provider")
    @classmethod
    def validate_ai_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"gemini", "openai"}:
            raise ValueError("AI_PROVIDER must be either 'gemini' or 'openai'.")
        return normalized


@lru_cache
def get_settings() -> Settings:
    return Settings()
