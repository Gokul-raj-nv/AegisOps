"""OpenTelemetry tracer — span creation helpers for AegisOps.

Every agent node, LLM call, and DB operation should be wrapped
with a span so that full investigation traces are visible in
the OTel collector / Grafana Tempo / Azure Monitor.
"""
from __future__ import annotations

import functools
import time
from contextlib import contextmanager
from typing import Any, Callable, Generator

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.trace import Status, StatusCode

from config import get_settings

_tracer: trace.Tracer | None = None


def init_tracer() -> trace.Tracer:
    """Initialize the OTel tracer and configure the OTLP exporter."""
    global _tracer
    if _tracer is not None:
        return _tracer

    settings = get_settings()

    resource = Resource.create({
        "service.name": settings.otel_service_name,
        "service.version": "0.1.0",
        "deployment.environment": settings.app_env,
    })

    provider = TracerProvider(resource=resource)

    try:
        exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
    except Exception:
        # Fallback: no-op if OTel collector is not running
        pass

    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer("aegisops")
    return _tracer


def get_tracer() -> trace.Tracer:
    """Get the initialized tracer (lazy init)."""
    global _tracer
    if _tracer is None:
        return init_tracer()
    return _tracer


@contextmanager
def agent_span(
    agent_name: str,
    incident_id: str,
    attributes: dict[str, Any] | None = None,
) -> Generator[trace.Span, None, None]:
    """Context manager that wraps an agent node execution in an OTel span.

    Usage:
        with agent_span("triage", incident_id) as span:
            span.set_attribute("service", state["service"])
            result = run_triage(state)
    """
    tracer = get_tracer()
    with tracer.start_as_current_span(f"agent.{agent_name}") as span:
        span.set_attribute("incident.id", incident_id)
        span.set_attribute("agent.name", agent_name)
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, str(value))
        try:
            yield span
        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            raise


@contextmanager
def llm_span(
    agent_name: str,
    model: str,
    incident_id: str,
) -> Generator[trace.Span, None, None]:
    """Context manager for an individual LLM API call."""
    tracer = get_tracer()
    start = time.time()
    with tracer.start_as_current_span(f"llm.{agent_name}") as span:
        span.set_attribute("llm.model", model)
        span.set_attribute("agent.name", agent_name)
        span.set_attribute("incident.id", incident_id)
        try:
            yield span
        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise
        finally:
            span.set_attribute("llm.latency_ms", round((time.time() - start) * 1000, 1))


def trace_agent(agent_name: str) -> Callable:
    """Decorator that wraps an agent node function in a span.

    The decorated function must accept a state dict as its first argument
    and the state must contain 'incident_id'.

    Usage:
        @trace_agent("triage")
        def run_triage(state: AgentState) -> dict:
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(state: dict, *args, **kwargs) -> dict:
            incident_id = state.get("incident_id", "unknown")
            with agent_span(agent_name, incident_id) as span:
                span.set_attribute("service", state.get("service", ""))
                span.set_attribute("severity", state.get("severity", ""))
                result = func(state, *args, **kwargs)
                if isinstance(result, dict) and result.get("error"):
                    span.set_status(Status(StatusCode.ERROR, result["error"]))
                return result
        return wrapper
    return decorator
