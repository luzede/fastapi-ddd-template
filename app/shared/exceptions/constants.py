from app.shared.exceptions.schemas import (
    AuthenticationProblem,
    BadRequestProblem,
    ConflictProblem,
    InternalServerProblem,
    PermissionProblem,
    RateLimitProblem,
    ResourceNotFoundProblem,
    ValidationProblem,
)

PROBLEM_400 = {
    "model": BadRequestProblem,
    "description": "Bad Request",
}


PROBLEM_401 = {
    "model": AuthenticationProblem,
    "description": "Unauthorized",
}


PROBLEM_403 = {
    "model": PermissionProblem,
    "description": "Forbidden",
}


PROBLEM_404 = {
    "model": ResourceNotFoundProblem,
    "description": "Not Found",
}


PROBLEM_409 = {
    "model": ConflictProblem,
    "description": "Conflict",
}


PROBLEM_422 = {
    "model": ValidationProblem,
    "description": "Validation Error",
}


PROBLEM_429 = {
    "model": RateLimitProblem,
    "description": "Too Many Requests",
}


PROBLEM_500 = {
    "model": InternalServerProblem,
    "description": "Internal Server Error",
}
