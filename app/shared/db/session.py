from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from app.shared.state import AppStateDep


def get_async_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create async session factory bound to engine."""
    return async_sessionmaker(
        engine,
        expire_on_commit=False,  # Do not expire objects on commit to avoid lazy loading issues
        autocommit=False,
        autoflush=False,
    )


async def get_session(state: AppStateDep) -> AsyncGenerator[AsyncSession]:
    async with state.async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


SessionDep = Annotated[AsyncSession, Depends(get_session)]
