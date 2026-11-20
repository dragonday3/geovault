"""Runtime configuration, read from environment variables (never from code or Git)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GEOVAULT_", extra="ignore")

    # SecretStr keeps the DSN (which embeds the DB password) out of reprs and logs.
    database_url: SecretStr
    env: Literal["local", "production"] = "local"
    migrations_dir: Path = Path(__file__).resolve().parent.parent / "db" / "migrations"
    frontend_dir: Path = Path(__file__).resolve().parent.parent / "frontend"

    @property
    def docs_enabled(self) -> bool:
        # Interactive API docs are a recon gift; only expose them on a developer machine.
        return self.env == "local"


@lru_cache
def get_settings() -> Settings:
    return Settings()
