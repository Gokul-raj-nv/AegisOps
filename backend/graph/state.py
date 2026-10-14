"""AgentState — the shared state passed between all nodes in the LangGraph workflow.

Every agent reads from and writes to this state dict. LangGraph merges
partial updates returned by each node into the running state.
"""
from __future__ import annotations

import uuid
from typing import Annotated, Any
from typing_extensions import TypedDict

from langgraph.graph.message import add_messages


# ---------------------------------------------------------------------------
# Sub-structures stored inside AgentState
# ---------------------------------------------------------------------------


class EvidenceItem(TypedDict):
    """A single piece of retrieved evidence."""
    content: str
    source: str
    doc_type: str
    relevance_score: float
    citation: str


class LogEvidenceItem(TypedDict):
    """A single log line parsed as evidence."""
    timestamp: str | None
    level: str | None
    service: str | None
    message: str | None
    error: str | None
    source_file: str


class MetricsSnapshot(TypedDict):
    """Key metrics at investigation time."""
    service: str
    error_rate: float
    p99_latency_ms: float
    db_pool_utilization: float | None
    db_pool_size: int | None
    db_active_connections: int | None
    cpu_percent: float
    healthy: bool


class DiagnosisResult(TypedDict):
    """Structured diagnosis output from the Diagnosis Agent."""
    root_cause: str
    root_cause_type: str       # e.g. 'db_pool_exhaustion', 'high_cpu'
    suspected_component: str
    confidence: float          # 0.0–1.0
    reasoning: str
    evidence_summary: str
    evidence_citations: list[str]


class RemediationResult(TypedDict):
    """Structured remediation plan from the Remediation Agent."""
    steps: list[str]
    risk_level: str            # LOW | MEDIUM | HIGH
    expected_impact: str
    rollback_plan: str
    rationale: str
    requires_approval: bool
    action_id: str


class ValidationResult(TypedDict):
    """Safety validation result from the Validation Agent."""
    safe_to_proceed: bool
    risk_assessment: str
    concerns: list[str]
    recommendation: str        # APPROVE | ESCALATE | REJECT


# ---------------------------------------------------------------------------
# The main AgentState
# ---------------------------------------------------------------------------


class AgentState(TypedDict):
    # ── Incident context ─────────────────────────────────────────────────
    incident_id: str                        # UUID as string
    service: str                            # affected service name
    severity: str                           # LOW | MEDIUM | HIGH | CRITICAL
    description: str                        # raw incident description
    raw_logs: str | None                    # logs attached to incident report
    raw_metrics: dict[str, Any] | None      # metrics attached to incident report

    # ── Evidence gathered ────────────────────────────────────────────────
    knowledge_evidence: list[EvidenceItem]  # RAG search results
    log_evidence: list[LogEvidenceItem]     # parsed log lines
    metrics: MetricsSnapshot | None         # live metric snapshot

    # ── Agent outputs ────────────────────────────────────────────────────
    triage_summary: str                     # triage agent narrative
    diagnosis: DiagnosisResult | None
    remediation: RemediationResult | None
    validation: ValidationResult | None

    # ── Workflow control ─────────────────────────────────────────────────
    current_node: str                       # which node is executing
    next_action: str                        # routing signal for conditional edges
    requires_human_approval: bool

    # ── Audit trail ─────────────────────────────────────────────────────
    audit_log: list[dict[str, Any]]         # sequence of audit events

    # ── Error handling ───────────────────────────────────────────────────
    error: str | None                       # last error message, if any
    agent_errors: list[str]                 # all errors encountered

    # ── LLM messages (optional — for debug tracing) ───────────────────────
    messages: Annotated[list, add_messages]


def make_initial_state(
    incident_id: str,
    service: str,
    severity: str,
    description: str,
    raw_logs: str | None = None,
    raw_metrics: dict[str, Any] | None = None,
) -> AgentState:
    """Create a clean initial AgentState for a new investigation."""
    return AgentState(
        incident_id=incident_id,
        service=service,
        severity=severity,
        description=description,
        raw_logs=raw_logs,
        raw_metrics=raw_metrics,
        knowledge_evidence=[],
        log_evidence=[],
        metrics=None,
        triage_summary="",
        diagnosis=None,
        remediation=None,
        validation=None,
        current_node="triage",
        next_action="",
        requires_human_approval=False,
        audit_log=[],
        error=None,
        agent_errors=[],
        messages=[],
    )
