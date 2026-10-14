"""Custom metrics — Prometheus / OTel metrics for AegisOps.

Exposes key business metrics:
  - incidents created, investigated, resolved
  - diagnosis confidence distribution
  - remediation risk level breakdown
  - agent latency histograms
  - LLM call counts and costs
"""
from __future__ import annotations

from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.prometheus import PrometheusMetricReader

_meter: metrics.Meter | None = None

# --- Instruments (created once) ---
_incident_counter = None
_diagnosis_confidence_histogram = None
_agent_latency_histogram = None
_llm_call_counter = None
_remediation_risk_counter = None


def init_metrics() -> metrics.Meter:
    """Initialize OTel metrics with Prometheus exporter."""
    global _meter, _incident_counter, _diagnosis_confidence_histogram
    global _agent_latency_histogram, _llm_call_counter, _remediation_risk_counter

    if _meter is not None:
        return _meter

    try:
        reader = PrometheusMetricReader()
        provider = MeterProvider(metric_readers=[reader])
        metrics.set_meter_provider(provider)
    except Exception:
        # Prometheus exporter not available — use default no-op
        metrics.set_meter_provider(MeterProvider())

    _meter = metrics.get_meter("aegisops", version="0.1.0")

    _incident_counter = _meter.create_counter(
        "aegisops.incidents.total",
        description="Total number of incidents ingested",
        unit="1",
    )
    _diagnosis_confidence_histogram = _meter.create_histogram(
        "aegisops.diagnosis.confidence",
        description="Distribution of diagnosis confidence scores",
        unit="1",
    )
    _agent_latency_histogram = _meter.create_histogram(
        "aegisops.agent.latency_ms",
        description="Agent node execution latency in milliseconds",
        unit="ms",
    )
    _llm_call_counter = _meter.create_counter(
        "aegisops.llm.calls.total",
        description="Total number of LLM API calls",
        unit="1",
    )
    _remediation_risk_counter = _meter.create_counter(
        "aegisops.remediation.risk.total",
        description="Count of remediation plans by risk level",
        unit="1",
    )

    return _meter


def record_incident_created(service: str, severity: str) -> None:
    init_metrics()
    if _incident_counter:
        _incident_counter.add(1, {"service": service, "severity": severity})


def record_diagnosis_confidence(confidence: float, service: str) -> None:
    init_metrics()
    if _diagnosis_confidence_histogram:
        _diagnosis_confidence_histogram.record(confidence, {"service": service})


def record_agent_latency(agent_name: str, latency_ms: float) -> None:
    init_metrics()
    if _agent_latency_histogram:
        _agent_latency_histogram.record(latency_ms, {"agent": agent_name})


def record_llm_call(agent_name: str, model: str) -> None:
    init_metrics()
    if _llm_call_counter:
        _llm_call_counter.add(1, {"agent": agent_name, "model": model})


def record_remediation_risk(risk_level: str, service: str) -> None:
    init_metrics()
    if _remediation_risk_counter:
        _remediation_risk_counter.add(1, {"risk_level": risk_level, "service": service})
