"""Persistence for auth aggregates."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.auth.models import Account, ApiKey, Jwks, Session, Verification
from app.shared.db.repository import AsyncRepository

CREDENTIAL_PROVIDER = "credential"


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
