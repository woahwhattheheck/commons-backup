#!/usr/bin/env python3
"""Role-gated SLA deadline + status for $199 diagnostic fulfillment roles.

Gates on tool `diagnostic_contract`, loads landed contract commercial window
via `diagnostic_contract.load_contract_from_role`, then applies the shared
one-business-day calendar. The landed Autopsy fulfillment module that used to
provide `next_business_day` was retired with the product; the calendar rule is
unchanged.

`run_deadline` returns delivery_due_at.
`run_sla_status` compares as_of vs due → OPEN|MISSED + refund miss-remedy card.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any, Mapping

from diagnostic_contract import load_contract_from_role, require_diagnostic_contract_tool
from roles import RoleError


def _require_one_business_day_window(window: Any) -> str:
    text = str(window or "").strip()
    if "one business day" not in text.lower():
        raise RoleError(
            f"diagnostic_window must be one business day; got {text!r}"
        )
    return text


def _parse_aware(stamp: str, label: str) -> datetime:
    text = str(stamp or "").strip()
    if not text:
        raise RoleError(f"{label} must be a nonempty string")
    if not re.search(r"(?:Z|[+-]\d{2}:\d{2})$", text):
        raise RoleError(f"{label} must be an offset-aware ISO timestamp")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RoleError(f"{label} is not a valid timestamp") from exc
    if parsed.tzinfo is None:
        raise RoleError(f"{label} must carry a UTC offset")
    return parsed


def _forbid_secrets(blob: str) -> None:
    for forbidden in ("sk_", "rk_", "whsec_", "prod_", "price_", "plink_"):
        if forbidden in blob:
            raise RoleError(f"card leaked forbidden token prefix {forbidden}")


def _next_business_day(timestamp: str) -> str:
    """Same wall-clock time on the next Monday through Friday."""
    candidate = _parse_aware(timestamp, "timestamp") + timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate.isoformat()


def run_deadline(
    role: Mapping[str, Any],
    *,
    slug: str,
    usable_evidence_at: str,
) -> dict[str, Any]:
    """Compute delivery_due_at for a $199 diagnostic slug.

    Uses the shared one-business-day calendar after confirming the role can
    load the landed contract for the slug.
    """
    require_diagnostic_contract_tool(role)
    stamp = str(usable_evidence_at or "").strip()
    if not stamp:
        raise RoleError("usable_evidence_at must be a nonempty string")
    card = load_contract_from_role(role, slug=slug)
    window = _require_one_business_day_window(card.get("diagnostic_window"))
    due = _next_business_day(stamp)
    out: dict[str, Any] = {
        "slug": card.get("slug"),
        "pointer": card.get("pointer"),
        "usable_evidence_at": stamp,
        "delivery_due_at": due,
        "diagnostic_window": window,
        "diagnostic_usd": card.get("diagnostic_usd"),
        "refund": card.get("refund"),
    }
    _forbid_secrets(json.dumps(out))
    return out


def run_sla_status(
    role: Mapping[str, Any],
    *,
    slug: str,
    usable_evidence_at: str,
    as_of: str,
) -> dict[str, Any]:
    """OPEN|MISSED SLA card vs as_of, with landed miss-remedy refund text.

    Reuses run_deadline calendar path.
    within_one_business_day matches the report rule: as_of <= delivery_due_at.
    """
    base = run_deadline(
        role, slug=slug, usable_evidence_at=usable_evidence_at
    )
    as_of_stamp = str(as_of or "").strip()
    as_of_dt = _parse_aware(as_of_stamp, "as_of")
    due_dt = _parse_aware(str(base["delivery_due_at"]), "delivery_due_at")
    within = as_of_dt <= due_dt
    out: dict[str, Any] = {
        **base,
        "as_of": as_of_stamp,
        "within_one_business_day": within,
        "sla_status": "OPEN" if within else "MISSED",
    }
    _forbid_secrets(json.dumps(out))
    return out
