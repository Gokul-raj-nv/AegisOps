"""Risk classifier — independent risk assessment of remediation actions.

The Remediation Agent assigns a risk level, but this guardrail re-validates
it independently to prevent the agent from under-classifying a dangerous action.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


# Keywords that always escalate risk to at least MEDIUM
_MEDIUM_RISK_KEYWORDS = {
    "restart", "rollout", "scale", "update", "patch", "deploy",
    "config", "env", "environment variable", "pool_size", "replica",
}

# Keywords that always escalate risk to HIGH
_HIGH_RISK_KEYWORDS = {
    "terminate", "kill", "drop", "delete", "truncate", "pg_terminate",
    "force", "emergency", "drain", "disable", "shutdown", "evict",
}

# Actions that are always HIGH risk regardless of description
_HIGH_RISK_ACTION_IDS = {
    "terminate_long_queries",
    "drop_table",
    "emergency_restart",
    "disable_service",
}


@dataclass
class RiskClassification:
    risk_level: str       # LOW | MEDIUM | HIGH
    agent_risk: str       # What the agent reported
    override: bool        # True if we escalated the agent's assessment
    reason: str


def classify_risk(
    action_id: str,
    steps: list[str],
    agent_risk: str,
) -> RiskClassification:
    """Independently classify the risk of a remediation action.

    Escalates the agent's risk level if dangerous keywords are found,
    but never downgrades the agent's reported risk.

    Args:
        action_id: ID of the action from the library.
        steps: Ordered list of remediation steps.
        agent_risk: Risk level the Remediation Agent assigned.

    Returns:
        RiskClassification with final risk level and override flag.
    """
    steps_text = " ".join(steps).lower()

    # Check for HIGH risk patterns first
    if action_id in _HIGH_RISK_ACTION_IDS:
        final_risk = "HIGH"
        reason = f"Action ID '{action_id}' is always classified as HIGH risk."
    elif any(kw in steps_text for kw in _HIGH_RISK_KEYWORDS):
        matched = [kw for kw in _HIGH_RISK_KEYWORDS if kw in steps_text]
        final_risk = "HIGH"
        reason = f"Steps contain high-risk keywords: {matched}."
    elif any(kw in steps_text for kw in _MEDIUM_RISK_KEYWORDS):
        matched = [kw for kw in _MEDIUM_RISK_KEYWORDS if kw in steps_text]
        final_risk = "MEDIUM" if agent_risk == "LOW" else agent_risk
        reason = f"Steps contain medium-risk keywords: {matched}."
    else:
        final_risk = agent_risk
        reason = "No risk escalation keywords detected."

    # Risk levels: LOW < MEDIUM < HIGH — never downgrade
    risk_order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
    agent_order = risk_order.get(agent_risk.upper(), 1)
    final_order = risk_order.get(final_risk.upper(), 1)

    if final_order < agent_order:
        final_risk = agent_risk
        reason = "Guardrail did not downgrade agent's risk assessment."

    override = final_risk != agent_risk

    return RiskClassification(
        risk_level=final_risk,
        agent_risk=agent_risk,
        override=override,
        reason=reason,
    )


def requires_approval(risk_level: str) -> bool:
    """Return True if a risk level mandates human approval before execution."""
    return risk_level.upper() in ("MEDIUM", "HIGH")
