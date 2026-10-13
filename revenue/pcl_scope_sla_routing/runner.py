#!/usr/bin/env python3
"""Packaging Compliance Labs post-acquisition scope/SLA routing pack.

Demand: pcl-scope-sla-routing-lims-01
Buyer pairing: Packaging Compliance Labs / Ryan Ott

Exact posted fixture only. 180 synthetic sterile-package study orders
spanning integrity, aging, distribution, and product tests. 150 valid,
30 incomplete or outside site scope. Valid orders route to the exact
facility / method revision / study sequence. All 30 block with the
expected reason. Custody complete. 24-hour dock-to-start and 48-hour
report fixture calculations exact. Retries idempotent. Named human
must act before report release. No automatic release. No core replacement.

Synthetic / mocked read-only. LIMS, instruments, scheduling, billing,
and delivery simulated. No production writes. No PHI. cash_usd=0.
HOLD / BUILD-AND-VERIFY.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PACK = Path(__file__).resolve().parent
FIXTURE_PATH = PACK / "fixture.json"
STATE_PATH = PACK / "state" / "journal.json"
RECEIPT_DIR = PACK / "receipts"
RUN_RECEIPT_PATH = RECEIPT_DIR / "run.json"
ORDER_RECEIPT_PATH = RECEIPT_DIR / "orders.json"
BLOCK_RECEIPT_PATH = RECEIPT_DIR / "blocks.json"
CLOCK_RECEIPT_PATH = RECEIPT_DIR / "clocks.json"
AUDIT_RECEIPT_PATH = RECEIPT_DIR / "audit.json"
REPLAY_RECEIPT_PATH = RECEIPT_DIR / "replay.json"
CONTRACT_PATH = PACK / "contract.json"

DEMAND_ID = "pcl-scope-sla-routing-lims-01"
SCHEMA = "commons-pcl-scope-sla-routing-lims/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
BUYER = "Packaging Compliance Labs / Ryan Ott"
NAMED_QA_ROLE = "NAMED_QA"
NAMED_QA_ACTOR = "qa-named-pcl-1"
COMMAND = "python3 revenue/pcl_scope_sla_routing/runner.py"

MICHIGAN = "PCL_MICHIGAN"
EAST = "PCL_EAST"
CUSTODY_ROLES = ("SHIPPER", "COURIER", "DOCK", "LAB_CUSTODY", "ANALYST")
ADAPTERS = ("LIMS", "INSTRUMENTS", "SCHEDULING", "BILLING", "DELIVERY")

# Public post-acquisition scope: Michigan Kraft remains the ISO 11607
# integrity / aging / ISTA home. East (former Quest, Billerica) added
# product-test methods and shared ASTM D4169 / F88 revisions.
METHODS: dict[str, dict[str, Any]] = {
    "ASTM_F2096_BUBBLE": {
        "family": "INTEGRITY",
        "revision": "REV-MI-2024-03",
        "sequence": ["DOCK", "CONDITION", "BUBBLE_LEAK", "SEAL_REVIEW"],
        "sites": (MICHIGAN,),
    },
    "ASTM_F1929_DYE": {
        "family": "INTEGRITY",
        "revision": "REV-MI-2024-03",
        "sequence": ["DOCK", "CONDITION", "DYE_LEAK", "SEAL_REVIEW"],
        "sites": (MICHIGAN,),
    },
    "ASTM_F88_SEAL": {
        "family": "INTEGRITY",
        "revision": "REV-BOTH-2025-06",
        "sequence": ["DOCK", "CONDITION", "SEAL_STRENGTH", "REVIEW"],
        "sites": (MICHIGAN, EAST),
    },
    "ASTM_F1980_AGING": {
        "family": "AGING",
        "revision": "REV-MI-2023-11",
        "sequence": ["DOCK", "CHAMBER_LOAD", "AGED_PULL", "INTEGRITY_RECHECK"],
        "sites": (MICHIGAN,),
    },
    "ASTM_D4169_DISTRIBUTION": {
        "family": "DISTRIBUTION",
        "revision": "REV-BOTH-2025-01",
        "sequence": ["DOCK", "DROP", "VIBRATION", "COMPRESSION", "INSPECTION"],
        "sites": (MICHIGAN, EAST),
    },
    "ISTA_3A": {
        "family": "DISTRIBUTION",
        "revision": "REV-MI-2024-08",
        "sequence": ["DOCK", "ISTA_SEQUENCE", "INSPECTION"],
        "sites": (MICHIGAN,),
    },
    "PRODUCT_MECH_SHOCK": {
        "family": "PRODUCT",
        "revision": "REV-EAST-2025-05",
        "sequence": ["DOCK", "FIXTURE", "MECHANICAL_SHOCK", "FUNCTIONAL"],
        "sites": (EAST,),
    },
    "PRODUCT_VIBRATION": {
        "family": "PRODUCT",
        "revision": "REV-EAST-2025-05",
        "sequence": ["DOCK", "FIXTURE", "VIBRATION", "FUNCTIONAL"],
        "sites": (EAST,),
    },
    "PRODUCT_IPX": {
        "family": "PRODUCT",
        "revision": "REV-EAST-2025-05",
        "sequence": ["DOCK", "FIXTURE", "IPX_WATER", "FUNCTIONAL"],
        "sites": (EAST,),
    },
}

VALID_PLAN: tuple[tuple[str, str, str], ...] = (
    *(( "INTEGRITY", "ASTM_F2096_BUBBLE", MICHIGAN) for _ in range(14)),
    *(( "INTEGRITY", "ASTM_F1929_DYE", MICHIGAN) for _ in range(13)),
    *(( "INTEGRITY", "ASTM_F88_SEAL", MICHIGAN) for _ in range(13)),
    *(( "AGING", "ASTM_F1980_AGING", MICHIGAN) for _ in range(40)),
    *(( "DISTRIBUTION", "ASTM_D4169_DISTRIBUTION", MICHIGAN) for _ in range(20)),
    *(( "DISTRIBUTION", "ASTM_D4169_DISTRIBUTION", EAST) for _ in range(10)),
    *(( "DISTRIBUTION", "ISTA_3A", MICHIGAN) for _ in range(10)),
    *(( "PRODUCT", "PRODUCT_MECH_SHOCK", EAST) for _ in range(10)),
    *(( "PRODUCT", "PRODUCT_VIBRATION", EAST) for _ in range(10)),
    *(( "PRODUCT", "PRODUCT_IPX", EAST) for _ in range(10)),
)

BLOCK_PLAN: tuple[tuple[str, str, str], ...] = (
    *(( "INCOMPLETE_ORDER_ID", "ASTM_F88_SEAL", MICHIGAN) for _ in range(5)),
    *(( "INCOMPLETE_CUSTODY", "ASTM_F1980_AGING", MICHIGAN) for _ in range(5)),
    *(( "INCOMPLETE_DOCK_TIMESTAMP", "ASTM_D4169_DISTRIBUTION", EAST) for _ in range(5)),
    *(( "SCOPE_PRODUCT_NOT_AT_MICHIGAN", "PRODUCT_MECH_SHOCK", MICHIGAN) for _ in range(5)),
    *(( "SCOPE_AGING_NOT_AT_EAST", "ASTM_F1980_AGING", EAST) for _ in range(5)),
    *(( "SCOPE_ISTA_NOT_AT_EAST", "ISTA_3A", EAST) for _ in range(5)),
)

INCOMPLETE_REASONS = {
    "INCOMPLETE_ORDER_ID",
    "INCOMPLETE_CUSTODY",
    "INCOMPLETE_DOCK_TIMESTAMP",
}
SCOPE_REASONS = {
    "SCOPE_PRODUCT_NOT_AT_MICHIGAN",
    "SCOPE_AGING_NOT_AT_EAST",
    "SCOPE_ISTA_NOT_AT_EAST",
}


def load_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _parse_epoch(epoch: str) -> datetime:
    base = datetime.fromisoformat(epoch.replace("Z", "+00:00"))
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    return base.astimezone(timezone.utc)


def _iso(stamp: datetime) -> str:
    return stamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _add_hours(epoch: str, hours: int) -> str:
    return _iso(_parse_epoch(epoch) + timedelta(hours=hours))


def _custody(order_no: int, complete: bool) -> list[dict[str, str]]:
    if not complete:
        return [{"role": "SHIPPER", "actor": f"syn-shipper-{order_no:03d}"}]
    return [{"role": role, "actor": f"syn-{role.lower().replace('_', '-')}-{order_no:03d}"} for role in CUSTODY_ROLES]


def _method(method_id: str) -> dict[str, Any]:
    return METHODS[method_id]


def _route_ok(method_id: str, facility: str) -> bool:
    return facility in _method(method_id)["sites"]


def build_acceptance_fixture(fixture: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    spec = fixture if fixture is not None else load_fixture()
    epoch = spec["timestamp_epoch"]
    dock_hours = int(spec["dock_to_start_hours"])
    report_hours = int(spec["start_to_report_hours"])
    if len(VALID_PLAN) != spec["valid_count"]:
        raise RuntimeError("valid plan must be exactly %s rows" % spec["valid_count"])
    if len(BLOCK_PLAN) != spec["blocked_count"]:
        raise RuntimeError("block plan must be exactly %s rows" % spec["blocked_count"])

    rows: list[dict[str, Any]] = []
    for index, (family, method_id, facility) in enumerate(VALID_PLAN, start=1):
        method = _method(method_id)
        dock_at = _add_hours(epoch, index - 1)
        start_at = _add_hours(dock_at, dock_hours)
        report_at = _add_hours(start_at, report_hours)
        if method["family"] != family:
            raise RuntimeError("family/method mismatch on valid %s" % index)
        if not _route_ok(method_id, facility):
            raise RuntimeError("valid plan routed outside published scope: %s" % index)
        rows.append(
            {
                "intake_id": f"SYN-PCL-INTAKE-{index:03d}",
                "order_id": f"SYN-PCL-ORD-{index:03d}",
                "order_no": index,
                "family": family,
                "method_id": method_id,
                "method_revision": method["revision"],
                "sequence": list(method["sequence"]),
                "requested_facility": facility,
                "dock_at": dock_at,
                "expected_start_at": start_at,
                "expected_report_at": report_at,
                "custody": _custody(index, True),
                "block": False,
                "block_reason": None,
            }
        )

    for offset, (reason, method_id, facility) in enumerate(BLOCK_PLAN):
        index = spec["valid_count"] + offset + 1
        method = _method(method_id)
        dock_at = None if reason == "INCOMPLETE_DOCK_TIMESTAMP" else _add_hours(epoch, index - 1)
        order_id = None if reason == "INCOMPLETE_ORDER_ID" else f"SYN-PCL-ORD-{index:03d}"
        custody_ok = reason != "INCOMPLETE_CUSTODY"
        rows.append(
            {
                "intake_id": f"SYN-PCL-INTAKE-{index:03d}",
                "order_id": order_id,
                "order_no": index,
                "family": method["family"],
                "method_id": method_id,
                "method_revision": method["revision"],
                "sequence": list(method["sequence"]),
                "requested_facility": facility,
                "dock_at": dock_at,
                "expected_start_at": None,
                "expected_report_at": None,
                "custody": _custody(index, custody_ok),
                "block": True,
                "block_reason": reason,
            }
        )

    if len(rows) != spec["order_count"]:
        raise RuntimeError("acceptance fixture must be exactly %s orders" % spec["order_count"])
    if sum(1 for row in rows if row["block"]) != spec["blocked_count"]:
        raise RuntimeError("acceptance fixture must seed exactly %s blocks" % spec["blocked_count"])
    return rows


def classify_row(row: dict[str, Any]) -> dict[str, Any]:
    if not row.get("order_id"):
        return {"ok": False, "reason": "INCOMPLETE_ORDER_ID"}
    if row.get("dock_at") in (None, ""):
        return {"ok": False, "reason": "INCOMPLETE_DOCK_TIMESTAMP"}
    roles = [link.get("role") for link in row.get("custody") or []]
    if tuple(roles) != CUSTODY_ROLES:
        return {"ok": False, "reason": "INCOMPLETE_CUSTODY"}
    method_id = row["method_id"]
    facility = row["requested_facility"]
    if method_id not in METHODS:
        return {"ok": False, "reason": "SCOPE_UNKNOWN_METHOD"}
    if not _route_ok(method_id, facility):
        if METHODS[method_id]["family"] == "PRODUCT" and facility == MICHIGAN:
            return {"ok": False, "reason": "SCOPE_PRODUCT_NOT_AT_MICHIGAN"}
        if method_id == "ASTM_F1980_AGING" and facility == EAST:
            return {"ok": False, "reason": "SCOPE_AGING_NOT_AT_EAST"}
        if method_id == "ISTA_3A" and facility == EAST:
            return {"ok": False, "reason": "SCOPE_ISTA_NOT_AT_EAST"}
        return {"ok": False, "reason": "SCOPE_OUTSIDE_SITE"}
    return {"ok": True, "reason": None}


def sla_times(dock_at: str, dock_hours: int, report_hours: int) -> tuple[str, str]:
    start_at = _add_hours(dock_at, dock_hours)
    report_at = _add_hours(start_at, report_hours)
    return start_at, report_at


def empty_journal(spec: dict[str, Any] | None = None) -> dict[str, Any]:
    hours = spec or load_fixture()
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "dock_to_start_hours": int(hours["dock_to_start_hours"]),
        "start_to_report_hours": int(hours["start_to_report_hours"]),
        "intakes": {},
        "orders": {},
        "blocks": {},
        "adapters": {name: {} for name in ADAPTERS},
        "events": [],
        "interface_live": False,
        "production_writes": 0,
        "phi_records": 0,
        "billing_writes": 0,
        "delivery_writes": 0,
        "automatic_releases": 0,
    }


def _event(journal: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    journal["events"].append({"seq": len(journal["events"]) + 1, "kind": kind, **deepcopy(payload)})


def _adapter_payload(record: dict[str, Any], adapter: str) -> dict[str, Any]:
    payload = {
        "adapter": adapter,
        "live": False,
        "readonly": True,
        "intake_id": record["intake_id"],
        "order_id": record.get("order_id"),
        "state": record["state"],
        "facility": record.get("facility"),
        "method_id": record.get("method_id"),
        "method_revision": record.get("method_revision"),
        "start_at": record.get("start_at"),
        "report_at": record.get("report_at"),
        "cash_usd": 0,
    }
    payload["payload_sha256"] = sha256_hex({k: v for k, v in payload.items() if k != "payload_sha256"})
    return payload


def _write_adapters(journal: dict[str, Any], record: dict[str, Any]) -> None:
    for name in ADAPTERS:
        journal["adapters"][name][record["intake_id"]] = _adapter_payload(record, name)


def _blank_record(row: dict[str, Any], *, decision: dict[str, Any]) -> dict[str, Any]:
    blocked = not decision["ok"]
    return {
        "intake_id": row["intake_id"],
        "order_id": row.get("order_id"),
        "order_no": row["order_no"],
        "family": row["family"],
        "method_id": row["method_id"],
        "method_revision": None,
        "sequence": None,
        "sequence_cursor": 0,
        "sequence_log": [],
        "requested_facility": row["requested_facility"],
        "facility": None,
        "dock_at": row.get("dock_at"),
        "start_at": None,
        "report_at": None,
        "custody": deepcopy(row.get("custody") or []),
        "custody_complete": False,
        "block": blocked,
        "block_reason": decision["reason"] if blocked else None,
        "state": "BLOCKED" if blocked else "INTAKEN",
        "released": False,
        "released_by": None,
        "inbound": deepcopy(row),
    }


def intake_order(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    """Accept one job. Incomplete or out-of-scope jobs HOLD here."""
    intake_id = row["intake_id"]
    if intake_id in journal["intakes"]:
        existing = journal["intakes"][intake_id]
        if existing["order_id"] == row.get("order_id") and existing["block_reason"] == (
            None if not row.get("block") else row.get("block_reason")
        ):
            _event(journal, "REPLAY_NOOP", {"intake_id": intake_id, "order_id": row.get("order_id")})
            return {"kind": "REPLAY_NOOP", "intake_id": intake_id, "state": existing["state"]}
        raise RuntimeError("duplicate intake with different body: %s" % intake_id)

    decision = classify_row(row)
    expected_reason = row.get("block_reason")
    if row.get("block"):
        if decision["ok"] or decision["reason"] != expected_reason:
            raise RuntimeError(
                "block %s expected %s got ok=%s reason=%s"
                % (intake_id, expected_reason, decision["ok"], decision["reason"])
            )
    elif not decision["ok"]:
        raise RuntimeError("valid order %s classified as %s" % (intake_id, decision["reason"]))

    record = _blank_record(row, decision=decision)
    journal["intakes"][intake_id] = record
    if record["block"]:
        journal["blocks"][intake_id] = {"intake_id": intake_id, "reason": record["block_reason"], "expected": True}
        _write_adapters(journal, record)
        _event(journal, "BLOCKED", {"intake_id": intake_id, "reason": record["block_reason"]})
        return {"kind": "BLOCKED", "intake_id": intake_id, "reason": record["block_reason"], "state": "BLOCKED"}

    _write_adapters(journal, record)
    _event(journal, "INTAKEN", {"intake_id": intake_id, "order_id": record["order_id"]})
    return {"kind": "INTAKEN", "intake_id": intake_id, "order_id": record["order_id"], "state": "INTAKEN"}


def route_order(journal: dict[str, Any], intake_id: str) -> dict[str, Any]:
    """Bind a valid intake to the exact facility / method revision / sequence."""
    record = journal["intakes"].get(intake_id)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_ORDER"}
    if record["block"]:
        return {"ok": False, "code": "ROUTE_BLOCKED", "reason": record["block_reason"], "state": "BLOCKED"}
    if record["state"] not in {"INTAKEN"}:
        return {"ok": True, "duplicate": True, "state": record["state"]}
    inbound = record["inbound"]
    method = _method(inbound["method_id"])
    if list(inbound["sequence"]) != list(method["sequence"]):
        raise RuntimeError("sequence mismatch on %s" % intake_id)
    if inbound["method_revision"] != method["revision"]:
        raise RuntimeError("revision mismatch on %s" % intake_id)
    if not _route_ok(inbound["method_id"], inbound["requested_facility"]):
        raise RuntimeError("route outside published scope: %s" % intake_id)
    record["facility"] = inbound["requested_facility"]
    record["method_revision"] = method["revision"]
    record["sequence"] = list(method["sequence"])
    record["custody_complete"] = tuple(link.get("role") for link in record["custody"]) == CUSTODY_ROLES
    record["state"] = "ROUTED"
    journal["orders"][record["order_id"]] = intake_id
    _write_adapters(journal, record)
    _event(
        journal,
        "ROUTED",
        {
            "intake_id": intake_id,
            "order_id": record["order_id"],
            "facility": record["facility"],
            "method_id": record["method_id"],
            "method_revision": record["method_revision"],
            "sequence": record["sequence"],
        },
    )
    return {"ok": True, "kind": "ROUTED", "intake_id": intake_id, "state": "ROUTED"}


def set_sla_clocks(journal: dict[str, Any], intake_id: str) -> dict[str, Any]:
    """Start the 24-hour dock-to-start and 48-hour report clocks."""
    record = journal["intakes"].get(intake_id)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_ORDER"}
    if record["block"]:
        return {"ok": False, "code": "CLOCK_BLOCKED", "reason": record["block_reason"], "state": "BLOCKED"}
    if record["state"] == "INTAKEN":
        return {"ok": False, "code": "CLOCK_BLOCKED_NOT_ROUTED", "state": record["state"]}
    if record["state"] not in {"ROUTED"}:
        return {"ok": True, "duplicate": True, "state": record["state"]}
    inbound = record["inbound"]
    start_at, report_at = sla_times(
        record["dock_at"],
        journal["dock_to_start_hours"],
        journal["start_to_report_hours"],
    )
    if start_at != inbound["expected_start_at"] or report_at != inbound["expected_report_at"]:
        raise RuntimeError("SLA fixture mismatch on %s" % intake_id)
    record["start_at"] = start_at
    record["report_at"] = report_at
    record["state"] = "CLOCKED"
    _write_adapters(journal, record)
    _event(
        journal,
        "CLOCKS_SET",
        {
            "intake_id": intake_id,
            "dock_at": record["dock_at"],
            "start_at": start_at,
            "report_at": report_at,
            "dock_to_start_hours": journal["dock_to_start_hours"],
            "start_to_report_hours": journal["start_to_report_hours"],
        },
    )
    return {"ok": True, "kind": "CLOCKS_SET", "intake_id": intake_id, "start_at": start_at, "report_at": report_at}


def advance_sequence(journal: dict[str, Any], intake_id: str) -> dict[str, Any]:
    """Advance one study-sequence step. Last step opens named-human release."""
    record = journal["intakes"].get(intake_id)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_ORDER"}
    if record["block"]:
        return {"ok": False, "code": "SEQUENCE_BLOCKED", "reason": record["block_reason"], "state": "BLOCKED"}
    if record["state"] in {"INTAKEN", "ROUTED"}:
        return {"ok": False, "code": "SEQUENCE_BLOCKED_CLOCKS_OPEN", "state": record["state"]}
    if record["state"] in {"READY_FOR_NAMED_QA", "RELEASED"}:
        return {"ok": True, "duplicate": True, "state": record["state"]}
    sequence = list(record["sequence"] or [])
    cursor = int(record["sequence_cursor"])
    if cursor >= len(sequence):
        record["state"] = "READY_FOR_NAMED_QA"
        _write_adapters(journal, record)
        return {"ok": True, "kind": "SEQUENCE_DONE", "intake_id": intake_id, "state": "READY_FOR_NAMED_QA"}
    step = sequence[cursor]
    record["sequence_cursor"] = cursor + 1
    record["sequence_log"].append(step)
    _event(journal, "SEQUENCE_STEP", {"intake_id": intake_id, "step": step, "cursor": record["sequence_cursor"]})
    if record["sequence_cursor"] >= len(sequence):
        record["state"] = "READY_FOR_NAMED_QA"
        _write_adapters(journal, record)
        _event(journal, "SEQUENCE_DONE", {"intake_id": intake_id, "sequence": sequence})
        return {"ok": True, "kind": "SEQUENCE_DONE", "intake_id": intake_id, "step": step, "state": "READY_FOR_NAMED_QA"}
    record["state"] = "CLOCKED"
    _write_adapters(journal, record)
    return {"ok": True, "kind": "SEQUENCE_STEP", "intake_id": intake_id, "step": step, "state": "CLOCKED"}


def run_sequence(journal: dict[str, Any], intake_id: str) -> dict[str, Any]:
    last: dict[str, Any] = {"ok": False, "code": "SEQUENCE_EMPTY"}
    while True:
        last = advance_sequence(journal, intake_id)
        if not last.get("ok") or last.get("kind") == "SEQUENCE_DONE" or last.get("duplicate"):
            return last


def process_order(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    """Working program: intake → route → SLA clocks → sequence → HOLD/ready."""
    taken = intake_order(journal, row)
    if taken.get("kind") == "REPLAY_NOOP":
        return taken
    if taken.get("kind") == "BLOCKED":
        return taken
    routed = route_order(journal, row["intake_id"])
    clocks = set_sla_clocks(journal, row["intake_id"])
    sequence = run_sequence(journal, row["intake_id"])
    return {"kind": "READY_FOR_NAMED_QA", "intake_id": row["intake_id"], "route": routed, "clocks": clocks, "sequence": sequence}


def import_order(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    return process_order(journal, row)


def import_rows(journal: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    before_intakes = set(journal["intakes"])
    before_orders = set(journal["orders"])
    before_blocks = set(journal["blocks"])
    effects = [process_order(journal, row) for row in rows]
    changed = (
        (set(journal["intakes"]) - before_intakes)
        | (set(journal["orders"]) - before_orders)
        | (set(journal["blocks"]) - before_blocks)
    )
    return {
        "effects": effects,
        "changed_records": len(changed),
        "replay_noops": sum(1 for item in effects if item.get("kind") == "REPLAY_NOOP"),
        "intake_count": len(journal["intakes"]),
        "order_count": len(journal["orders"]),
        "block_count": len(journal["blocks"]),
    }


def release_order(journal: dict[str, Any], intake_id: str, *, actor_role: str, actor: str) -> dict[str, Any]:
    record = journal["intakes"].get(intake_id)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_ORDER"}
    if record["released"]:
        return {"ok": True, "duplicate": True, "state": "RELEASED"}
    role = str(actor_role or "").strip().upper()
    if role != NAMED_QA_ROLE:
        code = "RELEASE_BLOCKED_AUTONOMOUS" if role == "SYSTEM" else "RELEASE_BLOCKED_NAMED_QA_MISSING"
        _event(journal, "RELEASE_BLOCKED", {"intake_id": intake_id, "code": code, "actor_role": role or None})
        return {"ok": False, "code": code, "state": record["state"]}
    if record["block"] or record["state"] == "BLOCKED":
        _event(
            journal,
            "RELEASE_BLOCKED",
            {"intake_id": intake_id, "code": "RELEASE_BLOCKED_OPEN_HOLD", "reason": record["block_reason"]},
        )
        return {"ok": False, "code": "RELEASE_BLOCKED_OPEN_HOLD", "state": "BLOCKED"}
    if record["state"] != "READY_FOR_NAMED_QA":
        _event(
            journal,
            "RELEASE_BLOCKED",
            {"intake_id": intake_id, "code": "RELEASE_BLOCKED_SEQUENCE_OPEN", "state": record["state"]},
        )
        return {"ok": False, "code": "RELEASE_BLOCKED_SEQUENCE_OPEN", "state": record["state"]}
    record["released"] = True
    record["released_by"] = actor
    record["state"] = "RELEASED"
    _write_adapters(journal, record)
    _event(journal, "RELEASED", {"intake_id": intake_id, "released_by": actor, "role": NAMED_QA_ROLE})
    return {"ok": True, "duplicate": False, "state": "RELEASED"}


def attempt_autonomous_release(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        release_order(journal, intake_id, actor_role="SYSTEM", actor="autonomous")
        for intake_id in sorted(journal["intakes"])
    ]


def named_qa_release(journal: dict[str, Any], actor: str = NAMED_QA_ACTOR) -> list[dict[str, Any]]:
    return [
        release_order(journal, intake_id, actor_role=NAMED_QA_ROLE, actor=actor)
        for intake_id in sorted(journal["intakes"])
    ]


def _audit_payload(journal: dict[str, Any], counts: dict[str, Any]) -> dict[str, Any]:
    intakes = [deepcopy(journal["intakes"][key]) for key in sorted(journal["intakes"])]
    blocks = [deepcopy(journal["blocks"][key]) for key in sorted(journal["blocks"])]
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "counts": counts,
        "intakes": [
            {
                "intake_id": item["intake_id"],
                "order_id": item["order_id"],
                "family": item["family"],
                "method_id": item["method_id"],
                "method_revision": item["method_revision"],
                "sequence": item["sequence"],
                "sequence_cursor": item.get("sequence_cursor"),
                "sequence_log": item.get("sequence_log"),
                "facility": item["facility"],
                "dock_at": item["dock_at"],
                "start_at": item["start_at"],
                "report_at": item["report_at"],
                "custody_complete": item["custody_complete"],
                "block": item["block"],
                "block_reason": item["block_reason"],
                "state": item["state"],
                "released": item["released"],
            }
            for item in intakes
        ],
        "blocks": blocks,
        "events": deepcopy(journal["events"]),
        "adapters": {name: "SIMULATED_READONLY" for name in ADAPTERS},
    }


def run_gate(rows: list[dict[str, Any]] | None = None, fixture: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = fixture if fixture is not None else load_fixture()
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture(spec))
    journal = empty_journal(spec)
    first_import = import_rows(journal, inbound)
    autonomous = attempt_autonomous_release(journal)
    human = named_qa_release(journal)
    replay = import_rows(journal, inbound)

    intakes = list(journal["intakes"].values())
    valid = [item for item in intakes if not item["block"]]
    blocked = [item for item in intakes if item["block"]]
    by_family = {family: sum(1 for item in valid if item["family"] == family) for family in spec["families"]}
    reason_counts = {
        reason: sum(1 for item in blocked if item["block_reason"] == reason)
        for reason in spec["block_reason_counts"]
    }
    inbound_by_id = {row["intake_id"]: row for row in inbound}
    routed_exact = 0
    sla_start_exact = 0
    sla_report_exact = 0
    for item in valid:
        row = inbound_by_id[item["intake_id"]]
        method = _method(item["method_id"])
        if (
            item["facility"] == row["requested_facility"]
            and item["method_revision"] == method["revision"]
            and item["sequence"] == list(method["sequence"])
        ):
            routed_exact += 1
        if item["start_at"] == row["expected_start_at"]:
            sla_start_exact += 1
        if item["report_at"] == row["expected_report_at"]:
            sla_report_exact += 1

    counts = {
        "orders": len(intakes),
        "valid": len(valid),
        "blocked": len(blocked),
        "integrity": by_family["INTEGRITY"],
        "aging": by_family["AGING"],
        "distribution": by_family["DISTRIBUTION"],
        "product": by_family["PRODUCT"],
        "incomplete": sum(1 for item in blocked if item["block_reason"] in INCOMPLETE_REASONS),
        "outside_site_scope": sum(1 for item in blocked if item["block_reason"] in SCOPE_REASONS),
        "routed_exact": routed_exact,
        "blocked_expected_reason": sum(1 for item in blocked if journal["blocks"][item["intake_id"]]["expected"]),
        "custody_complete": sum(1 for item in valid if item["custody_complete"]),
        "dock_to_start_exact": sla_start_exact,
        "report_sla_exact": sla_report_exact,
        "released_without_named_qa": sum(1 for item in autonomous if item.get("ok")),
        "released_after_named_qa": sum(1 for item in valid if item["released"]),
        "blocked_released": sum(1 for item in blocked if item["released"]),
        "replay_changed_records": replay["changed_records"],
    }
    audit = _audit_payload(journal, counts)
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "command": COMMAND,
        "counts": counts,
        "block_reasons": reason_counts,
        "first_import": {k: v for k, v in first_import.items() if k != "effects"},
        "replay": {k: v for k, v in replay.items() if k != "effects"},
        "autonomous_release_effects": autonomous,
        "named_qa_release_effects": human,
        "intakes": sorted(intakes, key=lambda item: item["intake_id"]),
        "blocks": [journal["blocks"][key] for key in sorted(journal["blocks"])],
        "adapters": {name: [journal["adapters"][name][key] for key in sorted(journal["adapters"][name])] for name in ADAPTERS},
        "events": deepcopy(journal["events"]),
        "interface_live": False,
        "interfaces": "SIMULATED",
        "production_writes": 0,
        "phi_records": 0,
        "billing_writes": 0,
        "delivery_writes": 0,
        "automatic_release": False,
        "cash_usd": 0,
        "pre_sale_transport": "NONE",
        "audit": audit,
        "audit_sha256": sha256_hex(audit),
        "golden_audit_sha256": spec.get("golden_audit_sha256"),
        "journal": journal,
        "official_binary": COMMAND,
        "official_test": "python3 -m unittest test_pcl_scope_sla_routing.py",
    }


def pass_contract(result: dict[str, Any], fixture: dict[str, Any] | None = None) -> list[str]:
    spec = fixture if fixture is not None else load_fixture()
    expected = spec["expected"]
    failures: list[str] = []
    counts = result.get("counts") or {}
    for key, value in expected.items():
        if counts.get(key) != value:
            failures.append(f"{key}!={value} actual={counts.get(key)}")
    if len(result.get("intakes") or []) != 180:
        failures.append("intake_rows")
    intake_ids = [item["intake_id"] for item in result.get("intakes") or []]
    if len(intake_ids) != len(set(intake_ids)):
        failures.append("duplicate_intake_ids")
    if result.get("interface_live") is not False:
        failures.append("interface_live")
    if result.get("interfaces") != "SIMULATED":
        failures.append("interfaces")
    if result.get("production_writes") != 0:
        failures.append("production_writes")
    if result.get("phi_records") != 0:
        failures.append("phi_records")
    if result.get("billing_writes") != 0:
        failures.append("billing_writes")
    if result.get("delivery_writes") != 0:
        failures.append("delivery_writes")
    if result.get("automatic_release") is not False:
        failures.append("automatic_release")
    if result.get("cash_usd") != 0:
        failures.append("cash_usd")
    if not all(item.get("code") == "RELEASE_BLOCKED_AUTONOMOUS" for item in result.get("autonomous_release_effects") or []):
        failures.append("autonomous_not_blocked")
    if any(item.get("released") for item in result.get("intakes") or [] if item.get("block")):
        failures.append("blocked_released")
    if result.get("replay", {}).get("changed_records") != 0:
        failures.append("replay_changed")
    if result.get("block_reasons") != spec["block_reason_counts"]:
        failures.append("block_reason_counts")
    golden = spec.get("golden_audit_sha256")
    if golden and golden != "PIN_AFTER_FIRST_RUN" and result.get("audit_sha256") != golden:
        failures.append("audit_sha256")
    if sha256_hex(result.get("audit")) != result.get("audit_sha256"):
        failures.append("audit_hash_internal")
    return failures


def expected_actual(result: dict[str, Any], fixture: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = fixture if fixture is not None else load_fixture()
    expected = spec["expected"]
    actual = {key: (result.get("counts") or {}).get(key) for key in expected}
    return {"expected": expected, "actual": actual, "match": expected == actual}


def compact_orders(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "intake_id": item["intake_id"],
            "order_id": item["order_id"],
            "facility": item["facility"],
            "method_id": item["method_id"],
            "method_revision": item["method_revision"],
            "sequence": item["sequence"],
            "sequence_log": item.get("sequence_log"),
            "dock_at": item["dock_at"],
            "start_at": item["start_at"],
            "report_at": item["report_at"],
            "state": item["state"],
            "released": item["released"],
        }
        for item in (journal["intakes"][key] for key in sorted(journal["intakes"]))
        if not item["block"]
    ]


def compact_blocks(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [deepcopy(journal["blocks"][key]) for key in sorted(journal["blocks"])]


def compact_clocks(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "intake_id": item["intake_id"],
            "dock_at": item["dock_at"],
            "start_at": item["start_at"],
            "report_at": item["report_at"],
            "dock_to_start_hours": journal["dock_to_start_hours"],
            "start_to_report_hours": journal["start_to_report_hours"],
        }
        for item in (journal["intakes"][key] for key in sorted(journal["intakes"]))
        if not item["block"]
    ]


def persist_run(result: dict[str, Any]) -> dict[str, str]:
    journal = deepcopy(result["journal"])
    for record in journal["intakes"].values():
        record.pop("inbound", None)
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(journal, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    payload = cli_payload(result)
    RUN_RECEIPT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    ORDER_RECEIPT_PATH.write_text(json.dumps(compact_orders(journal), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    BLOCK_RECEIPT_PATH.write_text(json.dumps(compact_blocks(journal), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    CLOCK_RECEIPT_PATH.write_text(json.dumps(compact_clocks(journal), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    AUDIT_RECEIPT_PATH.write_text(
        json.dumps(
            {
                "audit_sha256": result["audit_sha256"],
                "counts": expected_actual(result),
                "block_reasons": result["block_reasons"],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    REPLAY_RECEIPT_PATH.write_text(json.dumps(result["replay"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    CONTRACT_PATH.write_text(
        json.dumps(
            {
                "buyer": BUYER,
                "cash_usd": 0,
                "demand_id": DEMAND_ID,
                "interfaces": "SIMULATED_READ_ONLY",
                "live_lims": False,
                "official_binary": COMMAND,
                "official_test": "python3 -m unittest test_pcl_scope_sla_routing.py",
                "page": "pcl-scope-sla-routing-lims.html",
                "pre_sale_transport": "NONE",
                "production_deployment": False,
                "schema": SCHEMA,
                "state": TRUTH_GATE,
                "synthetic": True,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "journal": str(STATE_PATH),
        "run": str(RUN_RECEIPT_PATH),
        "orders": str(ORDER_RECEIPT_PATH),
        "blocks": str(BLOCK_RECEIPT_PATH),
        "clocks": str(CLOCK_RECEIPT_PATH),
        "audit": str(AUDIT_RECEIPT_PATH),
        "replay": str(REPLAY_RECEIPT_PATH),
        "contract": str(CONTRACT_PATH),
    }


def load_journal(path: Path = STATE_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def cli_payload(result: dict[str, Any]) -> dict[str, Any]:
    counts = expected_actual(result)
    return {
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "ok": not pass_contract(result),
        "failures": pass_contract(result),
        "command": COMMAND,
        "expected": counts["expected"],
        "actual": counts["actual"],
        "counts_match": counts["match"],
        "block_reasons": result["block_reasons"],
        "audit_sha256": result["audit_sha256"],
        "replay_changed_records": result.get("counts", {}).get("replay_changed_records"),
        "replay": result["replay"],
        "truth_gate": TRUTH_GATE,
        "interfaces": "SIMULATED",
        "pre_sale_transport": "NONE",
        "cash_usd": 0,
        "working_program": "intake → route → SLA clocks → HOLD/release",
        "official_binary": COMMAND,
        "official_test": "python3 -m unittest test_pcl_scope_sla_routing.py",
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PCL scope-controlled sterile-package routing + SLA runner")
    parser.add_argument("--replay", action="store_true", help="replay the fixture into the persisted journal")
    parser.add_argument("--print-goldens", action="store_true", help="print the computed audit hash and exit")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.print_goldens:
        result = run_gate()
        sys.stdout.write(_canonical({"audit_sha256": result["audit_sha256"], "expected": expected_actual(result)}) + "\n")
        return 0
    if args.replay:
        if not STATE_PATH.is_file():
            result = run_gate()
            persist_run(result)
        journal = load_journal()
        replay = import_rows(journal, build_acceptance_fixture())
        body = {
            "ok": replay["changed_records"] == 0 and replay["replay_noops"] == 180,
            "replay": {k: v for k, v in replay.items() if k != "effects"},
            "journal_sha256": sha256_hex(journal),
        }
        STATE_PATH.write_text(json.dumps(journal, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        REPLAY_RECEIPT_PATH.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        sys.stdout.write(_canonical(body) + "\n")
        return 0 if body["ok"] else 1

    first = run_gate()
    second = run_gate()
    failures = pass_contract(first)
    if first.get("audit_sha256") != second.get("audit_sha256"):
        failures.append("audit_replay_mismatch")
    written = persist_run(first)
    payload = cli_payload(first)
    payload["failures"] = failures
    payload["ok"] = not failures
    payload["written"] = written
    sys.stdout.write(_canonical(payload) + "\n")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
