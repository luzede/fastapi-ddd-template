from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    create_async_engine,
)

from app.core.config import get_settings


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Create async database engine with connection pooling."""
    settings = get_settings()
    return create_async_engine(
        settings.app_database_url,
        echo=settings.db_echo,
    )
