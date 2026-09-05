"""Exception hierarchy rendering as RFC 9457 Problem Detail."""

from datetime import UTC, datetime
from typing import Literal, Unpack, cast

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.shared.exceptions.enums import ProblemType
from app.shared.exceptions.types import (
    FieldErrorDict,
    ProblemDetailExceptionExtensionsDict,
    ProblemDetailPayloadWithCommonExtensions,
    ProblemExceptionExtensionsPayload,
)


class ProblemDetailException(Exception):
    """Base exception that renders as RFC 9457 Problem Detail."""

    def __init__(
        self,
        *,
        type: ProblemType | Literal["about:blank"] = "about:blank",
        title: str,
        status: int,
        detail: str | None = None,
        instance: str | None = None,
        **extensions: Unpack[ProblemDetailExceptionExtensionsDict],
    ):
        super().__init__(detail or title)
        self.status = status
        self.type = type
        self.title = title
        self.detail = detail
        self.instance = instance

        if extensions.get("timestamp") is None:
            extensions["timestamp"] = datetime.now(UTC)
        if extensions.get("headers") is None:
            extensions["headers"] = {}

        self.extensions = extensions

    def to_problem_detail(self) -> ProblemDetailPayloadWithCommonExtensions:
        """Convert to Problem Detail dict."""

        none_ommitted_extensions = cast(
            ProblemExceptionExtensionsPayload,
            jsonable_encoder(self.extensions, exclude_none=True),
        )

        problem: ProblemDetailPayloadWithCommonExtensions = {
            "type": self.type,
            "title": self.title,
            "status": self.status,
            **none_ommitted_extensions,
        }

        # Omit fields with 'None' values to comply with RFC 9457
        if self.detail is not None:
            problem["detail"] = self.detail
        if self.instance is not None:
            problem["instance"] = self.instance

        return problem

    def to_json_response(self) -> JSONResponse:
        headers: dict[str, str] = dict(self.extensions.get("headers") or {})

        # RFC 9110 §10.2.3: Retry-After applies to 429 and 503 responses
        # https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.3
        # https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Retry-After
        if self.extensions.get("retry_after") is not None:
            headers["Retry-After"] = str(self.extensions["retry_after"])

        return JSONResponse(
            status_code=self.status,
            content=self.to_problem_detail(),
            media_type="application/problem+json",
            headers=headers or None,
        )


class ResourceNotFoundError(ProblemDetailException):
    """Resource not found error."""

    def __init__(
        self,
        resource_type: str,
        resource_id: str,
    ):
        super().__init__(
            status=404,
            type=ProblemType.RESOURCE_NOT_FOUND,
            title="Resource Not Found",
            detail=f"{resource_type} with ID '{resource_id}' was not found",
            resource_type=resource_type,
            resource_id=resource_id,
        )


class ValidationError(ProblemDetailException):
    """Validation error with field-level details."""

    def __init__(
        self,
        errors: list[FieldErrorDict],
        detail: str = "One or more fields failed validation",
    ):
        super().__init__(
            status=422,
            type=ProblemType.VALIDATION_ERROR,
            title="Validation Error",
            detail=detail,
            errors=errors,
        )


class ConflictError(ProblemDetailException):
    """Resource conflict error."""

    def __init__(
        self,
        detail: str,
        conflicting_field: str | None = None,
        code: str | None = None,
    ):
        super().__init__(
            status=409,
            type=ProblemType.RESOURCE_CONFLICT,
            title="Resource Conflict",
            detail=detail,
            conflicting_field=conflicting_field,
            **({"code": code} if code else {}),
        )


class BadRequestError(ProblemDetailException):
    """Semantically invalid request (well-formed but cannot be processed as-is)."""

    def __init__(self, detail: str, code: str | None = None):
        super().__init__(
            status=400,
            type=ProblemType.INVALID_REQUEST,
            title="Bad Request",
            detail=detail,
            **({"code": code} if code else {}),
        )


class RateLimitError(ProblemDetailException):
    """Rate limit exceeded error."""

    def __init__(
        self,
        retry_after: int,
        limit: int,
        window: str = "1 minute",
        code: str | None = None,
    ):
        super().__init__(
            status=429,
            type=ProblemType.RATE_LIMIT_EXCEEDED,
            title="Rate Limit Exceeded",
            detail=f"You have exceeded {limit} requests per {window}",
            retry_after=retry_after,
            limit=limit,
            window=window,
        )


class AuthenticationError(ProblemDetailException):
    """Authentication required error.

    RFC 9110 §11.6.1: a 401 response MUST carry a `WWW-Authenticate` challenge.
    """

    def __init__(
        self,
        detail: str = "Authentication is required",
        code: str | None = None,
        www_authenticate: str = "Bearer",
    ):
        super().__init__(
            status=401,
            type=ProblemType.AUTHENTICATION_REQUIRED,
            title="Authentication Required",
            detail=detail,
            headers={"WWW-Authenticate": www_authenticate},
            **({"code": code} if code else {}),
        )


class AuthorizationError(ProblemDetailException):
    """Insufficient permissions error."""

    def __init__(
        self,
        detail: str = "You don't have permission to access this resource",
        required_permission: str | None = None,
        code: str | None = None,
    ):
        super().__init__(
            status=403,
            type=ProblemType.INSUFFICIENT_PERMISSIONS,
            title="Insufficient Permissions",
            detail=detail,
            required_permission=required_permission,
            **({"code": code} if code else {}),
        )


class InternalError(ProblemDetailException):
    """Unexpected server error. Detail is intentionally generic."""

    def __init__(self, detail: str | None = None):
        super().__init__(
            status=500,
            type=ProblemType.INTERNAL_ERROR,
            title="Internal Server Error",
            detail=detail,
        )


class ServiceUnavailableError(ProblemDetailException):
    """Service temporarily unavailable error."""

    def __init__(
        self,
        detail: str = "Service is temporarily unavailable",
        retry_after: int | None = None,
    ):
        super().__init__(
            status=503,
            type=ProblemType.SERVICE_UNAVAILABLE,
            title="Service Unavailable",
            detail=detail,
            retry_after=retry_after,
        )
