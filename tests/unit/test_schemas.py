"""Unit tests for API schemas (no DB required)."""
from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from models.schemas import (
    IncidentCreate,
    ApprovalRequest,
)
from models.orm import SeverityLevel, RiskLevel


def test_incident_create_valid():
    payload = IncidentCreate(
        service="payment-service",
        severity=SeverityLevel.HIGH,
        description="Error rate at 32%",
        error_rate=0.32,
    )
    assert payload.service == "payment-service"
    assert payload.severity == SeverityLevel.HIGH
    assert payload.error_rate == 0.32


def test_incident_create_missing_service():
    with pytest.raises(Exception):
        IncidentCreate(
            severity=SeverityLevel.HIGH,
            description="No service provided",
        )


def test_incident_create_error_rate_bounds():
    """error_rate must be between 0.0 and 1.0"""
    with pytest.raises(Exception):
        IncidentCreate(
            service="payment-service",
            severity=SeverityLevel.LOW,
            description="Test",
            error_rate=1.5,  # invalid
        )


def test_approval_request_optional_comment():
    req = ApprovalRequest()
    assert req.comment is None

    req_with = ApprovalRequest(comment="Looks good")
    assert req_with.comment == "Looks good"


def test_severity_enum_values():
    assert SeverityLevel.HIGH == "HIGH"
    assert SeverityLevel.CRITICAL == "CRITICAL"


def test_risk_level_enum_values():
    assert RiskLevel.LOW == "LOW"
    assert RiskLevel.HIGH == "HIGH"
