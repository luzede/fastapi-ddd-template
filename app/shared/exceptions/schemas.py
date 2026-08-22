"""Pydantic schemas documenting RFC 9457 problem detail responses."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.shared.exceptions.enums import ProblemType


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

    model_config = ConfigDict(
        extra="allow",
        json_schema_extra={
            "example": {
                "type": ProblemType.VALIDATION_ERROR,
                "title": "Validation Error",
                "status": 422,
                "detail": "The url field is required",
                "instance": "/api/v1/analyses",
                "trace_id": "abc123",
                "timestamp": "2026-01-07T10:30:00Z",
            }
        },
    )


class FieldError(BaseModel):
    """Individual field validation error."""

    field: str
    code: str
    message: str


class ValidationProblem(ProblemDetail):
    """Problem detail with validation errors."""

    errors: list[FieldError] = Field(
        default_factory=list,
        description="List of validation errors",
    )


class RateLimitProblem(ProblemDetail):
    """Problem detail for rate limiting."""

    retry_after: int = Field(description="Seconds until retry is allowed")
    limit: int = Field(description="Request limit")
    window: str = Field(description="Time window for limit")
