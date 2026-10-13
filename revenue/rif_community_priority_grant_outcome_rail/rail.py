#!/usr/bin/env python3
"""Deterministic post-award grant-to-outcome evidence reconciler.

This module is intentionally offline and authority-free.  It never selects awards,
initiates disbursements, scores outcomes, or certifies compliance.  It only
reconciles synthetic/approved post-award records into a canonical evidence
manifest and a content-addressed receipt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "rif-community-priority-grant-outcome-rail/v1"
EVENT_TYPES = {"award", "amendment", "disbursement", "milestone", "evidence", "return"}
PROGRAMS = {"COMMUNITY_PRIORITY", "CAPACITY_BUILDING"}
PRIORITIES = {"ECONOMIC_SECURITY", "EDUCATION", "HEALTH", "HOUSING", "CIVIC_VITALITY"}
MILESTONE_STATES = {"pending", "satisfied", "waived"}
HEX64 = re.compile(r"^[0-9a-f]{64}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PII_KEYS = {
    "beneficiary_name", "beneficiary_email", "beneficiary_phone", "beneficiary_address",
    "beneficiary_dob", "beneficiary_date_of_birth", "beneficiary_ssn",
    "email", "phone", "address", "ssn", "date_of_birth", "dob",
}
COMMON = {"event_id", "type"}
FIELDS = {
    "award": COMMON | {"award_id", "program", "priority", "fund", "grantee_id", "authorized_cents", "restrictions"},
    "amendment": COMMON | {"award_id", "version", "authorized_cents", "restrictions", "reason_code"},
    "disbursement": COMMON | {"award_id", "disbursement_id", "amount_cents", "restriction_version"},
    "milestone": COMMON | {"award_id", "milestone_id", "due_date", "status", "evidence_required"},
    "evidence": COMMON | {"award_id", "milestone_id", "evidence_id", "evidence_hash", "observed_on", "definition_version"},
    "return": COMMON | {"award_id", "disbursement_id", "return_id", "amount_cents", "reason_code"},
}

class RailError(ValueError):
    """Fail-closed validation error."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _expect_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise RailError(f"{label} must be a non-empty trimmed string")
    return value


def _expect_cents(value: Any, label: str, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RailError(f"{label} must be integer cents")
    floor = 1 if positive else 0
    if value < floor:
        raise RailError(f"{label} must be >= {floor}")
    return value


def _expect_date(value: Any, label: str) -> str:
    value = _expect_text(value, label)
    if not DATE.fullmatch(value):
        raise RailError(f"{label} must be YYYY-MM-DD")
    return value


def _expect_restrictions(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise RailError(f"{label} must be a non-empty string list")
    out = [_expect_text(item, label) for item in value]
    if len(out) != len(set(out)):
        raise RailError(f"{label} contains duplicates")
    return sorted(out)


def _reject_pii(value: Any, path: str = "event") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise RailError(f"{path} contains non-string key")
            if key.lower() in PII_KEYS or key.lower().startswith("beneficiary_"):
                raise RailError(f"PII field forbidden: {path}.{key}")
            _reject_pii(child, f"{path}.{key}")
    elif isinstance(value, list):
        for i, child in enumerate(value):
            _reject_pii(child, f"{path}[{i}]")


def _normalize_event(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise RailError("each event must be an object")
    _reject_pii(raw)
    event = dict(raw)
    event_id = _expect_text(event.get("event_id"), "event_id")
    kind = _expect_text(event.get("type"), "type")
    if kind not in EVENT_TYPES:
        raise RailError(f"unknown event type: {kind}")
    extras = set(event) - FIELDS[kind]
    missing = FIELDS[kind] - set(event)
    if extras or missing:
        raise RailError(f"{event_id}: schema mismatch missing={sorted(missing)} extra={sorted(extras)}")

    _expect_text(event.get("award_id"), f"{event_id}.award_id")
    if kind == "award":
        if event["program"] not in PROGRAMS:
            raise RailError(f"{event_id}: unknown program")
        if event["priority"] not in PRIORITIES:
            raise RailError(f"{event_id}: unknown priority")
        _expect_text(event["fund"], f"{event_id}.fund")
        _expect_text(event["grantee_id"], f"{event_id}.grantee_id")
        _expect_cents(event["authorized_cents"], f"{event_id}.authorized_cents", positive=True)
        event["restrictions"] = _expect_restrictions(event["restrictions"], f"{event_id}.restrictions")
    elif kind == "amendment":
        if isinstance(event["version"], bool) or not isinstance(event["version"], int) or event["version"] < 1:
            raise RailError(f"{event_id}.version must be positive integer")
        _expect_cents(event["authorized_cents"], f"{event_id}.authorized_cents", positive=True)
        event["restrictions"] = _expect_restrictions(event["restrictions"], f"{event_id}.restrictions")
        _expect_text(event["reason_code"], f"{event_id}.reason_code")
    elif kind == "disbursement":
        _expect_text(event["disbursement_id"], f"{event_id}.disbursement_id")
        _expect_cents(event["amount_cents"], f"{event_id}.amount_cents", positive=True)
        if isinstance(event["restriction_version"], bool) or not isinstance(event["restriction_version"], int) or event["restriction_version"] < 0:
            raise RailError(f"{event_id}.restriction_version must be non-negative integer")
    elif kind == "milestone":
        _expect_text(event["milestone_id"], f"{event_id}.milestone_id")
        _expect_date(event["due_date"], f"{event_id}.due_date")
        if event["status"] not in MILESTONE_STATES:
            raise RailError(f"{event_id}: unknown milestone status")
        if not isinstance(event["evidence_required"], bool):
            raise RailError(f"{event_id}.evidence_required must be boolean")
    elif kind == "evidence":
        _expect_text(event["milestone_id"], f"{event_id}.milestone_id")
        _expect_text(event["evidence_id"], f"{event_id}.evidence_id")
        digest = _expect_text(event["evidence_hash"], f"{event_id}.evidence_hash")
        if not HEX64.fullmatch(digest):
            raise RailError(f"{event_id}.evidence_hash must be lowercase SHA-256")
        _expect_date(event["observed_on"], f"{event_id}.observed_on")
        if isinstance(event["definition_version"], bool) or not isinstance(event["definition_version"], int) or event["definition_version"] < 1:
            raise RailError(f"{event_id}.definition_version must be positive integer")
    elif kind == "return":
        _expect_text(event["disbursement_id"], f"{event_id}.disbursement_id")
        _expect_text(event["return_id"], f"{event_id}.return_id")
        _expect_cents(event["amount_cents"], f"{event_id}.amount_cents", positive=True)
        _expect_text(event["reason_code"], f"{event_id}.reason_code")
    return event


def _unique_events(raw_events: Iterable[Any]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    encoded: dict[str, bytes] = {}
    for raw in raw_events:
        event = _normalize_event(raw)
        event_id = event["event_id"]
        blob = _canonical_bytes(event)
        if event_id in by_id:
            if encoded[event_id] != blob:
                raise RailError(f"conflicting duplicate event_id: {event_id}")
            continue
        by_id[event_id] = event
        encoded[event_id] = blob
    return [by_id[key] for key in sorted(by_id)]


def reconcile(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return an order-invariant canonical manifest or fail closed."""
    if not isinstance(payload, Mapping):
        raise RailError("payload must be an object")
    allowed = {"as_of_date", "review_owner_role", "events"}
    if set(payload) != allowed:
        raise RailError(f"payload schema mismatch missing={sorted(allowed-set(payload))} extra={sorted(set(payload)-allowed)}")
    as_of = _expect_date(payload["as_of_date"], "as_of_date")
    reviewer = _expect_text(payload["review_owner_role"], "review_owner_role")
    if not isinstance(payload["events"], list) or not payload["events"]:
        raise RailError("events must be a non-empty list")
    events = _unique_events(payload["events"])

    awards: dict[str, dict[str, Any]] = {}
    amendments: dict[str, list[dict[str, Any]]] = defaultdict(list)
    disbursements: dict[str, dict[str, Any]] = {}
    milestones: dict[str, dict[str, Any]] = {}
    evidence: dict[str, dict[str, Any]] = {}
    returns: dict[str, dict[str, Any]] = {}

    for event in events:
        kind = event["type"]
        if kind == "award":
            award_id = event["award_id"]
            if award_id in awards:
                raise RailError(f"duplicate award_id: {award_id}")
            awards[award_id] = event
        elif kind == "amendment":
            amendments[event["award_id"]].append(event)
        elif kind == "disbursement":
            key = event["disbursement_id"]
            if key in disbursements:
                raise RailError(f"duplicate disbursement_id: {key}")
            disbursements[key] = event
        elif kind == "milestone":
            key = event["milestone_id"]
            if key in milestones:
                raise RailError(f"duplicate milestone_id: {key}")
            milestones[key] = event
        elif kind == "evidence":
            key = event["evidence_id"]
            if key in evidence:
                raise RailError(f"duplicate evidence_id: {key}")
            evidence[key] = event
        elif kind == "return":
            key = event["return_id"]
            if key in returns:
                raise RailError(f"duplicate return_id: {key}")
            returns[key] = event

    if not awards:
        raise RailError("at least one award is required")

    versions: dict[str, dict[int, dict[str, Any]]] = {}
    final_auth: dict[str, int] = {}
    for award_id, award in awards.items():
        rows = sorted(amendments.get(award_id, []), key=lambda row: (row["version"], row["event_id"]))
        expected = list(range(1, len(rows) + 1))
        actual = [row["version"] for row in rows]
        if actual != expected:
            raise RailError(f"{award_id}: amendment versions must be contiguous from 1")
        version_map = {0: {"version": 0, "authorized_cents": award["authorized_cents"], "restrictions": award["restrictions"]}}
        for row in rows:
            version_map[row["version"]] = row
        versions[award_id] = version_map
        final_auth[award_id] = version_map[max(version_map)]["authorized_cents"]

    for foreign in set(amendments) - set(awards):
        raise RailError(f"amendment references unknown award: {foreign}")

    disbursed_by_award: dict[str, int] = defaultdict(int)
    for row in disbursements.values():
        award_id = row["award_id"]
        if award_id not in awards:
            raise RailError(f"disbursement references unknown award: {award_id}")
        if row["restriction_version"] not in versions[award_id]:
            raise RailError(f"{row['disbursement_id']}: unknown restriction_version")
        disbursed_by_award[award_id] += row["amount_cents"]
    for award_id, amount in disbursed_by_award.items():
        if amount > final_auth[award_id]:
            raise RailError(f"{award_id}: disbursements exceed final authorized amount")

    returned_by_disb: dict[str, int] = defaultdict(int)
    returned_by_award: dict[str, int] = defaultdict(int)
    for row in returns.values():
        disb = disbursements.get(row["disbursement_id"])
        if disb is None:
            raise RailError(f"return references unknown disbursement: {row['disbursement_id']}")
        if row["award_id"] != disb["award_id"]:
            raise RailError(f"{row['return_id']}: award/disbursement mismatch")
        returned_by_disb[row["disbursement_id"]] += row["amount_cents"]
        returned_by_award[row["award_id"]] += row["amount_cents"]
    for disb_id, amount in returned_by_disb.items():
        if amount > disbursements[disb_id]["amount_cents"]:
            raise RailError(f"{disb_id}: returns exceed disbursement")

    for row in milestones.values():
        if row["award_id"] not in awards:
            raise RailError(f"milestone references unknown award: {row['award_id']}")
    evidence_by_milestone: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in evidence.values():
        milestone = milestones.get(row["milestone_id"])
        if milestone is None:
            raise RailError(f"evidence references unknown milestone: {row['milestone_id']}")
        if row["award_id"] != milestone["award_id"]:
            raise RailError(f"{row['evidence_id']}: award/milestone mismatch")
        evidence_by_milestone[row["milestone_id"]].append(row)

    holds: list[dict[str, str]] = []
    for milestone_id, row in sorted(milestones.items()):
        linked = evidence_by_milestone.get(milestone_id, [])
        reason = None
        if row["status"] == "satisfied" and row["evidence_required"] and not linked:
            reason = "SATISFIED_WITHOUT_REQUIRED_EVIDENCE"
        elif row["status"] == "pending" and row["due_date"] < as_of:
            reason = "PAST_DUE_MILESTONE"
        elif row["status"] == "waived" and linked:
            reason = "WAIVED_MILESTONE_HAS_EVIDENCE"
        if reason:
            holds.append({"award_id": row["award_id"], "milestone_id": milestone_id, "owner_role": reviewer, "reason": reason})

    grouped: dict[str, dict[str, int]] = {
        "program": defaultdict(int), "priority": defaultdict(int), "fund": defaultdict(int), "grantee": defaultdict(int)
    }
    award_rows: list[dict[str, Any]] = []
    for award_id in sorted(awards):
        award = awards[award_id]
        net = disbursed_by_award[award_id] - returned_by_award[award_id]
        if net < 0:
            raise RailError(f"{award_id}: net disbursed is negative")
        for dimension, key in (("program", award["program"]), ("priority", award["priority"]), ("fund", award["fund"]), ("grantee", award["grantee_id"])):
            grouped[dimension][key] += net
        history = [{"version": 0, "authorized_cents": award["authorized_cents"], "restrictions": award["restrictions"]}]
        for version in sorted(v for v in versions[award_id] if v):
            row = versions[award_id][version]
            history.append({"version": version, "authorized_cents": row["authorized_cents"], "restrictions": row["restrictions"], "reason_code": row["reason_code"]})
        award_rows.append({
            "award_id": award_id,
            "program": award["program"],
            "priority": award["priority"],
            "fund": award["fund"],
            "grantee_id": award["grantee_id"],
            "authorization_history": history,
            "final_authorized_cents": final_auth[award_id],
            "disbursed_cents": disbursed_by_award[award_id],
            "returned_cents": returned_by_award[award_id],
            "net_disbursed_cents": net,
            "milestone_ids": sorted(key for key, row in milestones.items() if row["award_id"] == award_id),
        })

    net_total = sum(row["net_disbursed_cents"] for row in award_rows)
    totals = {dimension: dict(sorted(values.items())) for dimension, values in grouped.items()}
    for dimension, values in totals.items():
        if sum(values.values()) != net_total:
            raise RailError(f"internal reconciliation failure for {dimension}")

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "as_of_date": as_of,
        "authority": {"select_awards": False, "initiate_payments": False, "score_impact": False, "certify_compliance": False},
        "pii_policy": "beneficiary_pii_forbidden",
        "source_event_count": len(events),
        "award_count": len(awards),
        "net_disbursed_cents": net_total,
        "totals": totals,
        "review_holds": holds,
        "awards": award_rows,
        "evidence_index": [
            {"evidence_id": key, "award_id": row["award_id"], "milestone_id": row["milestone_id"], "evidence_hash": row["evidence_hash"], "definition_version": row["definition_version"]}
            for key, row in sorted(evidence.items())
        ],
    }
    manifest["manifest_sha256"] = _hash(manifest)
    return manifest


def receipt_for(manifest: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(manifest, Mapping) or "manifest_sha256" not in manifest:
        raise RailError("manifest missing manifest_sha256")
    unsigned = dict(manifest)
    claimed = unsigned.pop("manifest_sha256")
    actual = _hash(unsigned)
    if claimed != actual:
        raise RailError("manifest hash mismatch")
    return {"schema_version": SCHEMA_VERSION, "manifest_sha256": claimed, "receipt_sha256": _hash({"schema_version": SCHEMA_VERSION, "manifest_sha256": claimed})}


def verify_receipt(manifest: Mapping[str, Any], receipt: Mapping[str, Any]) -> bool:
    expected = receipt_for(manifest)
    return dict(receipt) == expected


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
            Path(args.manifest).write_bytes(_canonical_bytes(manifest) + b"\n")
            Path(args.receipt).write_bytes(_canonical_bytes(receipt) + b"\n")
            print(json.dumps({"ok": True, "manifest_sha256": manifest["manifest_sha256"], "review_hold_count": len(manifest["review_holds"])}, sort_keys=True))
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
