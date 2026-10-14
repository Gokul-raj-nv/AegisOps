"""Unit tests for metrics and remediation actions tools (no network required)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from tools.metrics import (
    get_service_metrics,
    get_all_service_metrics,
    check_db_pool_health,
)
from tools.remediation_actions import (
    increase_db_pool_size,
    scale_service_replicas,
    restart_service,
    terminate_long_running_db_queries,
    get_remediation_actions,
    RiskLevel,
)


# ---------------------------------------------------------------------------
# Metrics tool
# ---------------------------------------------------------------------------

class TestMetricsTool:
    def test_get_service_metrics_returns_snapshot(self):
        m = get_service_metrics("payment-service")
        assert m.service == "payment-service"
        assert 0.0 <= m.error_rate <= 1.0
        assert m.p99_latency_ms > 0
        assert m.db_pool_size == 20

    def test_normal_payment_service_is_healthy(self):
        m = get_service_metrics("payment-service", incident_mode=False)
        assert m.healthy is True
        assert m.error_rate < 0.05

    def test_incident_mode_payment_service_is_unhealthy(self):
        m = get_service_metrics("payment-service", incident_mode=True)
        assert m.healthy is False
        assert m.error_rate > 0.1
        assert m.db_pool_utilization >= 0.90

    def test_api_gateway_has_no_db(self):
        m = get_service_metrics("api-gateway")
        assert m.db_pool_utilization is None
        assert m.db_pool_size is None

    def test_get_all_service_metrics_returns_five_services(self):
        metrics = get_all_service_metrics()
        assert len(metrics) == 5

    def test_check_db_pool_critical_in_incident(self):
        report = check_db_pool_health("payment-service", incident_mode=True)
        assert report["has_db"] is True
        assert report["status"] in ("CRITICAL", "HIGH")  # jitter may push below 0.97 threshold
        assert report["pool_utilization"] >= 0.90

    def test_check_db_pool_ok_in_normal(self):
        report = check_db_pool_health("payment-service", incident_mode=False)
        assert report["status"] in ("OK", "WARNING")

    def test_to_dict_serializable(self):
        m = get_service_metrics("auth-service")
        d = m.to_dict()
        assert isinstance(d, dict)
        assert "error_rate" in d


# ---------------------------------------------------------------------------
# Remediation actions tool
# ---------------------------------------------------------------------------

class TestRemediationActionsTool:
    def test_increase_db_pool_size(self):
        action = increase_db_pool_size("payment-service", current_size=20, target_size=50)
        assert action.action_id == "increase_db_pool_size"
        assert action.risk_level == RiskLevel.MEDIUM
        assert action.requires_approval is True
        assert len(action.steps) >= 4
        assert "50" in " ".join(action.steps)

    def test_scale_service_replicas(self):
        action = scale_service_replicas("auth-service", current_replicas=2, target_replicas=4)
        assert action.risk_level == RiskLevel.LOW
        assert action.requires_approval is False

    def test_restart_service(self):
        action = restart_service("payment-service")
        assert action.risk_level == RiskLevel.MEDIUM
        assert action.requires_approval is True
        assert len(action.rollback_steps) > 0

    def test_terminate_queries_is_high_risk(self):
        action = terminate_long_running_db_queries("payment-service")
        assert action.risk_level == RiskLevel.HIGH
        assert action.requires_approval is True
        assert len(action.warnings) > 0

    def test_get_remediation_actions_db_pool(self):
        actions = get_remediation_actions("db_pool_exhaustion", "payment-service")
        assert len(actions) >= 2
        action_ids = [a.action_id for a in actions]
        assert "increase_db_pool_size" in action_ids

    def test_get_remediation_actions_unknown_returns_empty(self):
        actions = get_remediation_actions("unknown_root_cause", "payment-service")
        assert actions == []

    def test_action_to_dict(self):
        action = increase_db_pool_size("payment-service")
        d = action.to_dict()
        assert isinstance(d, dict)
        assert "steps" in d
        assert "risk_level" in d
