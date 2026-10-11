from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password_hash: str
    roles: list[str] = Field(default_factory=list)
