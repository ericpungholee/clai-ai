from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    redis_url: str = "redis://redis:6379/0"
    fal_key: SecretStr | None = None
    fal_timeout_seconds: float = 120.0

    artifact_storage_backend: Literal["filesystem", "s3"] = "filesystem"
    artifact_storage_path: Path = Path(".data/artifacts")
    artifact_public_base_url: str = "http://localhost:8000/artifacts"
    artifact_s3_bucket: str | None = None
    artifact_s3_endpoint_url: str | None = None
    artifact_s3_region: str = "us-east-1"
    artifact_s3_access_key_id: SecretStr | None = None
    artifact_s3_secret_access_key: SecretStr | None = None

    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ]

    @property
    def fal_api_key(self) -> str | None:
        return self.fal_key.get_secret_value() if self.fal_key else None


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
