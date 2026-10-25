"""Email + password credential provider: sign-up, sign-in, and password lifecycle."""

import asyncio
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends
from pwdlib import PasswordHash
from sqlalchemy.exc import IntegrityError

from app.core.config import get_auth_settings
from app.modules.auth.schemas import MyJWTClaims
from app.modules.user.model import User
from app.modules.user.repository import (
    UserRepository,
    UserRepositoryDep,
)
from app.shared.exceptions import (
    AuthenticationError,
    BadRequestError,
    ConflictError,
    ResourceNotFoundError,
)
from app.shared.exceptions.enums import ErrorCode

_password_hasher = PasswordHash.recommended()  # argon2id

# argon2id hash of a random string; used only to equalise timing on failed lookups
_DUMMY_HASH = _password_hasher.hash("timing-equalisation-dummy-password")


def validate_password_policy(password: str) -> None:
    settings = get_auth_settings()

    if len(password) < settings.password_min_length:
        raise BadRequestError(
            f"Password must be at least {settings.password_min_length} characters",
            code=ErrorCode.PASSWORD_TOO_SHORT,
        )
    if len(password) > settings.password_max_length:
        raise BadRequestError(
            f"Password must be at most {settings.password_max_length} characters",
            code=ErrorCode.PASSWORD_TOO_LONG,
        )


def email_conflict() -> ConflictError:
    return ConflictError(
        "A user with this email already exists",
        conflicting_field="email",
        code=ErrorCode.USER_ALREADY_EXISTS,
    )


class AuthService:
    def __init__(
        self,
        *,
        users: UserRepository,
    ):
        self._users = users

    async def verify_password(
        self, user_id: UUID, password: str, upgrade: bool = True
    ) -> User:
        """Verify `password` against the user's credential account; upgrades legacy hashes in place."""
        user = await self._users.get(user_id)
        if user is None:
            raise ResourceNotFoundError(
                resource_type=self._users.model.__name__, resource_id=str(user_id)
            )

        valid, updated_hash = await asyncio.to_thread(
            _password_hasher.verify_and_update, password, user.password_hash
        )
        if not valid:
            raise BadRequestError("Invalid password")
        if updated_hash and upgrade:
            await self._users.update(user, password_hash=updated_hash)
        return user

    async def sign_up(
        self,
        *,
        email: str,
        password: str,
        name: str,
    ) -> User:
        validate_password_policy(password)

        if await self._users.email_exists(email):
            raise email_conflict()

        try:
            password_hash = await asyncio.to_thread(_password_hasher.hash, password)
            user = await self._users.create(
                name=name,
                email=email.lower(),
                password_hash=password_hash,
            )

            return user
        except IntegrityError as exc:
            # Lost a race with a concurrent sign-up for the same email
            raise email_conflict() from exc

    async def sign_in(self, *, email: str, password: str) -> User:
        invalid = AuthenticationError(
            "Invalid email or password", code=ErrorCode.INVALID_EMAIL_OR_PASSWORD
        )
        user = await self._users.get_by_email(email)
        if user is None:
            # Burn comparable time so a missing user is indistinguishable from a wrong password
            await asyncio.to_thread(
                _password_hasher.verify_and_update, password, _DUMMY_HASH
            )
            raise invalid

        valid, updated_hash = await asyncio.to_thread(
            _password_hasher.verify_and_update, password, user.password_hash
        )
        if not valid:
            raise invalid
        if updated_hash:
            await self._users.update(user, password_hash=updated_hash)

        return user

    async def change_password(
        self,
        *,
        user_id: UUID,
        current_password: str,
        new_password: str,
    ) -> None:
        validate_password_policy(new_password)
        user = await self.verify_password(user_id, current_password, upgrade=False)
        new_password_hash = await asyncio.to_thread(_password_hasher.hash, new_password)
        await self._users.update(user, password_hash=new_password_hash)

    def create_access_token(self, user: User) -> str:
        """Create a JWT access token for the given user."""

        auth_settings = get_auth_settings()
        now = datetime.now(UTC)
        claims = MyJWTClaims(
            sub=user.id,
            exp=now + auth_settings.jwt_expires_in,
            iat=now,
            roles=user.roles,
        )

        payload = claims.to_payload()

        return jwt.encode(
            payload=dict(payload),
            key=auth_settings.jwt_secret.get_secret_value(),
            algorithm=auth_settings.jwt_algorithm,
        )


async def get_auth_service(
    user_repository: UserRepositoryDep,
) -> AuthService:
    return AuthService(users=user_repository)


type AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
