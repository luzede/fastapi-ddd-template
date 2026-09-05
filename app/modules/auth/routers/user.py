"""Self-service user endpoints (better-auth `update-user`, `change-email`, `delete-user`, `list-accounts`).

Part of the auth aggregate's HTTP surface; served at `/users` to match client expectations.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.modules.auth.cookies import clear_session_cookie
from app.modules.auth.dependencies import (
    AccountServiceDep,
    AuthSettingsDep,
    EmailAddressServiceDep,
    get_account_repository,
)
from app.modules.auth.guards import (
    AuthDep,
    SessionAuthDep,
)
from app.modules.auth.repository import AccountRepository
from app.modules.auth.schemas import (
    AccountRead,
    ChangeEmailRequest,
    ChangeEmailResponse,
    DeleteUserRequest,
    UserRead,
    UserUpdate,
)
from app.shared.exceptions.schemas import ProblemDetail
from app.shared.schemas import StatusResponse

router = APIRouter(prefix="/users", tags=["users"])

_PROBLEM = {"model": ProblemDetail}


@router.get(
    "/me",
    response_model=UserRead,
    responses={401: _PROBLEM},
    summary="Current user",
)
async def get_me(ctx: AuthDep) -> UserRead:
    return UserRead.model_validate(ctx.user)


@router.patch(
    "/me",
    response_model=UserRead,
    responses={401: _PROBLEM},
    summary="Update the current user's profile",
)
async def update_me(
    body: UserUpdate, ctx: SessionAuthDep, account: AccountServiceDep
) -> UserRead:
    user = await account.update_profile(
        ctx.user,
        name=body.name,
        image=str(body.image) if body.image else None,
        image_set="image" in body.model_fields_set,
    )
    return UserRead.model_validate(user)


@router.post(
    "/me/change-email",
    response_model=ChangeEmailResponse,
    responses={400: _PROBLEM, 401: _PROBLEM, 409: _PROBLEM},
    summary="Change the current user's email",
    description=(
        "If the current email is verified, a confirmation link is sent to it and the change is applied "
        "when followed. Otherwise the change is applied immediately and the new address must be verified."
    ),
)
async def change_email(
    body: ChangeEmailRequest,
    ctx: SessionAuthDep,
    email_address: EmailAddressServiceDep,
) -> ChangeEmailResponse:
    sent = await email_address.request_email_change(ctx.user, body.new_email)
    return ChangeEmailResponse(
        status=True,
        message=(
            "Confirmation sent to your current email address"
            if sent
            else "Email updated; verification sent to the new address"
        ),
    )


@router.get(
    "/confirm-email-change",
    response_model=UserRead,
    responses={400: _PROBLEM, 409: _PROBLEM},
    summary="Confirm an email change (link target)",
)
async def confirm_email_change(
    token: Annotated[str, Query(min_length=16, max_length=256)],
    email_address: EmailAddressServiceDep,
) -> UserRead:
    return UserRead.model_validate(await email_address.confirm_email_change(token))


@router.get(
    "/me/accounts",
    response_model=list[AccountRead],
    responses={401: _PROBLEM},
    summary="Linked credential/provider accounts",
)
async def list_accounts(
    ctx: SessionAuthDep,
    accounts: Annotated[AccountRepository, Depends(get_account_repository)],
) -> list[AccountRead]:
    return [
        AccountRead.model_validate(a) for a in await accounts.list_for_user(ctx.user.id)
    ]


@router.delete(
    "/me",
    response_model=StatusResponse,
    responses={400: _PROBLEM, 401: _PROBLEM, 403: _PROBLEM},
    summary="Delete the current user",
    description="Requires the current password when one is set; otherwise a fresh session.",
)
async def delete_me(
    response: Response,
    ctx: SessionAuthDep,
    account: AccountServiceDep,
    settings: AuthSettingsDep,
    body: DeleteUserRequest | None = None,
) -> StatusResponse:
    await account.delete_account(
        user=ctx.user,
        session=ctx.session,
        password=body.password if body else None,
    )
    clear_session_cookie(response, settings)
    return StatusResponse()
