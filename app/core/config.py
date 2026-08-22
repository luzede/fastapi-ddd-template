from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    app_database_url: str = "sqlite+aiosqlite:///app.sqlite"
    host: str = "127.0.0.1"
    port: int = 8000
    db_echo: bool = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
