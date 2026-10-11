from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

from app.core.config import get_auth_settings
from app.modules.auth.schemas import MyJWTClaims
from app.shared.exceptions import AuthenticationError
from app.shared.exceptions.enums import ErrorCode

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


type TokenDep = Annotated[str, Depends(oauth2_scheme)]


def get_jwt_claims(
    token: TokenDep,
) -> MyJWTClaims:

    settings = get_auth_settings()

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            options={
                "require": ["sub", "exp", "iat"],
                "verify_iat": True,
                "verify_sub": True,
                "verify_exp": True,
            },
        )
    except jwt.InvalidTokenError as e:
        raise AuthenticationError(
            f"Invalid JWT: {e!s}",
            code=ErrorCode.INVALID_JWT_TOKEN,
        )

    return MyJWTClaims.model_validate(payload)


type JWTClaimsDep = Annotated[MyJWTClaims, Depends(get_jwt_claims)]
