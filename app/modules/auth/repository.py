"""Persistence for auth aggregates."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import ColumnElement, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.auth.models import Account, ApiKey, Jwks, Session, User, Verification
from app.shared.db.repository import AsyncRepository

CREDENTIAL_PROVIDER = "credential"

type UserSortField = Literal["created_at", "updated_at", "email", "name", "role"]
type SearchField = Literal["email", "name"]
type SearchOperator = Literal["contains", "starts_with", "ends_with"]


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _as_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    return value.strip().lower() in {"1", "true", "yes"}


class UserRepository(AsyncRepository[User]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, User)

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.email == email.lower())
        )
        return result.scalar_one_or_none()

    async def email_exists(self, email: str, *, exclude_id: UUID | None = None) -> bool:
        stmt = select(User.id).where(User.email == email.lower())
        if exclude_id is not None:
            stmt = stmt.where(User.id != exclude_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def search(
        self,
        *,
        search_value: str | None = None,
        search_field: SearchField = "email",
        search_operator: SearchOperator = "contains",
        filter_field: Literal["role", "banned", "email_verified"] | None = None,
        filter_value: str | bool | None = None,
        sort_by: UserSortField = "created_at",
        sort_direction: Literal["asc", "desc"] = "desc",
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[User], int]:
        """Offset-paginated admin listing (mirrors better-auth `list-users`).

        Returns `(users, total)` where `total` counts every row matching the filters.
        """
        conditions: list[ColumnElement[bool]] = []

        if search_value:
            column = User.email if search_field == "email" else User.name
            pattern = _escape_like(search_value)
            match search_operator:
                case "contains":
                    conditions.append(column.ilike(f"%{pattern}%", escape="\\"))
                case "starts_with":
                    conditions.append(column.ilike(f"{pattern}%", escape="\\"))
                case "ends_with":
                    conditions.append(column.ilike(f"%{pattern}", escape="\\"))

        if filter_field is not None and filter_value is not None:
            match filter_field:
                case "role":
                    conditions.append(User.role == str(filter_value))
                case "banned":
                    conditions.append(User.banned == _as_bool(filter_value))
                case "email_verified":
                    conditions.append(User.email_verified == _as_bool(filter_value))

        base = select(User).where(*conditions)
        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self.session.execute(count_stmt)).scalar_one()

        sort_column = getattr(User, sort_by)
        order = sort_column.asc() if sort_direction == "asc" else sort_column.desc()
        # Secondary key on id keeps paging stable when sort_column has duplicates
        stmt = base.order_by(order, User.id.desc()).limit(limit).offset(offset)
        users = list((await self.session.execute(stmt)).scalars().all())
        return users, total


class SessionRepository(AsyncRepository[Session]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Session)

    async def get_by_token(self, token: str) -> Session | None:
        result = await self.session.execute(
            select(Session)
            .options(selectinload(Session.user))
            .where(Session.token == token)
        )
        return result.scalar_one_or_none()

    async def list_active_for_user(self, user_id: UUID, now: datetime) -> list[Session]:
        result = await self.session.execute(
            select(Session)
            .where(Session.user_id == user_id, Session.expires_at > now)
            .order_by(Session.created_at.desc())
        )
        return list(result.scalars().all())

    async def delete_by_token(self, token: str) -> int:
        result = await self.session.execute(
            delete(Session).where(Session.token == token)
        )
        await self.session.flush()
        return result.rowcount

    async def delete_for_user(
        self, user_id: UUID, *, except_token: str | None = None
    ) -> int:
        stmt = delete(Session).where(Session.user_id == user_id)
        if except_token is not None:
            stmt = stmt.where(Session.token != except_token)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    async def extend(self, session_id: UUID, expires_at: datetime) -> None:
        await self.session.execute(
            update(Session)
            .where(Session.id == session_id)
            .values(expires_at=expires_at)
        )
        await self.session.flush()


class AccountRepository(AsyncRepository[Account]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Account)

    async def get_credential_account(self, user_id: UUID) -> Account | None:
        result = await self.session.execute(
            select(Account).where(
                Account.user_id == user_id, Account.provider_id == CREDENTIAL_PROVIDER
            )
        )
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: UUID) -> list[Account]:
        result = await self.session.execute(
            select(Account)
            .where(Account.user_id == user_id)
            .order_by(Account.created_at)
        )
        return list(result.scalars().all())


class VerificationRepository(AsyncRepository[Verification]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Verification)

    async def get_by_identifier(self, identifier: str) -> Verification | None:
        result = await self.session.execute(
            select(Verification)
            .where(Verification.identifier == identifier)
            .order_by(Verification.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def delete_by_identifier(self, identifier: str) -> None:
        await self.session.execute(
            delete(Verification).where(Verification.identifier == identifier)
        )
        await self.session.flush()

    async def delete_expired(self, now: datetime) -> int:
        result = await self.session.execute(
            delete(Verification).where(Verification.expires_at <= now)
        )
        await self.session.flush()
        return result.rowcount


class JwksRepository(AsyncRepository[Jwks]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Jwks)

    async def list_all(self) -> list[Jwks]:
        result = await self.session.execute(
            select(Jwks).order_by(Jwks.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_latest_active(self) -> Jwks | None:
        result = await self.session.execute(
            select(Jwks)
            .where(Jwks.expires_at.is_(None))
            .order_by(Jwks.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


class ApiKeyRepository(AsyncRepository[ApiKey]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, ApiKey)

    async def get_by_hash(
        self, key_hash: str, *, for_update: bool = False
    ) -> ApiKey | None:
        stmt = select(ApiKey).where(ApiKey.key == key_hash)
        if for_update:
            # Serialises concurrent verifications of the same key so counters stay exact
            stmt = stmt.with_for_update()
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_user(self, key_id: UUID, user_id: UUID) -> ApiKey | None:
        result = await self.session.execute(
            select(ApiKey).where(ApiKey.id == key_id, ApiKey.reference_id == user_id)
        )
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: UUID) -> list[ApiKey]:
        result = await self.session.execute(
            select(ApiKey)
            .where(ApiKey.reference_id == user_id)
            .order_by(ApiKey.created_at.desc())
        )
        return list(result.scalars().all())

    async def delete_for_user(self, user_id: UUID) -> int:
        result = await self.session.execute(
            delete(ApiKey).where(ApiKey.reference_id == user_id)
        )
        await self.session.flush()
        return result.rowcount
