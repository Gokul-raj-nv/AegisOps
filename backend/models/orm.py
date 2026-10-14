"""SQLAlchemy ORM models for AegisOps."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SeverityLevel(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class IncidentStatus(str, enum.Enum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    DIAGNOSIS_READY = "DIAGNOSIS_READY"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    RESOLVED = "RESOLVED"
    FAILED = "FAILED"


class RiskLevel(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ApprovalStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    NOT_REQUIRED = "NOT_REQUIRED"


# ---------------------------------------------------------------------------
# Incident
# ---------------------------------------------------------------------------


class Incident(Base):
    """A production incident ingested into AegisOps."""

    __tablename__ = "incidents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service = Column(String(128), nullable=False, index=True)
    severity = Column(Enum(SeverityLevel), nullable=False)
    description = Column(Text, nullable=False)
    error_rate = Column(Float, nullable=True)
    alert_source = Column(String(128), nullable=True)
    raw_logs = Column(Text, nullable=True)
    raw_metrics = Column(JSON, nullable=True)
    status = Column(Enum(IncidentStatus), nullable=False, default=IncidentStatus.OPEN)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    agent_executions = relationship("AgentExecution", back_populates="incident", cascade="all, delete-orphan")
    diagnosis = relationship("Diagnosis", back_populates="incident", uselist=False, cascade="all, delete-orphan")
    remediation_plan = relationship("RemediationPlan", back_populates="incident", uselist=False, cascade="all, delete-orphan")
    approval = relationship("Approval", back_populates="incident", uselist=False, cascade="all, delete-orphan")
    audit_events = relationship("AuditEvent", back_populates="incident", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# Agent Execution
# ---------------------------------------------------------------------------


class AgentExecution(Base):
    """Record of a single agent run within an investigation."""

    __tablename__ = "agent_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id = Column(UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=False, index=True)
    agent_name = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="RUNNING")  # RUNNING | DONE | FAILED
    input_data = Column(JSON, nullable=True)
    output_data = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    llm_calls = Column(Integer, default=0)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    incident = relationship("Incident", back_populates="agent_executions")


# ---------------------------------------------------------------------------
# Diagnosis
# ---------------------------------------------------------------------------


class Diagnosis(Base):
    """Root-cause diagnosis produced by the Diagnosis Agent."""

    __tablename__ = "diagnoses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id = Column(UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=False, unique=True)
    root_cause = Column(Text, nullable=False)
    confidence = Column(Float, nullable=False)
    reasoning = Column(Text, nullable=True)
    evidence = Column(JSON, nullable=True)   # list of evidence strings
    citations = Column(JSON, nullable=True)  # list of {source, score} dicts
    suspected_component = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    incident = relationship("Incident", back_populates="diagnosis")


# ---------------------------------------------------------------------------
# Remediation Plan
# ---------------------------------------------------------------------------


class RemediationPlan(Base):
    """Proposed remediation produced by the Remediation Agent."""

    __tablename__ = "remediation_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id = Column(UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=False, unique=True)
    steps = Column(JSON, nullable=False)       # list of step strings
    risk_level = Column(Enum(RiskLevel), nullable=False)
    expected_impact = Column(Text, nullable=True)
    rollback_plan = Column(Text, nullable=True)
    rationale = Column(Text, nullable=True)
    requires_approval = Column(Integer, default=1)  # 1 = yes, 0 = no
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    incident = relationship("Incident", back_populates="remediation_plan")


# ---------------------------------------------------------------------------
# Approval
# ---------------------------------------------------------------------------


class Approval(Base):
    """Human approval or rejection of a remediation plan."""

    __tablename__ = "approvals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id = Column(UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=False, unique=True)
    status = Column(Enum(ApprovalStatus), nullable=False, default=ApprovalStatus.PENDING)
    approved_by = Column(String(128), nullable=True)   # user ID / header value
    comment = Column(Text, nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    incident = relationship("Incident", back_populates="approval")


# ---------------------------------------------------------------------------
# Audit Event
# ---------------------------------------------------------------------------


class AuditEvent(Base):
    """Immutable audit record of every significant AI decision."""

    __tablename__ = "audit_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id = Column(UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=False, index=True)
    event_type = Column(String(64), nullable=False)   # e.g. TRIAGE_COMPLETE, DIAGNOSIS_READY
    actor = Column(String(64), nullable=False)        # agent name or "human"
    summary = Column(Text, nullable=False)
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    incident = relationship("Incident", back_populates="audit_events")
