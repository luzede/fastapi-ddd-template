"""Self-service profile updates and account deletion."""

import logging

from app.modules.auth.constants import AuthErrorCode
from app.modules.auth.models import Session, User
from app.modules.auth.repository import AccountRepository, UserRepository
from app.modules.auth.services.credential import CredentialService
from app.modules.auth.services.session import SessionService
from app.shared.exceptions import AuthorizationError, BadRequestError

logger = logging.getLogger(__name__)


class AccountService:
    def __init__(
        self,
        *,
        users: UserRepository,
        accounts: AccountRepository,
        sessions: SessionService,
        credentials: CredentialService,
    ):
        self._users = users
        self._accounts = accounts
        self._sessions = sessions
        self._credentials = credentials

    async def update_profile(
        self, user: User, *, name: str | None, image: str | None, image_set: bool
    ) -> User:
        changes: dict[str, object] = {}
        if name is not None:
            changes["name"] = name
        if image_set:
            changes["image"] = image
        if not changes:
            return user
        return await self._users.update(user, **changes)

    async def delete_account(
        self, *, user: User, session: Session, password: str | None
    ) -> None:
        """Requires the password when the account has one; otherwise the session must be fresh."""
        account = await self._accounts.get_credential_account(user.id)
        if account is not None and account.password is not None:
            if password is None:
                raise BadRequestError(
                    "Password is required to delete this account",
                    code=AuthErrorCode.INVALID_PASSWORD,
                )
            await self._credentials.check_password(user.id, password)
        elif not self._sessions.is_fresh(session):
            raise AuthorizationError(
                "Please sign in again to delete your account",
                code=AuthErrorCode.SESSION_NOT_FRESH,
            )
        # FK cascades remove sessions, accounts and api keys
        await self._users.delete(user)
        logger.info("user_deleted", extra={"user_id": str(user.id)})
