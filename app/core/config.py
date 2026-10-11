import re
from datetime import timedelta
from enum import IntEnum, StrEnum
from functools import lru_cache
from typing import Any, Literal

from pydantic import BaseModel, Secret, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class DatabaseSettings(BaseModel):
    host: str = "localhost"
    port: int = 5432
    username: str
    password: Secret[str]
    name: str
    echo: bool = False

    # Connection pool
    pool_size: int = 20  # steady-state connections
    max_overflow: int = 10  # burst capacity (total max = pool_size + max_overflow)
    pool_pre_ping: bool = True  # validate connections before use
    pool_recycle: int = 1800  # recreate connections after 30 minutes
    pool_timeout: int = 30  # seconds to wait for a connection from the pool

    @computed_field
    @property
    def url(self) -> URL:
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.username,
            password=self.password.get_secret_value(),
            host=self.host,
            port=self.port,
            database=self.name,
        )


class ServerSettings(BaseModel):
    host: str = "localhost"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:3000"]


class AuthSettings(BaseModel):
    secret: Secret[str]
    """At least 32 characters. Encrypts private signing keys at rest and derives verification-token secrets."""

    password_min_length: int = 8
    password_max_length: int = 128

    jwt_expires_in: timedelta = timedelta(minutes=60)
    jwt_secret: Secret[str] = Secret("jwt-secret")
    jwt_algorithm: Literal["HS256"] = "HS256"

    @field_validator("secret", mode="after")
    @classmethod
    def secret_min_length(cls, value: Secret[str]) -> Secret[str]:
        if len(value.get_secret_value()) < 32:
            raise ValueError("AUTH__SECRET must be at least 32 characters")
        return value

    @field_validator("jwt_expires_in", mode="before")
    @classmethod
    def parse_human_duration(cls, value: Any) -> timedelta:
        if isinstance(value, timedelta):
            return value

        # If passed as integer or numeric string (seconds)
        if isinstance(value, (int, float)) or (
            isinstance(value, str) and value.isdigit()
        ):
            return timedelta(seconds=int(value))

        # Parse strings like "15m", "1h", "7d", "30s"
        if isinstance(value, str):
            match = re.match(r"^(\d+)([smhd])$", value.strip().lower())
            if match:
                amount, unit = int(match.group(1)), match.group(2)
                units = {
                    "s": "seconds",
                    "m": "minutes",
                    "h": "hours",
                    "d": "days",
                }
                return timedelta(**{units[unit]: amount})

        raise ValueError(
            f"Invalid duration format: '{value}'. Use formats like '15m', '1h', '7d', or total seconds."
        )


class LogLevel(IntEnum):
    CRITICAL = 50
    ERROR = 40
    WARNING = 30
    INFO = 20
    DEBUG = 10
    NOTSET = 0


class Environment(StrEnum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TESTING = "testing"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        env_nested_delimiter="__",
    )

    db: DatabaseSettings
    server: ServerSettings
    auth: AuthSettings

    log_level: LogLevel = LogLevel.INFO
    environment: Environment = Environment.DEVELOPMENT


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


@lru_cache(maxsize=1)
def get_auth_settings() -> AuthSettings:
    return get_settings().auth


def get_database_settings() -> DatabaseSettings:
    return get_settings().db
