from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.shared.db.session import create_async_session_factory
from app.shared.state import AppState


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state = AppState()

    # Initialize database engine
    app.state.db_engine = create_async_engine(
        settings.db.url,
        echo=settings.db.echo,
        pool_size=settings.db.pool_size,
        max_overflow=settings.db.max_overflow,
        pool_pre_ping=settings.db.pool_pre_ping,
        pool_recycle=settings.db.pool_recycle,
        pool_timeout=settings.db.pool_timeout,
        # asyncpg driver arguments
        connect_args={
            # Client cancels queries >65s, raises TimeoutError
            # slightly above 'statement_timeout' to avoid race condition
            "command_timeout": 65,
            "server_settings": {
                # Postgres server-side caps each statement at 60s (ms),
                # raises asyncpg.QueryCanceledError
                "statement_timeout": "60000"
            },
        },
    )
    # Instrument SQLAlchemy engine (Only works with sync engine, not async engine)
    SQLAlchemyInstrumentor().instrument(
        engine=app.state.db_engine.sync_engine, enable_commenter=True
    )

    # Create async session factory
    app.state.async_session_factory = create_async_session_factory(app.state.db_engine)

    # Verify database connection
    async with app.state.async_session_factory() as session:
        await session.execute(text("SELECT 1"))

    app.state.started_at = datetime.now(UTC)
    yield
    await app.state.db_engine.dispose()
