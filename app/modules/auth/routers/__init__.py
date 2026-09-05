from fastapi import APIRouter

from app.modules.auth.routers.admin import router as admin_router
from app.modules.auth.routers.api_key import router as api_key_router
from app.modules.auth.routers.core import router as core_router
from app.modules.auth.routers.jwt import router as jwt_router

router = APIRouter(prefix="/auth")
router.include_router(core_router)
router.include_router(jwt_router)
router.include_router(api_key_router)
router.include_router(admin_router)

__all__ = ["router"]
