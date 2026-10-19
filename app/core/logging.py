"""Structured logging configuration (structlog + stdlib bridge + OpenTelemetry LoggingHandler)."""

import logging
import sys
from typing import Any, Final, TextIO, assert_never, override

import structlog
from opentelemetry import trace
from opentelemetry.instrumentation.logging.handler import LoggingHandler
from opentelemetry.sdk._logs import LoggerProvider
from pythonjsonlogger.orjson import OrjsonFormatter
from structlog.typing import EventDict, Processor

from app.core.config import Environment, LogLevel

SENSITIVE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "password",
        "password_hash",
        "token",
        "access_token",
        "refresh_token",
        "api_key",
        "secret",
        "secret_key",
        "authorization",
    }
)

NOISY_LOGGERS: Final[tuple[str, ...]] = (
    "urllib3",
    "httpcore",
    "httpx",
    "asyncio",
)


class TraceContextFilter(logging.Filter):
    """Inject active OpenTelemetry trace_id and span_id into log records for stdout output."""

    @override
    def filter(self, record: logging.LogRecord) -> bool:
        span_ctx = trace.get_current_span().get_span_context()
        if span_ctx.is_valid:
            record.trace_id = trace.format_trace_id(span_ctx.trace_id)
            record.span_id = trace.format_span_id(span_ctx.span_id)
        return True


def redact_sensitive_fields(
    logger: Any, method_name: str, event_dict: EventDict
) -> EventDict:
    """Redact sensitive fields in the event dict (case-insensitive)."""
    for key in event_dict:
        if key.lower() in SENSITIVE_KEYS:
            event_dict[key] = "[REDACTED]"
    return event_dict


def resolve_log_level(log_level: LogLevel | None, environment: Environment) -> LogLevel:
    """Resolve the effective log level, falling back to the environment default."""
    if log_level is not None:
        return log_level

    match environment:
        case Environment.PRODUCTION | Environment.STAGING:
            return LogLevel.INFO
        case Environment.DEVELOPMENT:
            return LogLevel.DEBUG
        case Environment.TESTING:
            return LogLevel.WARNING
        case _ as unknown_env:
            assert_never(unknown_env)


def build_stdout_handler(
    log_level: LogLevel, environment: Environment
) -> logging.StreamHandler[TextIO]:
    """Build a stdout handler with JSON formatting in prod/staging and console output in dev/test."""
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(log_level)
    stdout_handler.addFilter(TraceContextFilter())

    if environment in (Environment.PRODUCTION, Environment.STAGING):
        stdout_handler.setFormatter(
            OrjsonFormatter(
                "{levelname} {name} {message}",
                style="{",
                rename_fields={"levelname": "severity"},
                timestamp=True,
            )
        )
    else:
        stdout_handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                foreign_pre_chain=[
                    structlog.contextvars.merge_contextvars,
                    structlog.stdlib.add_log_level,
                    structlog.stdlib.add_logger_name,
                    structlog.stdlib.ExtraAdder(),
                    redact_sensitive_fields,
                    structlog.processors.TimeStamper(
                        fmt="%Y-%m-%d %H:%M:%S", utc=False
                    ),
                ],
                processors=[
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    structlog.dev.ConsoleRenderer(
                        colors=(environment != Environment.TESTING)
                    ),
                ],
            )
        )

    return stdout_handler


def setup_logging(
    environment: Environment,
    log_level: LogLevel | None = None,
    logger_provider: LoggerProvider | None = None,
) -> None:
    """Configure Python's root logger and structlog for the given environment.

    Behavior by environment (`ENVIRONMENT`):
    - `production` / `staging`:
        * Level defaults to `INFO`
        * `stdout` uses `python-json-logger` (`OrjsonFormatter`) with ISO-8601 UTC timestamps
        * Attaches OpenTelemetry `LoggingHandler` when `logger_provider` is provided
        * Sets `cache_logger_on_first_use=True` for maximum speed
    - `development`:
        * Level defaults to `DEBUG`
        * `stdout` uses colorized human-readable output (`structlog.dev.ConsoleRenderer`)
        * Attaches OpenTelemetry `LoggingHandler` when `logger_provider` is provided
        * Sets `cache_logger_on_first_use=True`
    - `testing`:
        * Level defaults to `WARNING` (keeps test output quiet)
        * Skips OTLP network handler
        * Sets `cache_logger_on_first_use=False` so `structlog.testing.capture_logs()` works in pytest
    """
    effective_level = resolve_log_level(log_level, environment)

    handlers: list[logging.Handler] = []

    # Configure Handler A: OpenTelemetry LoggingHandler (registered first so it reads
    # the unmutated LogRecord before stdout's TraceContextFilter injects attributes)
    if logger_provider is not None:
        otel_handler = LoggingHandler(
            level=effective_level, logger_provider=logger_provider
        )
        handlers.append(otel_handler)

    # Configure Handler B: stdout (JSON in prod/staging, console in dev/test)
    stdout_handler = build_stdout_handler(effective_level, environment)
    handlers.append(stdout_handler)

    # Configure Python's root logger
    logging.basicConfig(level=effective_level, handlers=handlers, force=True)

    # Prevent low-level HTTP/event-loop debug logs from flooding output or
    # triggering recursive OTLP HTTP export loops when root level is DEBUG
    for logger_name in NOISY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    # Configure structlog processor pipeline bridging into stdlib logging
    processors: list[Processor] = [
        structlog.stdlib.filter_by_level,
        structlog.contextvars.merge_contextvars,
        redact_sensitive_fields,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
        structlog.stdlib.render_to_log_kwargs,
    ]

    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        # Must be False in testing so structlog.testing.capture_logs() works reliably
        cache_logger_on_first_use=(environment != Environment.TESTING),
    )
