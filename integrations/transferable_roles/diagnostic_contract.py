#!/usr/bin/env python3
"""Load landed $199 diagnostic contract.json by slug for transferable roles.

Successor execute path: gate on tool `diagnostic_contract`, read the checked-in
revenue/*/contract.json for dealer|referral|repair|plant. Does not remint
contracts, invent Stripe, or write CRM.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from roles import RoleError

_TOOL_NAME = "diagnostic_contract"
_TOOL_ENTRY = "integrations/transferable_roles/diagnostic_contract.py"

_ROOT = Path(__file__).resolve().parents[2]

SLUG_TO_CONTRACT = {
    "dealer": "revenue/dealer_service_lead_rescue/contract.json",
    "referral": "revenue/referral_intake_completeness/contract.json",
    "repair": "revenue/repair_booking_preflight/contract.json",
    "plant": "revenue/plant_downtime_handoff/contract.json",
}


def require_diagnostic_contract_tool(role: Mapping[str, Any]) -> dict[str, Any]:
    """Refuse unless the role tools this module's execute entry."""
    if not isinstance(role, Mapping):
        raise RoleError("role must be an object")
    for tool in role.get("tools") or []:
        if not isinstance(tool, Mapping):
            continue
        if tool.get("name") != _TOOL_NAME:
            continue
        entry = str(tool.get("entry") or "").strip()
        if entry != _TOOL_ENTRY and not entry.endswith("/diagnostic_contract.py"):
            raise RoleError(
                f"{_TOOL_NAME} entry must be {_TOOL_ENTRY}; got {entry!r}"
            )
        return dict(tool)
    raise RoleError(
        f"role lacks tool {_TOOL_NAME} → {_TOOL_ENTRY}; "
        "refusing diagnostic contract load (not a $199 diagnostic fulfillment role)"
    )


def _slug_pointer(slug: str) -> str:
    try:
        return SLUG_TO_CONTRACT[slug]
    except KeyError as exc:
        raise RoleError(
            f"unknown diagnostic slug {slug!r}; "
            f"expected one of {sorted(SLUG_TO_CONTRACT)}"
        ) from exc


def _role_knows_contract(role: Mapping[str, Any], pointer: str) -> bool:
    for item in role.get("knowledge") or []:
        if isinstance(item, str) and item.strip() == pointer:
            return True
        if isinstance(item, Mapping) and str(item.get("pointer") or "").strip() == pointer:
            return True
    return False


def load_contract_from_role(
    role: Mapping[str, Any],
    *,
    slug: str,
) -> dict[str, Any]:
    """Read landed contract.json for slug; return a compact operator card."""
    require_diagnostic_contract_tool(role)
    key = str(slug or "").strip().lower()
    pointer = _slug_pointer(key)
    if not _role_knows_contract(role, pointer):
        raise RoleError(
            f"role knowledge missing pointer {pointer}; "
            "refusing load (role must cite the landed contract)"
        )
    path = _ROOT / pointer
    if not path.is_file():
        raise RoleError(f"landed contract missing on disk: {pointer}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RoleError(f"failed to read {pointer}: {exc}") from exc
    if not isinstance(raw, dict):
        raise RoleError(f"{pointer} must be a JSON object")

    commercial = raw.get("commercial")
    if not isinstance(commercial, dict):
        commercial = {}
    if raw.get("schema") == "commons-repair-booking-contract-v1":
        offer = raw.get("offer")
        if not isinstance(offer, dict):
            raise RoleError(f"{pointer} offer must be a JSON object")
        commercial = {
            "diagnostic_usd": offer.get("diagnostic_price_usd"),
            "diagnostic_window": offer.get("diagnostic_delivery"),
            "refund": offer.get("refund"),
        }
    acceptance = raw.get("acceptance")
    acceptance_n = len(acceptance) if isinstance(acceptance, (list, dict)) else 0

    out: dict[str, Any] = {
        "slug": key,
        "pointer": pointer,
        "id": str(raw.get("id") or "").strip(),
        "version": raw.get("version"),
        "diagnostic_usd": commercial.get("diagnostic_usd"),
        "diagnostic_window": commercial.get("diagnostic_window"),
        "refund": commercial.get("refund"),
        "acceptance_count": acceptance_n,
        "acceptance": acceptance,
        "scope": raw.get("scope"),
        "accepted_terminal_states": raw.get("accepted_terminal_states"),
        "data_boundary": raw.get("data_boundary"),
        "decision_boundary": raw.get("decision_boundary"),
        "open_door": raw.get("open_door"),
    }
    # Never surface secrets / Stripe ids from a reminted shape.
    blob = json.dumps(out)
    for forbidden in ("sk_", "rk_", "whsec_", "prod_", "price_", "plink_"):
        if forbidden in blob:
            raise RoleError(f"contract card leaked forbidden token prefix {forbidden}")
    return out
