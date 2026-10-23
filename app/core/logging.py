"""Structured logging configuration (structlog + stdlib bridge + OpenTelemetry LoggingHandler).

Architecture Overview:
1. Both `structlog` loggers and standard library (`logging`) loggers flow through the root
   stdlib `Logger`.
2. `structlog` does NOT render strings directly; instead, `render_to_log_kwargs` unpacks
   structured key-value pairs into `extra={...}` on the stdlib `LogRecord`.
3. Every handler (OpenTelemetry and stdout) then receives a rich `LogRecord` with structured
   attributes attached, allowing OTel to export native structured attributes and stdout to
   render either JSON (prod/staging) or colored console output (dev/test).
"""

import logging
import sys
from typing import Any, Final, TextIO, assert_never, override

import structlog
from opentelemetry import trace
from opentelemetry.instrumentation.logging.handler import LoggingHandler
from opentelemetry.sdk._logs import LoggerProvider
from pythonjsonlogger.core import RESERVED_ATTRS
from pythonjsonlogger.orjson import OrjsonFormatter
from structlog.typing import EventDict, Processor

from app.core.config import Environment, LogLevel

# Keys matched case-insensitively across both top-level `extra` fields and nested payloads.
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

# Third-party loggers that emit excessive DEBUG/INFO noise during normal operation.
NOISY_LOGGERS: Final[tuple[str, ...]] = (
    "urllib3",
    "httpcore",
    "httpx",
    "asyncio",
    "watchfiles",
)


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


def redact_value(value: Any) -> Any:
    """Recursively redact sensitive keys inside nested dicts, lists, and tuples."""
    if isinstance(value, dict):
        return {
            k: "[REDACTED]"
            if isinstance(k, str) and k.lower() in SENSITIVE_KEYS
            else redact_value(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_value(item) for item in value)
    return value


def sanitize_event_dict(
    logger: Any, method_name: str, event_dict: EventDict
) -> EventDict:
    """Drop Uvicorn's internal `color_message` key and redact sensitive fields in place."""
    # Uvicorn attaches `color_message` with ANSI escape codes that pollute JSON/OTel logs.
    event_dict.pop("color_message", None)
    for key, value in event_dict.items():
        # Skip standard LogRecord attributes (msg, args, levelname, pathname, etc.)
        # so we don't accidentally clobber internal stdlib logging state.
        if key in RESERVED_ATTRS:
            continue
        if key.lower() in SENSITIVE_KEYS:
            event_dict[key] = "[REDACTED]"
        else:
            event_dict[key] = redact_value(value)
    return event_dict


def drop_formatter_cache_keys(
    logger: Any, method_name: str, event_dict: EventDict
) -> EventDict:
    """Drop attributes cached on the LogRecord by earlier formatters (e.g. OTel's handler)."""
    # When OTel's LoggingHandler runs before the stdout handler, it calls `record.getMessage()`,
    # which mutates `record.message` on the shared LogRecord instance. Subsequently, structlog's
    # `ExtraAdder` copies `record.message` into `event_dict`, causing `ConsoleRenderer` to print
    # `message='...'` as a duplicate key alongside the main event text.
    event_dict.pop("message", None)
    event_dict.pop("asctime", None)
    return event_dict


class TraceContextFilter(logging.Filter):
    """Inject active OpenTelemetry trace_id and span_id into log records for stdout output."""

    @override
    def filter(self, record: logging.LogRecord) -> bool:
        # Note: OTel's LoggingHandler attaches trace context to exported OTLP logs automatically,
        # so this filter is only needed on the stdout handler for log-trace correlation in stdout.
        span_ctx = trace.get_current_span().get_span_context()
        if span_ctx.is_valid:
            record.trace_id = trace.format_trace_id(span_ctx.trace_id)
            record.span_id = trace.format_span_id(span_ctx.span_id)
        return True


class StdlibRecordSanitizer(logging.Filter):
    """Merge structlog contextvars and sanitize every stdlib `LogRecord` in place."""

    @override
    def filter(self, record: logging.LogRecord) -> bool:
        # Filtering happens at the Handler level (rather than a structlog processor) so that
        # BOTH structlog loggers and third-party stdlib loggers (Uvicorn, SQLAlchemy, httpx)
        # receive contextvars and redaction before reaching OTel or stdout.
        record_dict = record.__dict__

        # Merge structlog contextvars so stdlib loggers (Uvicorn, libraries) include request_id, etc.
        for key, value in structlog.contextvars.get_contextvars().items():
            if key not in record_dict and key not in RESERVED_ATTRS:
                record_dict[key] = value

        # Sanitize both `extra` attributes and dict-style positional `record.args`
        # (e.g., `logger.info("User %(password)s", {"password": "secret"})`).
        sanitize_event_dict(None, "", record_dict)
        if record.args:
            record.args = redact_value(record.args)

        return True


def build_stdout_handler(
    log_level: LogLevel,
    environment: Environment,
    sanitizer: StdlibRecordSanitizer,
) -> logging.StreamHandler[TextIO]:
    """Build a stdout handler with JSON formatting in prod/staging and console output in dev/test."""
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(log_level)
    stdout_handler.addFilter(sanitizer)
    stdout_handler.addFilter(TraceContextFilter())

    if environment in (Environment.PRODUCTION, Environment.STAGING):
        # Fast Rust-backed JSON serialization; automatically serializes all non-reserved
        # attributes on `LogRecord` (including structlog's unpacked kwargs and trace_id/span_id).
        formatter: logging.Formatter = OrjsonFormatter(
            "{levelname} {name} {message}",
            style="{",
            rename_fields={"levelname": "severity"},
            timestamp=True,
        )
    else:
        # In dev/test, use ProcessorFormatter so both structlog and third-party stdlib logs
        # render with unified human-readable formatting and rich tracebacks.
        formatter = structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=[
                structlog.stdlib.add_log_level,
                structlog.stdlib.add_logger_name,
                # Pulls structured kwargs (placed onto `LogRecord` by `render_to_log_kwargs`
                # or `logging.info(..., extra={...})`) back into the structlog `event_dict`.
                structlog.stdlib.ExtraAdder(),
                drop_formatter_cache_keys,
                structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
            ],
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.dev.ConsoleRenderer(
                    colors=(environment != Environment.TESTING),
                    exception_formatter=structlog.dev.RichTracebackFormatter(
                        max_frames=10,  # Limit the number of frames in the traceback
                        show_locals=False,
                    ),
                ),
            ],
        )

    stdout_handler.setFormatter(formatter)
    return stdout_handler


def setup_logging(
    environment: Environment,
    log_level: LogLevel | None = None,
    logger_provider: LoggerProvider | None = None,
) -> None:
    """Configure Python's root logger and structlog for the given environment."""
    effective_level = resolve_log_level(log_level, environment)
    sanitizer = StdlibRecordSanitizer()
    handlers: list[logging.Handler] = []

    if logger_provider is not None and environment != Environment.TESTING:
        otel_handler = LoggingHandler(
            level=effective_level, logger_provider=logger_provider
        )
        # Attach the same sanitizer instance so OTel never exports unredacted attributes
        # or misses bound contextvars (Note: Python's logging runs Handler filters once per
        # handler, and `StdlibRecordSanitizer` is idempotent on already-mutated records).
        otel_handler.addFilter(sanitizer)
        handlers.append(otel_handler)

    handlers.append(build_stdout_handler(effective_level, environment, sanitizer))
    logging.basicConfig(level=effective_level, handlers=handlers, force=True)

    for logger_name in NOISY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    processors: list[Processor] = [
        structlog.stdlib.filter_by_level,
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
        # CRITICAL: Rather than rendering to a string or wrapping for ProcessorFormatter,
        # unpack the event_dict into `extra={...}` kwargs for `logging.Logger._log()`.
        # This allows OTel's `LoggingHandler` and `OrjsonFormatter` to inspect structured
        # fields directly on the `LogRecord` without parsing JSON strings.
        structlog.stdlib.render_to_log_kwargs,
    ]

    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        # Disable logger caching in tests so caplog / monkeypatched handlers work reliably.
        cache_logger_on_first_use=(environment != Environment.TESTING),
    )
