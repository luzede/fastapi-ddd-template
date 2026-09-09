import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.modules.auth.mailer import LoggingMailer
from app.modules.auth.repositories import JwksRepository
from app.modules.auth.services.jwt import JwtService
from app.shared.db.session import create_async_session_factory
from app.shared.state import AppState

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state = AppState()

    # Initialize database engine and async session factory
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
    app.state.async_session_factory = create_async_session_factory(app.state.db_engine)

    # Verify database connection
    async with app.state.async_session_factory() as session:
        await session.execute(text("SELECT 1"))

    # Outbound email. Replace with a real provider adapter in production.
    app.state.mailer = LoggingMailer()
    logger.warning("Using LoggingMailer: verification and reset emails are only logged")

    # Ensure a JWT signing key exists so the first /token and /jwks calls do not race to create one
    async with app.state.async_session_factory() as session:
        await JwtService(JwksRepository(session), settings.auth).get_signing_key()
        await session.commit()

    app.state.started_at = datetime.now(UTC)
    yield
    await app.state.db_engine.dispose()
