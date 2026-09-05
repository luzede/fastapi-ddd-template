"""JWT plugin endpoints: `/token` and `/jwks`."""

from fastapi import APIRouter

from app.modules.auth.dependencies import JwtServiceDep
from app.modules.auth.guards import SessionAuthDep
from app.modules.auth.schemas import JwksResponse, TokenResponse
from app.shared.exceptions.schemas import ProblemDetail

router = APIRouter(tags=["auth:jwt"])


@router.get(
    "/token",
    response_model=TokenResponse,
    responses={401: {"model": ProblemDetail}},
    summary="Mint a short-lived JWT for the current session",
)
async def get_token(ctx: SessionAuthDep, jwt_service: JwtServiceDep) -> TokenResponse:
    return TokenResponse(token=await jwt_service.sign_for_user(ctx.user))


@router.get(
    "/jwks",
    response_model=JwksResponse,
    summary="Public signing keys (JWK Set)",
)
async def get_jwks(jwt_service: JwtServiceDep) -> JwksResponse:
    return JwksResponse.model_validate(await jwt_service.jwks())
