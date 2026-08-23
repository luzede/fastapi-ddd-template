from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from sqlalchemy import text

from app.shared.db.engine import create_engine
from app.shared.db.session import create_async_session_factory
from app.shared.state import AppState


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state = AppState()

    # Initialize database engine and async session factory
    app.state.db_engine = create_engine()
    app.state.async_session_factory = create_async_session_factory(app.state.db_engine)

    # Verify database connection
    async with app.state.async_session_factory() as session:
        await session.execute(text("SELECT 1"))

    app.state.started_at = datetime.now(UTC)
    yield
    await app.state.db_engine.dispose()
