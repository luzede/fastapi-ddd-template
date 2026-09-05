"""FastAPI dependencies for the auth module.

Credential resolution order (first match wins):
1. `Authorization: Bearer <session-token>` — opaque session token (better-auth `bearer` plugin);
2. session cookie;
3. an API key in one of `AUTH__API_KEY__HEADER_NAMES` — yields a synthetic session (apikey plugin
   `enableSessionForAPIKeys`).
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, Request, Response
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import AuthSettings, Settings, get_settings
from app.modules.auth.access_control import AccessControl
from app.modules.auth.constants import AuthErrorCode
from app.modules.auth.mailer import Mailer
from app.modules.auth.models import Session
from app.modules.auth.repository import (
    AccountRepository,
    ApiKeyRepository,
    JwksRepository,
    SessionRepository,
    VerificationRepository,
)
from app.modules.auth.services.admin import AdminService
from app.modules.auth.services.api_key import ApiKeyService
from app.modules.auth.services.auth import AuthService
from app.modules.auth.services.jwt import JwtService
from app.modules.auth.services.session import AuthContext, ClientInfo, SessionService
from app.modules.auth.services.verification import VerificationService
from app.modules.users.repository import UserRepository
from app.shared.db.session import SessionDep
from app.shared.exceptions import AuthenticationError, AuthorizationError
from app.shared.state import AppStateDep

# --- settings ----------------------------------------------------------------------------


def get_auth_settings(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthSettings:
    return settings.auth


AuthSettingsDep = Annotated[AuthSettings, Depends(get_auth_settings)]


def get_mailer(state: AppStateDep) -> Mailer:
    return state.mailer


def get_access_control(settings: AuthSettingsDep) -> AccessControl:
    return AccessControl(settings.admin)


# --- repositories ------------------------------------------------------------------------


def get_user_repository(db: SessionDep) -> UserRepository:
    return UserRepository(db)


def get_session_repository(db: SessionDep) -> SessionRepository:
    return SessionRepository(db)


def get_account_repository(db: SessionDep) -> AccountRepository:
    return AccountRepository(db)


def get_verification_repository(db: SessionDep) -> VerificationRepository:
    return VerificationRepository(db)


def get_jwks_repository(db: SessionDep) -> JwksRepository:
    return JwksRepository(db)


def get_api_key_repository(db: SessionDep) -> ApiKeyRepository:
    return ApiKeyRepository(db)


# --- services ----------------------------------------------------------------------------


def get_session_service(
    repo: Annotated[SessionRepository, Depends(get_session_repository)],
    settings: AuthSettingsDep,
) -> SessionService:
    return SessionService(repo, settings.session)


def get_verification_service(
    repo: Annotated[VerificationRepository, Depends(get_verification_repository)],
    settings: AuthSettingsDep,
) -> VerificationService:
    return VerificationService(repo, settings.secret.get_secret_value())


def get_auth_service(
    settings: AuthSettingsDep,
    users: Annotated[UserRepository, Depends(get_user_repository)],
    accounts: Annotated[AccountRepository, Depends(get_account_repository)],
    api_keys: Annotated[ApiKeyRepository, Depends(get_api_key_repository)],
    sessions: Annotated[SessionService, Depends(get_session_service)],
    verifications: Annotated[VerificationService, Depends(get_verification_service)],
    mailer: Annotated[Mailer, Depends(get_mailer)],
) -> AuthService:
    return AuthService(
        settings=settings,
        users=users,
        accounts=accounts,
        api_keys=api_keys,
        sessions=sessions,
        verifications=verifications,
        mailer=mailer,
    )


def get_jwt_service(
    repo: Annotated[JwksRepository, Depends(get_jwks_repository)],
    settings: AuthSettingsDep,
) -> JwtService:
    return JwtService(repo, settings)


def get_api_key_service(
    repo: Annotated[ApiKeyRepository, Depends(get_api_key_repository)],
    settings: AuthSettingsDep,
) -> ApiKeyService:
    return ApiKeyService(repo, settings.api_key)


def get_admin_service(
    settings: AuthSettingsDep,
    access_control: Annotated[AccessControl, Depends(get_access_control)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
    accounts: Annotated[AccountRepository, Depends(get_account_repository)],
    sessions: Annotated[SessionService, Depends(get_session_service)],
) -> AdminService:
    return AdminService(
        settings=settings,
        access_control=access_control,
        users=users,
        accounts=accounts,
        sessions=sessions,
    )


SessionServiceDep = Annotated[SessionService, Depends(get_session_service)]
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
JwtServiceDep = Annotated[JwtService, Depends(get_jwt_service)]
ApiKeyServiceDep = Annotated[ApiKeyService, Depends(get_api_key_service)]
AdminServiceDep = Annotated[AdminService, Depends(get_admin_service)]
AccessControlDep = Annotated[AccessControl, Depends(get_access_control)]

# --- request context ---------------------------------------------------------------------


def get_client_info(request: Request) -> ClientInfo:
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[0].strip() if forwarded else None
    if not ip and request.client:
        ip = request.client.host
    return ClientInfo(ip_address=ip, user_agent=request.headers.get("user-agent"))


ClientInfoDep = Annotated[ClientInfo, Depends(get_client_info)]

# --- credential extraction ---------------------------------------------------------------

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


async def get_optional_auth_context(
    request: Request,
    settings: AuthSettingsDep,
    sessions: SessionServiceDep,
    api_keys: ApiKeyServiceDep,
    users: Annotated[UserRepository, Depends(get_user_repository)],
    bearer: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    # Declared only so the scheme shows up in OpenAPI; actual lookup honours all configured names
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

# --- cookies -----------------------------------------------------------------------------


def set_session_cookie(
    response: Response, settings: AuthSettings, session: Session
) -> None:
    cookie = settings.session
    response.set_cookie(
        key=cookie.cookie_name,
        value=session.token,
        max_age=max(int((session.expires_at - datetime.now(UTC)).total_seconds()), 0),
        httponly=True,
        secure=cookie.cookie_secure,
        samesite=cookie.cookie_same_site,
        domain=cookie.cookie_domain,
        path="/",
    )
    # Mirror better-auth `bearer` plugin so header-based clients can capture the token
    response.headers["set-auth-token"] = session.token


def clear_session_cookie(response: Response, settings: AuthSettings) -> None:
    cookie = settings.session
    response.delete_cookie(
        key=cookie.cookie_name,
        httponly=True,
        secure=cookie.cookie_secure,
        samesite=cookie.cookie_same_site,
        domain=cookie.cookie_domain,
        path="/",
    )
