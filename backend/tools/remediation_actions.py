"""Remediation actions tool.

Provides executable remediation actions that agents can propose.
Each action is described, risk-classified, and paired with a rollback.

In Phase 4 (guardrails), actions above a risk threshold will require
human approval before execution. In this MVP, no action actually
modifies infrastructure — they return a "would execute" response.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass
class RemediationAction:
    """A single proposed remediation action."""

    action_id: str
    title: str
    description: str
    steps: list[str]
    risk_level: RiskLevel
    expected_impact: str
    rollback_steps: list[str]
    requires_approval: bool
    parameters: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "action_id": self.action_id,
            "title": self.title,
            "description": self.description,
            "steps": self.steps,
            "risk_level": self.risk_level.value,
            "expected_impact": self.expected_impact,
            "rollback_steps": self.rollback_steps,
            "requires_approval": self.requires_approval,
            "parameters": self.parameters,
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# Action library — pre-defined remediation playbooks
# ---------------------------------------------------------------------------

def increase_db_pool_size(
    service: str,
    current_size: int = 20,
    target_size: int = 50,
) -> RemediationAction:
    """Increase the database connection pool size for a service."""
    return RemediationAction(
        action_id="increase_db_pool_size",
        title=f"Increase DB connection pool for {service}",
        description=(
            f"Update DB_POOL_SIZE from {current_size} to {target_size} and "
            f"perform a rolling restart of {service}."
        ),
        steps=[
            f"1. Verify PostgreSQL max_connections allows pool_size={target_size} "
            f"× replicas (check: SELECT setting FROM pg_settings WHERE name='max_connections').",
            f"2. Update environment variable: DB_POOL_SIZE={target_size}",
            f"3. Trigger rolling restart: kubectl rollout restart deployment/{service}",
            f"4. Monitor pool utilization metric — target <70% within 2 minutes.",
            f"5. Verify error rate drops below 1% within 2 minutes.",
        ],
        risk_level=RiskLevel.MEDIUM,
        expected_impact=(
            f"Pool utilization should drop from ~98% to ~40%. "
            f"HTTP 500 errors should cease within 2 minutes of restart."
        ),
        rollback_steps=[
            f"kubectl rollout undo deployment/{service}",
            f"Verify service returns to previous state.",
        ],
        requires_approval=True,
        parameters={"current_pool_size": current_size, "target_pool_size": target_size},
        warnings=[
            f"Ensure DB max_connections >= {target_size} × replica count.",
            "Rolling restart will cause brief connection interruption (~10s).",
        ],
    )


def scale_service_replicas(
    service: str,
    current_replicas: int = 2,
    target_replicas: int = 4,
) -> RemediationAction:
    """Scale a Kubernetes deployment to more replicas."""
    return RemediationAction(
        action_id="scale_service_replicas",
        title=f"Scale {service} from {current_replicas} to {target_replicas} replicas",
        description=f"Horizontally scale {service} to handle increased load.",
        steps=[
            f"1. kubectl scale deployment/{service} --replicas={target_replicas}",
            f"2. kubectl rollout status deployment/{service} --timeout=3m",
            f"3. Verify all {target_replicas} pods are Running.",
            f"4. Monitor error rate and latency — should improve within 1 minute.",
        ],
        risk_level=RiskLevel.LOW,
        expected_impact="Distributes load across more pods; reduces per-pod resource pressure.",
        rollback_steps=[
            f"kubectl scale deployment/{service} --replicas={current_replicas}",
        ],
        requires_approval=False,
        parameters={"current_replicas": current_replicas, "target_replicas": target_replicas},
    )


def restart_service(service: str) -> RemediationAction:
    """Rolling restart of a service."""
    return RemediationAction(
        action_id="restart_service",
        title=f"Rolling restart of {service}",
        description=f"Perform a zero-downtime rolling restart of {service}.",
        steps=[
            f"1. kubectl rollout restart deployment/{service}",
            f"2. kubectl rollout status deployment/{service} --timeout=5m",
            "3. Verify health endpoint returns 200.",
            "4. Monitor error rate for 5 minutes post-restart.",
        ],
        risk_level=RiskLevel.MEDIUM,
        expected_impact="Clears in-memory state, resets DB connections, applies env var changes.",
        rollback_steps=[
            f"kubectl rollout undo deployment/{service}",
        ],
        requires_approval=True,
        warnings=["Brief unavailability (~10s) per pod during rolling restart."],
    )


def terminate_long_running_db_queries(service: str, threshold_seconds: int = 60) -> RemediationAction:
    """Terminate DB queries running longer than threshold."""
    return RemediationAction(
        action_id="terminate_long_queries",
        title=f"Terminate long-running queries on {service} database",
        description=(
            f"Kill DB queries running longer than {threshold_seconds}s "
            f"to free connection pool slots."
        ),
        steps=[
            f"1. Connect to the {service} database.",
            f"2. Run: SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE query_start < now() - interval '{threshold_seconds} seconds' AND state != 'idle';",
            "3. Verify pool utilization drops.",
        ],
        risk_level=RiskLevel.HIGH,
        expected_impact="Immediately frees blocked connection pool slots.",
        rollback_steps=["Cannot rollback terminated queries — ensure safety before execution."],
        requires_approval=True,
        warnings=[
            "Terminating queries may cause in-flight transactions to fail.",
            "Verify no critical batch jobs are running before executing.",
        ],
        parameters={"threshold_seconds": threshold_seconds},
    )


# ---------------------------------------------------------------------------
# Action selector — used by the Remediation Agent
# ---------------------------------------------------------------------------

KNOWN_REMEDIATIONS: dict[str, Any] = {
    "db_pool_exhaustion": [
        lambda service, **kw: increase_db_pool_size(service, **kw),
        lambda service, **kw: terminate_long_running_db_queries(service),
        lambda service, **kw: restart_service(service),
    ],
    "high_cpu": [
        lambda service, **kw: scale_service_replicas(service),
    ],
    "memory_leak": [
        lambda service, **kw: restart_service(service),
    ],
    "replica_overload": [
        lambda service, **kw: scale_service_replicas(service),
    ],
}


def get_remediation_actions(
    root_cause_type: str,
    service: str,
    **kwargs: Any,
) -> list[RemediationAction]:
    """Return ordered list of remediation actions for a diagnosed root cause.

    Args:
        root_cause_type: Short key identifying the root cause category.
            e.g., 'db_pool_exhaustion', 'high_cpu', 'memory_leak'.
        service: Affected service name.
        **kwargs: Additional parameters forwarded to action constructors.

    Returns:
        List of RemediationAction in recommended execution order.
    """
    builders = KNOWN_REMEDIATIONS.get(root_cause_type, [])
    return [b(service, **kwargs) for b in builders]
