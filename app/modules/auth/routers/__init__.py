from fastapi import APIRouter

from app.modules.auth.routers.admin import router as admin_router
from app.modules.auth.routers.api_key import router as api_key_router
from app.modules.auth.routers.core import router as core_router
from app.modules.auth.routers.jwt import router as jwt_router
from app.modules.auth.routers.user import router as user_router

router = APIRouter()

# Core better-auth endpoints mounted at /auth
auth_subrouter = APIRouter(prefix="/auth")
auth_subrouter.include_router(core_router)
auth_subrouter.include_router(jwt_router)
auth_subrouter.include_router(api_key_router)
auth_subrouter.include_router(admin_router)

router.include_router(auth_subrouter)
# Self-service user endpoints mounted at /users
router.include_router(user_router)

__all__ = ["router"]
