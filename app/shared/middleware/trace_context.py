"""Trace context middleware: W3C traceparent with X-Request-ID fallback."""

import re
import secrets

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.shared.state import RequestState

TRACEPARENT_RE = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$")
ZERO_32 = "0" * 32
ZERO_16 = "0" * 16


class TraceContextMiddleware(BaseHTTPMiddleware):
    """Resolve request.state.trace_id from traceparent or X-Request-ID, minting one if absent."""

    async def dispatch(self, request: Request[RequestState], call_next):
        trace_id: str | None = None
        trace_flags = "01"

        traceparent = request.headers.get("traceparent")
        if traceparent:
            match = TRACEPARENT_RE.match(traceparent)
            if match and match.group(1) != ZERO_32 and match.group(2) != ZERO_16:
                trace_id = match.group(1)
                trace_flags = match.group(3)

        if not trace_id:
            trace_id = request.headers.get("x-request-id") or secrets.token_hex(16)

        request.state.trace_id = trace_id
        request.state.trace_flags = trace_flags

        response = await call_next(request)

        response.headers["X-Request-ID"] = trace_id

        return response
