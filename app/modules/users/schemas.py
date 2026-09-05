"""User API contracts."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, field_validator

type Name = Annotated[str, Field(min_length=1, max_length=128)]
type Email = Annotated[EmailStr, Field(max_length=320)]


def normalize_email(value: str) -> str:
    return value.strip().lower()


class UserRead(BaseModel):
    """Public representation of a user (mirrors better-auth `User`)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: str
    email_verified: bool
    image: str | None
    role: str | None
    banned: bool
    ban_reason: str | None
    ban_expires: datetime | None
    created_at: datetime
    updated_at: datetime


class UserUpdate(BaseModel):
    """Self-service profile update (`/update-user`). Email changes have their own flow."""

    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    image: HttpUrl | None = None


class ChangeEmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_email: Email

    @field_validator("new_email", mode="after")
    @classmethod
    def _normalize(cls, value: str) -> str:
        return normalize_email(value)


class ChangeEmailResponse(BaseModel):
    status: bool
    message: str


class DeleteUserRequest(BaseModel):
    """Requires the current password when the account has one; otherwise a fresh session suffices."""

    model_config = ConfigDict(extra="forbid")

    password: str | None = None


class StatusResponse(BaseModel):
    status: bool = True
