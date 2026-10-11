from enum import StrEnum

# The namespace root for every problem type URI. Kept OUTSIDE ProblemType:
# inside a StrEnum body it would become a member, so iterating the registry
# would yield the bare base URI as if it were a problem type.
PROBLEM_TYPE_BASE = "https://api.example.com/problems"


class ProblemType(StrEnum):
    """Registry of problem type URIs.

    A StrEnum, so members compare and serialize as their URI string while
    still being a closed, iterable set: `list(ProblemType)` is exactly the
    catalog of problem types this API can emit.
    """

    VALIDATION_ERROR = f"{PROBLEM_TYPE_BASE}/validation-error"
    RESOURCE_NOT_FOUND = f"{PROBLEM_TYPE_BASE}/resource-not-found"
    RESOURCE_CONFLICT = f"{PROBLEM_TYPE_BASE}/resource-conflict"
    AUTHENTICATION_REQUIRED = f"{PROBLEM_TYPE_BASE}/authentication-required"
    INSUFFICIENT_PERMISSIONS = f"{PROBLEM_TYPE_BASE}/insufficient-permissions"
    RATE_LIMIT_EXCEEDED = f"{PROBLEM_TYPE_BASE}/rate-limit-exceeded"
    INTERNAL_ERROR = f"{PROBLEM_TYPE_BASE}/internal-error"
    SERVICE_UNAVAILABLE = f"{PROBLEM_TYPE_BASE}/service-unavailable"
    BAD_REQUEST = f"{PROBLEM_TYPE_BASE}/invalid-request"


class ErrorCode(StrEnum):
    """Registry of stable machine-readable error codes.

    A StrEnum, so members compare and serialize as their code string while
    still being a closed, iterable set: `list(ErrorCode)` is exactly the
    catalog of error codes this API can emit.
    """

    # 1-1 mapping to ProblemType, for convenience
    VALIDATION_ERROR = "VALIDATION_ERROR"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    RESOURCE_CONFLICT = "RESOURCE_CONFLICT"
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    INSUFFICIENT_PERMISSIONS = "INSUFFICIENT_PERMISSIONS"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    BAD_REQUEST = "BAD_REQUEST"

    # Sub-codes for each problem type

    # --- BAD_REQUEST ---
    INVALID_TOKEN = "INVALID_TOKEN"
    PASSWORD_TOO_SHORT = "PASSWORD_TOO_SHORT"
    PASSWORD_TOO_LONG = "PASSWORD_TOO_LONG"

    # --- RESOURCE_CONFLICT ---
    USER_ALREADY_EXISTS = "USER_ALREADY_EXISTS"

    # --- AUTHENTICATION_REQUIRED ---
    INVALID_EMAIL_OR_PASSWORD = "INVALID_EMAIL_OR_PASSWORD"
    INVALID_JWT_TOKEN = "INVALID_JWT_TOKEN"
