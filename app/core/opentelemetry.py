"""OpenTelemetry providers for traces and logs, exported over OTLP/HTTP when configured."""

from dataclasses import dataclass

from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.semconv.attributes.deployment_attributes import (
    DEPLOYMENT_ENVIRONMENT_NAME,
)
from opentelemetry.semconv.attributes.service_attributes import SERVICE_NAME

from app.core.config import Environment


@dataclass(frozen=True, slots=True)
class Telemetry:
    tracer_provider: TracerProvider
    logger_provider: LoggerProvider | None
    """None when no OTLP endpoint is configured or in the testing environment."""


# Module-level singleton guard.
# OpenTelemetry's global `set_tracer_provider` and `set_logger_provider` use a strict
# write-once lock (`Once`) and silently ignore subsequent calls. Using a true module
# singleton instead of `@lru_cache` guarantees we never spawn orphaned background
# BatchProcessor worker threads or return a provider out of sync with OTel's globals.
_telemetry: Telemetry | None = None


def setup_opentelemetry(
    service_name: str,
    otlp_endpoint: str | None,
    environment: Environment,
) -> Telemetry:
    """Initialize global OpenTelemetry providers once per process and return them."""
    global _telemetry
    if _telemetry is not None:
        return _telemetry

    # Export over the network whenever an OTLP endpoint is configured, except during tests
    should_export_otlp = (
        otlp_endpoint is not None and environment != Environment.TESTING
    )

    # Create a Resource describing this service, attached to all spans and logs
    resource = Resource.create(
        {
            SERVICE_NAME: service_name,
            DEPLOYMENT_ENVIRONMENT_NAME: environment.value,
        }
    )

    # Always register a TracerProvider (even without an exporter in local/test envs)
    # so the SDK still generates valid trace_id and span_id values for log correlation.
    tracer_provider = TracerProvider(resource=resource)
    logger_provider: LoggerProvider | None = None

    if should_export_otlp:
        base_endpoint = otlp_endpoint.rstrip("/")

        # Passing an explicit `endpoint` to OTLP/HTTP exporters overrides their automatic
        # signal-path appending, so `/v1/traces` and `/v1/logs` must be included manually.
        tracer_provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{base_endpoint}/v1/traces"))
        )

        # Unlike TracerProvider, LoggerProvider is only needed when exporting over OTLP
        # because local/test environments rely on standard Python logging output.
        logger_provider = LoggerProvider(resource=resource)
        logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(
                OTLPLogExporter(endpoint=f"{base_endpoint}/v1/logs")
            )
        )
        set_logger_provider(logger_provider)

    trace.set_tracer_provider(tracer_provider)

    _telemetry = Telemetry(
        tracer_provider=tracer_provider, logger_provider=logger_provider
    )
    return _telemetry
