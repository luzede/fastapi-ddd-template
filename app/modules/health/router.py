"""Liveness and readiness probes."""

import logging

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.shared.db.session import SessionDep
from app.shared.exceptions import ServiceUnavailableError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/healthcheck", tags=["healthcheck"])


class HealthCheckResponse(BaseModel):
    status: str


@router.get("/live", response_model=HealthCheckResponse)
async def liveness_probe() -> HealthCheckResponse:
    return HealthCheckResponse(status="alive")


@router.get("/ready", response_model=HealthCheckResponse)
async def healthcheck(session: SessionDep) -> HealthCheckResponse:
    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("Healthcheck database probe failed")
        raise ServiceUnavailableError(detail="Database is unreachable")

    return HealthCheckResponse(status="healthy")
