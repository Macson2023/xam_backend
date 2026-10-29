from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "xam_backend"
    api_v1_prefix: str = "/api/v1"
    debug: bool = False

    secret_key: str = "dev-secret-key-change-me-32-bytes-min"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/xam"
    database_echo: bool = False
    auto_create_tables: bool = False

    upload_dir: str = "uploads"
    media_url_prefix: str = "/media"
    max_image_size_bytes: int = 5 * 1024 * 1024

    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
