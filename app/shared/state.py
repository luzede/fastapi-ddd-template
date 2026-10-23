from datetime import datetime
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from starlette.datastructures import State


class AppState(State):
    db_engine: AsyncEngine
    async_session_factory: async_sessionmaker[AsyncSession]
    started_at: datetime


class RequestState(State):
    trace_id: str
    """Set by `TraceContextMiddleware`; available in route handlers and exception handlers via request.state.trace_id."""


def get_app_state_from_request(request: Request) -> AppState:
    # In 'lifespan' we set 'app.state' to an instance of AppState
    # This function retrieves that instance from the request object
    # Note: annotated as plain Request because FastAPI cannot analyze Request[AppState]
    return cast(AppState, request.app.state)


type AppStateDep = Annotated[AppState, Depends(get_app_state_from_request)]
