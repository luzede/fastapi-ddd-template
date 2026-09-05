"""Email verification and email change flows."""

from uuid import UUID

from app.core.config import AuthSettings
from app.modules.auth.constants import AuthErrorCode
from app.modules.auth.mailer import Mailer
from app.modules.auth.models import User
from app.modules.auth.repository import UserRepository
from app.modules.auth.services.verification import (
    VerificationPurpose,
    VerificationService,
)
from app.shared.exceptions import (
    BadRequestError,
    ConflictError,
    ResourceNotFoundError,
)


def email_conflict() -> ConflictError:
    return ConflictError(
        "A user with this email already exists",
        conflicting_field="email",
        code=AuthErrorCode.USER_ALREADY_EXISTS,
    )


class EmailAddressService:
    def __init__(
        self,
        *,
        settings: AuthSettings,
        users: UserRepository,
        verifications: VerificationService,
        mailer: Mailer,
    ):
        self._settings = settings
        self._users = users
        self._verifications = verifications
        self._mailer = mailer

    def _verify_email_url(self, token: str) -> str:
        base = (
            self._settings.email_password.verify_email_url
            or f"{self._settings.base_url}/api/v1/auth/verify-email"
        )
        return f"{base}?token={token}"

    async def send_verification_email(self, user: User) -> None:
        token = await self._verifications.issue(
            VerificationPurpose.EMAIL_VERIFICATION,
            user.email,
            ttl_seconds=self._settings.email_password.email_verification_ttl_seconds,
        )
        await self._mailer.send_verification_email(
            to=user.email, url=self._verify_email_url(token), token=token
        )

    async def verify_email(self, token: str) -> User:
        email = await self._verifications.consume(
            VerificationPurpose.EMAIL_VERIFICATION, token
        )
        if email is None:
            raise BadRequestError(
                "Verification link is invalid or has expired",
                code=AuthErrorCode.INVALID_TOKEN,
            )
        user = await self._users.get_by_email(email)
        if user is None:
            raise ResourceNotFoundError("User", email)
        if not user.email_verified:
            await self._users.update(user, email_verified=True)
        return user

    async def resend_verification_email(self, email: str) -> None:
        """Always succeeds from the caller's perspective to avoid account enumeration."""
        user = await self._users.get_by_email(email)
        if user is None or user.email_verified:
            return
        await self.send_verification_email(user)

    async def request_email_change(self, user: User, new_email: str) -> bool:
        """Returns True when confirmation was sent to current inbox; False if applied immediately."""
        if new_email == user.email:
            raise BadRequestError(
                "New email is the same as the current one",
                code=AuthErrorCode.EMAIL_CAN_NOT_BE_UPDATED,
            )
        if await self._users.email_exists(new_email, exclude_id=user.id):
            raise email_conflict()

        if not user.email_verified:
            await self._users.update(user, email=new_email, email_verified=False)
            await self.send_verification_email(user)
            return False

        token = await self._verifications.issue(
            VerificationPurpose.CHANGE_EMAIL,
            f"{user.id}:{new_email}",
            ttl_seconds=self._settings.email_password.email_verification_ttl_seconds,
        )
        await self._mailer.send_change_email_verification(
            to=user.email,
            new_email=new_email,
            url=self._verify_email_url(token),
            token=token,
        )
        return True

    async def confirm_email_change(self, token: str) -> User:
        value = await self._verifications.consume(
            VerificationPurpose.CHANGE_EMAIL, token
        )
        if value is None:
            raise BadRequestError(
                "Verification link is invalid or has expired",
                code=AuthErrorCode.INVALID_TOKEN,
            )
        user_id_raw, new_email = value.split(":", 1)
        user = await self._users.get(UUID(user_id_raw))
        if user is None:
            raise ResourceNotFoundError("User", user_id_raw)
        if await self._users.email_exists(new_email, exclude_id=user.id):
            raise email_conflict()
        # Confirmation came from the old, verified inbox → new address is treated as verified
        return await self._users.update(user, email=new_email, email_verified=True)
