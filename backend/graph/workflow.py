"""LangGraph workflow — the multi-agent investigation pipeline.

Graph topology:
  triage → rag_search → log_analysis → diagnosis
              ↓ (confidence >= threshold)         ↓ (confidence < threshold)
          remediation → validation            escalation_node
              ↓                                    ↓
    [APPROVE] → complete           [ESCALATE] → awaiting_approval_node
    [REJECT]  → failed_node
    [ESCALATE]→ awaiting_approval_node

After the graph completes, the caller persists results to PostgreSQL.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from langgraph.graph import StateGraph, START, END

from graph.state import AgentState, make_initial_state
from agents.triage import run_triage
from agents.rag import run_rag_search
from agents.log_analysis import run_log_analysis
from agents.diagnosis import run_diagnosis
from agents.remediation import run_remediation
from agents.validation import run_validation


# ---------------------------------------------------------------------------
# Terminal nodes
# ---------------------------------------------------------------------------


def escalation_node(state: AgentState) -> dict:
    """Reached when diagnosis confidence is below threshold."""
    now = datetime.now(tz=timezone.utc).isoformat()
    audit_log = list(state.get("audit_log", []))
    diagnosis = state.get("diagnosis")
    confidence = diagnosis.get("confidence", 0.0) if diagnosis else 0.0

    audit_log.append({
        "timestamp": now,
        "event_type": "ESCALATED_TO_HUMAN",
        "actor": "workflow",
        "summary": (
            f"Confidence {confidence:.0%} below threshold. "
            "Escalating to on-call engineer for manual investigation."
        ),
        "details": {"confidence": confidence, "diagnosis": diagnosis},
    })
    return {
        "requires_human_approval": True,
        "next_action": "awaiting_approval",
        "current_node": "complete",
        "audit_log": audit_log,
    }


def awaiting_approval_node(state: AgentState) -> dict:
    """Marks the workflow as awaiting human approval before execution."""
    now = datetime.now(tz=timezone.utc).isoformat()
    audit_log = list(state.get("audit_log", []))
    audit_log.append({
        "timestamp": now,
        "event_type": "AWAITING_HUMAN_APPROVAL",
        "actor": "workflow",
        "summary": "Investigation complete. Remediation plan is awaiting human approval.",
        "details": {
            "risk_level": state.get("remediation", {}).get("risk_level") if state.get("remediation") else None,
        },
    })
    return {
        "current_node": "complete",
        "audit_log": audit_log,
    }


def complete_node(state: AgentState) -> dict:
    """Final node — marks the workflow as complete."""
    now = datetime.now(tz=timezone.utc).isoformat()
    audit_log = list(state.get("audit_log", []))
    audit_log.append({
        "timestamp": now,
        "event_type": "INVESTIGATION_COMPLETE",
        "actor": "workflow",
        "summary": "Full investigation complete. Results ready for review.",
        "details": {
            "total_agents": 6,
            "error_count": len(state.get("agent_errors", [])),
        },
    })
    return {"current_node": "done", "audit_log": audit_log}


def failed_node(state: AgentState) -> dict:
    """Reached when validation rejects the remediation plan."""
    now = datetime.now(tz=timezone.utc).isoformat()
    audit_log = list(state.get("audit_log", []))
    audit_log.append({
        "timestamp": now,
        "event_type": "REMEDIATION_REJECTED_BY_VALIDATION",
        "actor": "workflow",
        "summary": "Validation agent rejected the remediation plan. Manual review required.",
        "details": {"validation": state.get("validation")},
    })
    return {
        "requires_human_approval": True,
        "current_node": "complete",
        "audit_log": audit_log,
    }


# ---------------------------------------------------------------------------
# Conditional edge routers
# ---------------------------------------------------------------------------


def route_after_diagnosis(state: AgentState) -> Literal["remediation", "escalation"]:
    """Route to remediation if confident enough, otherwise escalate."""
    return "remediation" if state.get("next_action") == "remediate" else "escalation"


def route_after_validation(
    state: AgentState,
) -> Literal["awaiting_approval", "complete", "failed"]:
    """Route based on the validation agent's recommendation."""
    next_action = state.get("next_action", "awaiting_approval")
    if next_action == "failed":
        return "failed"
    if next_action == "complete":
        return "complete"
    return "awaiting_approval"


# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------


def build_graph() -> StateGraph:
    """Construct and compile the AegisOps investigation workflow."""
    graph = StateGraph(AgentState)

    # ── Register nodes ────────────────────────────────────────────────────
    graph.add_node("triage", run_triage)
    graph.add_node("rag_search", run_rag_search)
    graph.add_node("log_analysis", run_log_analysis)
    graph.add_node("diagnosis", run_diagnosis)
    graph.add_node("remediation", run_remediation)
    graph.add_node("validation", run_validation)
    graph.add_node("escalation", escalation_node)
    graph.add_node("awaiting_approval", awaiting_approval_node)
    graph.add_node("complete", complete_node)
    graph.add_node("failed", failed_node)

    # ── Linear edges ──────────────────────────────────────────────────────
    graph.add_edge(START, "triage")
    graph.add_edge("triage", "rag_search")
    graph.add_edge("rag_search", "log_analysis")
    graph.add_edge("log_analysis", "diagnosis")

    # ── Conditional: diagnosis → remediation or escalation ────────────────
    graph.add_conditional_edges(
        "diagnosis",
        route_after_diagnosis,
        {"remediation": "remediation", "escalation": "escalation"},
    )

    graph.add_edge("remediation", "validation")

    # ── Conditional: validation → approval | complete | failed ─────────────
    graph.add_conditional_edges(
        "validation",
        route_after_validation,
        {
            "awaiting_approval": "awaiting_approval",
            "complete": "complete",
            "failed": "failed",
        },
    )

    # ── Terminal edges ────────────────────────────────────────────────────
    graph.add_edge("escalation", "awaiting_approval")
    graph.add_edge("awaiting_approval", END)
    graph.add_edge("complete", END)
    graph.add_edge("failed", END)

    return graph.compile()


# ── Compiled graph (singleton) ────────────────────────────────────────────
_workflow = None


def get_workflow():
    """Return the compiled workflow (lazily instantiated)."""
    global _workflow
    if _workflow is None:
        _workflow = build_graph()
    return _workflow


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def run_workflow(
    incident_id: str,
    service: str,
    severity: str,
    description: str,
    raw_logs: str | None = None,
    raw_metrics: dict | None = None,
) -> AgentState:
    """Run the full investigation workflow and return the final state.

    This is called by the FastAPI background task in api/incidents.py.

    Args:
        incident_id: UUID string of the incident record.
        service: Affected service name.
        severity: Incident severity level.
        description: Incident description from the alert.
        raw_logs: Optional raw log text attached to the incident.
        raw_metrics: Optional raw metrics dict attached to the incident.

    Returns:
        Final AgentState with all agent outputs populated.
    """
    initial_state = make_initial_state(
        incident_id=incident_id,
        service=service,
        severity=severity,
        description=description,
        raw_logs=raw_logs,
        raw_metrics=raw_metrics,
    )

    workflow = get_workflow()
    final_state = await workflow.ainvoke(initial_state)
    return final_state


def run_workflow_sync(
    incident_id: str,
    service: str,
    severity: str,
    description: str,
    raw_logs: str | None = None,
    raw_metrics: dict | None = None,
) -> AgentState:
    """Synchronous version of run_workflow — for testing and CLI use."""
    initial_state = make_initial_state(
        incident_id=incident_id,
        service=service,
        severity=severity,
        description=description,
        raw_logs=raw_logs,
        raw_metrics=raw_metrics,
    )
    workflow = get_workflow()
    return workflow.invoke(initial_state)
