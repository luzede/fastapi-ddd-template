"""Trace context middleware: W3C traceparent with X-Request-ID fallback."""

import secrets
from typing import override

from fastapi import Request
from opentelemetry import trace
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


class TraceContextMiddleware(BaseHTTPMiddleware):
    """Resolve request.state.trace_id from traceparent, minting one if absent."""

    @override
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Extract current span context set by OpenTelemetry middleware
        span_ctx = trace.get_current_span().get_span_context()

        # If the span context is valid, use its trace_id; otherwise, generate a random one.
        if span_ctx.is_valid:
            request.state.trace_id = trace.format_trace_id(span_ctx.trace_id)
        else:
            request.state.trace_id = secrets.token_hex(16)

        response = await call_next(request)

        response.headers["X-Request-ID"] = request.state.trace_id

        return response
