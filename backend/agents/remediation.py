"""Remediation Agent — selects and structures the optimal remediation plan.

Responsibilities:
  1. Use the diagnosed root_cause_type to select candidate actions from the library.
  2. Use Gemini to rank and tailor the actions to the specific incident.
  3. Produce a structured RemediationResult with ordered steps, risk level, 
     expected impact, and rollback plan.
  4. Set requires_approval based on risk level.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from config import get_settings
from graph.state import AgentState, RemediationResult
from tools.remediation_actions import get_remediation_actions, RiskLevel


_REMEDIATION_SYSTEM_PROMPT = """You are a senior SRE creating a precise, safe remediation 
plan for a diagnosed production incident.

Given the diagnosis, affected service, and candidate remediation actions, 
produce a structured remediation plan.

Return JSON:
{
  "steps": [
    "<step 1 — specific and actionable>",
    "<step 2>",
    ...
  ],
  "risk_level": "LOW|MEDIUM|HIGH",
  "expected_impact": "<what will happen after remediation, timeframe>",
  "rollback_plan": "<how to revert if remediation makes things worse>",
  "rationale": "<why this specific remediation was chosen>",
  "requires_approval": true|false,
  "action_id": "<primary action id from the candidates>",
  "warnings": ["<warning 1>", ...]
}

Risk classification:
- LOW: Read-only or config-only changes, no service interruption
- MEDIUM: Rolling restarts, pool size changes — brief interruption possible
- HIGH: Killing queries, manual DB changes, emergency procedures

Set requires_approval=true for MEDIUM and HIGH risk actions."""


def run_remediation(state: AgentState) -> dict:
    """Remediation agent node — builds a risk-classified remediation plan."""
    settings = get_settings()
    now = datetime.now(tz=timezone.utc).isoformat()
    errors = list(state.get("agent_errors", []))
    audit_log = list(state.get("audit_log", []))

    diagnosis = state.get("diagnosis")
    service = state["service"]
    metrics = state.get("metrics")

    if not diagnosis:
        errors.append("Remediation: No diagnosis available to base remediation on.")
        return {
            "remediation": None,
            "current_node": "validation",
            "audit_log": audit_log,
            "agent_errors": errors,
        }

    root_cause_type = diagnosis.get("root_cause_type", "unknown")

    # ── Get candidate actions from library ────────────────────────────────
    pool_size = metrics.get("db_pool_size", 20) if metrics else 20
    candidates = get_remediation_actions(
        root_cause_type=root_cause_type,
        service=service,
        current_size=pool_size,
        target_size=max(50, pool_size * 2),
    )

    # ── Use Gemini to tailor the plan ─────────────────────────────────────
    llm = ChatGoogleGenerativeAI(
        model=settings.llm_model,
        google_api_key=settings.google_api_key,
        temperature=0.1,
    )

    candidates_text = "\n\n".join([
        f"ACTION: {a.action_id}\nRisk: {a.risk_level.value}\n"
        f"Steps:\n" + "\n".join(f"  {s}" for s in a.steps) +
        f"\nExpected impact: {a.expected_impact}"
        for a in candidates[:3]
    ]) or "No pre-defined actions found. Recommend manual investigation."

    user_content = f"""=== INCIDENT ===
Service: {service}
Severity: {state['severity']}

=== DIAGNOSIS ===
Root cause: {diagnosis['root_cause']}
Root cause type: {root_cause_type}
Confidence: {diagnosis['confidence']:.0%}
Suspected component: {diagnosis['suspected_component']}

=== LIVE METRICS ===
{json.dumps(metrics, indent=2) if metrics else 'Unavailable'}

=== CANDIDATE REMEDIATION ACTIONS ===
{candidates_text}

Create the optimal, ordered remediation plan as JSON."""

    remediation: RemediationResult | None = None

    try:
        response = llm.invoke([
            SystemMessage(content=_REMEDIATION_SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ])
        raw_text = response.content.strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]

        data = json.loads(raw_text)

        risk_str = data.get("risk_level", "MEDIUM").upper()
        requires_approval = data.get("requires_approval", risk_str != "LOW")

        remediation = RemediationResult(
            steps=data.get("steps", []),
            risk_level=risk_str,
            expected_impact=data.get("expected_impact", ""),
            rollback_plan=data.get("rollback_plan", ""),
            rationale=data.get("rationale", ""),
            requires_approval=requires_approval,
            action_id=data.get("action_id", root_cause_type),
        )

    except Exception as e:
        errors.append(f"Remediation LLM failed: {e}")
        # Fallback: use first candidate action directly
        if candidates:
            a = candidates[0]
            remediation = RemediationResult(
                steps=a.steps,
                risk_level=a.risk_level.value,
                expected_impact=a.expected_impact,
                rollback_plan="\n".join(a.rollback_steps),
                rationale=a.description,
                requires_approval=a.requires_approval,
                action_id=a.action_id,
            )

    audit_log.append({
        "timestamp": now,
        "event_type": "REMEDIATION_PLAN_CREATED",
        "actor": "remediation-agent",
        "summary": (
            f"Remediation plan created. "
            f"Risk: {remediation['risk_level'] if remediation else 'N/A'}. "
            f"Requires approval: {remediation['requires_approval'] if remediation else 'N/A'}."
        ),
        "details": remediation,
    })

    return {
        "remediation": remediation,
        "current_node": "validation",
        "audit_log": audit_log,
        "agent_errors": errors,
    }
