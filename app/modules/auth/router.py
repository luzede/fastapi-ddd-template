"""Core auth endpoints (better-auth base routes: sign-up/in/out, session, password, email)."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from app.modules.auth.schemas import (
    ChangePasswordBody,
    SignUpBody,
    TokenResponse,
)
from app.modules.auth.service import AuthServiceDep
from app.modules.user.dependencies import CurrentUserIdDep
from app.shared.exceptions.constants import (
    PROBLEM_400,
    PROBLEM_401,
    PROBLEM_404,
    PROBLEM_409,
    PROBLEM_422,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token", response_model=TokenResponse, responses={401: PROBLEM_401})
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    auth_service: AuthServiceDep,
) -> TokenResponse:
    user = await auth_service.sign_in(
        email=form_data.username, password=form_data.password
    )

    return TokenResponse(access_token=auth_service.create_access_token(user))


@router.post(
    "/sign-up/email",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    responses={400: PROBLEM_400, 409: PROBLEM_409, 422: PROBLEM_422},
    summary="Register with email and password",
)
async def sign_up(
    body: SignUpBody,
    auth_service: AuthServiceDep,
) -> TokenResponse:
    new_user = await auth_service.sign_up(
        email=body.email,
        password=body.password,
        name=body.name,
    )

    return TokenResponse(access_token=auth_service.create_access_token(new_user))


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={400: PROBLEM_400, 401: PROBLEM_401, 404: PROBLEM_404, 422: PROBLEM_422},
    summary="Change password (requires current password)",
)
async def change_password(
    body: ChangePasswordBody,
    cui: CurrentUserIdDep,
    auth_service: AuthServiceDep,
):
    await auth_service.change_password(
        user_id=cui,
        current_password=body.current_password,
        new_password=body.new_password,
    )
