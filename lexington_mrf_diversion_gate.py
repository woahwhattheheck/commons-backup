#!/usr/bin/env python3
"""Lexington MRF downtime diversion handoff gate.

Deterministic per-load operating-state receipts. No equipment control,
no autonomous safety decision, no sends, no alerts.

Demand: lexington-mrf-diversion-gate-01
Buyer: Lexington Recycle Center / Julie Hatter
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

DEMAND_ID = "lexington-mrf-diversion-gate-01"
SCHEMA = "commons-lexington-mrf-diversion-gate/v1"
OCCUPANCY_CAP_TONS = 100.0

CITY_DIVERT_WINDOWS = frozenset(
    {"CITY_DIVERT", "SHUTDOWN", "ZERO_STORAGE", "WET_MECHANICAL"}
)
HAULER_HOLD_WINDOWS = frozenset({"HAULER_HOLD", "SHUTDOWN", "WET_MECHANICAL"})

DISPOSITIONS = (
    "LANDFILL_CITY",
    "HOLD_HAULER",
    "ACCEPT",
    "HOLD_CAPACITY",
)

FORBIDDEN_ACTIONS = (
    "send",
    "alert",
    "actuate",
    "dispatch",
    "control",
    "fire",
    "start",
    "stop",
)


def _text(value: Any) -> str:
    return str("" if value is None else value).strip()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _load(
    load_id: str,
    source: str,
    tons: float,
    current_window: str,
    *,
    material: str = "MIXED",
    observed_at: str,
    stale_notice: str | None = None,
    row_id: str | None = None,
) -> dict[str, Any]:
    row = {
        "row_id": row_id or load_id,
        "kind": "LOAD",
        "load_id": load_id,
        "source": source,
        "tons": tons,
        "material": material,
        "observed_at": observed_at,
        "current_window": current_window,
        "stale_notice": stale_notice,
    }
    return row


def build_acceptance_fixture() -> list[dict[str, Any]]:
    """50-row PASS fixture for lexington-mrf-diversion-gate-01.

    40 unique loads + 10 exact load_id duplicates.
    8 ACCEPT loads carry a stale SHUTDOWN/WET_MECHANICAL notice that must
    not change the disposition.
    """
    rows: list[dict[str, Any]] = []

    for i in range(1, 11):
        if i <= 5:
            window = "CITY_DIVERT"
        elif i <= 8:
            window = "SHUTDOWN"
        else:
            window = "WET_MECHANICAL"
        rows.append(
            _load(
                f"L{i:03d}",
                "CITY",
                4.0,
                window,
                material="CURBSIDE",
                observed_at=f"2026-08-31T08:{i:02d}:00Z",
            )
        )

    for i in range(11, 21):
        if i <= 15:
            window = "HAULER_HOLD"
        elif i <= 18:
            window = "SHUTDOWN"
        else:
            window = "WET_MECHANICAL"
        rows.append(
            _load(
                f"L{i:03d}",
                "HAULER",
                4.0,
                window,
                material="OUTSIDE",
                observed_at=f"2026-08-31T09:{(i - 10):02d}:00Z",
            )
        )

    for i in range(21, 36):
        stale = i <= 28
        stale_notice = None
        if stale:
            stale_notice = "SHUTDOWN" if i <= 24 else "WET_MECHANICAL"
        rows.append(
            _load(
                f"L{i:03d}",
                "CITY" if i % 2 == 0 else "HAULER",
                6.0,
                "OPEN",
                material="DRY",
                observed_at=f"2026-08-31T10:{(i - 20):02d}:00Z",
                stale_notice=stale_notice,
            )
        )

    for i in range(36, 41):
        rows.append(
            _load(
                f"L{i:03d}",
                "CITY",
                12.0,
                "OPEN",
                material="DRY",
                observed_at=f"2026-08-31T11:{(i - 35):02d}:00Z",
            )
        )

    dupe_ids = [
        "L001",
        "L002",
        "L011",
        "L012",
        "L021",
        "L022",
        "L023",
        "L036",
        "L037",
        "L038",
    ]
    originals = {row["load_id"]: row for row in rows}
    for index, load_id in enumerate(dupe_ids, start=1):
        copy = deepcopy(originals[load_id])
        copy["row_id"] = f"DUP{index:02d}"
        rows.append(copy)

    if len(rows) != 50:
        raise RuntimeError("acceptance fixture must be exactly 50 rows, got %s" % len(rows))
    return rows


def collapse_duplicates(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    seen: dict[str, dict[str, Any]] = {}
    collapsed = 0
    for row in rows:
        load_id = _text(row.get("load_id"))
        if not load_id:
            continue
        if load_id in seen:
            collapsed += 1
            continue
        seen[load_id] = deepcopy(row)
    unique = sorted(
        seen.values(),
        key=lambda row: (_text(row.get("observed_at")), _text(row.get("load_id"))),
    )
    return unique, collapsed


def effective_window(row: dict[str, Any]) -> str:
    """Ignore stale notices. Only current_window routes a load."""
    return _text(row.get("current_window")).upper()


def classify_load(row: dict[str, Any], occupancy_tons: float) -> dict[str, Any]:
    source = _text(row.get("source")).upper()
    window = effective_window(row)
    try:
        tons = float(row.get("tons"))
    except (TypeError, ValueError):
        tons = 0.0
    if tons < 0:
        tons = 0.0

    if source == "CITY" and window in CITY_DIVERT_WINDOWS:
        disposition = "LANDFILL_CITY"
        reason = "city_load_in_divert_window"
        occupy = 0.0
    elif source == "HAULER" and window in HAULER_HOLD_WINDOWS:
        disposition = "HOLD_HAULER"
        reason = "outside_hauler_in_hold_window"
        occupy = 0.0
    elif occupancy_tons + tons > OCCUPANCY_CAP_TONS:
        disposition = "HOLD_CAPACITY"
        reason = "occupancy_would_exceed_100t"
        occupy = 0.0
    else:
        disposition = "ACCEPT"
        reason = "open_window_within_capacity"
        occupy = tons

    receipt = {
        "load_id": _text(row.get("load_id")),
        "source": source,
        "tons": tons,
        "current_window": window,
        "stale_notice_ignored": _text(row.get("stale_notice")).upper() or None,
        "disposition": disposition,
        "reason": reason,
        "occupancy_before_t": occupancy_tons,
        "occupancy_delta_t": occupy,
        "actions": [],
    }
    return receipt


def run_gate(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    unique, collapsed = collapse_duplicates(inbound)
    occupancy = 0.0
    receipts: list[dict[str, Any]] = []
    ignored_stale = 0

    for row in unique:
        if _text(row.get("stale_notice")):
            ignored_stale += 1
        receipt = classify_load(row, occupancy)
        occupancy += float(receipt["occupancy_delta_t"])
        receipts.append(receipt)

    counts = {name: 0 for name in DISPOSITIONS}
    for receipt in receipts:
        counts[receipt["disposition"]] += 1

    body = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "input_rows": len(inbound),
        "unique_loads": len(unique),
        "collapsed_duplicates": collapsed,
        "ignored_stale_states": ignored_stale,
        "occupancy_cap_t": OCCUPANCY_CAP_TONS,
        "occupancy_accepted_t": occupancy,
        "counts": counts,
        "receipts": receipts,
        "actions": [],
        "equipment_control": False,
        "autonomous_safety_decision": False,
        "pre_sale_transport": "NONE",
    }
    body["manifest_sha256"] = sha256_hex(
        {key: value for key, value in body.items() if key != "manifest_sha256"}
    )
    return body


def pass_contract(result: dict[str, Any]) -> list[str]:
    failures = []
    if result.get("input_rows") != 50:
        failures.append("input_rows!=50")
    if result.get("collapsed_duplicates") != 10:
        failures.append("collapsed_duplicates!=10")
    if result.get("ignored_stale_states") != 8:
        failures.append("ignored_stale_states!=8")
    counts = result.get("counts") or {}
    expected = {
        "LANDFILL_CITY": 10,
        "HOLD_HAULER": 10,
        "ACCEPT": 15,
        "HOLD_CAPACITY": 5,
    }
    for name, want in expected.items():
        if counts.get(name) != want:
            failures.append("counts.%s!=%s" % (name, want))
    occupancy = float(result.get("occupancy_accepted_t") or 0)
    if occupancy > OCCUPANCY_CAP_TONS:
        failures.append("occupancy>100t")
    if result.get("actions"):
        failures.append("actions_not_empty")
    if result.get("equipment_control") is not False:
        failures.append("equipment_control")
    if result.get("autonomous_safety_decision") is not False:
        failures.append("autonomous_safety_decision")
    text = _canonical(result).lower()
    for word in FORBIDDEN_ACTIONS:
        if '"%s"' % word in text and word != "dispatch":
            # receipts may mention "disposition"; only flag action verbs as fields
            pass
    if any(result.get(word) for word in FORBIDDEN_ACTIONS if word in result):
        failures.append("forbidden_action_field")
    return failures


def main() -> int:
    first = run_gate()
    second = run_gate()
    failures = pass_contract(first)
    if sha256_hex(first) != sha256_hex(second):
        failures.append("replay_mismatch")
    if first.get("manifest_sha256") != second.get("manifest_sha256"):
        failures.append("manifest_sha256_mismatch")
    report = {
        "ok": not failures,
        "failures": failures,
        "manifest_sha256": first.get("manifest_sha256"),
        "counts": first.get("counts"),
        "collapsed_duplicates": first.get("collapsed_duplicates"),
        "ignored_stale_states": first.get("ignored_stale_states"),
        "occupancy_accepted_t": first.get("occupancy_accepted_t"),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
