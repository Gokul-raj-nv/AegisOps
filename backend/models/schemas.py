"""Pydantic request/response schemas for the AegisOps API."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from models.orm import ApprovalStatus, IncidentStatus, RiskLevel, SeverityLevel


# ---------------------------------------------------------------------------
# Incident
# ---------------------------------------------------------------------------


class IncidentCreate(BaseModel):
    """Payload to ingest a new incident."""

    service: str = Field(..., min_length=1, max_length=128, examples=["payment-service"])
    severity: SeverityLevel
    description: str = Field(..., min_length=1, examples=["HTTP 500 error rate at 32%"])
    error_rate: float | None = Field(None, ge=0.0, le=1.0, examples=[0.32])
    alert_source: str | None = Field(None, examples=["PagerDuty"])
    raw_logs: str | None = None
    raw_metrics: dict[str, Any] | None = None


class IncidentResponse(BaseModel):
    """Full incident response including status."""

    id: uuid.UUID
    service: str
    severity: SeverityLevel
    description: str
    error_rate: float | None
    alert_source: str | None
    status: IncidentStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IncidentSummary(BaseModel):
    """Lightweight incident summary for list views."""

    id: uuid.UUID
    service: str
    severity: SeverityLevel
    status: IncidentStatus
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Diagnosis
# ---------------------------------------------------------------------------


class DiagnosisResponse(BaseModel):
    """Diagnosis produced by the Diagnosis Agent."""

    id: uuid.UUID
    incident_id: uuid.UUID
    root_cause: str
    confidence: float
    reasoning: str | None
    evidence: list[str] | None
    citations: list[dict[str, Any]] | None
    suspected_component: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Remediation Plan
# ---------------------------------------------------------------------------


class RemediationPlanResponse(BaseModel):
    """Remediation plan proposed by the Remediation Agent."""

    id: uuid.UUID
    incident_id: uuid.UUID
    steps: list[str]
    risk_level: RiskLevel
    expected_impact: str | None
    rollback_plan: str | None
    rationale: str | None
    requires_approval: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Approval
# ---------------------------------------------------------------------------


class ApprovalRequest(BaseModel):
    """Human approval or rejection payload."""

    comment: str | None = Field(None, max_length=1000)


class ApprovalResponse(BaseModel):
    """Approval record response."""

    id: uuid.UUID
    incident_id: uuid.UUID
    status: ApprovalStatus
    approved_by: str | None
    comment: str | None
    decided_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


class AuditEventResponse(BaseModel):
    """Single audit event."""

    id: uuid.UUID
    incident_id: uuid.UUID
    event_type: str
    actor: str
    summary: str
    details: dict[str, Any] | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Agent Execution
# ---------------------------------------------------------------------------


class AgentExecutionResponse(BaseModel):
    """Agent execution record."""

    id: uuid.UUID
    incident_id: uuid.UUID
    agent_name: str
    status: str
    duration_ms: int | None
    llm_calls: int
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Investigation Result (full incident detail)
# ---------------------------------------------------------------------------


class InvestigationResult(BaseModel):
    """Complete investigation result returned to the frontend."""

    incident: IncidentResponse
    agent_executions: list[AgentExecutionResponse]
    diagnosis: DiagnosisResponse | None
    remediation_plan: RemediationPlanResponse | None
    approval: ApprovalResponse | None
    audit_events: list[AuditEventResponse]
