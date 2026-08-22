"""FastAPI exception handlers emitting RFC 9457 problem detail responses."""

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic_core import ErrorDetails

from app.shared.exceptions.enums import ProblemType
from app.shared.exceptions.exceptions import (
    ProblemDetailException,
    ValidationError,
)
from app.shared.exceptions.types import (
    FieldErrorDict,
)


async def problem_exception_handler(
    request: Request,
    exc: ProblemDetailException,
) -> JSONResponse:
    """Handle ProblemException subclasses."""

    trace_id = getattr(request.state, "request_id", None)
    if exc.instance is None:
        exc.instance = request.url.path
    if trace_id:
        exc.extensions.setdefault("trace_id", trace_id)

    return exc.to_json_response()


async def request_validation_exception_handler(
    request: Request,
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

    return await problem_exception_handler(
        request,
        validation_error,
    )


async def http_exception_handler(
    request: Request,
    exc: HTTPException,
) -> JSONResponse:
    """Handle FastAPI HTTPException errors."""

    problem_detail_exception = ProblemDetailException(
        title="HTTP Exception",
        status=exc.status_code,
        type="about:blank",
        detail=exc.detail,
    )

    return await problem_exception_handler(
        request,
        problem_detail_exception,
    )


async def generic_exception_handler(
    request: Request,
    _: Exception,
) -> JSONResponse:
    """Handle unexpected exceptions."""

    problem_detail_exception = ProblemDetailException(
        title="Internal Server Error",
        status=500,
        type=ProblemType.INTERNAL_ERROR,
        detail="An unexpected error occurred. Please try again later.",
    )

    return await problem_exception_handler(
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
    app.add_exception_handler(ProblemDetailException, problem_exception_handler)  # type: ignore
    app.add_exception_handler(Exception, generic_exception_handler)
