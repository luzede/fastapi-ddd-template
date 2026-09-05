import uvicorn
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.healthcheck import router as healthcheck_router
from app.core.lifespan import lifespan
from app.modules.auth.routers import router as auth_router
from app.modules.users.router import router as users_router
from app.shared.exceptions.handlers import register_exception_handlers
from app.shared.middleware import (
    LoggingMiddleware,
    TimingMiddleware,
    TraceContextMiddleware,
)

API_V1_PREFIX = "/api/v1"


def run_migrations() -> None:
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(title="FastAPI DDD Template", lifespan=lifespan)
    register_exception_handlers(app)

    # Added bottom-up: the LAST add_middleware call runs FIRST on the request path
    app.add_middleware(TimingMiddleware)  # innermost
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(TraceContextMiddleware)
    # Outermost: preflight OPTIONS short-circuits here, never reaching app middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.server.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "X-Request-ID",
            "X-Response-Time",
            "Server-Timing",
            # better-auth bearer/jwt plugin headers for header-based clients
            "set-auth-token",
            "set-auth-jwt",
        ],
    )

    app.include_router(healthcheck_router)
    app.include_router(auth_router, prefix=API_V1_PREFIX)
    app.include_router(users_router, prefix=API_V1_PREFIX)

    return app


def main() -> None:
    settings = get_settings()

    # Run database migrations
    run_migrations()

    uvicorn.run(create_app(), host=settings.server.host, port=settings.server.port)


if __name__ == "__main__":
    main()
