"""Admin plugin endpoints. Every route requires an admin session (`AdminAuthDep`); individual
actions are additionally gated by fine-grained permissions inside `AdminService`."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.modules.auth.dependencies import (
    AdminAuthDep,
    AdminServiceDep,
    AuthSettingsDep,
    ClientInfoDep,
    SessionAuthDep,
    clear_session_cookie,
    set_session_cookie,
)
from app.modules.auth.schemas import (
    AdminCreateUserRequest,
    AdminSetPasswordRequest,
    AdminUpdateUserRequest,
    BanUserRequest,
    ImpersonateResponse,
    ListUsersResponse,
    ListUsersSortBy,
    RevokedCountResponse,
    RevokeSessionRequest,
    SessionRead,
    SetRoleRequest,
)
from app.modules.users.schemas import StatusResponse, UserRead
from app.shared.exceptions.schemas import ProblemDetail

router = APIRouter(prefix="/admin", tags=["auth:admin"])

_PROBLEM = {"model": ProblemDetail}
_GUARDED = {401: _PROBLEM, 403: _PROBLEM}


@router.post(
    "/create-user",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    responses={**_GUARDED, 409: _PROBLEM},
    summary="Create a user",
)
async def create_user(
    body: AdminCreateUserRequest, ctx: AdminAuthDep, admin: AdminServiceDep
) -> UserRead:
    user = await admin.create_user(
        ctx,
        email=body.email,
        password=body.password,
        name=body.name,
        role=body.role,
        image=str(body.image) if body.image else None,
        email_verified=body.email_verified,
    )
    return UserRead.model_validate(user)


@router.get(
    "/list-users",
    response_model=ListUsersResponse,
    responses=_GUARDED,
    summary="List users with search, filter and pagination",
)
async def list_users(
    ctx: AdminAuthDep,
    admin: AdminServiceDep,
    search_value: Annotated[str | None, Query(max_length=320)] = None,
    search_field: Literal["email", "name"] = "email",
    search_operator: Literal["contains", "starts_with", "ends_with"] = "contains",
    filter_field: Literal["role", "banned", "email_verified"] | None = None,
    filter_value: str | None = None,
    sort_by: ListUsersSortBy = "created_at",
    sort_direction: Literal["asc", "desc"] = "desc",
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ListUsersResponse:
    users, total = await admin.list_users(
        ctx,
        search_value=search_value,
        search_field=search_field,
        search_operator=search_operator,
        filter_field=filter_field,
        filter_value=filter_value,
        sort_by=sort_by,
        sort_direction=sort_direction,
        limit=limit,
        offset=offset,
    )
    return ListUsersResponse(
        users=[UserRead.model_validate(u) for u in users],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/users/{user_id}",
    response_model=UserRead,
    responses={**_GUARDED, 404: _PROBLEM},
    summary="Get a user",
)
async def get_user(
    user_id: UUID, ctx: AdminAuthDep, admin: AdminServiceDep
) -> UserRead:
    return UserRead.model_validate(await admin.get_user(ctx, user_id))


@router.patch(
    "/users/{user_id}",
    response_model=UserRead,
    responses={**_GUARDED, 404: _PROBLEM, 409: _PROBLEM},
    summary="Update a user's profile fields",
)
async def update_user(
    user_id: UUID,
    body: AdminUpdateUserRequest,
    ctx: AdminAuthDep,
    admin: AdminServiceDep,
) -> UserRead:
    user = await admin.update_user(
        ctx,
        user_id,
        name=body.name,
        image=str(body.image) if body.image else None,
        image_set="image" in body.model_fields_set,
        email=body.email,
        email_verified=body.email_verified,
    )
    return UserRead.model_validate(user)


@router.post(
    "/users/{user_id}/set-role",
    response_model=UserRead,
    responses={**_GUARDED, 404: _PROBLEM},
    summary="Set a user's role(s)",
)
async def set_role(
    user_id: UUID, body: SetRoleRequest, ctx: AdminAuthDep, admin: AdminServiceDep
) -> UserRead:
    return UserRead.model_validate(await admin.set_role(ctx, user_id, body.role))


@router.post(
    "/users/{user_id}/set-password",
    response_model=StatusResponse,
    responses={**_GUARDED, 400: _PROBLEM, 404: _PROBLEM},
    summary="Set a user's password (revokes their sessions)",
)
async def set_user_password(
    user_id: UUID,
    body: AdminSetPasswordRequest,
    ctx: AdminAuthDep,
    admin: AdminServiceDep,
) -> StatusResponse:
    await admin.set_password(ctx, user_id, body.new_password)
    return StatusResponse()


@router.post(
    "/users/{user_id}/ban",
    response_model=UserRead,
    responses={**_GUARDED, 400: _PROBLEM, 404: _PROBLEM},
    summary="Ban a user",
)
async def ban_user(
    user_id: UUID, body: BanUserRequest, ctx: AdminAuthDep, admin: AdminServiceDep
) -> UserRead:
    user = await admin.ban_user(
        ctx, user_id, reason=body.reason, ban_expires_in=body.expires_in
    )
    return UserRead.model_validate(user)


@router.post(
    "/users/{user_id}/unban",
    response_model=UserRead,
    responses={**_GUARDED, 404: _PROBLEM},
    summary="Lift a user's ban",
)
async def unban_user(
    user_id: UUID, ctx: AdminAuthDep, admin: AdminServiceDep
) -> UserRead:
    return UserRead.model_validate(await admin.unban_user(ctx, user_id))


@router.delete(
    "/users/{user_id}",
    response_model=StatusResponse,
    responses={**_GUARDED, 400: _PROBLEM, 404: _PROBLEM},
    summary="Permanently remove a user",
)
async def remove_user(
    user_id: UUID, ctx: AdminAuthDep, admin: AdminServiceDep
) -> StatusResponse:
    await admin.remove_user(ctx, user_id)
    return StatusResponse()


# --- sessions ----------------------------------------------------------------------------


@router.get(
    "/users/{user_id}/sessions",
    response_model=list[SessionRead],
    responses={**_GUARDED, 404: _PROBLEM},
    summary="List a user's active sessions",
)
async def list_user_sessions(
    user_id: UUID, ctx: AdminAuthDep, admin: AdminServiceDep
) -> list[SessionRead]:
    return [
        SessionRead.model_validate(s)
        for s in await admin.list_user_sessions(ctx, user_id)
    ]


@router.post(
    "/revoke-user-session",
    response_model=StatusResponse,
    responses=_GUARDED,
    summary="Revoke a session by token",
)
async def revoke_user_session(
    body: RevokeSessionRequest, ctx: AdminAuthDep, admin: AdminServiceDep
) -> StatusResponse:
    await admin.revoke_user_session(ctx, body.token)
    return StatusResponse()


@router.post(
    "/users/{user_id}/revoke-sessions",
    response_model=RevokedCountResponse,
    responses={**_GUARDED, 404: _PROBLEM},
    summary="Revoke all of a user's sessions",
)
async def revoke_user_sessions(
    user_id: UUID, ctx: AdminAuthDep, admin: AdminServiceDep
) -> RevokedCountResponse:
    return RevokedCountResponse(revoked=await admin.revoke_user_sessions(ctx, user_id))


# --- impersonation -----------------------------------------------------------------------


@router.post(
    "/users/{user_id}/impersonate",
    response_model=ImpersonateResponse,
    responses={**_GUARDED, 400: _PROBLEM, 404: _PROBLEM},
    summary="Start an impersonation session for a user",
    description=(
        "Returns a time-boxed session acting as the target user and switches the session cookie to it. "
        "Keep the admin token to resume once impersonation ends."
    ),
)
async def impersonate_user(
    user_id: UUID,
    response: Response,
    ctx: AdminAuthDep,
    admin: AdminServiceDep,
    settings: AuthSettingsDep,
    client: ClientInfoDep,
) -> ImpersonateResponse:
    target, session = await admin.impersonate(ctx, user_id, client)
    set_session_cookie(response, settings, session)
    return ImpersonateResponse(
        token=session.token,
        session=SessionRead.model_validate(session),
        user=UserRead.model_validate(target),
    )


@router.post(
    "/stop-impersonating",
    response_model=StatusResponse,
    responses={400: _PROBLEM, 401: _PROBLEM},
    summary="End the current impersonation session",
)
async def stop_impersonating(
    response: Response,
    ctx: SessionAuthDep,
    admin: AdminServiceDep,
    settings: AuthSettingsDep,
) -> StatusResponse:
    await admin.stop_impersonating(ctx)
    clear_session_cookie(response, settings)
    return StatusResponse()
