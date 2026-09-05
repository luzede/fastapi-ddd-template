"""Email + password credential provider: sign-up, sign-in, and password lifecycle."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.core.config import AuthSettings
from app.modules.auth.constants import AuthErrorCode
from app.modules.auth.context import ClientInfo
from app.modules.auth.mailer import Mailer
from app.modules.auth.models import Account, Session, User
from app.modules.auth.repository import (
    CREDENTIAL_PROVIDER,
    AccountRepository,
    UserRepository,
)
from app.modules.auth.security import hash_password, verify_password
from app.modules.auth.services.email_address import EmailAddressService
from app.modules.auth.services.session import SessionService
from app.modules.auth.services.verification import (
    VerificationPurpose,
    VerificationService,
)
from app.shared.exceptions import (
    AuthenticationError,
    AuthorizationError,
    BadRequestError,
    ConflictError,
)

# argon2id hash of a random string; used only to equalise timing on failed lookups
_DUMMY_HASH = hash_password("timing-equalisation-dummy-password")


@dataclass(slots=True)
class SignInResult:
    user: User
    session: Session


@dataclass(slots=True)
class SignUpResult:
    user: User
    session: Session | None
    """None when email verification is required before the first sign-in."""


def validate_password_policy(settings: AuthSettings, password: str) -> None:
    ep = settings.email_password
    if len(password) < ep.password_min_length:
        raise BadRequestError(
            f"Password must be at least {ep.password_min_length} characters",
            code=AuthErrorCode.PASSWORD_TOO_SHORT,
        )
    if len(password) > ep.password_max_length:
        raise BadRequestError(
            f"Password must be at most {ep.password_max_length} characters",
            code=AuthErrorCode.PASSWORD_TOO_LONG,
        )


def email_conflict() -> ConflictError:
    return ConflictError(
        "A user with this email already exists",
        conflicting_field="email",
        code=AuthErrorCode.USER_ALREADY_EXISTS,
    )


class CredentialService:
    def __init__(
        self,
        *,
        settings: AuthSettings,
        users: UserRepository,
        accounts: AccountRepository,
        sessions: SessionService,
        verifications: VerificationService,
        email_address: EmailAddressService,
        mailer: Mailer,
    ):
        self._settings = settings
        self._users = users
        self._accounts = accounts
        self._sessions = sessions
        self._verifications = verifications
        self._email_address = email_address
        self._mailer = mailer

    async def check_password(self, user_id: UUID, password: str) -> Account:
        """Verify `password` against the user's credential account; upgrades legacy hashes in place."""
        account = await self._accounts.get_credential_account(user_id)
        if account is None or account.password is None:
            raise BadRequestError(
                "This account has no password set",
                code=AuthErrorCode.CREDENTIAL_ACCOUNT_NOT_FOUND,
            )
        valid, upgraded = verify_password(password, account.password)
        if not valid:
            raise BadRequestError(
                "Invalid password", code=AuthErrorCode.INVALID_PASSWORD
            )
        if upgraded:
            await self._accounts.update(account, password=upgraded)
        return account

    # --- sign up / sign in / sign out ---------------------------------------------------

    async def sign_up_email(
        self,
        *,
        email: str,
        password: str,
        name: str,
        image: str | None,
        client: ClientInfo,
    ) -> SignUpResult:
        validate_password_policy(self._settings, password)
        ep = self._settings.email_password

        if await self._users.email_exists(email):
            raise email_conflict()

        try:
            user = await self._users.create(
                email=email,
                name=name,
                image=image,
                email_verified=False,
                role=self._settings.admin.default_role,
            )
            await self._accounts.create(
                user_id=user.id,
                account_id=str(user.id),
                provider_id=CREDENTIAL_PROVIDER,
                password=hash_password(password),
            )
        except IntegrityError as exc:
            # Lost a race with a concurrent sign-up for the same email
            raise email_conflict() from exc

        if ep.send_verification_on_sign_up or ep.require_email_verification:
            await self._email_address.send_verification_email(user)

        if ep.require_email_verification:
            return SignUpResult(user=user, session=None)

        session = await self._sessions.create(user.id, client)
        return SignUpResult(user=user, session=session)

    async def sign_in_email(
        self, *, email: str, password: str, client: ClientInfo
    ) -> SignInResult:
        invalid = AuthenticationError(
            "Invalid email or password", code=AuthErrorCode.INVALID_EMAIL_OR_PASSWORD
        )
        user = await self._users.get_by_email(email)
        if user is None:
            # Burn comparable time so a missing user is indistinguishable from a wrong password
            verify_password(password, _DUMMY_HASH)
            raise invalid

        account = await self._accounts.get_credential_account(user.id)
        if account is None or account.password is None:
            verify_password(password, _DUMMY_HASH)
            raise invalid

        valid, upgraded = verify_password(password, account.password)
        if not valid:
            raise invalid
        if upgraded:
            await self._accounts.update(account, password=upgraded)

        now = datetime.now(UTC)
        if user.is_currently_banned(now):
            raise AuthorizationError(
                user.ban_reason or "You have been banned from this application",
                code=AuthErrorCode.BANNED_USER,
            )
        if user.banned and user.ban_expires is not None and user.ban_expires <= now:
            # Ban has lapsed: clear it so it stops showing in admin listings
            await self._users.update(
                user, banned=False, ban_reason=None, ban_expires=None
            )

        if (
            self._settings.email_password.require_email_verification
            and not user.email_verified
        ):
            await self._email_address.send_verification_email(user)
            raise AuthorizationError(
                "Email is not verified", code=AuthErrorCode.EMAIL_NOT_VERIFIED
            )

        session = await self._sessions.create(user.id, client)
        return SignInResult(user=user, session=session)

    async def sign_out(self, token: str) -> None:
        await self._sessions.revoke(token)

    # --- passwords ---------------------------------------------------------------------

    async def request_password_reset(self, email: str) -> None:
        """Always succeeds from the caller's perspective to avoid account enumeration."""
        user = await self._users.get_by_email(email)
        if user is None:
            return
        account = await self._accounts.get_credential_account(user.id)
        if account is None:
            return
        token = await self._verifications.issue(
            VerificationPurpose.PASSWORD_RESET,
            str(user.id),
            ttl_seconds=self._settings.email_password.password_reset_ttl_seconds,
        )
        url = f"{self._settings.email_password.reset_password_url}?token={token}"
        await self._mailer.send_password_reset(to=user.email, url=url, token=token)

    async def reset_password(self, *, token: str, new_password: str) -> None:
        validate_password_policy(self._settings, new_password)
        user_id_raw = await self._verifications.consume(
            VerificationPurpose.PASSWORD_RESET, token
        )
        if user_id_raw is None:
            raise BadRequestError(
                "Reset link is invalid or has expired", code=AuthErrorCode.INVALID_TOKEN
            )
        user_id = UUID(user_id_raw)
        account = await self._accounts.get_credential_account(user_id)
        if account is None:
            raise BadRequestError(
                "This account has no password set",
                code=AuthErrorCode.CREDENTIAL_ACCOUNT_NOT_FOUND,
            )
        await self._accounts.update(account, password=hash_password(new_password))
        # Credential change → every existing session is untrusted
        await self._sessions.revoke_all(user_id)

    async def change_password(
        self,
        *,
        user: User,
        current_token: str,
        current_password: str,
        new_password: str,
        revoke_other_sessions: bool,
    ) -> None:
        validate_password_policy(self._settings, new_password)
        account = await self.check_password(user.id, current_password)
        await self._accounts.update(account, password=hash_password(new_password))
        if revoke_other_sessions:
            await self._sessions.revoke_all(user.id, except_token=current_token)

    async def set_password(self, *, user: User, new_password: str) -> None:
        """For users who signed up via a provider and have no credential account yet."""
        validate_password_policy(self._settings, new_password)
        if await self._accounts.get_credential_account(user.id) is not None:
            raise BadRequestError(
                "User already has a password; use change-password",
                code=AuthErrorCode.USER_ALREADY_HAS_PASSWORD,
            )
        await self._accounts.create(
            user_id=user.id,
            account_id=str(user.id),
            provider_id=CREDENTIAL_PROVIDER,
            password=hash_password(new_password),
        )

    async def verify_password(self, *, user: User, password: str) -> None:
        await self.check_password(user.id, password)
