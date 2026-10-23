import uvicorn
from fastapi import APIRouter, FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from starlette.middleware.cors import CORSMiddleware

from app.core.config import Environment, Settings, get_settings
from app.core.lifespan import lifespan
from app.core.logging import setup_logging
from app.core.opentelemetry import setup_opentelemetry
from app.modules.auth.router import router as auth_router
from app.modules.health.router import router as healthcheck_router
from app.shared.exceptions.handlers import register_exception_handlers
from app.shared.middleware import (
    ServerTimingMiddleware,
    TraceContextMiddleware,
)


def register_middlewares(app: FastAPI, settings: Settings) -> None:
    # Added bottom-up: the LAST add_middleware call runs FIRST on the request path
    app.add_middleware(ServerTimingMiddleware)  # innermost
    app.add_middleware(TraceContextMiddleware)
    # Outermost user middleware: preflight OPTIONS short-circuits here before reaching app middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.server.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "X-Request-ID",
            "Server-Timing",
        ],
    )


def register_routers(app: FastAPI) -> None:
    v1_router = APIRouter(prefix="/api/v1")
    v1_router.include_router(auth_router)

    app.include_router(healthcheck_router)
    app.include_router(v1_router)


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

    is_production = settings.environment == Environment.PRODUCTION
    app = FastAPI(
        title="FastAPI DDD Template",
        lifespan=lifespan,
        openapi_url=None if is_production else "/openapi.json",
    )

    register_exception_handlers(app)
    register_middlewares(app, settings)
    register_routers(app)

    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=telemetry.tracer_provider,
        excluded_urls="/health,/metrics,/docs,/redoc,/openapi.json",
    )

    return app


def main() -> None:
    settings = get_settings()

    is_dev = settings.environment == Environment.DEVELOPMENT

    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host=settings.server.host,
        port=settings.server.port,
        reload=is_dev,
        # Uvicorn does not support multiple workers while reload=True
        workers=None if is_dev else settings.server.workers,
        # Logging is configured by setup_logging; don't let uvicorn install its own handlers
        log_config=None,
        # OpenTelemetry already traces every request with duration, status, and spans
        access_log=False,
    )


if __name__ == "__main__":
    main()
