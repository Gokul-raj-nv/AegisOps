"""Evaluation test harness — runs all evaluation suites and prints a report.

Usage:
    cd d:\\AegisOps
    python -m pytest tests/evaluation/ -v

Or run directly:
    python tests/evaluation/run_all.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make backend importable
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

import os
os.environ.setdefault("GOOGLE_API_KEY", "placeholder-for-unit-tests")
os.environ.setdefault("DATABASE_URL", "postgresql://dummy:dummy@localhost/dummy")
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
os.environ.setdefault("APP_ENV", "test")

import pytest


class TestConfidenceGateGuardrail:
    def test_low_confidence_blocked(self):
        from guardrails.confidence_gate import check_confidence
        r = check_confidence(0.40)
        assert not r.passed

    def test_at_threshold_passes(self):
        from guardrails.confidence_gate import check_confidence
        r = check_confidence(0.75)
        assert r.passed

    def test_high_confidence_passes(self):
        from guardrails.confidence_gate import check_confidence
        r = check_confidence(0.92)
        assert r.passed

    def test_zero_always_blocked(self):
        from guardrails.confidence_gate import check_confidence
        assert not check_confidence(0.0).passed

    def test_perfect_score_passes(self):
        from guardrails.confidence_gate import check_confidence
        assert check_confidence(1.0).passed

    def test_require_confidence_raises_on_low(self):
        from guardrails.confidence_gate import require_confidence
        with pytest.raises(ValueError):
            require_confidence(0.5)

    def test_require_confidence_ok_on_high(self):
        from guardrails.confidence_gate import require_confidence
        require_confidence(0.90)  # should not raise


class TestRiskClassifierGuardrail:
    def test_terminate_always_high(self):
        from guardrails.risk_classifier import classify_risk
        r = classify_risk("terminate_long_queries", ["pg_terminate_backend(42)"], "LOW")
        assert r.risk_level == "HIGH"
        assert r.override is True

    def test_restart_escalated_from_low(self):
        from guardrails.risk_classifier import classify_risk
        r = classify_risk("restart_service", ["kubectl rollout restart deployment/svc"], "LOW")
        assert r.risk_level in ("MEDIUM", "HIGH")

    def test_high_never_downgraded(self):
        from guardrails.risk_classifier import classify_risk
        r = classify_risk("safe_action", ["just read logs"], "HIGH")
        assert r.risk_level == "HIGH"

    def test_low_risk_clean_steps(self):
        from guardrails.risk_classifier import classify_risk
        r = classify_risk("check_metrics", ["read Prometheus dashboard"], "LOW")
        assert r.risk_level == "LOW"
        assert r.override is False

    def test_requires_approval_high(self):
        from guardrails.risk_classifier import requires_approval
        assert requires_approval("HIGH") is True

    def test_requires_approval_medium(self):
        from guardrails.risk_classifier import requires_approval
        assert requires_approval("MEDIUM") is True

    def test_no_approval_needed_low(self):
        from guardrails.risk_classifier import requires_approval
        assert requires_approval("LOW") is False


class TestPermissionCheckerGuardrail:
    def test_anonymous_cannot_approve(self):
        from guardrails.permission_checker import can_approve_remediation
        assert not can_approve_remediation("anonymous").allowed

    def test_empty_user_cannot_approve(self):
        from guardrails.permission_checker import can_approve_remediation
        assert not can_approve_remediation("").allowed

    def test_readonly_cannot_approve(self):
        from guardrails.permission_checker import can_approve_remediation
        assert not can_approve_remediation("readonly-auditor").allowed

    def test_sre_can_approve(self):
        from guardrails.permission_checker import can_approve_remediation
        assert can_approve_remediation("sre-alice").allowed

    def test_admin_can_approve(self):
        from guardrails.permission_checker import can_approve_remediation
        assert can_approve_remediation("admin-bob").allowed

    def test_engineer_can_approve(self):
        from guardrails.permission_checker import can_approve_remediation
        assert can_approve_remediation("eng-carol").allowed

    def test_can_trigger_investigation(self):
        from guardrails.permission_checker import can_trigger_investigation
        assert can_trigger_investigation("sre-alice").allowed

    def test_readonly_cannot_trigger(self):
        from guardrails.permission_checker import can_trigger_investigation
        assert not can_trigger_investigation("readonly-user").allowed


class TestOutputValidatorGuardrail:
    def test_valid_diagnosis_passes(self):
        from guardrails.output_validator import validate_diagnosis_output
        result = validate_diagnosis_output({
            "root_cause": "DB pool exhausted",
            "root_cause_type": "db_pool_exhaustion",
            "suspected_component": "payment-service PostgreSQL",
            "confidence": 0.92,
            "reasoning": "Pool at 98% utilization",
            "evidence_summary": "Multiple signals confirm pool exhaustion",
            "evidence_citations": ["database-runbook.md"],
        })
        assert result.valid

    def test_missing_field_fails(self):
        from guardrails.output_validator import validate_diagnosis_output
        result = validate_diagnosis_output({"root_cause": "something"})
        assert not result.valid
        assert any("Missing" in e for e in result.errors)

    def test_confidence_out_of_range_fails(self):
        from guardrails.output_validator import validate_diagnosis_output
        result = validate_diagnosis_output({
            "root_cause": "x", "root_cause_type": "unknown",
            "suspected_component": "svc", "confidence": 1.5,
            "reasoning": "r", "evidence_summary": "s", "evidence_citations": [],
        })
        assert not result.valid

    def test_valid_remediation_passes(self):
        from guardrails.output_validator import validate_remediation_output
        result = validate_remediation_output({
            "steps": ["Step 1", "Step 2"],
            "risk_level": "MEDIUM",
            "expected_impact": "Pool utilization drops",
            "rollback_plan": "kubectl rollout undo",
            "rationale": "Increase pool size",
            "requires_approval": True,
            "action_id": "increase_db_pool_size",
        })
        assert result.valid

    def test_empty_steps_fails(self):
        from guardrails.output_validator import validate_remediation_output
        result = validate_remediation_output({
            "steps": [], "risk_level": "LOW",
            "expected_impact": "x", "rollback_plan": "y",
            "rationale": "z", "requires_approval": False, "action_id": "a",
        })
        assert not result.valid

    def test_invalid_risk_level_fails(self):
        from guardrails.output_validator import validate_remediation_output
        result = validate_remediation_output({
            "steps": ["step"], "risk_level": "EXTREME",
            "expected_impact": "x", "rollback_plan": "y",
            "rationale": "z", "requires_approval": True, "action_id": "a",
        })
        assert not result.valid

    def test_parse_json_with_markdown_fence(self):
        from guardrails.output_validator import parse_and_validate_llm_json
        raw = '```json\n{"root_cause": "x", "root_cause_type": "unknown", "suspected_component": "svc", "confidence": 0.5, "reasoning": "r", "evidence_summary": "s", "evidence_citations": []}\n```'
        result = parse_and_validate_llm_json(raw, "diagnosis")
        assert result.valid


class TestActionLimiterGuardrail:
    def test_first_call_allowed(self):
        from guardrails.action_limiter import ActionLimiter
        limiter = ActionLimiter()
        result = limiter.check("restart_service")
        assert result.allowed

    def test_check_and_record_increments(self):
        from guardrails.action_limiter import ActionLimiter
        limiter = ActionLimiter()
        r1 = limiter.check_and_record("scale_service_replicas")
        assert r1.allowed
        assert r1.count_in_window == 0  # count before recording

    def test_exceeding_limit_blocked(self):
        from guardrails.action_limiter import ActionLimiter
        limiter = ActionLimiter()
        # restart_service limit is 2 per 600s
        limiter.record("restart_service")
        limiter.record("restart_service")
        result = limiter.check("restart_service")
        assert not result.allowed


class TestAgentEvaluation:
    def test_correct_diagnosis_passes(self):
        from evaluation.agent_eval import evaluate_diagnosis
        result = evaluate_diagnosis({
            "root_cause": "Database connection pool exhaustion on payment-service. Pool at 98%.",
            "root_cause_type": "db_pool_exhaustion",
            "suspected_component": "payment-service PostgreSQL connection pool",
            "confidence": 0.92,
            "reasoning": "DB pool utilization critical. Connection queue growing.",
            "evidence_summary": "Multiple signals confirm pool exhaustion.",
            "evidence_citations": ["database-pool-runbook.md", "incident-INC-1842.md"],
        })
        assert result.passed
        assert result.score >= 0.7

    def test_wrong_root_cause_type_scores_low(self):
        from evaluation.agent_eval import evaluate_diagnosis
        result = evaluate_diagnosis({
            "root_cause": "Unknown issue",
            "root_cause_type": "high_cpu",
            "suspected_component": "some-service",
            "confidence": 0.4,
            "reasoning": "Unknown",
            "evidence_summary": "No clear evidence",
            "evidence_citations": [],
        })
        assert not result.passed

    def test_none_diagnosis_fails(self):
        from evaluation.agent_eval import evaluate_diagnosis
        result = evaluate_diagnosis(None)
        assert not result.passed
        assert result.score == 0.0

    def test_good_remediation_passes(self):
        from evaluation.agent_eval import evaluate_remediation
        result = evaluate_remediation({
            "steps": [
                "Set DB_POOL_SIZE=50 in payment-service config",
                "kubectl rollout restart deployment/payment-service",
                "Monitor DB pool utilization for 5 minutes",
            ],
            "risk_level": "MEDIUM",
            "expected_impact": "Pool utilization drops below 50% within 2 minutes.",
            "rollback_plan": "kubectl rollout undo deployment/payment-service && revert DB_POOL_SIZE",
            "rationale": "Increase pool size to accommodate peak load",
            "requires_approval": True,
            "action_id": "increase_db_pool_size",
        })
        assert result.passed
        assert result.score >= 0.6


class TestCostTracker:
    def test_record_and_report(self):
        from evaluation.cost_tracker import CostTracker
        tracker = CostTracker()
        tracker.record_call(
            incident_id="test-123",
            agent_name="diagnosis",
            model="gemini-2.5-flash",
            input_tokens=1500,
            output_tokens=400,
            latency_ms=1200.0,
        )
        report = tracker.get_report("test-123")
        assert report.call_count == 1
        assert report.total_input_tokens == 1500
        assert report.total_output_tokens == 400
        assert report.total_cost_usd > 0
        assert "diagnosis" in report.by_agent

    def test_empty_report(self):
        from evaluation.cost_tracker import CostTracker
        tracker = CostTracker()
        report = tracker.get_report("nonexistent")
        assert report.call_count == 0
        assert report.total_cost_usd == 0.0

    def test_estimate_tokens(self):
        from evaluation.cost_tracker import estimate_tokens
        tokens = estimate_tokens("Hello world")
        assert tokens >= 1

    def test_cost_calculation(self):
        from evaluation.cost_tracker import LLMCallRecord
        rec = LLMCallRecord(
            agent_name="triage", model="gemini-2.5-flash",
            input_tokens=1_000_000, output_tokens=0, latency_ms=0,
        )
        # 1M input tokens at $0.15/1M = $0.15
        assert abs(rec.cost_usd - 0.15) < 0.001
