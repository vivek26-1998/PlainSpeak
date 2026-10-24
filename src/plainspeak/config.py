"""Application settings loaded from environment variables and `.env`."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"
    anthropic_effort: str = "medium"
    anthropic_fallbacks: str = "default"
    reson8_api_key: str = ""
    port: int = 3001
    plainspeak_data_dir: Path = Path("data")

    @property
    def cases_dir(self) -> Path:
        return self.plainspeak_data_dir / "cases"

    @property
    def uploads_dir(self) -> Path:
        return self.plainspeak_data_dir / "uploads"


@lru_cache
def get_settings() -> Settings:
    return Settings()
