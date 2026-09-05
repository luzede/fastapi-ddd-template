"""Opaque-token session lifecycle (better-auth core session semantics)."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.core.config import SessionSettings
from app.modules.auth.models import Session
from app.modules.auth.repository import SessionRepository
from app.modules.auth.security import generate_session_token
from app.modules.users.models import User


@dataclass(slots=True, frozen=True)
class ClientInfo:
    ip_address: str | None
    user_agent: str | None


@dataclass(slots=True)
class AuthContext:
    """The resolved principal for a request."""

    user: User
    session: Session
    via_api_key: bool = False
    """True when the principal was established from an API key (synthetic session, never persisted)."""

    @property
    def is_impersonation(self) -> bool:
        return self.session.impersonated_by is not None


class SessionService:
    def __init__(self, repo: SessionRepository, settings: SessionSettings):
        self._repo = repo
        self._settings = settings

    async def create(
        self,
        user_id: UUID,
        client: ClientInfo,
        *,
        ttl_seconds: int | None = None,
        impersonated_by: UUID | None = None,
    ) -> Session:
        ttl = ttl_seconds if ttl_seconds is not None else self._settings.ttl_seconds
        return await self._repo.create(
            user_id=user_id,
            token=generate_session_token(),
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl),
            ip_address=client.ip_address,
            user_agent=client.user_agent,
            impersonated_by=impersonated_by,
        )

    async def resolve(self, token: str) -> Session | None:
        """Look up a live session and apply sliding expiry (`update_age`)."""
        session = await self._repo.get_by_token(token)
        now = datetime.now(UTC)
        if session is None:
            return None
        if session.expires_at <= now:
            await self._repo.delete(session)
            return None

        # Impersonation sessions have a fixed lifetime and are never extended
        if session.impersonated_by is None and self._settings.update_age_seconds > 0:
            age_threshold = session.expires_at - timedelta(
                seconds=self._settings.ttl_seconds
            )
            if now - age_threshold >= timedelta(
                seconds=self._settings.update_age_seconds
            ):
                new_expiry = now + timedelta(seconds=self._settings.ttl_seconds)
                await self._repo.extend(session.id, new_expiry)
                session.expires_at = new_expiry
        return session

    def is_fresh(self, session: Session) -> bool:
        fresh_age = self._settings.fresh_age_seconds
        if fresh_age <= 0:
            return True
        # `created_at` is DB-assigned and timezone-aware
        return datetime.now(UTC) - session.created_at <= timedelta(seconds=fresh_age)

    async def list_active(self, user_id: UUID) -> list[Session]:
        return await self._repo.list_active_for_user(user_id, datetime.now(UTC))

    async def revoke(self, token: str) -> bool:
        return await self._repo.delete_by_token(token) > 0

    async def revoke_all(
        self, user_id: UUID, *, except_token: str | None = None
    ) -> int:
        return await self._repo.delete_for_user(user_id, except_token=except_token)
