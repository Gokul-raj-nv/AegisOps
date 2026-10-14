"""Incident API router.

Endpoints:
    POST   /incidents                       Ingest a new incident
    GET    /incidents                       List incidents (paginated)
    GET    /incidents/{id}                  Get incident + full investigation result
    POST   /incidents/{id}/investigate      Trigger the agent workflow
    GET    /incidents/{id}/diagnosis        Get diagnosis result
    POST   /incidents/{id}/approve          Human approves remediation
    POST   /incidents/{id}/reject           Human rejects remediation
    GET    /incidents/{id}/audit            Get full audit trail
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Header, status
from sqlalchemy.orm import Session

from models.database import get_db
from models.orm import (
    Approval,
    ApprovalStatus,
    AuditEvent,
    Incident,
    IncidentStatus,
)
from models.schemas import (
    ApprovalRequest,
    ApprovalResponse,
    AuditEventResponse,
    DiagnosisResponse,
    IncidentCreate,
    IncidentResponse,
    IncidentSummary,
    InvestigationResult,
    AgentExecutionResponse,
    RemediationPlanResponse,
)

router = APIRouter(prefix="/incidents", tags=["incidents"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_incident_or_404(incident_id: uuid.UUID, db: Session) -> Incident:
    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not inc:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    return inc


def _add_audit(
    db: Session,
    incident_id: uuid.UUID,
    event_type: str,
    actor: str,
    summary: str,
    details: dict | None = None,
) -> None:
    event = AuditEvent(
        incident_id=incident_id,
        event_type=event_type,
        actor=actor,
        summary=summary,
        details=details,
    )
    db.add(event)


# ---------------------------------------------------------------------------
# POST /incidents  — ingest a new incident
# ---------------------------------------------------------------------------


@router.post("", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
def create_incident(
    payload: IncidentCreate,
    db: Session = Depends(get_db),
    x_user_id: str = Header(default="anonymous"),
) -> IncidentResponse:
    """Ingest a new production incident into AegisOps."""
    inc = Incident(
        service=payload.service,
        severity=payload.severity,
        description=payload.description,
        error_rate=payload.error_rate,
        alert_source=payload.alert_source,
        raw_logs=payload.raw_logs,
        raw_metrics=payload.raw_metrics,
        status=IncidentStatus.OPEN,
    )
    db.add(inc)
    db.flush()  # get ID before audit event

    _add_audit(
        db, inc.id, "INCIDENT_CREATED", x_user_id,
        f"Incident created for {inc.service} (severity={inc.severity})",
        {"service": inc.service, "severity": inc.severity.value},
    )
    db.commit()
    db.refresh(inc)
    return IncidentResponse.model_validate(inc)


# ---------------------------------------------------------------------------
# GET /incidents  — list incidents
# ---------------------------------------------------------------------------


@router.get("", response_model=list[IncidentSummary])
def list_incidents(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> list[IncidentSummary]:
    """Return a paginated list of incidents, newest first."""
    incidents = (
        db.query(Incident)
        .order_by(Incident.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [IncidentSummary.model_validate(i) for i in incidents]


# ---------------------------------------------------------------------------
# GET /incidents/{id}  — full investigation result
# ---------------------------------------------------------------------------


@router.get("/{incident_id}", response_model=InvestigationResult)
def get_incident(
    incident_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> InvestigationResult:
    """Return the full investigation result for an incident."""
    inc = _get_incident_or_404(incident_id, db)

    diagnosis = None
    if inc.diagnosis:
        diagnosis = DiagnosisResponse.model_validate(inc.diagnosis)

    remediation_plan = None
    if inc.remediation_plan:
        remediation_plan = RemediationPlanResponse.model_validate(inc.remediation_plan)

    approval = None
    if inc.approval:
        approval = ApprovalResponse.model_validate(inc.approval)

    return InvestigationResult(
        incident=IncidentResponse.model_validate(inc),
        agent_executions=[AgentExecutionResponse.model_validate(e) for e in inc.agent_executions],
        diagnosis=diagnosis,
        remediation_plan=remediation_plan,
        approval=approval,
        audit_events=[AuditEventResponse.model_validate(e) for e in inc.audit_events],
    )


# ---------------------------------------------------------------------------
# POST /incidents/{id}/investigate  — trigger agent workflow
# ---------------------------------------------------------------------------


@router.post("/{incident_id}/investigate", response_model=IncidentResponse)
def trigger_investigation(
    incident_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    x_user_id: str = Header(default="anonymous"),
) -> IncidentResponse:
    """Trigger the multi-agent investigation workflow for an incident.

    The workflow runs asynchronously. Poll GET /incidents/{id} for status.
    """
    inc = _get_incident_or_404(incident_id, db)

    if inc.status not in (IncidentStatus.OPEN, IncidentStatus.FAILED):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot investigate incident in status {inc.status}. Must be OPEN or FAILED.",
        )

    inc.status = IncidentStatus.INVESTIGATING
    _add_audit(
        db, inc.id, "INVESTIGATION_TRIGGERED", x_user_id,
        "Multi-agent investigation triggered",
    )
    db.commit()
    db.refresh(inc)

    # Import here to avoid circular imports at module load time
    background_tasks.add_task(_run_investigation_background, incident_id=inc.id)

    return IncidentResponse.model_validate(inc)


async def _run_investigation_background(incident_id: uuid.UUID) -> None:
    """Background task: runs the LangGraph multi-agent workflow and persists results."""
    from models.database import SessionLocal
    from models.orm import (
        AgentExecution, Diagnosis, RemediationPlan,
        Approval, ApprovalStatus, AuditEvent, IncidentStatus,
    )
    from graph.workflow import run_workflow

    db = SessionLocal()
    try:
        inc = db.query(Incident).filter(Incident.id == incident_id).first()
        if not inc:
            return

        # ── Run the workflow ──────────────────────────────────────────────
        final_state = await run_workflow(
            incident_id=str(incident_id),
            service=inc.service,
            severity=inc.severity.value,
            description=inc.description,
            raw_logs=inc.raw_logs,
            raw_metrics=inc.raw_metrics,
        )

        # ── Persist diagnosis ─────────────────────────────────────────────
        diag_data = final_state.get("diagnosis")
        if diag_data and not inc.diagnosis:
            db_diag = Diagnosis(
                incident_id=incident_id,
                root_cause=diag_data["root_cause"],
                confidence=diag_data["confidence"],
                reasoning=diag_data.get("reasoning"),
                evidence=diag_data.get("evidence_citations", []),
                citations=[{"source": c} for c in diag_data.get("evidence_citations", [])],
                suspected_component=diag_data.get("suspected_component"),
            )
            db.add(db_diag)

        # ── Persist remediation plan ──────────────────────────────────────
        rem_data = final_state.get("remediation")
        if rem_data and not inc.remediation_plan:
            from models.orm import RiskLevel as OrmRiskLevel
            risk = OrmRiskLevel(rem_data.get("risk_level", "MEDIUM"))
            db_rem = RemediationPlan(
                incident_id=incident_id,
                steps=rem_data.get("steps", []),
                risk_level=risk,
                expected_impact=rem_data.get("expected_impact"),
                rollback_plan=rem_data.get("rollback_plan"),
                rationale=rem_data.get("rationale"),
                requires_approval=1 if rem_data.get("requires_approval", True) else 0,
            )
            db.add(db_rem)

        # ── Persist audit trail ───────────────────────────────────────────
        for event in final_state.get("audit_log", []):
            db_event = AuditEvent(
                incident_id=incident_id,
                event_type=event.get("event_type", "UNKNOWN"),
                actor=event.get("actor", "workflow"),
                summary=event.get("summary", ""),
                details=event.get("details"),
            )
            db.add(db_event)

        # ── Update incident status ────────────────────────────────────────
        requires_approval = final_state.get("requires_human_approval", True)
        errors = final_state.get("agent_errors", [])

        if errors and not diag_data:
            inc.status = IncidentStatus.FAILED
        elif requires_approval:
            inc.status = IncidentStatus.AWAITING_APPROVAL
        else:
            inc.status = IncidentStatus.DIAGNOSIS_READY

        db.commit()

    except Exception as e:
        try:
            inc = db.query(Incident).filter(Incident.id == incident_id).first()
            if inc:
                inc.status = IncidentStatus.FAILED
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


# ---------------------------------------------------------------------------
# GET /incidents/{id}/diagnosis
# ---------------------------------------------------------------------------


@router.get("/{incident_id}/diagnosis", response_model=DiagnosisResponse)
def get_diagnosis(
    incident_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> DiagnosisResponse:
    """Return the diagnosis for an incident."""
    inc = _get_incident_or_404(incident_id, db)
    if not inc.diagnosis:
        raise HTTPException(status_code=404, detail="No diagnosis available yet")
    return DiagnosisResponse.model_validate(inc.diagnosis)


# ---------------------------------------------------------------------------
# POST /incidents/{id}/approve
# ---------------------------------------------------------------------------


@router.post("/{incident_id}/approve", response_model=ApprovalResponse)
def approve_remediation(
    incident_id: uuid.UUID,
    payload: ApprovalRequest,
    db: Session = Depends(get_db),
    x_user_id: str = Header(default="anonymous"),
) -> ApprovalResponse:
    """Human approves the proposed remediation plan."""
    inc = _get_incident_or_404(incident_id, db)

    if inc.status != IncidentStatus.AWAITING_APPROVAL:
        raise HTTPException(
            status_code=409,
            detail=f"Incident is not awaiting approval (status={inc.status})",
        )

    # Create or update approval record
    if inc.approval:
        appr = inc.approval
    else:
        appr = Approval(incident_id=incident_id)
        db.add(appr)

    appr.status = ApprovalStatus.APPROVED
    appr.approved_by = x_user_id
    appr.comment = payload.comment
    appr.decided_at = datetime.now(tz=timezone.utc)

    inc.status = IncidentStatus.APPROVED

    _add_audit(
        db, inc.id, "REMEDIATION_APPROVED", x_user_id,
        f"Remediation plan approved by {x_user_id}",
        {"comment": payload.comment},
    )
    db.commit()
    db.refresh(appr)
    return ApprovalResponse.model_validate(appr)


# ---------------------------------------------------------------------------
# POST /incidents/{id}/reject
# ---------------------------------------------------------------------------


@router.post("/{incident_id}/reject", response_model=ApprovalResponse)
def reject_remediation(
    incident_id: uuid.UUID,
    payload: ApprovalRequest,
    db: Session = Depends(get_db),
    x_user_id: str = Header(default="anonymous"),
) -> ApprovalResponse:
    """Human rejects the proposed remediation plan."""
    inc = _get_incident_or_404(incident_id, db)

    if inc.status != IncidentStatus.AWAITING_APPROVAL:
        raise HTTPException(
            status_code=409,
            detail=f"Incident is not awaiting approval (status={inc.status})",
        )

    if inc.approval:
        appr = inc.approval
    else:
        appr = Approval(incident_id=incident_id)
        db.add(appr)

    appr.status = ApprovalStatus.REJECTED
    appr.approved_by = x_user_id
    appr.comment = payload.comment
    appr.decided_at = datetime.now(tz=timezone.utc)

    inc.status = IncidentStatus.REJECTED

    _add_audit(
        db, inc.id, "REMEDIATION_REJECTED", x_user_id,
        f"Remediation plan rejected by {x_user_id}",
        {"comment": payload.comment},
    )
    db.commit()
    db.refresh(appr)
    return ApprovalResponse.model_validate(appr)


# ---------------------------------------------------------------------------
# GET /incidents/{id}/audit
# ---------------------------------------------------------------------------


@router.get("/{incident_id}/audit", response_model=list[AuditEventResponse])
def get_audit_trail(
    incident_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> list[AuditEventResponse]:
    """Return the full audit trail for an incident."""
    inc = _get_incident_or_404(incident_id, db)
    return [AuditEventResponse.model_validate(e) for e in inc.audit_events]
