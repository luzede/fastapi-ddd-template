"""Pydantic schemas documenting RFC 9457 problem detail responses."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.shared.exceptions.enums import ErrorCode, ProblemType


class ProblemDetail(BaseModel):
    """RFC 9457 Problem Details response schema."""

    type: ProblemType | Literal["about:blank"] = Field(
        default="about:blank",
        description="URI reference identifying the problem type",
    )
    title: str = Field(
        description="Short, human-readable summary",
    )
    status: int = Field(
        description="HTTP status code",
    )
    detail: str | None = Field(
        default=None,
        description="Human-readable explanation specific to this occurrence",
    )
    instance: str | None = Field(
        default=None,
        description="URI reference identifying the specific occurrence",
    )
    # Common extensions
    trace_id: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    code: ErrorCode | None = Field(
        default=None,
        description="Stable machine-readable error code",
    )

    model_config = ConfigDict(
        extra="allow",
        from_attributes=True,
    )


class FieldError(BaseModel):
    """Individual field validation error."""

    field: str
    code: str
    message: str


class ValidationProblem(ProblemDetail):
    """Problem detail with validation errors. Status code 422 Unprocessable Entity."""

    errors: list[FieldError] = Field(
        default_factory=list,
        description="List of validation errors",
    )


class ResourceNotFoundProblem(ProblemDetail):
    """Problem detail for resource not found errors. Status code 404 Not Found."""

    resource_type: str = Field(
        description="Type of the resource that was not found",
    )
    resource_id: str = Field(
        description="ID of the resource that was not found",
    )


class BadRequestProblem(ProblemDetail):
    """Problem detail for bad request errors. Status code 400 Bad Request."""


class ConflictProblem(ProblemDetail):
    """Problem detail for conflict errors. Status code 409 Conflict."""

    conflicting_field: str | None = Field(
        default=None,
        description="Field that caused the conflict, if applicable",
    )


class AuthenticationProblem(ProblemDetail):
    """Problem detail for authentication errors. Status code 401 Unauthorized."""


class PermissionProblem(ProblemDetail):
    """Problem detail for authorization errors. Status code 403 Forbidden."""

    required_permission: str | None = Field(
        default=None,
        description="The permission required to perform the requested action",
    )


class InternalServerProblem(ProblemDetail):
    """Problem detail for internal server errors. Status code 500 Internal Server Error."""


class ServiceUnavailableProblem(ProblemDetail):
    """Problem detail for service unavailable errors. Status code 503 Service Unavailable."""


class RateLimitProblem(ProblemDetail):
    """Problem detail for rate limiting. Status code 429 Too Many Requests."""

    limit: int = Field(description="Request limit")
    window: str = Field(description="Time window for limit")
