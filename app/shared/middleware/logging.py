"""Request logging middleware."""

import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.shared.state import RequestState

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Log all requests with structured data."""

    async def dispatch(self, request: Request[RequestState], call_next):
        method = request.method
        path = request.url.path

        try:
            response = await call_next(request)
            duration = request.state.duration

            logger.info(
                "request_completed",
                extra={
                    "method": method,
                    "path": path,
                    "status_code": response.status_code,
                    "duration": duration,
                },
            )
            return response

        except Exception as exc:
            logger.exception(
                "request_failed",
                extra={
                    "method": method,
                    "path": path,
                    "error": str(exc),
                },
            )
            raise
