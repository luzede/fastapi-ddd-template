"""Core auth endpoints (better-auth base routes: sign-up/in/out, session, password, email)."""

from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.modules.auth.dependencies import (
    AuthDep,
    AuthServiceDep,
    AuthSettingsDep,
    ClientInfoDep,
    FreshAuthDep,
    JwtServiceDep,
    SessionAuthDep,
    SessionServiceDep,
    clear_session_cookie,
    set_session_cookie,
)
from app.modules.auth.schemas import (
    AuthResponse,
    ChangePasswordRequest,
    EmailRequest,
    ResetPasswordRequest,
    RevokeSessionRequest,
    SessionRead,
    SessionResponse,
    SetPasswordRequest,
    SignInEmailRequest,
    SignUpEmailRequest,
    VerifyPasswordRequest,
)
from app.modules.users.schemas import StatusResponse, UserRead
from app.shared.exceptions.schemas import ProblemDetail

router = APIRouter(tags=["auth"])

_PROBLEM = {"model": ProblemDetail}


@router.post(
    "/sign-up/email",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    responses={400: _PROBLEM, 409: _PROBLEM},
    summary="Register with email and password",
)
async def sign_up_email(
    body: SignUpEmailRequest,
    response: Response,
    auth: AuthServiceDep,
    settings: AuthSettingsDep,
    client: ClientInfoDep,
) -> AuthResponse:
    result = await auth.sign_up_email(
        email=body.email,
        password=body.password,
        name=body.name,
        image=str(body.image) if body.image else None,
        client=client,
    )
    if result.session is not None:
        set_session_cookie(response, settings, result.session)
    return AuthResponse(
        token=result.session.token if result.session else None,
        user=UserRead.model_validate(result.user),
    )


@router.post(
    "/sign-in/email",
    response_model=AuthResponse,
    responses={401: _PROBLEM, 403: _PROBLEM},
    summary="Sign in with email and password",
)
async def sign_in_email(
    body: SignInEmailRequest,
    response: Response,
    auth: AuthServiceDep,
    settings: AuthSettingsDep,
    client: ClientInfoDep,
) -> AuthResponse:
    result = await auth.sign_in_email(
        email=body.email, password=body.password, client=client
    )
    set_session_cookie(response, settings, result.session)
    return AuthResponse(
        token=result.session.token, user=UserRead.model_validate(result.user)
    )


@router.post(
    "/sign-out",
    response_model=StatusResponse,
    summary="Revoke the current session",
)
async def sign_out(
    response: Response,
    auth: AuthServiceDep,
    settings: AuthSettingsDep,
    ctx: SessionAuthDep,
) -> StatusResponse:
    await auth.sign_out(ctx.session.token)
    clear_session_cookie(response, settings)
    return StatusResponse()


@router.get(
    "/get-session",
    response_model=SessionResponse,
    responses={401: _PROBLEM},
    summary="Current session and user",
)
async def get_session(
    response: Response,
    ctx: AuthDep,
    settings: AuthSettingsDep,
    jwt_service: JwtServiceDep,
) -> SessionResponse:
    # better-auth jwt plugin: attach a JWT for downstream services
    if settings.jwt.set_jwt_header_on_get_session and not ctx.via_api_key:
        response.headers["set-auth-jwt"] = await jwt_service.sign_for_user(ctx.user)
    return SessionResponse(
        session=SessionRead.model_validate(ctx.session),
        user=UserRead.model_validate(ctx.user),
    )


@router.get(
    "/list-sessions",
    response_model=list[SessionRead],
    responses={401: _PROBLEM},
    summary="Active sessions for the current user",
)
async def list_sessions(
    ctx: SessionAuthDep, sessions: SessionServiceDep
) -> list[SessionRead]:
    return [
        SessionRead.model_validate(s) for s in await sessions.list_active(ctx.user.id)
    ]


@router.post(
    "/revoke-session",
    response_model=StatusResponse,
    responses={401: _PROBLEM, 404: _PROBLEM},
    summary="Revoke one of the current user's sessions by token",
)
async def revoke_session(
    body: RevokeSessionRequest, ctx: SessionAuthDep, sessions: SessionServiceDep
) -> StatusResponse:
    # Only the owner may revoke: scope the lookup to their sessions
    owned = {s.token for s in await sessions.list_active(ctx.user.id)}
    if body.token not in owned:
        # Do not disclose whether the token belongs to another user
        return StatusResponse()
    await sessions.revoke(body.token)
    return StatusResponse()


@router.post(
    "/revoke-sessions",
    response_model=StatusResponse,
    responses={401: _PROBLEM},
    summary="Revoke every session of the current user, including this one",
)
async def revoke_sessions(
    response: Response,
    ctx: SessionAuthDep,
    sessions: SessionServiceDep,
    settings: AuthSettingsDep,
) -> StatusResponse:
    await sessions.revoke_all(ctx.user.id)
    clear_session_cookie(response, settings)
    return StatusResponse()


@router.post(
    "/revoke-other-sessions",
    response_model=StatusResponse,
    responses={401: _PROBLEM},
    summary="Revoke every session of the current user except this one",
)
async def revoke_other_sessions(
    ctx: SessionAuthDep, sessions: SessionServiceDep
) -> StatusResponse:
    await sessions.revoke_all(ctx.user.id, except_token=ctx.session.token)
    return StatusResponse()


# --- email verification ------------------------------------------------------------------


@router.post(
    "/send-verification-email",
    response_model=StatusResponse,
    summary="(Re)send the email verification link",
)
async def send_verification_email(
    body: EmailRequest, auth: AuthServiceDep
) -> StatusResponse:
    await auth.resend_verification_email(body.email)
    return StatusResponse()


@router.get(
    "/verify-email",
    response_model=UserRead,
    responses={400: _PROBLEM},
    summary="Verify an email address (link target)",
)
async def verify_email(
    token: Annotated[str, Query(min_length=16, max_length=256)], auth: AuthServiceDep
) -> UserRead:
    return UserRead.model_validate(await auth.verify_email(token))


# --- passwords ---------------------------------------------------------------------------


@router.post(
    "/request-password-reset",
    response_model=StatusResponse,
    summary="Send a password reset link",
)
async def request_password_reset(
    body: EmailRequest, auth: AuthServiceDep
) -> StatusResponse:
    await auth.request_password_reset(body.email)
    return StatusResponse()


@router.post(
    "/reset-password",
    response_model=StatusResponse,
    responses={400: _PROBLEM},
    summary="Set a new password using a reset token",
)
async def reset_password(
    body: ResetPasswordRequest, auth: AuthServiceDep
) -> StatusResponse:
    await auth.reset_password(token=body.token, new_password=body.new_password)
    return StatusResponse()


@router.post(
    "/change-password",
    response_model=StatusResponse,
    responses={400: _PROBLEM, 401: _PROBLEM},
    summary="Change password (requires current password)",
)
async def change_password(
    body: ChangePasswordRequest, ctx: SessionAuthDep, auth: AuthServiceDep
) -> StatusResponse:
    await auth.change_password(
        user=ctx.user,
        current_token=ctx.session.token,
        current_password=body.current_password,
        new_password=body.new_password,
        revoke_other_sessions=body.revoke_other_sessions,
    )
    return StatusResponse()


@router.post(
    "/set-password",
    response_model=StatusResponse,
    responses={400: _PROBLEM, 401: _PROBLEM, 403: _PROBLEM},
    summary="Set a password on an account that has none (fresh session required)",
)
async def set_password(
    body: SetPasswordRequest, ctx: FreshAuthDep, auth: AuthServiceDep
) -> StatusResponse:
    await auth.set_password(user=ctx.user, new_password=body.new_password)
    return StatusResponse()


@router.post(
    "/verify-password",
    response_model=StatusResponse,
    responses={400: _PROBLEM, 401: _PROBLEM},
    summary="Re-verify the current user's password",
)
async def verify_password(
    body: VerifyPasswordRequest, ctx: SessionAuthDep, auth: AuthServiceDep
) -> StatusResponse:
    await auth.verify_password(user=ctx.user, password=body.password)
    return StatusResponse()
