"""User aggregate (better-auth `user` table, extended with admin-plugin fields)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String, Text, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.db.base import Base

if TYPE_CHECKING:
    from app.modules.auth.models import Account, ApiKey, Session


class User(Base):
    __tablename__ = "user"
    __table_args__ = (UniqueConstraint("email"),)

    name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    email_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    image: Mapped[str | None] = mapped_column(Text)

    # admin plugin
    role: Mapped[str | None] = mapped_column(Text)
    """Comma-separated role list (better-auth convention), e.g. "admin" or "admin,user"."""
    banned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    ban_reason: Mapped[str | None] = mapped_column(Text)
    ban_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    sessions: Mapped[list[Session]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        # `session` also has `impersonated_by → user.id`; disambiguate the ownership path
        foreign_keys="Session.user_id",
    )
    accounts: Mapped[list[Account]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    api_keys: Mapped[list[ApiKey]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )

    @property
    def roles(self) -> list[str]:
        if not self.role:
            return []
        return [r.strip() for r in self.role.split(",") if r.strip()]

    def is_currently_banned(self, now: datetime) -> bool:
        """A ban with an elapsed `ban_expires` is treated as lifted."""
        if not self.banned:
            return False
        return self.ban_expires is None or self.ban_expires > now
