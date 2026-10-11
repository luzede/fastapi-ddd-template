"""Auth tables (better-auth core + jwt/admin/apikey plugins).

`id`, `created_at`, `updated_at` and constraint naming come from `Base`.
"""

from __future__ import annotations

from sqlalchemy import (
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db.base import Base


class User(Base):
    __tablename__ = "user"

    name: Mapped[str]
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str]

    roles: Mapped[list[str]] = mapped_column(
        JSONB(none_as_null=True),
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    """List of roles for the user."""
