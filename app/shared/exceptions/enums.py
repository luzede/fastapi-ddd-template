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
