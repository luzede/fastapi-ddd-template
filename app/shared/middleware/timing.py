"""Request timing middleware."""

import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.shared.state import RequestState


class TimingMiddleware(BaseHTTPMiddleware):
    """Track request processing time."""

    async def dispatch(self, request: Request[RequestState], call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start

        response.headers["X-Response-Time"] = f"{duration:.4f}s"
        request.state.duration = duration

        return response
