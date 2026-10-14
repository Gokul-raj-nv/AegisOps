"""Confidence gate — blocks automatic remediation below threshold.

This is the primary safety guardrail: if the Diagnosis Agent's
confidence score is below MIN_AUTO_ACTION_CONFIDENCE, the workflow
cannot proceed to automatic remediation — it must escalate to a human.
"""
from __future__ import annotations

from dataclasses import dataclass

from config import get_settings


@dataclass
class ConfidenceGateResult:
    passed: bool
    confidence: float
    threshold: float
    reason: str


def check_confidence(confidence: float) -> ConfidenceGateResult:
    """Check whether a diagnosis confidence score clears the auto-action gate.

    Args:
        confidence: Score from 0.0–1.0 returned by the Diagnosis Agent.

    Returns:
        ConfidenceGateResult with pass/fail and human-readable reason.
    """
    settings = get_settings()
    threshold = settings.min_auto_action_confidence

    if confidence >= threshold:
        return ConfidenceGateResult(
            passed=True,
            confidence=confidence,
            threshold=threshold,
            reason=f"Confidence {confidence:.0%} meets threshold {threshold:.0%}. Auto-action permitted.",
        )
    else:
        return ConfidenceGateResult(
            passed=False,
            confidence=confidence,
            threshold=threshold,
            reason=(
                f"Confidence {confidence:.0%} is below threshold {threshold:.0%}. "
                "Escalating to human for manual review."
            ),
        )


def require_confidence(confidence: float) -> None:
    """Raise ValueError if confidence is below the auto-action threshold.

    Use this as a hard guard in code that must not proceed with low confidence.
    """
    result = check_confidence(confidence)
    if not result.passed:
        raise ValueError(result.reason)
