"""Request timing middleware."""

import time
from typing import override

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


class TimingMiddleware(BaseHTTPMiddleware):
    """Track request processing time."""

    @override
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start

        # Store duration in request.state for access
        # in LoggingMiddleware
        request.state.duration = duration

        # W3C Server-Timing: dur is in milliseconds
        response.headers["Server-Timing"] = f"total;dur={duration * 1000:.2f}"

        # I like 'X-Response-Time' too so let's add it for convenience
        response.headers["X-Response-Time"] = f"{duration * 1000:.3f}"

        return response
