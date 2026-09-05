"""API key plugin endpoints.

better-auth marks quota/rate-limit/permission fields as *server-only* (not settable from the
client SDK). Here the equivalent is: those fields are accepted only from admins.
"""

from uuid import UUID

from fastapi import APIRouter, status

from app.modules.auth.access_control import AccessControl
from app.modules.auth.constants import AuthErrorCode
from app.modules.auth.dependencies import (
    AccessControlDep,
    AdminAuthDep,
    ApiKeyServiceDep,
    SessionAuthDep,
)
from app.modules.auth.models import ApiKey
from app.modules.auth.schemas import (
    ApiKeyCreated,
    ApiKeyCreateRequest,
    ApiKeyRead,
    ApiKeyUpdateRequest,
    ApiKeyVerifyError,
    ApiKeyVerifyRequest,
    ApiKeyVerifyResponse,
)
from app.modules.auth.services.api_key import ApiKeyService
from app.modules.auth.services.session import AuthContext
from app.modules.users.schemas import StatusResponse
from app.shared.exceptions import AuthorizationError
from app.shared.exceptions.schemas import ProblemDetail

router = APIRouter(prefix="/api-key", tags=["auth:api-key"])

_PROBLEM = {"model": ProblemDetail}


def _to_read(record: ApiKey) -> ApiKeyRead:
    return ApiKeyRead(
        id=record.id,
        config_id=record.config_id,
        name=record.name,
        start=record.start,
        prefix=record.prefix,
        reference_id=record.reference_id,
        enabled=record.enabled,
        remaining=record.remaining,
        refill_interval=record.refill_interval,
        refill_amount=record.refill_amount,
        last_refill_at=record.last_refill_at,
        rate_limit_enabled=record.rate_limit_enabled,
        rate_limit_time_window=record.rate_limit_time_window,
        rate_limit_max=record.rate_limit_max,
        request_count=record.request_count,
        last_request=record.last_request,
        expires_at=record.expires_at,
        permissions=ApiKeyService.permissions_of(record),
        metadata=ApiKeyService.metadata_of(record),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _require_admin_for_privileged(
    ctx: AuthContext, ac: AccessControl, privileged: bool
) -> None:
    if privileged and not ac.is_admin(user_id=ctx.user.id, role=ctx.user.role):
        raise AuthorizationError(
            "Quota, rate-limit and permission fields can only be set by an admin",
            code=AuthErrorCode.YOU_ARE_NOT_ALLOWED_TO_PERFORM_THIS_ACTION,
        )


@router.post(
    "/create",
    response_model=ApiKeyCreated,
    status_code=status.HTTP_201_CREATED,
    responses={400: _PROBLEM, 401: _PROBLEM, 403: _PROBLEM},
    summary="Create an API key for the current user",
)
async def create_api_key(
    body: ApiKeyCreateRequest,
    ctx: SessionAuthDep,
    ac: AccessControlDep,
    api_keys: ApiKeyServiceDep,
) -> ApiKeyCreated:
    _require_admin_for_privileged(ctx, ac, body.has_privileged_fields())
    record, plaintext = await api_keys.create(
        user_id=ctx.user.id,
        name=body.name,
        prefix=body.prefix,
        expires_in=body.expires_in,
        remaining=body.remaining,
        refill_amount=body.refill_amount,
        refill_interval=body.refill_interval,
        rate_limit_enabled=body.rate_limit_enabled,
        rate_limit_time_window=body.rate_limit_time_window,
        rate_limit_max=body.rate_limit_max,
        permissions=body.permissions,
        metadata=body.metadata,
    )
    return ApiKeyCreated(**_to_read(record).model_dump(), key=plaintext)


@router.get(
    "/list",
    response_model=list[ApiKeyRead],
    responses={401: _PROBLEM},
    summary="List the current user's API keys",
)
async def list_api_keys(
    ctx: SessionAuthDep, api_keys: ApiKeyServiceDep
) -> list[ApiKeyRead]:
    return [_to_read(k) for k in await api_keys.list_owned(ctx.user.id)]


@router.get(
    "/get/{key_id}",
    response_model=ApiKeyRead,
    responses={401: _PROBLEM, 404: _PROBLEM},
    summary="Get one of the current user's API keys",
)
async def get_api_key(
    key_id: UUID, ctx: SessionAuthDep, api_keys: ApiKeyServiceDep
) -> ApiKeyRead:
    return _to_read(await api_keys.get_owned(key_id, ctx.user.id))


@router.patch(
    "/update/{key_id}",
    response_model=ApiKeyRead,
    responses={400: _PROBLEM, 401: _PROBLEM, 403: _PROBLEM, 404: _PROBLEM},
    summary="Update one of the current user's API keys",
)
async def update_api_key(
    key_id: UUID,
    body: ApiKeyUpdateRequest,
    ctx: SessionAuthDep,
    ac: AccessControlDep,
    api_keys: ApiKeyServiceDep,
) -> ApiKeyRead:
    _require_admin_for_privileged(ctx, ac, body.has_privileged_fields())
    provided = body.model_dump(exclude_unset=True)
    record = await api_keys.update_owned(key_id, ctx.user.id, **provided)
    return _to_read(record)


@router.delete(
    "/delete/{key_id}",
    response_model=StatusResponse,
    responses={401: _PROBLEM, 404: _PROBLEM},
    summary="Delete one of the current user's API keys",
)
async def delete_api_key(
    key_id: UUID, ctx: SessionAuthDep, api_keys: ApiKeyServiceDep
) -> StatusResponse:
    await api_keys.delete_owned(key_id, ctx.user.id)
    return StatusResponse()


@router.post(
    "/verify",
    response_model=ApiKeyVerifyResponse,
    responses={401: _PROBLEM, 403: _PROBLEM},
    summary="Verify an API key (admin / server-to-server)",
    description=(
        "Consumes one request of the key's quota and rate-limit window, exactly like presenting "
        "the key in `x-api-key`. Server-only in better-auth; restricted to admins here."
    ),
)
async def verify_api_key(
    body: ApiKeyVerifyRequest, _: AdminAuthDep, api_keys: ApiKeyServiceDep
) -> ApiKeyVerifyResponse:
    result = await api_keys.verify(body.key, required_permissions=body.permissions)
    return ApiKeyVerifyResponse(
        valid=result.valid,
        error=(
            ApiKeyVerifyError(
                code=result.error_code, message=result.error_message or ""
            )
            if result.error_code
            else None
        ),
        key=_to_read(result.key) if result.valid and result.key else None,
    )
