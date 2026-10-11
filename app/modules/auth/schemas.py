from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.modules.auth.types import MyJWTClaimsPayload


class SignUpBody(BaseModel):
    name: str
    email: EmailStr
    password: str


class ChangePasswordBody(BaseModel):
    current_password: str
    new_password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"


class MyJWTClaims(BaseModel):
    sub: UUID
    exp: datetime
    iat: datetime

    roles: list[str] = Field(default_factory=list)

    def to_payload(self) -> MyJWTClaimsPayload:
        payload: MyJWTClaimsPayload = {
            "sub": str(self.sub),
            "exp": int(self.exp.timestamp()),
            "iat": int(self.iat.timestamp()),
        }

        if self.roles:
            payload["roles"] = self.roles

        return payload
