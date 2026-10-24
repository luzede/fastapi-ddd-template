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
        examples=["about:blank", ProblemType.BAD_REQUEST],
    )
    title: str = Field(
        description="Short, human-readable summary",
        examples=["Bad Request"],
    )
    status: int = Field(
        description="HTTP status code",
        examples=[400],
    )
    detail: str | None = Field(
        default=None,
        description="Human-readable explanation specific to this occurrence",
        examples=["The request could not be processed due to invalid parameters."],
    )
    instance: str | None = Field(
        default=None,
        description="URI reference identifying the specific occurrence",
        examples=["/api/v1/resource/123"],
    )
    # Common extensions
    trace_id: str | None = Field(
        default=None,
        description="Unique request tracing identifier",
        examples=["0af7651916cd43dd8448eb211c80319c"],
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when the error occurred",
        examples=["2026-10-24T12:00:00Z"],
    )
    code: ErrorCode | None = Field(
        default=None,
        description="Stable machine-readable error code",
        examples=[ErrorCode.BAD_REQUEST],
    )

    model_config = ConfigDict(
        extra="allow",
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "type": "about:blank",
                    "title": "Bad Request",
                    "status": 400,
                    "detail": "The request could not be processed due to invalid parameters.",
                    "instance": "/api/v1/resource/123",
                    "code": ErrorCode.BAD_REQUEST,
                    "timestamp": "2026-10-24T12:00:00Z",
                    "trace_id": "0af7651916cd43dd8448eb211c80319c",
                }
            ]
        },
    )


class FieldError(BaseModel):
    """Individual field validation error."""

    field: str = Field(
        description="Path to the invalid field",
        examples=["email"],
    )
    code: str = Field(
        description="Validation error code or type",
        examples=["value_error"],
    )
    message: str = Field(
        description="Human-readable validation message",
        examples=["Value is not a valid email address"],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "field": "email",
                    "code": "value_error",
                    "message": "Value is not a valid email address",
                }
            ]
        }
    )


class ValidationProblem(ProblemDetail):
    """Problem detail with validation errors. Status code 422 Unprocessable Entity."""

    errors: list[FieldError] = Field(
        default_factory=list,
        description="List of validation errors",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "type": ProblemType.VALIDATION_ERROR,
                    "title": "Validation Error",
                    "status": 422,
                    "detail": "One or more fields failed validation",
                    "instance": "/api/v1/auth/sign-up/email",
                    "code": ErrorCode.VALIDATION_ERROR,
                    "timestamp": "2026-10-24T12:00:00Z",
                    "trace_id": "0af7651916cd43dd8448eb211c80319c",
                    "errors": [
                        {
                            "field": "email",
                            "code": "value_error",
                            "message": "Value is not a valid email address",
                        }
                    ],
                }
            ]
        }
    )


class ResourceNotFoundProblem(ProblemDetail):
    """Problem detail for resource not found errors. Status code 404 Not Found."""

    resource_type: str = Field(
        description="Type of the resource that was not found",
        examples=["User"],
    )
    resource_id: str = Field(
        description="ID of the resource that was not found",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "type": ProblemType.RESOURCE_NOT_FOUND,
                    "title": "Resource Not Found",
                    "status": 404,
                    "detail": "User with ID '123e4567-e89b-12d3-a456-426614174000' was not found",
                    "instance": "/api/v1/users/123e4567-e89b-12d3-a456-426614174000",
                    "code": ErrorCode.RESOURCE_NOT_FOUND,
                    "timestamp": "2026-10-24T12:00:00Z",
                    "trace_id": "0af7651916cd43dd8448eb211c80319c",
                    "resource_type": "User",
                    "resource_id": "123e4567-e89b-12d3-a456-426614174000",
                }
            ]
        }
    )


class BadRequestProblem(ProblemDetail):
    """Problem detail for bad request errors. Status code 400 Bad Request."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "type": ProblemType.BAD_REQUEST,
                    "title": "Bad Request",
                    "status": 400,
                    "detail": "The request body is malformed or invalid",
                    "instance": "/api/v1/auth/sign-up/email",
                    "code": ErrorCode.BAD_REQUEST,
                    "timestamp": "2026-10-24T12:00:00Z",
                    "trace_id": "0af7651916cd43dd8448eb211c80319c",
                }
            ]
        }
    )


class ConflictProblem(ProblemDetail):
    """Problem detail for conflict errors. Status code 409 Conflict."""

    conflicting_field: str | None = Field(
        default=None,
        description="Field that caused the conflict, if applicable",
        examples=["email"],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "type": ProblemType.RESOURCE_CONFLICT,
                    "title": "Resource Conflict",
                    "status": 409,
                    "detail": "User with this email already exists",
                    "instance": "/api/v1/auth/sign-up/email",
                    "code": ErrorCode.USER_ALREADY_EXISTS,
                    "timestamp": "2026-10-24T12:00:00Z",
                    "trace_id": "0af7651916cd43dd8448eb211c80319c",
                    "conflicting_field": "email",
                }
            ]
        }
    )


class AuthenticationProblem(ProblemDetail):
    """Problem detail for authentication errors. Status code 401 Unauthorized."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "type": ProblemType.AUTHENTICATION_REQUIRED,
                    "title": "Authentication Required",
                    "status": 401,
                    "detail": "Authentication is required to access this resource",
                    "instance": "/api/v1/users/me",
                    "code": ErrorCode.AUTHENTICATION_REQUIRED,
                    "timestamp": "2026-10-24T12:00:00Z",
                    "trace_id": "0af7651916cd43dd8448eb211c80319c",
                }
            ]
        }
    )


class PermissionProblem(ProblemDetail):
    """Problem detail for authorization errors. Status code 403 Forbidden."""

    required_permission: str | None = Field(
        default=None,
        description="The permission required to perform the requested action",
        examples=["users:write"],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "type": ProblemType.INSUFFICIENT_PERMISSIONS,
                    "title": "Insufficient Permissions",
                    "status": 403,
                    "detail": "You do not have permission to access this resource",
                    "instance": "/api/v1/users/123e4567-e89b-12d3-a456-426614174000",
                    "code": ErrorCode.INSUFFICIENT_PERMISSIONS,
                    "timestamp": "2026-10-24T12:00:00Z",
                    "trace_id": "0af7651916cd43dd8448eb211c80319c",
                    "required_permission": "users:write",
                }
            ]
        }
    )


class InternalServerProblem(ProblemDetail):
    """Problem detail for internal server errors. Status code 500 Internal Server Error."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "type": ProblemType.INTERNAL_ERROR,
                    "title": "Internal Server Error",
                    "status": 500,
                    "detail": "An unexpected error occurred. Please try again later.",
                    "instance": "/api/v1/users",
                    "code": ErrorCode.INTERNAL_ERROR,
                    "timestamp": "2026-10-24T12:00:00Z",
                    "trace_id": "0af7651916cd43dd8448eb211c80319c",
                }
            ]
        }
    )


class ServiceUnavailableProblem(ProblemDetail):
    """Problem detail for service unavailable errors. Status code 503 Service Unavailable."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "type": ProblemType.SERVICE_UNAVAILABLE,
                    "title": "Service Unavailable",
                    "status": 503,
                    "detail": "Service is temporarily unavailable",
                    "instance": "/health/ready",
                    "code": ErrorCode.SERVICE_UNAVAILABLE,
                    "timestamp": "2026-10-24T12:00:00Z",
                    "trace_id": "0af7651916cd43dd8448eb211c80319c",
                }
            ]
        }
    )


class RateLimitProblem(ProblemDetail):
    """Problem detail for rate limiting. Status code 429 Too Many Requests."""

    limit: int = Field(
        description="Request limit",
        examples=[100],
    )
    window: str = Field(
        description="Time window for limit",
        examples=["1 minute"],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "type": ProblemType.RATE_LIMIT_EXCEEDED,
                    "title": "Rate Limit Exceeded",
                    "status": 429,
                    "detail": "You have exceeded 100 requests per 1 minute",
                    "instance": "/api/v1/auth/token",
                    "code": ErrorCode.RATE_LIMIT_EXCEEDED,
                    "timestamp": "2026-10-24T12:00:00Z",
                    "trace_id": "0af7651916cd43dd8448eb211c80319c",
                    "limit": 100,
                    "window": "1 minute",
                }
            ]
        }
    )
