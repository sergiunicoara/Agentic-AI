"""ABAC (Attribute-Based Access Control) policy engine.

Subject attributes : role, email, department, clearance_level
Resource attributes: agent_name, owner_email, data_sensitivity (public|internal|confidential)
Action             : read | write | delete | admin
"""
from __future__ import annotations

from typing import Any, Dict

_SENSITIVITY_LEVEL: Dict[str, int] = {"public": 0, "internal": 1, "confidential": 2}
_ROLE_CLEARANCE: Dict[str, int]    = {"viewer": 0, "developer": 1, "admin": 2}


def _effective_clearance(subject: Dict[str, Any]) -> int:
    """Use explicit clearance_level when set; otherwise derive from role."""
    explicit = subject.get("clearance_level")
    if explicit is not None:
        return int(explicit)
    return _ROLE_CLEARANCE.get(subject.get("role", "viewer"), 0)


def check_span_access(
    subject: Dict[str, Any],
    resource: Dict[str, Any],
    action: str = "read",
) -> bool:
    """Return True if subject may perform action on resource.

    subject : {role, email, department?, clearance_level?}
    resource: {agent_name?, owner_email?, data_sensitivity?}
    action  : "read" | "write" | "delete"
    """
    role = subject.get("role", "viewer")

    if role == "admin":
        return True

    # Owner of the trace can always read their own data
    owner = resource.get("owner_email", "")
    if action == "read" and owner and owner == subject.get("email"):
        return True

    # Security-department users can read confidential data regardless of role
    if action == "read" and subject.get("department") == "security":
        return True

    sensitivity = resource.get("data_sensitivity", "internal")
    required = _SENSITIVITY_LEVEL.get(sensitivity, 0)
    clearance = _effective_clearance(subject)

    if action == "read":
        return clearance >= required

    if action in ("write", "delete"):
        return role in ("developer", "admin") and clearance >= required

    return False


def check_action(subject: Dict[str, Any], action: str) -> bool:
    """Policy for non-span resources (evals, admin endpoints)."""
    role = subject.get("role", "viewer")
    if role == "admin":
        return True
    _policy: Dict[str, set] = {
        "read":   {"viewer", "developer", "admin"},
        "write":  {"developer", "admin"},
        "delete": {"developer", "admin"},
        "admin":  {"admin"},
    }
    return role in _policy.get(action, set())


def filter_spans(
    subject: Dict[str, Any],
    spans: list,
    owner_email_field: str = "owner_email",
) -> list:
    """Return only spans subject is allowed to read."""
    return [
        s for s in spans
        if check_span_access(
            subject,
            {
                "data_sensitivity": getattr(s, "attributes", {}).get("data_sensitivity", "internal"),
                "owner_email": getattr(s, "attributes", {}).get(owner_email_field, ""),
            },
        )
    ]
