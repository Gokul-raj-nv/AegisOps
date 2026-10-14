"""Unit tests for the Phase 4 workflow components (no LLM/API keys needed)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from graph.state import AgentState, make_initial_state, DiagnosisResult, RemediationResult


# ---------------------------------------------------------------------------
# AgentState tests
# ---------------------------------------------------------------------------

class TestAgentState:
    def test_make_initial_state_defaults(self):
        state = make_initial_state(
            incident_id="test-id-123",
            service="payment-service",
            severity="HIGH",
            description="Error rate at 32%",
        )
        assert state["incident_id"] == "test-id-123"
        assert state["service"] == "payment-service"
        assert state["knowledge_evidence"] == []
        assert state["log_evidence"] == []
        assert state["diagnosis"] is None
        assert state["remediation"] is None
        assert state["requires_human_approval"] is False
        assert state["agent_errors"] == []

    def test_make_initial_state_with_logs(self):
        state = make_initial_state(
            incident_id="abc",
            service="auth-service",
            severity="MEDIUM",
            description="CPU high",
            raw_logs="ERROR timeout\nERROR connection refused",
        )
        assert state["raw_logs"] is not None
        assert "ERROR" in state["raw_logs"]

    def test_diagnosis_result_structure(self):
        diag = DiagnosisResult(
            root_cause="DB pool exhausted",
            root_cause_type="db_pool_exhaustion",
            suspected_component="payment-service PostgreSQL",
            confidence=0.92,
            reasoning="Pool at 98%",
            evidence_summary="Multiple signals confirm pool exhaustion",
            evidence_citations=["database-connection-pool.md (score: 0.94)"],
        )
        assert diag["confidence"] == 0.92
        assert diag["root_cause_type"] == "db_pool_exhaustion"

    def test_remediation_result_structure(self):
        rem = RemediationResult(
            steps=["Step 1", "Step 2"],
            risk_level="MEDIUM",
            expected_impact="Pool utilization will drop",
            rollback_plan="kubectl rollout undo",
            rationale="Increase pool size to accommodate load",
            requires_approval=True,
            action_id="increase_db_pool_size",
        )
        assert rem["risk_level"] == "MEDIUM"
        assert rem["requires_approval"] is True
        assert len(rem["steps"]) == 2


# ---------------------------------------------------------------------------
# Workflow graph construction test (no execution)
# ---------------------------------------------------------------------------

class TestWorkflowGraph:
    def test_graph_builds_without_error(self):
        """Verify the LangGraph graph compiles without import or wiring errors."""
        from graph.workflow import build_graph
        graph = build_graph()
        assert graph is not None

    def test_get_workflow_returns_compiled_graph(self):
        from graph.workflow import get_workflow
        workflow = get_workflow()
        assert workflow is not None

    def test_workflow_has_expected_nodes(self):
        """Verify all 6 agent nodes plus terminal nodes are registered."""
        from graph.workflow import build_graph
        graph = build_graph()
        # LangGraph compiled graphs expose node names
        node_names = set(graph.nodes.keys())
        expected = {
            "triage", "rag_search", "log_analysis", "diagnosis",
            "remediation", "validation", "escalation",
            "awaiting_approval", "complete", "failed",
        }
        assert expected.issubset(node_names), f"Missing nodes: {expected - node_names}"


# ---------------------------------------------------------------------------
# Routing logic tests (unit — no LLM)
# ---------------------------------------------------------------------------

class TestRoutingLogic:
    def test_route_after_diagnosis_to_remediation(self):
        from graph.workflow import route_after_diagnosis
        state = make_initial_state("id", "svc", "HIGH", "desc")
        state["next_action"] = "remediate"
        assert route_after_diagnosis(state) == "remediation"

    def test_route_after_diagnosis_to_escalation(self):
        from graph.workflow import route_after_diagnosis
        state = make_initial_state("id", "svc", "HIGH", "desc")
        state["next_action"] = "escalate"
        assert route_after_diagnosis(state) == "escalation"

    def test_route_after_validation_awaiting_approval(self):
        from graph.workflow import route_after_validation
        state = make_initial_state("id", "svc", "HIGH", "desc")
        state["next_action"] = "awaiting_approval"
        assert route_after_validation(state) == "awaiting_approval"

    def test_route_after_validation_complete(self):
        from graph.workflow import route_after_validation
        state = make_initial_state("id", "svc", "HIGH", "desc")
        state["next_action"] = "complete"
        assert route_after_validation(state) == "complete"

    def test_route_after_validation_failed(self):
        from graph.workflow import route_after_validation
        state = make_initial_state("id", "svc", "HIGH", "desc")
        state["next_action"] = "failed"
        assert route_after_validation(state) == "failed"


# ---------------------------------------------------------------------------
# Rule-based diagnosis fallback (no LLM)
# ---------------------------------------------------------------------------

class TestRuleBasedDiagnosis:
    def test_db_pool_exhaustion_detected_from_metrics(self):
        from agents.diagnosis import _rule_based_diagnosis
        state = make_initial_state("id", "payment-service", "HIGH", "500 errors")
        state["metrics"] = {
            "service": "payment-service",
            "error_rate": 0.32,
            "p99_latency_ms": 30000,
            "db_pool_utilization": 0.98,
            "db_pool_size": 20,
            "db_active_connections": 20,
            "cpu_percent": 35,
            "healthy": False,
        }
        diag = _rule_based_diagnosis(state)
        assert diag["root_cause_type"] == "db_pool_exhaustion"
        assert diag["confidence"] > 0.7

    def test_unknown_root_cause_when_metrics_normal(self):
        from agents.diagnosis import _rule_based_diagnosis
        state = make_initial_state("id", "payment-service", "HIGH", "500 errors")
        state["metrics"] = {
            "service": "payment-service",
            "error_rate": 0.32,
            "p99_latency_ms": 30000,
            "db_pool_utilization": 0.40,
            "db_pool_size": 20,
            "db_active_connections": 8,
            "cpu_percent": 35,
            "healthy": False,
        }
        diag = _rule_based_diagnosis(state)
        assert diag["root_cause_type"] == "unknown"
        assert diag["confidence"] < 0.5
