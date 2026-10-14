"""Permission checker — enforces user-level access control.

MVP uses the X-User-ID header. In production this would validate
a JWT against an auth provider. The checker ensures that only
authorized users can approve or reject remediation plans.
"""
from __future__ import annotations

from dataclasses import dataclass


# In production, these would come from a database/RBAC system.
# For MVP, we define role tiers by prefix conventions.
_ADMIN_PREFIXES = {"admin-", "sre-lead-", "platform-"}
_ENGINEER_PREFIXES = {"eng-", "sre-", "dev-"}
_READ_ONLY_PREFIXES = {"readonly-", "auditor-"}


@dataclass
class PermissionResult:
    allowed: bool
    user_id: str
    role: str
    reason: str


def _infer_role(user_id: str) -> str:
    uid = user_id.lower()
    for prefix in _ADMIN_PREFIXES:
        if uid.startswith(prefix):
            return "admin"
    for prefix in _ENGINEER_PREFIXES:
        if uid.startswith(prefix):
            return "engineer"
    for prefix in _READ_ONLY_PREFIXES:
        if uid.startswith(prefix):
            return "readonly"
    # Default: anonymous callers get engineer-level in MVP
    return "engineer"


def can_approve_remediation(user_id: str) -> PermissionResult:
    """Check if a user can approve or reject a remediation plan."""
    if not user_id or user_id == "anonymous":
        return PermissionResult(
            allowed=False,
            user_id=user_id,
            role="anonymous",
            reason="Anonymous users cannot approve remediation. Set X-User-ID header.",
        )

    role = _infer_role(user_id)
    allowed = role in ("admin", "engineer")

    return PermissionResult(
        allowed=allowed,
        user_id=user_id,
        role=role,
        reason=(
            f"User '{user_id}' (role={role}) {'can' if allowed else 'cannot'} approve remediation."
        ),
    )


def can_trigger_investigation(user_id: str) -> PermissionResult:
    """Check if a user can trigger an agent investigation."""
    role = _infer_role(user_id or "anonymous")
    allowed = role != "readonly"

    return PermissionResult(
        allowed=allowed,
        user_id=user_id or "anonymous",
        role=role,
        reason=f"User '{user_id}' (role={role}) {'can' if allowed else 'cannot'} trigger investigations.",
    )
