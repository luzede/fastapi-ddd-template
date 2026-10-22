"""Liveness and readiness probes."""

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.shared.db.session import SessionDep
from app.shared.exceptions import ServiceUnavailableError

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    status: str


@router.get("/live", response_model=HealthResponse)
async def liveness_probe() -> HealthResponse:
    return HealthResponse(status="live")


@router.get("/ready", response_model=HealthResponse)
async def readiness_probe(session: SessionDep) -> HealthResponse:
    try:
        await session.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError) as e:
        raise ServiceUnavailableError(detail="Database is unreachable") from e

    return HealthResponse(status="ready")
