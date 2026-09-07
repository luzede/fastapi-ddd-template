"""TypedDict contracts for RFC 9457 problem detail payloads."""

from datetime import datetime
from typing import Any, NotRequired

# typing.TypedDict lacks PEP 728 extra_items before Python 3.15
from typing_extensions import TypedDict


class ProblemDetailPayload(TypedDict, extra_items=Any):
    """RFC 9457 Problem Details response schema."""

    type: str  # URI reference identifying the problem type
    title: str  # Short, human-readable summary
    status: int  # HTTP status code
    detail: NotRequired[str]  # Human-readable explanation
    instance: NotRequired[str]  # Occurrence URI


class ProblemDetailPayloadWithCommonExtensions(ProblemDetailPayload):
    trace_id: NotRequired[str]  # Trace ID for debugging
    timestamp: NotRequired[str]  # Timestamp of the error occurrence


class FieldErrorDict(TypedDict):
    """Individual field validation error."""

    field: str
    code: str
    message: str


class ProblemDetailExceptionExtensionsDict(TypedDict, total=False):
    # Common extensions
    trace_id: str
    timestamp: datetime

    # Resource-specific extensions
    resource_type: str
    resource_id: str

    # Validation-specific extensions
    errors: list[FieldErrorDict]

    # Conflict-specific extensions
    conflicting_field: str | None

    # Rate limit-specific extensions
    limit: int
    window: str

    # Authorization-specific extensions
    required_permission: str | None


class ProblemDetailExceptionExtensionsPayload(TypedDict, total=False, closed=True):
    """Problem detail exception extensions payload (JSON-serialized, None omitted)."""

    trace_id: str
    timestamp: str

    resource_type: str
    resource_id: str

    errors: list[FieldErrorDict]

    conflicting_field: str

    limit: int
    window: str

    required_permission: str
