from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="CVP Semanal API", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    app_debug: bool = Field(default=True, alias="APP_DEBUG")

    database_url: str = Field(alias="DATABASE_URL")

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model_primary: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL_PRIMARY")
    openai_model_fallback: str | None = Field(default=None, alias="OPENAI_MODEL_FALLBACK")

    upload_dir: str = Field(default="./app/uploads", alias="UPLOAD_DIR")
    output_dir: str = Field(default="./app/outputs", alias="OUTPUT_DIR")

    backend_cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        alias="BACKEND_CORS_ORIGINS",
    )

    @property
    def cors_origins(self) -> List[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]

    @property
    def upload_path(self) -> Path:
        path = Path(self.upload_dir)
        if path.is_absolute():
            return path
        return BACKEND_DIR / path

    @property
    def output_path(self) -> Path:
        path = Path(self.output_dir)
        if path.is_absolute():
            return path
        return BACKEND_DIR / path


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    settings.output_path.mkdir(parents=True, exist_ok=True)
    return settings
