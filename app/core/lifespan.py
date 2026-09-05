import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from sqlalchemy import text

from app.core.config import get_settings
from app.modules.auth.mailer import LoggingMailer
from app.modules.auth.repository import JwksRepository
from app.modules.auth.services.jwt import JwtService
from app.shared.db.engine import create_engine
from app.shared.db.session import create_async_session_factory
from app.shared.state import AppState

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state = AppState()

    # Initialize database engine and async session factory
    app.state.db_engine = create_engine()
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
