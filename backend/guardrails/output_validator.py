"""Output validator — validates LLM-generated JSON against expected schemas.

Prevents malformed or hallucinated agent outputs from poisoning
the workflow state or being persisted to the database.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    sanitized: dict[str, Any] | None = None


# Required fields and their types for each agent output
_DIAGNOSIS_SCHEMA: dict[str, type] = {
    "root_cause": str,
    "root_cause_type": str,
    "suspected_component": str,
    "confidence": float,
    "reasoning": str,
    "evidence_summary": str,
    "evidence_citations": list,
}

_REMEDIATION_SCHEMA: dict[str, type] = {
    "steps": list,
    "risk_level": str,
    "expected_impact": str,
    "rollback_plan": str,
    "rationale": str,
    "requires_approval": bool,
    "action_id": str,
}

_VALID_RISK_LEVELS = {"LOW", "MEDIUM", "HIGH"}
_VALID_ROOT_CAUSE_TYPES = {
    "db_pool_exhaustion", "high_cpu", "memory_leak",
    "external_dependency_failure", "network_partition",
    "configuration_error", "replica_overload", "redis_failure", "unknown",
}


def validate_diagnosis_output(data: dict[str, Any]) -> ValidationResult:
    """Validate Diagnosis Agent JSON output."""
    errors: list[str] = []

    for field_name, expected_type in _DIAGNOSIS_SCHEMA.items():
        if field_name not in data:
            errors.append(f"Missing required field: '{field_name}'")
        elif not isinstance(data[field_name], expected_type):
            errors.append(
                f"Field '{field_name}' should be {expected_type.__name__}, "
                f"got {type(data[field_name]).__name__}"
            )

    if "confidence" in data:
        conf = data["confidence"]
        if isinstance(conf, (int, float)):
            if not (0.0 <= float(conf) <= 1.0):
                errors.append(f"'confidence' must be between 0.0 and 1.0, got {conf}")
        else:
            errors.append(f"'confidence' must be numeric, got {type(conf).__name__}")

    if "root_cause_type" in data and isinstance(data["root_cause_type"], str):
        if data["root_cause_type"] not in _VALID_ROOT_CAUSE_TYPES:
            # Don't fail — just default to unknown
            data["root_cause_type"] = "unknown"

    if errors:
        return ValidationResult(valid=False, errors=errors)

    # Sanitize: clamp confidence to valid range
    sanitized = dict(data)
    sanitized["confidence"] = max(0.0, min(1.0, float(sanitized.get("confidence", 0.5))))
    sanitized["evidence_citations"] = [str(c) for c in sanitized.get("evidence_citations", [])]

    return ValidationResult(valid=True, sanitized=sanitized)


def validate_remediation_output(data: dict[str, Any]) -> ValidationResult:
    """Validate Remediation Agent JSON output."""
    errors: list[str] = []

    for field_name, expected_type in _REMEDIATION_SCHEMA.items():
        if field_name not in data:
            errors.append(f"Missing required field: '{field_name}'")
        elif not isinstance(data[field_name], expected_type):
            # Coerce bool-like ints
            if expected_type == bool and isinstance(data[field_name], int):
                data[field_name] = bool(data[field_name])
            else:
                errors.append(
                    f"Field '{field_name}' should be {expected_type.__name__}, "
                    f"got {type(data[field_name]).__name__}"
                )

    if "risk_level" in data and isinstance(data["risk_level"], str):
        if data["risk_level"].upper() not in _VALID_RISK_LEVELS:
            errors.append(
                f"'risk_level' must be one of {_VALID_RISK_LEVELS}, got '{data['risk_level']}'"
            )

    if "steps" in data and isinstance(data["steps"], list):
        if len(data["steps"]) == 0:
            errors.append("'steps' cannot be empty — remediation must have at least one step")

    if errors:
        return ValidationResult(valid=False, errors=errors)

    sanitized = dict(data)
    sanitized["risk_level"] = sanitized["risk_level"].upper()
    sanitized["steps"] = [str(s) for s in sanitized.get("steps", [])]

    return ValidationResult(valid=True, sanitized=sanitized)


def parse_and_validate_llm_json(
    raw_text: str,
    schema: str,
) -> ValidationResult:
    """Parse LLM output text as JSON and validate against a named schema.

    Args:
        raw_text: Raw text from the LLM (may contain markdown fences).
        schema: One of 'diagnosis' | 'remediation'.

    Returns:
        ValidationResult with sanitized dict or list of errors.
    """
    # Strip markdown fences
    text = raw_text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return ValidationResult(valid=False, errors=[f"Invalid JSON: {e}"])

    if schema == "diagnosis":
        return validate_diagnosis_output(data)
    elif schema == "remediation":
        return validate_remediation_output(data)
    else:
        return ValidationResult(valid=True, sanitized=data)
