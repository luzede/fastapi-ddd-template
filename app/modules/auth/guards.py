"""Route guards and principal resolution.

Credential resolution order (first match wins):
1. `Authorization: Bearer <session-token>` — opaque session token (better-auth `bearer` plugin);
2. session cookie;
3. an API key in one of `AUTH__API_KEY__HEADER_NAMES` — yields a synthetic session (apikey plugin
   `enableSessionForAPIKeys`).
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, Request
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import AuthSettings
from app.modules.auth.constants import AuthErrorCode
from app.modules.auth.context import AuthContext, ClientInfo
from app.modules.auth.dependencies import (
    AccessControlDep,
    ApiKeyServiceDep,
    AuthSettingsDep,
    SessionServiceDep,
    get_user_repository,
)
from app.modules.auth.models import Session
from app.modules.auth.repository import UserRepository
from app.shared.exceptions import AuthenticationError, AuthorizationError

# --- client context ---------------------------------------------------------------------


def get_client_info(request: Request) -> ClientInfo:
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[0].strip() if forwarded else None
    if not ip and request.client:
        ip = request.client.host
    return ClientInfo(ip_address=ip, user_agent=request.headers.get("user-agent"))


ClientInfoDep = Annotated[ClientInfo, Depends(get_client_info)]

# --- schemes (OpenAPI documentation only) ------------------------------------------------

_bearer = HTTPBearer(
    auto_error=False,
    scheme_name="SessionBearer",
    description="Opaque session token from sign-in (`set-auth-token` header / response body).",
)
_api_key_scheme = APIKeyHeader(
    name="x-api-key",
    auto_error=False,
    scheme_name="ApiKey",
    description="API key issued via `/api-key/create`.",
)


def _extract_api_key(request: Request, settings: AuthSettings) -> str | None:
    for name in settings.api_key.header_names:
        value = request.headers.get(name)
        if value:
            return value.strip()
    return None


# --- resolution -------------------------------------------------------------------------


async def get_optional_auth_context(
    request: Request,
    settings: AuthSettingsDep,
    sessions: SessionServiceDep,
    api_keys: ApiKeyServiceDep,
    users: Annotated[UserRepository, Depends(get_user_repository)],
    bearer: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    _: Annotated[str | None, Depends(_api_key_scheme)],
) -> AuthContext | None:
    token = (
        bearer.credentials
        if bearer
        else request.cookies.get(settings.session.cookie_name)
    )
    now = datetime.now(UTC)

    if token:
        session = await sessions.resolve(token)
        if session is None:
            return None
        user = session.user
        if user is None:
            # Orphaned session (owner removed without FK cascade): treat as revoked
            await sessions.revoke(token)
            return None
        if user.is_currently_banned(now):
            # Ban applied after sign-in: kill the session on contact
            await sessions.revoke(token)
            raise AuthorizationError(
                user.ban_reason or "You have been banned from this application",
                code=AuthErrorCode.BANNED_USER,
            )
        return AuthContext(user=user, session=session)

    if settings.api_key.enable_session_for_api_keys:
        raw_key = _extract_api_key(request, settings)
        if raw_key:
            record = await api_keys.verify_or_raise(raw_key)
            user = await users.get(record.reference_id)
            if user is None:
                raise AuthenticationError(
                    "Invalid API key", code=AuthErrorCode.INVALID_API_KEY
                )
            if user.is_currently_banned(now):
                raise AuthorizationError(
                    user.ban_reason or "You have been banned from this application",
                    code=AuthErrorCode.BANNED_USER,
                )
            # Synthetic, non-persisted session mirroring better-auth's mocked session
            synthetic = Session(
                id=uuid4(),
                token=record.key,
                user_id=user.id,
                expires_at=record.expires_at
                or (now + timedelta(seconds=settings.session.ttl_seconds)),
                ip_address=None,
                user_agent=request.headers.get("user-agent"),
                impersonated_by=None,
            )
            synthetic.created_at = now
            synthetic.updated_at = now
            return AuthContext(user=user, session=synthetic, via_api_key=True)

    return None


OptionalAuthDep = Annotated[AuthContext | None, Depends(get_optional_auth_context)]


async def get_auth_context(ctx: OptionalAuthDep) -> AuthContext:
    if ctx is None:
        raise AuthenticationError(code=AuthErrorCode.UNAUTHORIZED)
    return ctx


AuthDep = Annotated[AuthContext, Depends(get_auth_context)]


async def get_session_auth_context(ctx: AuthDep) -> AuthContext:
    """A real (persisted) session is required; API-key principals are rejected."""
    if ctx.via_api_key:
        raise AuthenticationError(
            "This action requires a signed-in session", code=AuthErrorCode.UNAUTHORIZED
        )
    return ctx


SessionAuthDep = Annotated[AuthContext, Depends(get_session_auth_context)]


async def get_fresh_auth_context(
    ctx: SessionAuthDep, sessions: SessionServiceDep
) -> AuthContext:
    """better-auth `freshSessionMiddleware`: sensitive actions need a recently created session."""
    if not sessions.is_fresh(ctx.session):
        raise AuthorizationError(
            "Please sign in again to perform this action",
            code=AuthErrorCode.SESSION_NOT_FRESH,
        )
    return ctx


FreshAuthDep = Annotated[AuthContext, Depends(get_fresh_auth_context)]


async def get_admin_auth_context(
    ctx: SessionAuthDep, access_control: AccessControlDep
) -> AuthContext:
    """better-auth `adminMiddleware`: any role in `admin_roles` (or an `admin_user_ids` entry)."""
    if not access_control.is_admin(user_id=ctx.user.id, role=ctx.user.role):
        raise AuthorizationError(
            "You are not allowed to perform this action",
            code=AuthErrorCode.YOU_ARE_NOT_ALLOWED_TO_PERFORM_THIS_ACTION,
        )
    return ctx


AdminAuthDep = Annotated[AuthContext, Depends(get_admin_auth_context)]
