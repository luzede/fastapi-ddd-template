import uvicorn
from fastapi import APIRouter, FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from starlette.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.lifespan import lifespan
from app.core.logging import setup_logging
from app.core.opentelemetry import setup_opentelemetry
from app.modules.auth.router import router as auth_router
from app.modules.health.router import router as healthcheck_router
from app.shared.exceptions.handlers import register_exception_handlers
from app.shared.middleware import (
    LoggingMiddleware,
    ServerTimingMiddleware,
    TraceContextMiddleware,
)


def create_app() -> FastAPI:
    settings = get_settings()

    telemetry = setup_opentelemetry(
        service_name=settings.otel_service_name,
        otlp_endpoint=settings.otel_exporter_otlp_endpoint,
        environment=settings.environment,
    )
    setup_logging(
        environment=settings.environment,
        log_level=settings.log_level,
        logger_provider=telemetry.logger_provider,
    )

    app = FastAPI(title="FastAPI DDD Template", lifespan=lifespan)
    register_exception_handlers(app)

    # Added bottom-up: the LAST add_middleware call runs FIRST on the request path
    app.add_middleware(ServerTimingMiddleware)  # innermost
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

    v1_router = APIRouter(prefix="/api/v1")
    v1_router.include_router(auth_router)

    app.include_router(healthcheck_router)
    app.include_router(v1_router)

    FastAPIInstrumentor.instrument_app(app, tracer_provider=telemetry.tracer_provider)

    return app


def main() -> None:
    settings = get_settings()

    uvicorn.run(
        create_app(),
        host=settings.server.host,
        port=settings.server.port,
        # Logging is configured by setup_logging; don't let uvicorn install its own handlers
        log_config=None,
        # LoggingMiddleware already logs every request (with duration and trace IDs)
        access_log=False,
    )


if __name__ == "__main__":
    main()
