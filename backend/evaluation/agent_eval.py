"""Agent Evaluation — measures accuracy and quality of agent outputs.

Evaluates against the canonical INC-1842 scenario (payment-service 
DB pool exhaustion) where the expected outputs are known.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# ---------------------------------------------------------------------------
# Golden-set ground truth for INC-1842
# ---------------------------------------------------------------------------

INC_1842_GROUND_TRUTH = {
    "service": "payment-service",
    "severity": "HIGH",
    "description": "Payment service HTTP 500 error rate at 32%, P99 latency 30s",
    "expected_root_cause_type": "db_pool_exhaustion",
    "expected_suspected_component": "payment-service",
    "expected_min_confidence": 0.75,
    "expected_risk_levels": ["MEDIUM", "HIGH"],
    "expected_remediation_keywords": ["pool", "DB_POOL_SIZE", "restart"],
    "expected_requires_approval": True,
}


@dataclass
class AgentEvalResult:
    passed: bool
    score: float          # 0.0 – 1.0 composite score
    checks: dict[str, bool]
    details: dict[str, Any]


def evaluate_diagnosis(diagnosis: dict[str, Any] | None) -> AgentEvalResult:
    """Evaluate a Diagnosis Agent output against the INC-1842 ground truth."""
    gt = INC_1842_GROUND_TRUTH
    checks: dict[str, bool] = {}
    details: dict[str, Any] = {}

    if not diagnosis:
        return AgentEvalResult(passed=False, score=0.0, checks={}, details={"error": "No diagnosis"})

    # Check 1: Root cause type correct
    checks["root_cause_type_correct"] = (
        diagnosis.get("root_cause_type") == gt["expected_root_cause_type"]
    )

    # Check 2: Confidence meets threshold
    confidence = diagnosis.get("confidence", 0.0)
    checks["confidence_meets_threshold"] = confidence >= gt["expected_min_confidence"]
    details["confidence"] = confidence

    # Check 3: Suspected component mentions expected service
    component = (diagnosis.get("suspected_component") or "").lower()
    checks["component_identified"] = gt["expected_suspected_component"] in component

    # Check 4: Root cause mentions key concepts
    root_cause = (diagnosis.get("root_cause") or "").lower()
    key_terms = {"pool", "connection", "exhaustion", "database", "db"}
    matched_terms = [t for t in key_terms if t in root_cause]
    checks["root_cause_has_key_terms"] = len(matched_terms) >= 2
    details["matched_terms"] = matched_terms

    # Check 5: Has evidence citations
    citations = diagnosis.get("evidence_citations", [])
    checks["has_evidence_citations"] = len(citations) > 0
    details["citation_count"] = len(citations)

    score = sum(checks.values()) / len(checks)
    passed = score >= 0.7  # Pass if 70%+ checks pass

    return AgentEvalResult(passed=passed, score=round(score, 3), checks=checks, details=details)


def evaluate_remediation(remediation: dict[str, Any] | None) -> AgentEvalResult:
    """Evaluate a Remediation Agent output against the INC-1842 ground truth."""
    gt = INC_1842_GROUND_TRUTH
    checks: dict[str, bool] = {}
    details: dict[str, Any] = {}

    if not remediation:
        return AgentEvalResult(passed=False, score=0.0, checks={}, details={"error": "No remediation"})

    # Check 1: Risk level is appropriate
    checks["risk_level_appropriate"] = (
        remediation.get("risk_level", "").upper() in gt["expected_risk_levels"]
    )
    details["risk_level"] = remediation.get("risk_level")

    # Check 2: Requires approval for a HIGH/MEDIUM risk action
    checks["requires_approval"] = remediation.get("requires_approval", False) == gt["expected_requires_approval"]

    # Check 3: Steps contain expected keywords
    steps_text = " ".join(remediation.get("steps", [])).lower()
    matched_kw = [kw for kw in gt["expected_remediation_keywords"] if kw.lower() in steps_text]
    checks["steps_have_key_terms"] = len(matched_kw) >= 2
    details["matched_keywords"] = matched_kw

    # Check 4: Has rollback plan
    rollback = remediation.get("rollback_plan", "")
    checks["has_rollback_plan"] = len(rollback.strip()) > 20

    # Check 5: Has at least 3 steps
    steps = remediation.get("steps", [])
    checks["sufficient_steps"] = len(steps) >= 3
    details["step_count"] = len(steps)

    score = sum(checks.values()) / len(checks)
    passed = score >= 0.6

    return AgentEvalResult(passed=passed, score=round(score, 3), checks=checks, details=details)


def run_full_agent_eval(final_state: dict[str, Any]) -> dict[str, Any]:
    """Run complete agent evaluation on a completed workflow state.

    Args:
        final_state: The final AgentState dict from run_workflow_sync().

    Returns:
        Dict with diagnosis_eval and remediation_eval results.
    """
    diag_eval = evaluate_diagnosis(final_state.get("diagnosis"))
    rem_eval = evaluate_remediation(final_state.get("remediation"))

    overall_score = (diag_eval.score + rem_eval.score) / 2

    return {
        "diagnosis_eval": {
            "passed": diag_eval.passed,
            "score": diag_eval.score,
            "checks": diag_eval.checks,
            "details": diag_eval.details,
        },
        "remediation_eval": {
            "passed": rem_eval.passed,
            "score": rem_eval.score,
            "checks": rem_eval.checks,
            "details": rem_eval.details,
        },
        "overall_score": round(overall_score, 3),
        "overall_passed": diag_eval.passed and rem_eval.passed,
    }
