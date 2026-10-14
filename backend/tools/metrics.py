"""Metrics tool — provides simulated service health metrics.

In a production deployment, this would call Prometheus, Datadog, or
CloudWatch. For the MVP/demo, it returns realistic synthetic metrics
that match the INC-1842 scenario (payment-service DB pool exhaustion).

The Triage and Diagnosis agents use these metrics to confirm/deny
hypotheses before committing to a root cause.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class ServiceMetrics:
    """Point-in-time snapshot of a service's key health metrics."""

    service: str
    timestamp: str
    error_rate: float            # 0.0–1.0
    p99_latency_ms: float
    request_rate_rps: float
    cpu_percent: float
    memory_percent: float
    db_pool_utilization: float | None  # 0.0–1.0, None if service has no DB
    db_active_connections: int | None
    db_pool_size: int | None
    healthy: bool

    def to_dict(self) -> dict:
        return {
            "service": self.service,
            "timestamp": self.timestamp,
            "error_rate": self.error_rate,
            "p99_latency_ms": self.p99_latency_ms,
            "request_rate_rps": self.request_rate_rps,
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
            "db_pool_utilization": self.db_pool_utilization,
            "db_active_connections": self.db_active_connections,
            "db_pool_size": self.db_pool_size,
            "healthy": self.healthy,
        }


# ---------------------------------------------------------------------------
# Synthetic metric definitions for each service
# Normal values are "green" baselines. Incident values simulate INC-1842.
# ---------------------------------------------------------------------------

_NORMAL_METRICS: dict[str, dict] = {
    "payment-service": dict(
        error_rate=0.002, p99_latency_ms=820, request_rate_rps=45,
        cpu_percent=38, memory_percent=52,
        db_pool_utilization=0.35, db_active_connections=7, db_pool_size=20,
    ),
    "order-service": dict(
        error_rate=0.001, p99_latency_ms=380, request_rate_rps=110,
        cpu_percent=42, memory_percent=48,
        db_pool_utilization=0.40, db_active_connections=8, db_pool_size=20,
    ),
    "auth-service": dict(
        error_rate=0.001, p99_latency_ms=45, request_rate_rps=280,
        cpu_percent=22, memory_percent=35,
        db_pool_utilization=0.28, db_active_connections=3, db_pool_size=10,
    ),
    "api-gateway": dict(
        error_rate=0.002, p99_latency_ms=12, request_rate_rps=500,
        cpu_percent=18, memory_percent=30,
        db_pool_utilization=None, db_active_connections=None, db_pool_size=None,
    ),
    "notification-service": dict(
        error_rate=0.000, p99_latency_ms=0, request_rate_rps=90,
        cpu_percent=12, memory_percent=28,
        db_pool_utilization=None, db_active_connections=None, db_pool_size=None,
    ),
}

# INC-1842: payment-service during pool exhaustion
_INCIDENT_METRICS: dict[str, dict] = {
    "payment-service": dict(
        error_rate=0.32, p99_latency_ms=30012, request_rate_rps=45,
        cpu_percent=35, memory_percent=53,
        db_pool_utilization=0.98, db_active_connections=20, db_pool_size=20,
    ),
}


def get_service_metrics(service: str, incident_mode: bool = False) -> ServiceMetrics:
    """Return current metrics for a service.

    Args:
        service: Service name (e.g., 'payment-service').
        incident_mode: If True, return INC-1842-style stressed metrics.

    Returns:
        ServiceMetrics snapshot.
    """
    now = datetime.now(tz=timezone.utc).isoformat()
    base = _NORMAL_METRICS.get(service, _NORMAL_METRICS["api-gateway"]).copy()

    if incident_mode and service in _INCIDENT_METRICS:
        base.update(_INCIDENT_METRICS[service])

    # Add small random jitter to make metrics feel real
    jitter = lambda v, pct=0.05: v * (1 + random.uniform(-pct, pct)) if v else v

    healthy = base["error_rate"] < 0.05 and base["p99_latency_ms"] < 5000

    return ServiceMetrics(
        service=service,
        timestamp=now,
        error_rate=round(jitter(base["error_rate"]), 4),
        p99_latency_ms=round(jitter(base["p99_latency_ms"])),
        request_rate_rps=round(jitter(base["request_rate_rps"])),
        cpu_percent=round(jitter(base["cpu_percent"]), 1),
        memory_percent=round(jitter(base["memory_percent"]), 1),
        db_pool_utilization=round(jitter(base["db_pool_utilization"]), 3) if base["db_pool_utilization"] is not None else None,
        db_active_connections=base["db_active_connections"],
        db_pool_size=base["db_pool_size"],
        healthy=healthy,
    )


def get_all_service_metrics(incident_service: str | None = None) -> list[ServiceMetrics]:
    """Return metrics for all services.

    Args:
        incident_service: If provided, that service gets incident-mode metrics.
    """
    services = list(_NORMAL_METRICS.keys())
    return [
        get_service_metrics(svc, incident_mode=(svc == incident_service))
        for svc in services
    ]


def check_db_pool_health(service: str, incident_mode: bool = False) -> dict:
    """Return a focused DB pool health report for a service."""
    metrics = get_service_metrics(service, incident_mode=incident_mode)
    if metrics.db_pool_utilization is None:
        return {"service": service, "has_db": False}

    utilization = metrics.db_pool_utilization
    if utilization >= 0.97:
        status = "CRITICAL"
    elif utilization >= 0.90:
        status = "HIGH"
    elif utilization >= 0.80:
        status = "WARNING"
    else:
        status = "OK"

    return {
        "service": service,
        "has_db": True,
        "pool_utilization": utilization,
        "active_connections": metrics.db_active_connections,
        "pool_size": metrics.db_pool_size,
        "status": status,
        "exhausted": utilization >= 0.97,
    }
