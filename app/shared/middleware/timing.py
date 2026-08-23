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

        request.state.duration = duration

        # W3C Server-Timing: dur is in milliseconds
        response.headers["Server-Timing"] = f"total;dur={duration * 1000:.2f}"

        # I like 'X-Response-Time' too so let's add it for convenience
        response.headers["X-Response-Time"] = f"{duration * 1000:.3f}"

        return response
