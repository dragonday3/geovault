"""Runtime configuration, read from environment variables (never from code or Git).

Secure-by-default: the app refuses to start with a weak JWT secret or token lifetimes
beyond safe bounds, so a misconfiguration fails loudly instead of running insecurely.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_WEAK_SECRETS = {"secret", "changeme", "change-me", "password", "jwt-secret", "geovault"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GEOVAULT_", extra="ignore")

    # SecretStr keeps the DSN (which embeds the DB password) out of reprs and logs.
    database_url: SecretStr
    env: Literal["local", "production"] = "local"
    migrations_dir: Path = Path(__file__).resolve().parent.parent / "db" / "migrations"
    frontend_dir: Path = Path(__file__).resolve().parent.parent / "frontend"
    # Uploaded photos (server-generated file names only). A named volume in docker-compose.
    photo_dir: Path = Path("/data/photos")

    # HS256 signing key. 32+ chars of high-entropy random data (e.g. secrets.token_urlsafe(48)).
    jwt_secret: SecretStr
    access_token_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_days: int = Field(default=14, ge=1, le=30)

    @field_validator("jwt_secret")
    @classmethod
    def _strong_secret(cls, v: SecretStr) -> SecretStr:
        s = v.get_secret_value()
        if len(s) < 32 or s.lower() in _WEAK_SECRETS or len(set(s)) < 12:
            raise ValueError("GEOVAULT_JWT_SECRET must be 32+ characters of random data")
        return v

    @property
    def docs_enabled(self) -> bool:
        # Interactive API docs are a recon gift; only expose them on a developer machine.
        return self.env == "local"


@lru_cache
def get_settings() -> Settings:
    return Settings()
