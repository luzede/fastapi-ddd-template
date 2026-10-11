from typing import Annotated
from uuid import UUID

from fastapi import Depends

from app.modules.auth.security import JWTClaimsDep
from app.modules.user.model import User
from app.modules.user.repository import UserRepositoryDep
from app.shared.exceptions import ResourceNotFoundError


def get_current_user_id(
    claims: JWTClaimsDep,
) -> UUID:
    return claims.sub


type CurrentUserIdDep = Annotated[UUID, Depends(get_current_user_id)]


async def get_current_user(
    user_id: CurrentUserIdDep,
    user_repo: UserRepositoryDep,
) -> User:
    user = await user_repo.get(user_id)
    if user is None:
        raise ResourceNotFoundError(
            resource_type=User.__name__,
            resource_id=user_id,
        )

    return user


type CurrentUserDep = Annotated[User, Depends(get_current_user)]
