from sqlalchemy import URL
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    create_async_engine,
)

from app.core.config import get_settings


def create_engine() -> AsyncEngine:
    """Create async database engine with connection pooling."""
    settings = get_settings()
    url = URL.create(
        drivername="postgresql+asyncpg",
        username=settings.db.username,
        password=settings.db.password.get_secret_value(),
        host=settings.db.host,
        port=settings.db.port,
        database=settings.db.name,
    )
    return create_async_engine(
        url,
        echo=settings.db.echo,
    )
