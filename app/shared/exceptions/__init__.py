"""
RFC 9457 Problem Detail Exceptions Template

Production-ready exception handling for FastAPI with:
- RFC 9457 compliant responses
- Field-level validation errors
- Trace ID correlation
- Structured logging
"""

from app.shared.exceptions.exceptions import (
    AuthenticationError,
    AuthorizationError,
    BadRequestError,
    ConflictError,
    InternalError,
    ProblemDetailException,
    RateLimitError,
    ResourceNotFoundError,
    ServiceUnavailableError,
    ValidationError,
)

__all__ = [
    "AuthenticationError",
    "AuthorizationError",
    "BadRequestError",
    "ConflictError",
    "InternalError",
    "ProblemDetailException",
    "RateLimitError",
    "ResourceNotFoundError",
    "ServiceUnavailableError",
    "ValidationError",
]
