from typing import NotRequired

from typing_extensions import TypedDict


class MyJWTClaimsPayload(TypedDict, closed=True):
    sub: str
    exp: int
    iat: int

    roles: NotRequired[list[str]]  # Custom claim for user roles
