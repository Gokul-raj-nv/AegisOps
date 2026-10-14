"""Validation Agent — safety-checks the remediation plan before execution.

Responsibilities:
  1. Verify the remediation plan is coherent and complete.
  2. Check for dangerous patterns (e.g., destructive commands without rollback).
  3. Assess blast radius of the remediation action.
  4. Produce a final recommendation: APPROVE | ESCALATE | REJECT.
  5. Set requires_human_approval based on risk level and confidence.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from config import get_settings
from graph.state import AgentState, ValidationResult


_VALIDATION_SYSTEM_PROMPT = """You are a principal SRE and safety reviewer. 
Your job is to validate a proposed remediation plan before it is executed 
or routed to a human approver.

Check for:
1. Does the plan directly address the diagnosed root cause?
2. Are the steps safe, specific, and reversible?
3. Does the rollback plan work if remediation makes things worse?
4. Is the risk classification appropriate?
5. Are there any missing steps or dangerous assumptions?

Return JSON:
{
  "safe_to_proceed": true|false,
  "risk_assessment": "<1-2 sentences on blast radius and safety>",
  "concerns": ["<concern 1>", "<concern 2>"],
  "recommendation": "APPROVE|ESCALATE|REJECT",
  "validation_notes": "<any additional notes for the approver>"
}

Recommendation guide:
- APPROVE: Plan is safe, specific, addresses root cause, has rollback
- ESCALATE: Plan needs human review before execution (normal for MEDIUM/HIGH risk)
- REJECT: Plan is dangerous, incomplete, or targets wrong component"""


def run_validation(state: AgentState) -> dict:
    """Validation agent node — safety-checks the remediation plan."""
    settings = get_settings()
    now = datetime.now(tz=timezone.utc).isoformat()
    errors = list(state.get("agent_errors", []))
    audit_log = list(state.get("audit_log", []))

    diagnosis = state.get("diagnosis")
    remediation = state.get("remediation")

    if not remediation:
        # No remediation plan to validate — mark as needing escalation
        validation = ValidationResult(
            safe_to_proceed=False,
            risk_assessment="No remediation plan was generated.",
            concerns=["Remediation agent did not produce a plan."],
            recommendation="ESCALATE",
        )
        requires_human_approval = True
        next_action = "awaiting_approval"

        audit_log.append({
            "timestamp": now,
            "event_type": "VALIDATION_COMPLETE",
            "actor": "validation-agent",
            "summary": "No remediation plan to validate. Escalating to human.",
            "details": validation,
        })

        return {
            "validation": validation,
            "requires_human_approval": requires_human_approval,
            "next_action": next_action,
            "current_node": "complete",
            "audit_log": audit_log,
            "agent_errors": errors,
        }

    # ── Invoke Gemini for validation ──────────────────────────────────────
    llm = ChatGoogleGenerativeAI(
        model=settings.llm_model,
        google_api_key=settings.google_api_key,
        temperature=0.1,
    )

    steps_text = "\n".join(remediation.get("steps", []))
    user_content = f"""=== INCIDENT ===
Service: {state['service']}
Severity: {state['severity']}

=== DIAGNOSIS ===
Root cause: {diagnosis.get('root_cause', 'Unknown') if diagnosis else 'None'}
Root cause type: {diagnosis.get('root_cause_type', 'unknown') if diagnosis else 'None'}
Confidence: {diagnosis.get('confidence', 0):.0%}

=== PROPOSED REMEDIATION ===
Risk level: {remediation.get('risk_level')}
Steps:
{steps_text}

Rollback plan: {remediation.get('rollback_plan', 'None specified')}
Expected impact: {remediation.get('expected_impact', 'Not specified')}

Validate this remediation plan and return JSON."""

    validation: ValidationResult | None = None

    try:
        response = llm.invoke([
            SystemMessage(content=_VALIDATION_SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ])
        raw_text = response.content.strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]

        data = json.loads(raw_text)
        validation = ValidationResult(
            safe_to_proceed=data.get("safe_to_proceed", False),
            risk_assessment=data.get("risk_assessment", ""),
            concerns=data.get("concerns", []),
            recommendation=data.get("recommendation", "ESCALATE"),
        )

    except Exception as e:
        errors.append(f"Validation LLM failed: {e}")
        # Default to escalation on validation failure
        validation = ValidationResult(
            safe_to_proceed=False,
            risk_assessment="Validation could not be completed automatically.",
            concerns=[f"Validation LLM error: {e}"],
            recommendation="ESCALATE",
        )

    # ── Determine final routing ───────────────────────────────────────────
    recommendation = validation.get("recommendation", "ESCALATE")
    risk_level = remediation.get("risk_level", "MEDIUM")
    requires_approval = remediation.get("requires_approval", True)

    # Force human approval for HIGH risk or if remediation itself requests it
    requires_human_approval = (
        risk_level == "HIGH"
        or requires_approval
        or recommendation == "ESCALATE"
    )

    # Determine final next_action:
    # - REJECT: mark failed
    # - APPROVE + LOW risk + auto-approval enabled: complete directly
    # - Otherwise: awaiting_approval
    if recommendation == "REJECT":
        next_action = "failed"
    elif recommendation == "APPROVE" and not requires_human_approval:
        next_action = "complete"
    else:
        next_action = "awaiting_approval"

    audit_log.append({
        "timestamp": now,
        "event_type": "VALIDATION_COMPLETE",
        "actor": "validation-agent",
        "summary": (
            f"Validation {recommendation}. "
            f"Safe to proceed: {validation['safe_to_proceed']}. "
            f"Requires human approval: {requires_human_approval}."
        ),
        "details": {
            "validation": validation,
            "requires_human_approval": requires_human_approval,
            "next_action": next_action,
        },
    })

    return {
        "validation": validation,
        "requires_human_approval": requires_human_approval,
        "next_action": next_action,
        "current_node": "complete",
        "audit_log": audit_log,
        "agent_errors": errors,
    }
