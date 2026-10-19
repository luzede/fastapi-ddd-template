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
from pydantic import HttpUrl

from app.core.config import Environment


@dataclass(frozen=True, slots=True)
class Telemetry:
    tracer_provider: TracerProvider
    logger_provider: LoggerProvider | None
    """None when no OTLP endpoint is configured or in the testing environment."""


def setup_opentelemetry(
    service_name: str,
    otlp_endpoint: HttpUrl | None,
    environment: Environment,
) -> Telemetry:
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

    # Tracing Pipeline (always registered so trace_id & span_id are generated in all envs)
    tracer_provider = TracerProvider(resource=resource)
    logger_provider: LoggerProvider | None = None

    if should_export_otlp and otlp_endpoint is not None:
        base_endpoint = otlp_endpoint.encoded_string().rstrip("/")

        tracer_provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{base_endpoint}/v1/traces"))
        )

        logger_provider = LoggerProvider(resource=resource)
        logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(
                OTLPLogExporter(endpoint=f"{base_endpoint}/v1/logs")
            )
        )
        set_logger_provider(logger_provider)

    trace.set_tracer_provider(tracer_provider)

    return Telemetry(tracer_provider=tracer_provider, logger_provider=logger_provider)
