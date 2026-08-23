from functools import lru_cache

from pydantic import BaseModel, Secret
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseModel):
    host: str = "localhost"
    port: int = 5432
    username: str
    password: Secret[str]
    name: str
    echo: bool = False


class ServerSettings(BaseModel):
    host: str = "localhost"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:3000"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        env_nested_delimiter="__",
    )

    db: DatabaseSettings
    server: ServerSettings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
