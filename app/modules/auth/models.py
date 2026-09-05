"""Auth tables (better-auth core + jwt/admin/apikey plugins).

`id`, `created_at`, `updated_at` and constraint naming come from `Base`.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.db.base import Base

if TYPE_CHECKING:
    from app.modules.users.models import User


class Session(Base):
    __tablename__ = "session"
    __table_args__ = (
        UniqueConstraint("token"),
        Index(None, "user_id"),
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    token: Mapped[str] = mapped_column(String(128), nullable=False)
    """Opaque, high-entropy bearer secret. Stored in clear so revocation-by-token is a direct lookup."""
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )

    # admin plugin
    impersonated_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL")
    )
    """Admin who created this session on behalf of `user_id`; NULL for ordinary sessions."""

    user: Mapped[User] = relationship(back_populates="sessions", foreign_keys=[user_id])


class Account(Base):
    """A credential/provider link. The `credential` provider stores the password hash."""

    __tablename__ = "account"
    __table_args__ = (Index(None, "user_id"),)

    account_id: Mapped[str] = mapped_column(Text, nullable=False)
    """Provider-side subject. For the credential provider this is the user's id."""
    provider_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    access_token: Mapped[str | None] = mapped_column(Text)
    refresh_token: Mapped[str | None] = mapped_column(Text)
    id_token: Mapped[str | None] = mapped_column(Text)
    access_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    refresh_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    scope: Mapped[str | None] = mapped_column(Text)
    password: Mapped[str | None] = mapped_column(Text)

    user: Mapped[User] = relationship(back_populates="accounts")


class Verification(Base):
    """Short-lived, single-use tokens (email verification, password reset, email change)."""

    __tablename__ = "verification"
    __table_args__ = (Index(None, "identifier"),)

    identifier: Mapped[str] = mapped_column(Text, nullable=False)
    """Purpose-prefixed lookup key, e.g. `email-verification:<hash>` or `reset-password:<hash>`."""
    value: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class Jwks(Base):
    """Asymmetric signing key pair. `private_key` is encrypted at rest with `AUTH__SECRET`."""

    __tablename__ = "jwks"

    public_key: Mapped[str] = mapped_column(Text, nullable=False)
    """Public JWK as JSON."""
    private_key: Mapped[str] = mapped_column(Text, nullable=False)
    """Encrypted private JWK (see `auth.security.encrypt`)."""
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    """Set when the key is rotated out; it stays published for the grace period."""
    alg: Mapped[str | None] = mapped_column(String(16))
    crv: Mapped[str | None] = mapped_column(String(16))


class ApiKey(Base):
    __tablename__ = "apikey"
    __table_args__ = (
        Index(None, "config_id"),
        Index(None, "reference_id"),
        Index(None, "key"),
    )

    config_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default="default", server_default="default"
    )
    name: Mapped[str | None] = mapped_column(Text)
    start: Mapped[str | None] = mapped_column(String(16))
    """First characters of the plaintext key, for display."""
    reference_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    prefix: Mapped[str | None] = mapped_column(String(32))
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    """SHA-256 (base64url, unpadded) of the plaintext key."""

    # quota (refill)
    refill_interval: Mapped[int | None] = mapped_column(Integer)
    """Milliseconds between refills."""
    refill_amount: Mapped[int | None] = mapped_column(Integer)
    last_refill_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    remaining: Mapped[int | None] = mapped_column(Integer)
    """NULL means unlimited."""

    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )

    # sliding-window rate limit
    rate_limit_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    rate_limit_time_window: Mapped[int | None] = mapped_column(Integer)
    """Milliseconds."""
    rate_limit_max: Mapped[int | None] = mapped_column(Integer)
    request_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_request: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    permissions: Mapped[str | None] = mapped_column(Text)
    """JSON object `{resource: [action, ...]}`."""
    metadata_: Mapped[str | None] = mapped_column("metadata", Text)
    """JSON blob. Attribute is `metadata_` because `Base.metadata` is the SQLAlchemy registry."""

    user: Mapped[User] = relationship(back_populates="api_keys")
