"""Admin plugin: user administration, moderation and impersonation."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.core.config import AuthSettings
from app.modules.auth.access_control import AccessControl, Permissions
from app.modules.auth.constants import AuthErrorCode
from app.modules.auth.models import Session
from app.modules.auth.repository import CREDENTIAL_PROVIDER, AccountRepository
from app.modules.auth.security import hash_password
from app.modules.auth.services.session import AuthContext, ClientInfo, SessionService
from app.modules.users.models import User
from app.modules.users.repository import (
    SearchField,
    SearchOperator,
    UserRepository,
    UserSortField,
)
from app.shared.exceptions import (
    AuthorizationError,
    BadRequestError,
    ConflictError,
    ResourceNotFoundError,
)

logger = logging.getLogger(__name__)


class AdminService:
    def __init__(
        self,
        *,
        settings: AuthSettings,
        access_control: AccessControl,
        users: UserRepository,
        accounts: AccountRepository,
        sessions: SessionService,
    ):
        self._settings = settings
        self._ac = access_control
        self._users = users
        self._accounts = accounts
        self._sessions = sessions

    # --- authorisation -----------------------------------------------------------------

    def require(self, actor: AuthContext, permissions: Permissions) -> None:
        if not self._ac.has_permission(
            user_id=actor.user.id, role=actor.user.role, permissions=permissions
        ):
            required = ", ".join(
                f"{r}:{a}" for r, acts in permissions.items() for a in acts
            )
            raise AuthorizationError(
                "You are not allowed to perform this action",
                required_permission=required,
                code=AuthErrorCode.YOU_ARE_NOT_ALLOWED_TO_PERFORM_THIS_ACTION,
            )

    def has_permission(self, actor: AuthContext, permissions: Permissions) -> bool:
        return self._ac.has_permission(
            user_id=actor.user.id, role=actor.user.role, permissions=permissions
        )

    async def _get_user(self, user_id: UUID) -> User:
        user = await self._users.get(user_id)
        if user is None:
            raise ResourceNotFoundError("User", str(user_id))
        return user

    @staticmethod
    def _normalise_role(role: str | list[str]) -> str:
        roles = [role] if isinstance(role, str) else role
        cleaned = [r.strip() for r in roles if r.strip()]
        if not cleaned:
            raise BadRequestError("At least one role is required")
        return ",".join(cleaned)

    # --- users -------------------------------------------------------------------------

    async def create_user(
        self,
        actor: AuthContext,
        *,
        email: str,
        password: str,
        name: str,
        role: str | list[str] | None,
        image: str | None = None,
        email_verified: bool = False,
    ) -> User:
        self.require(actor, {"user": ["create"]})
        if await self._users.email_exists(email):
            raise ConflictError(
                "A user with this email already exists",
                conflicting_field="email",
                code=AuthErrorCode.USER_ALREADY_EXISTS,
            )
        try:
            user = await self._users.create(
                email=email,
                name=name,
                image=image,
                email_verified=email_verified,
                role=self._normalise_role(role)
                if role
                else self._settings.admin.default_role,
            )
            await self._accounts.create(
                user_id=user.id,
                account_id=str(user.id),
                provider_id=CREDENTIAL_PROVIDER,
                password=hash_password(password),
            )
        except IntegrityError as exc:
            raise ConflictError(
                "A user with this email already exists",
                conflicting_field="email",
                code=AuthErrorCode.USER_ALREADY_EXISTS,
            ) from exc
        logger.info(
            "admin_user_created",
            extra={"actor": str(actor.user.id), "user": str(user.id)},
        )
        return user

    async def list_users(
        self,
        actor: AuthContext,
        *,
        search_value: str | None,
        search_field: SearchField,
        search_operator: SearchOperator,
        filter_field: Literal["role", "banned", "email_verified"] | None,
        filter_value: str | bool | None,
        sort_by: UserSortField,
        sort_direction: Literal["asc", "desc"],
        limit: int,
        offset: int,
    ) -> tuple[list[User], int]:
        self.require(actor, {"user": ["list"]})
        return await self._users.search(
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

    async def get_user(self, actor: AuthContext, user_id: UUID) -> User:
        self.require(actor, {"user": ["get"]})
        return await self._get_user(user_id)

    async def update_user(
        self,
        actor: AuthContext,
        user_id: UUID,
        *,
        name: str | None,
        image: str | None,
        image_set: bool,
        email: str | None,
        email_verified: bool | None,
    ) -> User:
        self.require(actor, {"user": ["update"]})
        user = await self._get_user(user_id)
        changes: dict[str, object] = {}
        if name is not None:
            changes["name"] = name
        if image_set:
            changes["image"] = image
        if email is not None and email != user.email:
            self.require(actor, {"user": ["set-email"]})
            if await self._users.email_exists(email, exclude_id=user.id):
                raise ConflictError(
                    "A user with this email already exists",
                    conflicting_field="email",
                    code=AuthErrorCode.USER_ALREADY_EXISTS,
                )
            changes["email"] = email
        if email_verified is not None:
            changes["email_verified"] = email_verified
        if not changes:
            return user
        return await self._users.update(user, **changes)

    async def set_role(
        self, actor: AuthContext, user_id: UUID, role: str | list[str]
    ) -> User:
        self.require(actor, {"user": ["set-role"]})
        user = await self._get_user(user_id)
        return await self._users.update(user, role=self._normalise_role(role))

    async def set_password(
        self, actor: AuthContext, user_id: UUID, new_password: str
    ) -> None:
        self.require(actor, {"user": ["set-password"]})
        ep = self._settings.email_password
        if not (ep.password_min_length <= len(new_password) <= ep.password_max_length):
            raise BadRequestError(
                f"Password must be between {ep.password_min_length} and "
                f"{ep.password_max_length} characters",
                code=AuthErrorCode.PASSWORD_TOO_SHORT,
            )
        user = await self._get_user(user_id)
        account = await self._accounts.get_credential_account(user.id)
        hashed = hash_password(new_password)
        if account is None:
            await self._accounts.create(
                user_id=user.id,
                account_id=str(user.id),
                provider_id=CREDENTIAL_PROVIDER,
                password=hashed,
            )
        else:
            await self._accounts.update(account, password=hashed)
        await self._sessions.revoke_all(user.id)

    async def remove_user(self, actor: AuthContext, user_id: UUID) -> None:
        self.require(actor, {"user": ["delete"]})
        if user_id == actor.user.id:
            raise BadRequestError(
                "You cannot remove yourself",
                code=AuthErrorCode.YOU_CANNOT_REMOVE_YOURSELF,
            )
        user = await self._get_user(user_id)
        await self._users.delete(user)
        logger.info(
            "admin_user_removed",
            extra={"actor": str(actor.user.id), "user": str(user_id)},
        )

    # --- moderation --------------------------------------------------------------------

    async def ban_user(
        self,
        actor: AuthContext,
        user_id: UUID,
        *,
        reason: str | None,
        ban_expires_in: int | None,
    ) -> User:
        self.require(actor, {"user": ["ban"]})
        if user_id == actor.user.id:
            raise BadRequestError(
                "You cannot ban yourself", code=AuthErrorCode.YOU_CANNOT_BAN_YOURSELF
            )
        user = await self._get_user(user_id)
        expires = (
            datetime.now(UTC) + timedelta(seconds=ban_expires_in)
            if ban_expires_in is not None
            else None
        )
        user = await self._users.update(
            user, banned=True, ban_reason=reason or "No reason", ban_expires=expires
        )
        if self._settings.admin.bans_revoke_sessions:
            await self._sessions.revoke_all(user.id)
        return user

    async def unban_user(self, actor: AuthContext, user_id: UUID) -> User:
        self.require(actor, {"user": ["ban"]})
        user = await self._get_user(user_id)
        return await self._users.update(
            user, banned=False, ban_reason=None, ban_expires=None
        )

    # --- sessions ----------------------------------------------------------------------

    async def list_user_sessions(
        self, actor: AuthContext, user_id: UUID
    ) -> list[Session]:
        self.require(actor, {"session": ["list"]})
        await self._get_user(user_id)
        return await self._sessions.list_active(user_id)

    async def revoke_user_session(self, actor: AuthContext, session_token: str) -> bool:
        self.require(actor, {"session": ["revoke"]})
        return await self._sessions.revoke(session_token)

    async def revoke_user_sessions(self, actor: AuthContext, user_id: UUID) -> int:
        self.require(actor, {"session": ["revoke"]})
        await self._get_user(user_id)
        return await self._sessions.revoke_all(user_id)

    # --- impersonation -----------------------------------------------------------------

    async def impersonate(
        self, actor: AuthContext, user_id: UUID, client: ClientInfo
    ) -> tuple[User, Session]:
        if not self.has_permission(actor, {"user": ["impersonate"]}):
            raise AuthorizationError(
                "You are not allowed to impersonate users",
                code=AuthErrorCode.YOU_ARE_NOT_ALLOWED_TO_IMPERSONATE_USERS,
            )
        if actor.is_impersonation:
            raise BadRequestError("Already impersonating; stop impersonating first")
        target = await self._get_user(user_id)

        if self._ac.is_admin(user_id=target.id, role=target.role):
            allowed = (
                self._settings.admin.allow_impersonating_admins
                or self.has_permission(actor, {"user": ["impersonate-admins"]})
            )
            if not allowed:
                raise AuthorizationError(
                    "You cannot impersonate admins",
                    code=AuthErrorCode.YOU_CANNOT_IMPERSONATE_ADMINS,
                )

        session = await self._sessions.create(
            target.id,
            client,
            ttl_seconds=self._settings.admin.impersonation_session_ttl_seconds,
            impersonated_by=actor.user.id,
        )
        logger.info(
            "impersonation_started",
            extra={"actor": str(actor.user.id), "target": str(target.id)},
        )
        return target, session

    async def stop_impersonating(self, ctx: AuthContext) -> None:
        if not ctx.is_impersonation:
            raise BadRequestError(
                "Not impersonating", code=AuthErrorCode.NOT_IMPERSONATING
            )
        await self._sessions.revoke(ctx.session.token)
