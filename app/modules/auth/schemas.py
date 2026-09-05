"""Auth API contracts (snake_case equivalents of better-auth's request/response bodies)."""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, field_validator

from app.modules.users.schemas import Name, UserRead, normalize_email

type Password = Annotated[str, Field(min_length=1, max_length=1024)]
type Permissions = dict[str, list[str]]


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- core --------------------------------------------------------------------------------


class SessionRead(BaseModel):
    """Session as exposed to clients. The token is only returned to its own holder."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    expires_at: datetime
    ip_address: str | None
    user_agent: str | None
    impersonated_by: UUID | None
    created_at: datetime
    updated_at: datetime


class SessionWithTokenRead(SessionRead):
    token: str


class SessionResponse(BaseModel):
    """`get-session` payload: `{ session, user }`."""

    session: SessionRead
    user: UserRead


class SignUpEmailRequest(_Body):
    name: Name
    email: EmailStr
    password: Password
    image: HttpUrl | None = None

    @field_validator("email", mode="after")
    @classmethod
    def _normalize(cls, value: str) -> str:
        return normalize_email(value)


class SignInEmailRequest(_Body):
    email: EmailStr
    password: Password

    @field_validator("email", mode="after")
    @classmethod
    def _normalize(cls, value: str) -> str:
        return normalize_email(value)


class AuthResponse(BaseModel):
    """Sign-in / sign-up result. `token` is the opaque session token for header-based clients."""

    token: str | None
    user: UserRead


class EmailRequest(_Body):
    email: EmailStr

    @field_validator("email", mode="after")
    @classmethod
    def _normalize(cls, value: str) -> str:
        return normalize_email(value)


class ResetPasswordRequest(_Body):
    token: str = Field(min_length=16, max_length=256)
    new_password: Password


class ChangePasswordRequest(_Body):
    current_password: Password
    new_password: Password
    revoke_other_sessions: bool = False


class SetPasswordRequest(_Body):
    new_password: Password


class VerifyPasswordRequest(_Body):
    password: Password


class RevokeSessionRequest(_Body):
    token: str = Field(min_length=16, max_length=256)


class VerificationTokenQuery(BaseModel):
    token: str = Field(min_length=16, max_length=256)


class AccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider_id: str
    account_id: str
    scope: str | None
    created_at: datetime
    updated_at: datetime


# --- jwt plugin --------------------------------------------------------------------------


class TokenResponse(BaseModel):
    token: str


class Jwk(BaseModel):
    model_config = ConfigDict(extra="allow")

    kid: str
    kty: str
    alg: str
    use: str = "sig"


class JwksResponse(BaseModel):
    keys: list[Jwk]


# --- admin plugin ------------------------------------------------------------------------


class AdminCreateUserRequest(_Body):
    email: EmailStr
    password: Password
    name: Name
    role: str | list[str] | None = None
    image: HttpUrl | None = None
    email_verified: bool = False

    @field_validator("email", mode="after")
    @classmethod
    def _normalize(cls, value: str) -> str:
        return normalize_email(value)


class AdminUpdateUserRequest(_Body):
    name: Name | None = None
    image: HttpUrl | None = None
    email: EmailStr | None = None
    email_verified: bool | None = None

    @field_validator("email", mode="after")
    @classmethod
    def _normalize(cls, value: str | None) -> str | None:
        return normalize_email(value) if value else value


class ListUsersResponse(BaseModel):
    users: list[UserRead]
    total: int
    limit: int
    offset: int


class SetRoleRequest(_Body):
    role: str | list[str]


class BanUserRequest(_Body):
    reason: str | None = Field(default=None, max_length=512)
    expires_in: int | None = Field(
        default=None, gt=0, description="Seconds until the ban lifts"
    )


class AdminSetPasswordRequest(_Body):
    new_password: Password


class ImpersonateResponse(BaseModel):
    token: str
    session: SessionRead
    user: UserRead


class RevokedCountResponse(BaseModel):
    status: bool = True
    revoked: int


# --- api key plugin ----------------------------------------------------------------------


class ApiKeyRead(BaseModel):
    """API key without its secret (better-auth `Omit<ApiKey, "key">`)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    config_id: str
    name: str | None
    start: str | None
    prefix: str | None
    reference_id: UUID
    enabled: bool
    remaining: int | None
    refill_interval: int | None
    refill_amount: int | None
    last_refill_at: datetime | None
    rate_limit_enabled: bool
    rate_limit_time_window: int | None
    rate_limit_max: int | None
    request_count: int
    last_request: datetime | None
    expires_at: datetime | None
    permissions: Permissions | None
    metadata: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class ApiKeyCreated(ApiKeyRead):
    key: str = Field(description="Plaintext key. Shown once; store it securely.")


class ApiKeyCreateRequest(_Body):
    name: str | None = None
    prefix: str | None = None
    expires_in: int | None = Field(default=None, gt=0, description="Seconds")
    metadata: dict[str, Any] | None = None
    # server-side controls in better-auth; here they're admin-only (see router)
    remaining: int | None = None
    refill_amount: int | None = Field(default=None, gt=0)
    refill_interval: int | None = Field(default=None, gt=0, description="Milliseconds")
    rate_limit_enabled: bool | None = None
    rate_limit_time_window: int | None = Field(
        default=None, gt=0, description="Milliseconds"
    )
    rate_limit_max: int | None = Field(default=None, gt=0)
    permissions: Permissions | None = None

    def has_privileged_fields(self) -> bool:
        return any(
            v is not None
            for v in (
                self.remaining,
                self.refill_amount,
                self.refill_interval,
                self.rate_limit_enabled,
                self.rate_limit_time_window,
                self.rate_limit_max,
                self.permissions,
            )
        )


class ApiKeyUpdateRequest(_Body):
    name: str | None = None
    metadata: dict[str, Any] | None = None
    enabled: bool | None = None
    remaining: int | None = None
    refill_amount: int | None = Field(default=None, gt=0)
    refill_interval: int | None = Field(default=None, gt=0)
    expires_in: int | None = Field(
        default=None, ge=0, description="Seconds; 0 removes expiry"
    )
    rate_limit_enabled: bool | None = None
    rate_limit_time_window: int | None = Field(default=None, gt=0)
    rate_limit_max: int | None = Field(default=None, gt=0)
    permissions: Permissions | None = None

    def has_privileged_fields(self) -> bool:
        return any(
            f in self.model_fields_set
            for f in (
                "enabled",
                "remaining",
                "refill_amount",
                "refill_interval",
                "expires_in",
                "rate_limit_enabled",
                "rate_limit_time_window",
                "rate_limit_max",
                "permissions",
            )
        )


class ApiKeyVerifyRequest(_Body):
    key: str = Field(min_length=8, max_length=256)
    permissions: Permissions | None = None


class ApiKeyVerifyError(BaseModel):
    code: str
    message: str


class ApiKeyVerifyResponse(BaseModel):
    valid: bool
    error: ApiKeyVerifyError | None
    key: ApiKeyRead | None


type ListUsersSortBy = Literal["created_at", "updated_at", "email", "name", "role"]
