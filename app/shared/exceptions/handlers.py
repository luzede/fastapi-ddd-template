"""FastAPI exception handlers emitting RFC 9457 problem detail responses."""

from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic_core import ErrorDetails

# Base class of fastapi.HTTPException; registering it catches router 404/405 too
from starlette.exceptions import HTTPException

from app.shared.exceptions.enums import ProblemType
from app.shared.exceptions.exceptions import (
    AuthenticationError,
    ProblemDetailException,
    ValidationError,
)
from app.shared.exceptions.types import (
    FieldErrorDict,
)
from app.shared.state import RequestState


async def problem_detail_exception_handler(
    request: Request[RequestState],
    exc: ProblemDetailException,
) -> JSONResponse:
    """Handle ProblemException subclasses."""

    trace_id = request.state.trace_id
    if exc.instance is None:
        exc.instance = request.url.path
    if trace_id:
        exc.extensions.setdefault("trace_id", trace_id)

    return exc.to_json_response()


async def request_validation_exception_handler(
    request: Request[RequestState],
    exc: RequestValidationError,
) -> JSONResponse:
    """Handle Pydantic validation errors."""
    errors: list[FieldErrorDict] = []
    for error in exc.errors():
        error: ErrorDetails

        # Skip 'body' prefix in location
        # example: ('body', 'field_name', 1) -> 'field_name.1'
        loc = error["loc"]
        if len(loc) > 1 and loc[0] == "body":
            field_path = ".".join(str(x) for x in loc[1:])
        elif len(loc) > 1:
            field_path = ".".join(str(x) for x in loc)
        else:
            field_path = str(loc[0])

        errors.append(
            {
                "field": field_path,
                "code": error["type"],
                "message": error["msg"],
            }
        )

    validation_error = ValidationError(errors=errors)

    return await problem_detail_exception_handler(
        request,
        validation_error,
    )


async def http_exception_handler(
    request: Request[RequestState],
    exc: HTTPException,
) -> JSONResponse:
    """Handle Starlette/FastAPI HTTPException errors."""

    # Map every 401 to the typed problem URI, regardless of how it was raised
    if exc.status_code == 401:
        authentication_error = AuthenticationError(
            detail=exc.detail,
        )
        response = await problem_detail_exception_handler(
            request,
            authentication_error,
        )
    else:
        # RFC 9457 §4.2: 'about:blank' pairs with the HTTP status phrase as title
        try:
            title = HTTPStatus(exc.status_code).phrase
        except ValueError:
            title = "Unknown Error"

        problem_detail_exception = ProblemDetailException(
            title=title,
            status=exc.status_code,
            type="about:blank",
            detail=None if exc.status_code >= 500 else exc.detail,
        )

        response = await problem_detail_exception_handler(
            request,
            problem_detail_exception,
        )

    # RFC 9110: 401 requires WWW-Authenticate, 405 requires Allow
    if exc.headers:
        response.headers.update(exc.headers)

    return response


async def generic_exception_handler(
    request: Request[RequestState],
    _: Exception,
) -> JSONResponse:
    """Handle unexpected exceptions."""

    problem_detail_exception = ProblemDetailException(
        title="Internal Server Error",
        status=500,
        type=ProblemType.INTERNAL_ERROR,
        detail="An unexpected error occurred. Please try again later.",
    )

    return await problem_detail_exception_handler(
        request,
        problem_detail_exception,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register RFC 9457 handlers for domain, validation, HTTP, and unexpected errors."""

    app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore
    app.add_exception_handler(
        RequestValidationError,
        request_validation_exception_handler,  # type: ignore
    )
    app.add_exception_handler(ProblemDetailException, problem_detail_exception_handler)  # type: ignore
    app.add_exception_handler(Exception, generic_exception_handler)
