from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field, Secret, computed_field, field_validator
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


class SessionSettings(BaseModel):
    """Opaque session token lifecycle (mirrors better-auth `session` options)."""

    ttl_seconds: int = 60 * 60 * 24 * 7
    """Absolute lifetime of a session. Default: 7 days."""
    update_age_seconds: int = 60 * 60 * 24
    """Sliding-expiry threshold: once a session has aged past this, its expiry is extended on use. Default: 1 day."""
    fresh_age_seconds: int = 60 * 60 * 24
    """A session younger than this is considered *fresh* and may perform sensitive actions without re-authentication.
    Set to 0 to disable freshness checks."""
    cookie_name: str = "session_token"
    cookie_secure: bool = True
    cookie_domain: str | None = None
    cookie_same_site: Literal["lax", "strict", "none"] = "lax"


class EmailPasswordSettings(BaseModel):
    """Email + password credential provider (better-auth `emailAndPassword`)."""

    require_email_verification: bool = False
    """When true, unverified users cannot sign in; a verification email is (re)sent instead."""
    send_verification_on_sign_up: bool = True
    password_min_length: int = 8
    password_max_length: int = 128
    email_verification_ttl_seconds: int = 60 * 60
    password_reset_ttl_seconds: int = 60 * 60
    reset_password_url: str = "http://localhost:3000/reset-password"
    """Frontend URL the reset token is appended to (`?token=`)."""
    verify_email_url: str | None = None
    """Frontend URL the verification token is appended to. Defaults to the API `verify-email` endpoint."""


class AdminSettings(BaseModel):
    """Admin plugin: role-based access control and moderation."""

    default_role: str = "user"
    admin_roles: list[str] = ["admin"]
    admin_user_ids: list[str] = []
    """User IDs that are treated as admins regardless of role."""
    impersonation_session_ttl_seconds: int = 60 * 60
    allow_impersonating_admins: bool = False
    bans_revoke_sessions: bool = True


class JwtSettings(BaseModel):
    """JWT plugin: asymmetric tokens for downstream services, published via JWKS."""

    issuer: str | None = None
    """Defaults to `AUTH__BASE_URL`."""
    audience: str | list[str] | None = None
    """Defaults to `AUTH__BASE_URL`."""
    expiration_seconds: int = 60 * 15
    algorithm: Literal["EdDSA", "ES256", "ES512", "RS256", "PS256"] = "EdDSA"
    curve: Literal["Ed25519"] = "Ed25519"
    """Curve for EdDSA keys; ignored for other algorithms."""
    rsa_modulus_length: int = 2048
    rotation_interval_seconds: int | None = None
    """When set, a new signing key is generated once the current one is older than this. Disabled by default."""
    grace_period_seconds: int = 60 * 60 * 24 * 30
    """Retired keys remain in the JWKS for this long so in-flight tokens still verify. Default: 30 days."""
    set_jwt_header_on_get_session: bool = True
    """Mirror better-auth: attach a `set-auth-jwt` header to `get-session` responses."""


class ApiKeySettings(BaseModel):
    """API key plugin: long-lived keys for server-to-server access."""

    header_names: list[str] = ["x-api-key"]
    default_key_length: int = 64
    default_prefix: str | None = None
    starting_characters_length: int = 6
    """How many leading characters of the key are stored in clear (`start`) for identification."""
    max_name_length: int = 32
    min_name_length: int = 1
    min_expires_in_seconds: int = 60 * 60 * 24
    max_expires_in_seconds: int = 60 * 60 * 24 * 365
    default_expires_in_seconds: int | None = None
    """When None, keys created without `expires_in` never expire."""
    rate_limit_enabled: bool = True
    rate_limit_time_window_ms: int = 1000 * 60 * 60 * 24
    rate_limit_max: int = 10
    enable_session_for_api_keys: bool = True
    """Accept a valid API key in `header_names` as an authenticated principal on any endpoint."""


class AuthSettings(BaseModel):
    secret: Secret[str]
    """At least 32 characters. Encrypts private signing keys at rest and derives verification-token secrets."""
    base_url: str = "http://localhost:8000"
    """Public origin of this API; default JWT issuer/audience and email link base."""

    session: SessionSettings = Field(default_factory=SessionSettings)
    email_password: EmailPasswordSettings = Field(default_factory=EmailPasswordSettings)
    admin: AdminSettings = Field(default_factory=AdminSettings)
    jwt: JwtSettings = Field(default_factory=JwtSettings)
    api_key: ApiKeySettings = Field(default_factory=ApiKeySettings)

    @field_validator("secret")
    @classmethod
    def _secret_min_length(cls, value: Secret[str]) -> Secret[str]:
        if len(value.get_secret_value()) < 32:
            raise ValueError("AUTH__SECRET must be at least 32 characters")
        return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        env_nested_delimiter="__",
    )

    db: DatabaseSettings
    server: ServerSettings
    auth: AuthSettings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
