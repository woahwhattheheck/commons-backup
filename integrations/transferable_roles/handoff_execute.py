#!/usr/bin/env python3
"""Prove role-gated executes still run after transfer / export→import handoff.

RIVET claim rivet-r4-handoff-execute-survive-20260905-01 (HINGE peer-assist).
Extend: rivet-r4-handoff-prove-diag-receipt-fulfill-20260905-01 — also prove
diagnostic_receipt + diagnostic_fulfill after handoff.
Extend: hinge-r4-handoff-prove-diag-sla-20260905-01 — also prove
diagnostic_fulfill.run_sla_status (OPEN|MISSED).
Import-only wraps of landed diagnostic_* helpers.
Does not remint paid_case, fulfillment, diagnostic_fulfill body, or peers.py.
"""

from __future__ import annotations

import json
from typing import Any

from diagnostic_contract import load_contract_from_role
from diagnostic_fulfill import run_deadline as run_diagnostic_deadline
from diagnostic_fulfill import run_sla_status as run_diagnostic_sla
from diagnostic_receipt import load_receipt_from_role
from roles import RoleError, RoleStore

_FORBIDDEN = ("sk_", "rk_", "whsec_", "prod_", "price_", "plink_")


def _tool_names(role: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for tool in role.get("tools") or []:
        if isinstance(tool, dict) and tool.get("name"):
            names.add(str(tool["name"]).strip())
    return names


def _bound_routes(role: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for route in role.get("access_routes") or []:
        if not isinstance(route, dict):
            continue
        name = str(route.get("name") or "").strip()
        if not name:
            continue
        entry: dict[str, Any] = {"name": name}
        for field in ("session_id", "last_run_id", "pool_id"):
            if route.get(field):
                entry[field] = str(route[field]).strip()
        out.append(entry)
    return out


def _forbid_leaks(obj: Any) -> None:
    blob = json.dumps(obj)
    for forbidden in _FORBIDDEN:
        if forbidden in blob:
            raise RoleError(f"handoff prove leaked forbidden token prefix {forbidden}")


def prove_successor_executes(
    store: RoleStore,
    role_id: str,
    *,
    case_ref: str = "handoff_case",
    usable_evidence_at: str = "2026-09-04T15:00:00-04:00",
    diagnostic_slug: str = "dealer",
    as_of: str | None = None,
) -> dict[str, Any]:
    """Run whichever role-gated executes the role tools after a handoff."""
    role = store.get(role_id)
    names = _tool_names(role)
    executes: dict[str, Any] = {}
    sla_as_of = str(as_of or usable_evidence_at).strip()

    if "diagnostic_contract" in names:
        executes["diagnostic-contract"] = load_contract_from_role(
            role, slug=diagnostic_slug
        )

    if "diagnostic_receipt" in names:
        # repair has no receipt twin — skip rather than invent / remint
        if str(diagnostic_slug).strip() != "repair":
            executes["diagnostic-receipt"] = load_receipt_from_role(
                role, slug=diagnostic_slug
            )

    if "diagnostic_fulfill" in names:
        executes["diagnostic-fulfill-deadline"] = run_diagnostic_deadline(
            role,
            slug=diagnostic_slug,
            usable_evidence_at=usable_evidence_at,
        )
        executes["diagnostic-fulfill-sla"] = run_diagnostic_sla(
            role,
            slug=diagnostic_slug,
            usable_evidence_at=usable_evidence_at,
            as_of=sla_as_of,
        )

    if not executes:
        raise RoleError(
            f"role {role_id} has no role-gated execute tools "
            "(diagnostic_contract / diagnostic_receipt / diagnostic_fulfill); "
            "refusing prove (CRM / non-execute role)"
        )

    occupant = role.get("occupant")
    occupant_session = None
    if isinstance(occupant, dict):
        occupant_session = occupant.get("session_id")

    out: dict[str, Any] = {
        "ok": True,
        "verification_scope": "LOCAL_HELPER_EXECUTION",
        "service_operations_performed": False,
        "role_id": role["role_id"],
        "occupant_session": occupant_session,
        "bound_routes": _bound_routes(role),
        "executes": executes,
    }
    _forbid_leaks(out)
    return out
