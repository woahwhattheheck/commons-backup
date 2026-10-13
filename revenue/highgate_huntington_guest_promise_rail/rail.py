#!/usr/bin/env python3
"""Deterministic offline guest-promise reconciliation core.

This module consumes approved synthetic post-booking events only. It does not
connect to hotel, spa, restaurant, payment, gift-card, or guest systems and it
never makes rate, availability, service-recovery, or monetary decisions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "highgate-huntington-guest-promise-rail/v1"
SURFACES = {"ROOM", "SPA", "DINING", "BAR"}
RESOURCE_STATES = {"AVAILABLE", "HOLD", "OUT_OF_SERVICE", "NOT_READY"}
BOOKING_ACTIONS = {"RESERVE", "RELEASE", "COMPLETE", "NO_SHOW"}
OUTCOMES = {"APPLIED", "REJECTED", "UNKNOWN"}
ACCOUNT_TYPES = {"FOLIO", "GIFT_CARD", "PACKAGE"}
MONEY_KINDS = {
    "FOLIO": {"DEPOSIT", "CHARGE", "VOID", "REFUND"},
    "GIFT_CARD": {"LOAD", "REDEEM"},
    "PACKAGE": {"LOAD", "REDEEM"},
}
HANDOFF_STATES = {"QUEUED", "ACKED", "HOLD"}
RECOVERY_STATES = {"OPEN", "IN_PROGRESS", "RESOLVED", "HOLD"}
HEX64 = re.compile(r"^[0-9a-f]{64}$")
PII_KEYS = {
    "guest_name", "guest_email", "guest_phone", "guest_address", "guest_dob",
    "name", "email", "phone", "address", "ssn", "dob", "date_of_birth",
    "card_number", "pan", "cvv", "passport", "loyalty_number",
}
COMMON = {"event_id", "type", "sequence"}
FIELDS = {
    "promise": COMMON | {"promise_id", "journey_id", "expected_surfaces"},
    "resource": COMMON | {"surface", "resource_id", "state"},
    "booking": COMMON | {"operation_id", "promise_id", "surface", "resource_id", "slot_id", "action", "outcome"},
    "money": COMMON | {"operation_id", "promise_id", "account_type", "account_id", "kind", "amount_cents", "related_operation_id", "outcome"},
    "handoff": COMMON | {"handoff_id", "promise_id", "from_surface", "to_surface", "state"},
    "recovery": COMMON | {"recovery_id", "promise_id", "state", "reason_code"},
    "resolution": COMMON | {"resolution_id", "operation_id", "resolved_outcome", "reason_code"},
}

class RailError(ValueError):
    """Fail-closed validation error."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def hash_value(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise RailError(f"{label} must be a non-empty trimmed string")
    return value


def _int(value: Any, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise RailError(f"{label} must be an integer >= {minimum}")
    return value


def _cents(value: Any, label: str) -> int:
    return _int(value, label, minimum=1)


def _reject_pii(value: Any, path: str = "event") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise RailError(f"{path} contains non-string key")
            lowered = key.lower()
            if lowered in PII_KEYS or lowered.startswith("guest_") or lowered.startswith("beneficiary_"):
                raise RailError(f"PII field forbidden: {path}.{key}")
            _reject_pii(child, f"{path}.{key}")
    elif isinstance(value, list):
        for i, child in enumerate(value):
            _reject_pii(child, f"{path}[{i}]")


def _normalize(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise RailError("each event must be an object")
    _reject_pii(raw)
    event = dict(raw)
    event_id = _text(event.get("event_id"), "event_id")
    kind = _text(event.get("type"), f"{event_id}.type")
    if kind not in FIELDS:
        raise RailError(f"{event_id}: unknown event type {kind}")
    missing = FIELDS[kind] - set(event)
    extra = set(event) - FIELDS[kind]
    if missing or extra:
        raise RailError(f"{event_id}: schema mismatch missing={sorted(missing)} extra={sorted(extra)}")
    _int(event["sequence"], f"{event_id}.sequence", minimum=1)

    if kind == "promise":
        _text(event["promise_id"], f"{event_id}.promise_id")
        _text(event["journey_id"], f"{event_id}.journey_id")
        surfaces = event["expected_surfaces"]
        if not isinstance(surfaces, list) or not surfaces or any(x not in SURFACES for x in surfaces):
            raise RailError(f"{event_id}.expected_surfaces invalid")
        if len(surfaces) != len(set(surfaces)):
            raise RailError(f"{event_id}.expected_surfaces contains duplicates")
        event["expected_surfaces"] = sorted(surfaces)
    elif kind == "resource":
        if event["surface"] not in SURFACES or event["state"] not in RESOURCE_STATES:
            raise RailError(f"{event_id}: invalid resource surface/state")
        _text(event["resource_id"], f"{event_id}.resource_id")
    elif kind == "booking":
        _text(event["operation_id"], f"{event_id}.operation_id")
        _text(event["promise_id"], f"{event_id}.promise_id")
        if event["surface"] not in SURFACES:
            raise RailError(f"{event_id}: invalid booking surface")
        _text(event["resource_id"], f"{event_id}.resource_id")
        _text(event["slot_id"], f"{event_id}.slot_id")
        if event["action"] not in BOOKING_ACTIONS or event["outcome"] not in OUTCOMES:
            raise RailError(f"{event_id}: invalid booking action/outcome")
    elif kind == "money":
        _text(event["operation_id"], f"{event_id}.operation_id")
        _text(event["promise_id"], f"{event_id}.promise_id")
        account_type = event["account_type"]
        if account_type not in ACCOUNT_TYPES or event["kind"] not in MONEY_KINDS.get(account_type, set()):
            raise RailError(f"{event_id}: invalid money account/kind")
        _text(event["account_id"], f"{event_id}.account_id")
        _cents(event["amount_cents"], f"{event_id}.amount_cents")
        related = event["related_operation_id"]
        if event["kind"] in {"VOID", "REFUND"}:
            _text(related, f"{event_id}.related_operation_id")
        elif related is not None:
            raise RailError(f"{event_id}.related_operation_id must be null")
        if event["outcome"] not in OUTCOMES:
            raise RailError(f"{event_id}: invalid money outcome")
    elif kind == "handoff":
        _text(event["handoff_id"], f"{event_id}.handoff_id")
        _text(event["promise_id"], f"{event_id}.promise_id")
        if event["from_surface"] not in SURFACES or event["to_surface"] not in SURFACES:
            raise RailError(f"{event_id}: invalid handoff surface")
        if event["state"] not in HANDOFF_STATES:
            raise RailError(f"{event_id}: invalid handoff state")
    elif kind == "recovery":
        _text(event["recovery_id"], f"{event_id}.recovery_id")
        _text(event["promise_id"], f"{event_id}.promise_id")
        if event["state"] not in RECOVERY_STATES:
            raise RailError(f"{event_id}: invalid recovery state")
        _text(event["reason_code"], f"{event_id}.reason_code")
    elif kind == "resolution":
        _text(event["resolution_id"], f"{event_id}.resolution_id")
        _text(event["operation_id"], f"{event_id}.operation_id")
        if event["resolved_outcome"] not in {"APPLIED", "REJECTED"}:
            raise RailError(f"{event_id}: invalid resolved outcome")
        _text(event["reason_code"], f"{event_id}.reason_code")
    return event


def _unique_events(raw_events: Iterable[Any]) -> tuple[list[dict[str, Any]], int]:
    by_id: dict[str, dict[str, Any]] = {}
    encoded: dict[str, bytes] = {}
    retry = 0
    for raw in raw_events:
        event = _normalize(raw)
        key = event["event_id"]
        blob = canonical_bytes(event)
        if key in by_id:
            if encoded[key] != blob:
                raise RailError(f"conflicting duplicate event_id: {key}")
            retry += 1
            continue
        by_id[key] = event
        encoded[key] = blob
    return sorted(by_id.values(), key=lambda x: (x["sequence"], x["event_id"])), retry


def _operation_semantics(event: Mapping[str, Any]) -> bytes:
    semantic = {k: v for k, v in event.items() if k not in {"event_id", "sequence"}}
    return canonical_bytes(semantic)


def _collapse_operations(events: Iterable[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], int]:
    operations: dict[str, dict[str, Any]] = {}
    semantics: dict[str, bytes] = {}
    retries = 0
    for event in events:
        if event["type"] not in {"booking", "money"}:
            continue
        op_id = event["operation_id"]
        sem = _operation_semantics(event)
        if op_id in operations:
            if semantics[op_id] != sem:
                raise RailError(f"conflicting duplicate operation_id: {op_id}")
            retries += 1
            continue
        operations[op_id] = event
        semantics[op_id] = sem
    return operations, retries


def reconcile(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise RailError("payload must be an object")
    allowed = {"review_owner_role", "events"}
    if set(payload) != allowed:
        raise RailError(f"payload schema mismatch missing={sorted(allowed-set(payload))} extra={sorted(set(payload)-allowed)}")
    reviewer = _text(payload["review_owner_role"], "review_owner_role")
    if not isinstance(payload["events"], list) or not payload["events"]:
        raise RailError("events must be a non-empty list")
    events, event_retries = _unique_events(payload["events"])

    promises: dict[str, dict[str, Any]] = {}
    journey_ids: set[str] = set()
    resources: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    handoffs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    recoveries: dict[str, list[dict[str, Any]]] = defaultdict(list)
    recovery_owner: dict[str, str] = {}
    resolutions: dict[str, dict[str, Any]] = {}
    resolution_ids: set[str] = set()

    for event in events:
        kind = event["type"]
        if kind == "promise":
            pid = event["promise_id"]
            if pid in promises:
                raise RailError(f"duplicate promise_id: {pid}")
            if event["journey_id"] in journey_ids:
                raise RailError(f"duplicate journey_id: {event['journey_id']}")
            promises[pid] = event
            journey_ids.add(event["journey_id"])
        elif kind == "resource":
            resources[(event["surface"], event["resource_id"])].append(event)
        elif kind == "handoff":
            handoffs[event["promise_id"]].append(event)
        elif kind == "recovery":
            rid = event["recovery_id"]
            owner = recovery_owner.setdefault(rid, event["promise_id"])
            if owner != event["promise_id"]:
                raise RailError(f"recovery_id {rid} crosses promises")
            recoveries[rid].append(event)
        elif kind == "resolution":
            rid = event["resolution_id"]
            if rid in resolution_ids:
                raise RailError(f"duplicate resolution_id: {rid}")
            resolution_ids.add(rid)
            op = event["operation_id"]
            if op in resolutions:
                raise RailError(f"multiple resolutions for operation_id: {op}")
            resolutions[op] = event

    operations, operation_retries = _collapse_operations(events)
    if not promises:
        raise RailError("at least one promise is required")

    for pid in set(handoffs) | set(recovery_owner.values()):
        if pid not in promises:
            raise RailError(f"event references unknown promise: {pid}")
    for event in operations.values():
        if event["promise_id"] not in promises:
            raise RailError(f"operation references unknown promise: {event['promise_id']}")

    final_outcome: dict[str, str] = {}
    for op_id, event in operations.items():
        outcome = event["outcome"]
        resolution = resolutions.get(op_id)
        if resolution is not None:
            if outcome != "UNKNOWN":
                raise RailError(f"resolution references non-UNKNOWN operation: {op_id}")
            if resolution["sequence"] <= event["sequence"]:
                raise RailError(f"resolution precedes operation: {op_id}")
            outcome = resolution["resolved_outcome"]
        final_outcome[op_id] = outcome
    for op_id in set(resolutions) - set(operations):
        raise RailError(f"resolution references unknown operation: {op_id}")

    holds: list[dict[str, Any]] = []
    unknown_effects: list[dict[str, str]] = []
    for op_id, outcome in sorted(final_outcome.items()):
        if outcome == "UNKNOWN":
            event = operations[op_id]
            unknown_effects.append({"operation_id": op_id, "promise_id": event["promise_id"], "type": event["type"]})
            holds.append({"reason": "UNKNOWN_EFFECT", "owner_role": reviewer, "promise_id": event["promise_id"], "operation_id": op_id})

    booking_ops = [e for e in operations.values() if e["type"] == "booking"]
    applied_booking = [e for e in booking_ops if final_outcome[e["operation_id"]] == "APPLIED"]
    applied_booking.sort(key=lambda x: (x["sequence"], x["operation_id"]))

    for event in applied_booking:
        if event["action"] != "RESERVE":
            continue
        key = (event["surface"], event["resource_id"])
        prior = [r for r in resources.get(key, []) if r["sequence"] <= event["sequence"]]
        if not prior:
            holds.append({"reason": "RESOURCE_STATE_UNKNOWN", "owner_role": reviewer, "promise_id": event["promise_id"], "operation_id": event["operation_id"], "resource": f"{key[0]}:{key[1]}"})
        else:
            state = max(prior, key=lambda r: (r["sequence"], r["event_id"]))["state"]
            if state != "AVAILABLE":
                holds.append({"reason": "BOOKING_ON_UNAVAILABLE_RESOURCE", "owner_role": reviewer, "promise_id": event["promise_id"], "operation_id": event["operation_id"], "resource": f"{key[0]}:{key[1]}", "resource_state": state})

    reservations: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for event in applied_booking:
        if event["action"] == "RESERVE":
            reservations[(event["surface"], event["resource_id"], event["slot_id"])].append(event)
    overbook_count = 0
    for key, rows in sorted(reservations.items()):
        promises_here = sorted({r["promise_id"] for r in rows})
        if len(promises_here) > 1:
            overbook_count += 1
            holds.append({"reason": "OVERBOOK_COLLISION", "owner_role": reviewer, "resource": f"{key[0]}:{key[1]}", "slot_id": key[2], "promise_ids": promises_here, "operation_ids": sorted(r["operation_id"] for r in rows)})

    observed_surfaces: dict[str, set[str]] = defaultdict(set)
    for event in booking_ops:
        observed_surfaces[event["promise_id"]].add(event["surface"])
    for pid, rows in handoffs.items():
        for row in rows:
            observed_surfaces[pid].add(row["to_surface"])
    for pid, promise in promises.items():
        for surface in promise["expected_surfaces"]:
            if surface not in observed_surfaces[pid]:
                holds.append({"reason": "EXPECTED_SURFACE_UNACCOUNTED", "owner_role": reviewer, "promise_id": pid, "surface": surface})

    money_ops = [e for e in operations.values() if e["type"] == "money"]
    applied_money = [e for e in money_ops if final_outcome[e["operation_id"]] == "APPLIED"]
    applied_money.sort(key=lambda x: (x["sequence"], x["operation_id"]))
    by_account: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    by_op = {e["operation_id"]: e for e in applied_money}
    reversals: dict[str, int] = defaultdict(int)
    balances: dict[tuple[str, str], int] = defaultdict(int)

    for event in applied_money:
        key = (event["account_type"], event["account_id"])
        by_account[key].append(event)
        kind = event["kind"]
        amount = event["amount_cents"]
        if event["account_type"] == "FOLIO":
            if kind in {"DEPOSIT", "CHARGE"}:
                balances[key] += amount
            else:
                related = by_op.get(event["related_operation_id"])
                if related is None or related["account_type"] != "FOLIO" or related["kind"] not in {"DEPOSIT", "CHARGE"}:
                    raise RailError(f"{event['operation_id']}: invalid reversal source")
                if related["account_id"] != event["account_id"] or related["promise_id"] != event["promise_id"]:
                    raise RailError(f"{event['operation_id']}: reversal crosses account/promise")
                reversals[related["operation_id"]] += amount
                if reversals[related["operation_id"]] > related["amount_cents"]:
                    raise RailError(f"{related['operation_id']}: reversals exceed source amount")
                balances[key] -= amount
        else:
            if kind == "LOAD":
                balances[key] += amount
            else:
                balances[key] -= amount
                if balances[key] < 0:
                    raise RailError(f"{event['account_id']}: redeem exceeds loaded balance")

    recovery_rows: list[dict[str, str]] = []
    for rid, rows in sorted(recoveries.items()):
        latest = max(rows, key=lambda r: (r["sequence"], r["event_id"]))
        recovery_rows.append({"recovery_id": rid, "promise_id": latest["promise_id"], "state": latest["state"], "reason_code": latest["reason_code"]})
        if latest["state"] != "RESOLVED":
            holds.append({"reason": "RECOVERY_NOT_RESOLVED", "owner_role": reviewer, "promise_id": latest["promise_id"], "recovery_id": rid, "state": latest["state"]})

    resource_rows = []
    for key, rows in sorted(resources.items()):
        latest = max(rows, key=lambda r: (r["sequence"], r["event_id"]))
        resource_rows.append({"surface": key[0], "resource_id": key[1], "state": latest["state"]})

    account_rows = []
    all_money_accounts: set[tuple[str, str]] = set()
    unknown_by_account: dict[tuple[str, str], list[str]] = defaultdict(list)
    for event in money_ops:
        key = (event["account_type"], event["account_id"])
        all_money_accounts.add(key)
        if final_outcome[event["operation_id"]] == "UNKNOWN":
            unknown_by_account[key].append(event["operation_id"])
    for key in sorted(all_money_accounts):
        account_rows.append({
            "account_type": key[0],
            "account_id": key[1],
            "balance_cents": balances[key],
            "unknown_operation_ids": sorted(unknown_by_account[key]),
        })

    promise_rows = []
    booking_by_promise: dict[str, list[str]] = defaultdict(list)
    money_by_promise: dict[str, list[str]] = defaultdict(list)
    for event in booking_ops:
        booking_by_promise[event["promise_id"]].append(event["operation_id"])
    for event in money_ops:
        money_by_promise[event["promise_id"]].append(event["operation_id"])
    for pid in sorted(promises):
        p = promises[pid]
        promise_rows.append({
            "promise_id": pid,
            "journey_id": p["journey_id"],
            "expected_surfaces": p["expected_surfaces"],
            "booking_operation_ids": sorted(set(booking_by_promise[pid])),
            "money_operation_ids": sorted(set(money_by_promise[pid])),
        })

    holds.sort(key=canonical_bytes)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "authority": {
            "set_rates": False,
            "allocate_rooms_or_tables": False,
            "initiate_or_reverse_money": False,
            "contact_guests": False,
            "approve_service_recovery": False,
        },
        "pii_policy": "guest_pii_forbidden",
        "journey_count": len(journey_ids),
        "promise_count": len(promises),
        "source_event_count": len(events),
        "event_retry_count": event_retries,
        "operation_retry_count": operation_retries,
        "booking_operation_count": len(booking_ops),
        "money_operation_count": len(money_ops),
        "unknown_effect_count": len(unknown_effects),
        "overbook_collision_count": overbook_count,
        "unknown_effects": unknown_effects,
        "review_holds": holds,
        "resources": resource_rows,
        "accounts": account_rows,
        "recoveries": recovery_rows,
        "promises": promise_rows,
    }
    manifest["manifest_sha256"] = hash_value(manifest)
    return manifest


def receipt_for(manifest: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(manifest, Mapping) or "manifest_sha256" not in manifest:
        raise RailError("manifest missing manifest_sha256")
    unsigned = dict(manifest)
    claimed = unsigned.pop("manifest_sha256")
    if claimed != hash_value(unsigned):
        raise RailError("manifest hash mismatch")
    receipt = {"schema_version": SCHEMA_VERSION, "manifest_sha256": claimed}
    receipt["receipt_sha256"] = hash_value(receipt)
    return receipt


def verify_receipt(manifest: Mapping[str, Any], receipt: Mapping[str, Any]) -> bool:
    return dict(receipt) == receipt_for(manifest)


def _load(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("input")
    build.add_argument("--manifest", required=True)
    build.add_argument("--receipt", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("manifest")
    verify.add_argument("receipt")
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            manifest = reconcile(_load(args.input))
            receipt = receipt_for(manifest)
            Path(args.manifest).write_bytes(canonical_bytes(manifest) + b"\n")
            Path(args.receipt).write_bytes(canonical_bytes(receipt) + b"\n")
            print(json.dumps({"ok": True, "journey_count": manifest["journey_count"], "unknown_effect_count": manifest["unknown_effect_count"], "manifest_sha256": manifest["manifest_sha256"]}, sort_keys=True))
            return 0
        manifest = _load(args.manifest)
        receipt = _load(args.receipt)
        ok = verify_receipt(manifest, receipt)
        print(json.dumps({"ok": ok}, sort_keys=True))
        return 0 if ok else 2
    except (OSError, json.JSONDecodeError, RailError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
