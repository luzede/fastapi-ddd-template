"""Persistence for auth aggregates."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.user.model import User
from app.shared.db.repository import AsyncRepository
from app.shared.db.session import SessionDep


class UserRepository(AsyncRepository[User]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, User)

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.email == email.lower())
        )
        return result.scalar_one_or_none()

    async def email_exists(self, email: str) -> bool:
        result = await self.session.execute(
            select(exists().where(User.email == email.lower()))
        )
        return result.scalar_one()


async def get_user_repository(session: SessionDep) -> UserRepository:
    return UserRepository(session)


type UserRepositoryDep = Annotated[UserRepository, Depends(get_user_repository)]
