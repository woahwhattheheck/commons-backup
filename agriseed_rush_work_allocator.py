#!/usr/bin/env python3
"""Agri Seed rush-aware work allocator LIMS.

Demand: agriseed-rush-work-allocator-lims-01
Buyer: Agri Seed Testing / Sharon Davidson
Slack OPEN: #build-demand 1788150743.201099

Working runner: structured AOSA / Canadian / ISTA intake, two-site routing,
analyst qualification and workload allocation, rush-impact visibility,
controlled reports. Replay 300 frozen synthetic submissions — 240 valid and
60 with predefined missing billing data, duplicate bag barcodes, invalid
rule/certificate combinations, lot-size errors, or unauthorized ISTA
samplers.

PASS only when all 240 valid cases accession exactly once with the expected
method revision and qualified-role assignment; all 60 exceptions receive the
truth-set HOLD code; rush never shortens regulated biological duration;
report fields and digests match the manifest; reviewer sign-off is mandatory;
replay adds nothing.

Adapters stay synthetic and read-only / simulated. HOLD / BUILD-AND-VERIFY.
No outreach. PRE-SALE TRANSPORT: NONE. cash_usd=0.

Official command:
    python3 agriseed_rush_work_allocator.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

DEMAND_ID = "agriseed-rush-work-allocator-lims-01"
SCHEMA = "commons-agriseed-rush-work-allocator-lims/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
BUYER = "Agri Seed Testing / Sharon Davidson"
HUMAN_APPROVER = "SYN-AST-REVIEWER"
HUMAN_ROLE = "NAMED_HUMAN_REVIEWER"
OPEN_SLACK_TS = "1788150743.201099"
OPEN_SLACK_CHANNEL = "C0BTRNE6Y58"
COMMAND = "python3 agriseed_rush_work_allocator.py"
TEST_COMMAND = "python3 test_agriseed_rush_work_allocator.py"
SEED = "agriseed-rush-work-allocator-20260831"

VALID_COUNT = 240
HOLD_COUNT = 60
INPUT_COUNT = VALID_COUNT + HOLD_COUNT
HOLD_PER_FAMILY = 12
RUSH_SHORTEN_ATTEMPT_HOURS = 24

HOLD_CODES = (
    "MISSING_BILLING",
    "DUPLICATE_BAG_BARCODE",
    "INVALID_RULE_CERTIFICATE",
    "LOT_SIZE_ERROR",
    "UNAUTHORIZED_ISTA_SAMPLER",
)

SITE_A = "AST_BOISE"
SITE_B = "AST_NAMPA"
SITES = (SITE_A, SITE_B)

METHOD_CATALOG: dict[str, dict[str, Any]] = {
    "AOSA_GERM_V2024_03": {
        "framework": "AOSA",
        "revision": "2024.03",
        "biological_hours": 168,
        "role": "AOSA_ANALYST",
        "site": SITE_A,
        "certificate": "AOSA_LAB_CERT_2024",
        "requires_authorized_sampler": False,
    },
    "AOSA_PURITY_V2024_01": {
        "framework": "AOSA",
        "revision": "2024.01",
        "biological_hours": 72,
        "role": "AOSA_ANALYST",
        "site": SITE_A,
        "certificate": "AOSA_LAB_CERT_2024",
        "requires_authorized_sampler": False,
    },
    "CAN_GERM_V2023_11": {
        "framework": "CANADIAN",
        "revision": "2023.11",
        "biological_hours": 144,
        "role": "CANADIAN_ANALYST",
        "site": SITE_B,
        "certificate": "CFIA_SEED_LAB_2023",
        "requires_authorized_sampler": False,
    },
    "CAN_PURITY_V2023_08": {
        "framework": "CANADIAN",
        "revision": "2023.08",
        "biological_hours": 48,
        "role": "CANADIAN_ANALYST",
        "site": SITE_B,
        "certificate": "CFIA_SEED_LAB_2023",
        "requires_authorized_sampler": False,
    },
    "ISTA_GERM_V2025_01": {
        "framework": "ISTA",
        "revision": "2025.01",
        "biological_hours": 240,
        "role": "ISTA_ANALYST",
        "site": SITE_A,
        "certificate": "ISTA_ACC_ID_2025",
        "requires_authorized_sampler": True,
    },
    "ISTA_PURITY_V2025_01": {
        "framework": "ISTA",
        "revision": "2025.01",
        "biological_hours": 96,
        "role": "ISTA_ANALYST",
        "site": SITE_B,
        "certificate": "ISTA_ACC_ID_2025",
        "requires_authorized_sampler": True,
    },
}
METHODS = tuple(METHOD_CATALOG.keys())

ANALYSTS: dict[str, dict[str, Any]] = {
    "SYN-AOSA-01": {"roles": ("AOSA_ANALYST",), "site": SITE_A, "capacity": 50},
    "SYN-AOSA-02": {"roles": ("AOSA_ANALYST",), "site": SITE_A, "capacity": 50},
    "SYN-CAN-01": {"roles": ("CANADIAN_ANALYST",), "site": SITE_B, "capacity": 50},
    "SYN-CAN-02": {"roles": ("CANADIAN_ANALYST",), "site": SITE_B, "capacity": 50},
    "SYN-ISTA-01": {"roles": ("ISTA_ANALYST",), "site": SITE_A, "capacity": 40},
    "SYN-ISTA-02": {"roles": ("ISTA_ANALYST",), "site": SITE_B, "capacity": 40},
}

AUTHORIZED_ISTA_SAMPLERS = frozenset(
    {
        "ISTA-SAMPLER-001",
        "ISTA-SAMPLER-002",
        "ISTA-SAMPLER-003",
        "ISTA-SAMPLER-004",
    }
)

EPOCH = datetime(2026, 8, 15, 14, 0, 0, tzinfo=timezone.utc)

EXPECTED_COUNTS = {
    "input_rows": INPUT_COUNT,
    "accessioned": VALID_COUNT,
    "held": HOLD_COUNT,
    "hold_missing_billing": HOLD_PER_FAMILY,
    "hold_duplicate_bag_barcode": HOLD_PER_FAMILY,
    "hold_invalid_rule_certificate": HOLD_PER_FAMILY,
    "hold_lot_size_error": HOLD_PER_FAMILY,
    "hold_unauthorized_ista_sampler": HOLD_PER_FAMILY,
    "rush_never_shortened": VALID_COUNT,
    "duplicates": 0,
    "replay_added_accessions": 0,
    "released_without_named_human": 0,
    "released_after_named_human": VALID_COUNT,
    "held_released": 0,
    "production_writes": 0,
}

GOLDEN_FIXTURE_SHA256 = "f9f8c49394b5826f1979f80a67a1bc970774aeee91063f1cd76638ef5d729d30"
GOLDEN_CATALOG_SHA256 = "cd34c32e66b206f259ceb8d489cfa94473449bcb0e2143526807262ced51d9fe"
GOLDEN_MANIFEST_SHA256 = "ea131085cfeb938d2b694c34543e8000ca7b2ae55a89bc19a1479e4b4dac3066"
GOLDEN_AUDIT_SHA256 = "329242123ee0512cae064a14905f0a97d5f72f8dee9759732cf94c110932c3a1"


def _text(value: Any) -> str:
    return str("" if value is None else value).strip()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def iso(moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


CATALOG_SHA256 = sha256_hex(
    {
        "methods": METHOD_CATALOG,
        "analysts": ANALYSTS,
        "authorized_ista_samplers": sorted(AUTHORIZED_ISTA_SAMPLERS),
        "sites": list(SITES),
    }
)


def _method_for(index: int) -> str:
    return METHODS[(index - 1) % len(METHODS)]


def _analyst_for(role: str, site: str, slot: int) -> str:
    pool = [
        name
        for name, spec in ANALYSTS.items()
        if role in spec["roles"] and spec["site"] == site
    ]
    if not pool:
        raise RuntimeError(f"no analyst for role={role!r} site={site!r}")
    return pool[slot % len(pool)]


def _bag_barcode(index: int) -> str:
    return f"BAG-{index:04d}"


def _lot_size(framework: str, index: int) -> int:
    if framework == "AOSA":
        return 400 + (index % 50)
    if framework == "CANADIAN":
        return 300 + (index % 40)
    return 1000 + (index % 100)


def _source_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "submission_id": row["submission_id"],
        "bag_barcode": row["bag_barcode"],
        "method": row["method"],
        "framework": row["framework"],
        "method_revision": row["method_revision"],
        "site": row["site"],
        "role": row["role"],
        "lot_size": row["lot_size"],
        "billing_account": row["billing_account"],
        "certificate": row["certificate"],
        "sampler_id": row["sampler_id"],
        "rush": row["rush"],
        "regulated_biological_hours": row["regulated_biological_hours"],
        "reported_duration_hours": row["reported_duration_hours"],
        "received_at": row["received_at"],
        "due_at": row["due_at"],
    }


def _base_row(
    index: int,
    *,
    submission_id: str,
    method: str,
    bag_barcode: str,
    lot_size: int,
    billing_account: str,
    certificate: str,
    sampler_id: str,
    rush: bool,
    expected_state: str,
    expected_reason: str | None,
) -> dict[str, Any]:
    spec = METHOD_CATALOG[method]
    received = EPOCH + timedelta(minutes=index)
    regulated_hours = int(spec["biological_hours"])
    due = received + timedelta(hours=regulated_hours)
    analyst = _analyst_for(spec["role"], spec["site"], index)
    return {
        "index": index,
        "submission_id": submission_id,
        "bag_barcode": bag_barcode,
        "method": method,
        "framework": spec["framework"],
        "method_revision": spec["revision"],
        "site": spec["site"],
        "role": spec["role"],
        "analyst_id": analyst,
        "lot_size": lot_size,
        "billing_account": billing_account,
        "certificate": certificate,
        "sampler_id": sampler_id,
        "rush": rush,
        "regulated_biological_hours": regulated_hours,
        "reported_duration_hours": regulated_hours,
        "received_at": iso(received),
        "due_at": iso(due),
        "expected_state": expected_state,
        "expected_reason": expected_reason,
        "source_sha256": "",
    }


def build_acceptance_fixture() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for i in range(1, VALID_COUNT + 1):
        method = _method_for(i)
        spec = METHOD_CATALOG[method]
        sampler = (
            sorted(AUTHORIZED_ISTA_SAMPLERS)[(i - 1) % len(AUTHORIZED_ISTA_SAMPLERS)]
            if spec["requires_authorized_sampler"]
            else f"INTERNAL-SAMPLER-{(i % 20) + 1:02d}"
        )
        row = _base_row(
            i,
            submission_id=f"AST-SUB-{i:04d}",
            method=method,
            bag_barcode=_bag_barcode(i),
            lot_size=_lot_size(spec["framework"], i),
            billing_account=f"BILL-AST-{(i % 40) + 1:03d}",
            certificate=spec["certificate"],
            sampler_id=sampler,
            rush=(i % 5 == 0),
            expected_state="ACCESSIONED",
            expected_reason=None,
        )
        row["source_sha256"] = sha256_hex(_source_payload(row))
        rows.append(row)

    hold_start = VALID_COUNT + 1
    for family_idx, code in enumerate(HOLD_CODES):
        for j in range(HOLD_PER_FAMILY):
            index = hold_start + family_idx * HOLD_PER_FAMILY + j
            method = _method_for(index)
            spec = METHOD_CATALOG[method]
            bag = _bag_barcode(index)
            lot = _lot_size(spec["framework"], index)
            billing = f"BILL-AST-{(index % 40) + 1:03d}"
            certificate = spec["certificate"]
            sampler = (
                sorted(AUTHORIZED_ISTA_SAMPLERS)[j % len(AUTHORIZED_ISTA_SAMPLERS)]
                if spec["requires_authorized_sampler"]
                else f"INTERNAL-SAMPLER-{(index % 20) + 1:02d}"
            )

            if code == "UNAUTHORIZED_ISTA_SAMPLER":
                method = "ISTA_GERM_V2025_01" if j % 2 == 0 else "ISTA_PURITY_V2025_01"
                spec = METHOD_CATALOG[method]
                certificate = spec["certificate"]
                sampler = f"UNAUTHORIZED-SAMPLER-{j + 1:02d}"
            elif code == "MISSING_BILLING":
                billing = ""
            elif code == "DUPLICATE_BAG_BARCODE":
                bag = _bag_barcode(j + 1)
            elif code == "INVALID_RULE_CERTIFICATE":
                certificate = "WRONG_CERT_NOT_ON_FILE"
            elif code == "LOT_SIZE_ERROR":
                lot = 0 if j % 2 == 0 else -5

            row = _base_row(
                index,
                submission_id=f"AST-SUB-{index:04d}",
                method=method,
                bag_barcode=bag,
                lot_size=lot,
                billing_account=billing,
                certificate=certificate,
                sampler_id=sampler,
                rush=(index % 3 == 0),
                expected_state="HELD",
                expected_reason=code,
            )
            row["source_sha256"] = sha256_hex(_source_payload(row))
            rows.append(row)

    assert len(rows) == INPUT_COUNT
    assert sum(1 for r in rows if r["expected_state"] == "ACCESSIONED") == VALID_COUNT
    assert sum(1 for r in rows if r["expected_state"] == "HELD") == HOLD_COUNT
    return rows


def fixture_manifest(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = rows if rows is not None else build_acceptance_fixture()
    body = {
        "demand_id": DEMAND_ID,
        "seed": SEED,
        "input_count": len(rows),
        "valid_count": sum(1 for r in rows if r["expected_state"] == "ACCESSIONED"),
        "hold_count": sum(1 for r in rows if r["expected_state"] == "HELD"),
        "hold_family_counts": {
            code: sum(1 for r in rows if r.get("expected_reason") == code)
            for code in HOLD_CODES
        },
        "submission_ids": [r["submission_id"] for r in rows],
        "source_sha256s": [r["source_sha256"] for r in rows],
    }
    return {
        "manifest": body,
        "fixture_sha256": sha256_hex(body),
        "catalog_sha256": CATALOG_SHA256,
    }


def _hold_record(row: dict[str, Any], reason: str) -> dict[str, Any]:
    record = {
        "submission_id": row["submission_id"],
        "bag_barcode": row.get("bag_barcode"),
        "method": row.get("method"),
        "reason": reason,
        "state": "HELD",
        "released": False,
        "released_by": None,
        "rush": bool(row.get("rush")),
        "source_sha256": row.get("source_sha256"),
    }
    record["hold_sha256"] = sha256_hex(record)
    return record


def _bound_submission_replay(
    row: dict[str, Any],
    seen_submissions: dict[str, str],
) -> dict[str, Any] | None:
    """Resolve an already-bound submission before any first-seen HOLD path."""
    submission_id = _text(row.get("submission_id"))
    previous_source_sha256 = seen_submissions.get(submission_id)
    if previous_source_sha256 is None:
        return None

    method = _text(row.get("method"))
    if method not in METHOD_CATALOG:
        raise ValueError("SUBMISSION_ID_PAYLOAD_MISMATCH")

    spec = METHOD_CATALOG[method]
    try:
        regulated = int(spec["biological_hours"])
        reported = int(row.get("reported_duration_hours") or 0)
        if reported < regulated:
            reported = regulated
        if bool(row.get("rush")) and int(row.get("rush_shorten_hours") or 0):
            reported = regulated
        source_row = dict(row)
        source_row["reported_duration_hours"] = reported
        source_sha256 = sha256_hex(_source_payload(source_row))
    except (KeyError, TypeError, ValueError):
        raise ValueError("SUBMISSION_ID_PAYLOAD_MISMATCH") from None

    if previous_source_sha256 != source_sha256:
        raise ValueError("SUBMISSION_ID_PAYLOAD_MISMATCH")
    return {
        "submission_id": row["submission_id"],
        "bag_barcode": row.get("bag_barcode"),
        "method": row.get("method"),
        "state": "IDEMPOTENT_REPLAY",
        "released": False,
        "released_by": None,
        "rush": bool(row.get("rush")),
        "source_sha256": source_sha256,
    }


def evaluate_row(
    row: dict[str, Any],
    seen_bags: set[str],
    seen_submissions: dict[str, str],
) -> dict[str, Any]:
    bound_replay = _bound_submission_replay(row, seen_submissions)
    if bound_replay is not None:
        return bound_replay

    method = _text(row.get("method"))
    if method not in METHOD_CATALOG:
        return _hold_record(row, "INVALID_RULE_CERTIFICATE")

    spec = METHOD_CATALOG[method]
    if not _text(row.get("billing_account")):
        return _hold_record(row, "MISSING_BILLING")

    bag = _text(row.get("bag_barcode"))
    if not bag or bag in seen_bags:
        return _hold_record(row, "DUPLICATE_BAG_BARCODE")

    if _text(row.get("certificate")) != spec["certificate"]:
        return _hold_record(row, "INVALID_RULE_CERTIFICATE")

    lot = int(row.get("lot_size") or 0)
    if lot <= 0:
        return _hold_record(row, "LOT_SIZE_ERROR")

    if spec["requires_authorized_sampler"] and _text(row.get("sampler_id")) not in AUTHORIZED_ISTA_SAMPLERS:
        return _hold_record(row, "UNAUTHORIZED_ISTA_SAMPLER")

    # Preserve the preimage order exactly for first-seen rows: regulated
    # duration parsing/normalization precedes analyst/site validation.
    regulated = int(spec["biological_hours"])
    reported = int(row.get("reported_duration_hours") or 0)
    if reported < regulated:
        reported = regulated
    if bool(row.get("rush")) and int(row.get("rush_shorten_hours") or 0):
        reported = regulated

    analyst = _text(row.get("analyst_id")) or _analyst_for(spec["role"], spec["site"], int(row["index"]))
    if analyst not in ANALYSTS or spec["role"] not in ANALYSTS[analyst]["roles"]:
        return _hold_record(row, "INVALID_RULE_CERTIFICATE")
    if ANALYSTS[analyst]["site"] != spec["site"]:
        return _hold_record(row, "INVALID_RULE_CERTIFICATE")

    source_row = dict(row)
    source_row["reported_duration_hours"] = reported
    source_sha256 = sha256_hex(_source_payload(source_row))
    submission_id = _text(row.get("submission_id"))

    # Construct and hash the complete accession before committing either
    # identity set. Any exception below this point must leave replay/bag state
    # unchanged so only a successfully returned accession becomes bound.
    accession_id = f"AST-ACC-{int(row['index']):04d}"
    report = {
        "accession_id": accession_id,
        "submission_id": row["submission_id"],
        "bag_barcode": bag,
        "method": method,
        "method_revision": spec["revision"],
        "framework": spec["framework"],
        "site": spec["site"],
        "role": spec["role"],
        "analyst_id": analyst,
        "lot_size": lot,
        "billing_account": row["billing_account"],
        "certificate": row["certificate"],
        "sampler_id": row["sampler_id"],
        "rush": bool(row.get("rush")),
        "regulated_biological_hours": regulated,
        "reported_duration_hours": reported,
        "rush_shortened": False,
        "received_at": row["received_at"],
        "due_at": row["due_at"],
        "state": "ACCESSIONED",
        "released": False,
        "released_by": None,
        "source_sha256": source_sha256,
    }
    report["report_sha256"] = sha256_hex(
        {k: v for k, v in report.items() if k != "report_sha256"}
    )

    seen_submissions[submission_id] = source_sha256
    seen_bags.add(bag)
    return report


def run_gate(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = deepcopy(rows) if rows is not None else build_acceptance_fixture()
    seen_bags: set[str] = set()
    seen_submissions: dict[str, str] = {}
    accessions: list[dict[str, Any]] = []
    holds: list[dict[str, Any]] = []
    duplicates = 0

    for row in rows:
        working = dict(row)
        if working.get("rush") and working.get("expected_state") == "ACCESSIONED":
            working["rush_shorten_hours"] = RUSH_SHORTEN_ATTEMPT_HOURS
            working["reported_duration_hours"] = max(
                1, int(working["regulated_biological_hours"]) - RUSH_SHORTEN_ATTEMPT_HOURS
            )
        outcome = evaluate_row(working, seen_bags, seen_submissions)
        if outcome["state"] == "ACCESSIONED":
            accessions.append(outcome)
        elif outcome["state"] == "IDEMPOTENT_REPLAY":
            duplicates += 1
        else:
            holds.append(outcome)

    # Replay must add zero new accessions.
    replay_seen = set(seen_bags)
    replay_submissions = dict(seen_submissions)
    replay_added = 0
    first_pass_bags = set(seen_bags)
    for row in rows:
        before = set(replay_seen)
        outcome = evaluate_row(dict(row), replay_seen, replay_submissions)
        if outcome["state"] == "ACCESSIONED":
            new_bags = replay_seen - before
            if new_bags - first_pass_bags:
                replay_added += 1

    released: list[dict[str, Any]] = []
    for acc in accessions:
        item = dict(acc)
        item["released"] = True
        item["released_by"] = HUMAN_APPROVER
        item["released_role"] = HUMAN_ROLE
        item["released_at"] = iso(EPOCH + timedelta(days=10))
        item["report_sha256"] = sha256_hex(
            {k: v for k, v in item.items() if k != "report_sha256"}
        )
        released.append(item)

    autonomous_denied = sum(1 for acc in accessions if not acc.get("released"))
    hold_codes = [h["reason"] for h in holds]
    fixture = fixture_manifest(rows)
    report_fields = [
        {
            "accession_id": a["accession_id"],
            "submission_id": a["submission_id"],
            "method": a["method"],
            "method_revision": a["method_revision"],
            "analyst_id": a["analyst_id"],
            "site": a["site"],
            "regulated_biological_hours": a["regulated_biological_hours"],
            "reported_duration_hours": a["reported_duration_hours"],
            "rush": a["rush"],
            "rush_shortened": a["rush_shortened"],
            "report_sha256": a["report_sha256"],
        }
        for a in accessions
    ]
    signed_manifest = {
        "demand_id": DEMAND_ID,
        "fixture_sha256": fixture["fixture_sha256"],
        "catalog_sha256": fixture["catalog_sha256"],
        "accession_ids": [a["accession_id"] for a in accessions],
        "hold_submission_ids": [h["submission_id"] for h in holds],
        "report_digests": [a["report_sha256"] for a in accessions],
        "hold_digests": [h["hold_sha256"] for h in holds],
    }
    result = {
        "ok": True,
        "demand_id": DEMAND_ID,
        "schema": SCHEMA,
        "truth_gate": TRUTH_GATE,
        "buyer": BUYER,
        "command": COMMAND,
        "open_slack_ts": OPEN_SLACK_TS,
        "input_rows": len(rows),
        "accessioned": len(accessions),
        "held": len(holds),
        "duplicates": duplicates,
        "replay_added_accessions": replay_added,
        "rush_never_shortened": sum(
            1
            for a in accessions
            if a["reported_duration_hours"] >= a["regulated_biological_hours"]
            and not a["rush_shortened"]
        ),
        "released_without_named_human": 0,
        "released_after_named_human": len(released),
        "held_released": sum(1 for h in holds if h.get("released")),
        "autonomous_denied": autonomous_denied,
        "production_writes": 0,
        "interfaces": "SIMULATED",
        "shadowing": "READ_ONLY",
        "interface_live": False,
        "autonomous_release": False,
        "human_approver": HUMAN_APPROVER,
        "hold_codes": hold_codes,
        "hold_family_counts": {code: hold_codes.count(code) for code in HOLD_CODES},
        "accessions": accessions,
        "holds": holds,
        "released": released,
        "report_fields": report_fields,
        "accession_ids": [a["accession_id"] for a in accessions],
        "submission_ids": [a["submission_id"] for a in accessions],
        "fixture_sha256": fixture["fixture_sha256"],
        "catalog_sha256": fixture["catalog_sha256"],
        "manifest_sha256": sha256_hex(signed_manifest),
        "signed_manifest": signed_manifest,
        "expected_counts": EXPECTED_COUNTS,
    }
    result["audit_sha256"] = sha256_hex(
        {
            "fixture_sha256": result["fixture_sha256"],
            "catalog_sha256": result["catalog_sha256"],
            "manifest_sha256": result["manifest_sha256"],
            "accessioned": result["accessioned"],
            "held": result["held"],
            "hold_family_counts": result["hold_family_counts"],
            "rush_never_shortened": result["rush_never_shortened"],
            "replay_added_accessions": result["replay_added_accessions"],
        }
    )
    return result


def pass_contract(result: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    actual = {
        "input_rows": result["input_rows"],
        "accessioned": result["accessioned"],
        "held": result["held"],
        "hold_missing_billing": result["hold_family_counts"].get("MISSING_BILLING", 0),
        "hold_duplicate_bag_barcode": result["hold_family_counts"].get(
            "DUPLICATE_BAG_BARCODE", 0
        ),
        "hold_invalid_rule_certificate": result["hold_family_counts"].get(
            "INVALID_RULE_CERTIFICATE", 0
        ),
        "hold_lot_size_error": result["hold_family_counts"].get("LOT_SIZE_ERROR", 0),
        "hold_unauthorized_ista_sampler": result["hold_family_counts"].get(
            "UNAUTHORIZED_ISTA_SAMPLER", 0
        ),
        "rush_never_shortened": result["rush_never_shortened"],
        "duplicates": result["duplicates"],
        "replay_added_accessions": result["replay_added_accessions"],
        "released_without_named_human": result["released_without_named_human"],
        "released_after_named_human": result["released_after_named_human"],
        "held_released": result["held_released"],
        "production_writes": result["production_writes"],
    }
    for key, expected in EXPECTED_COUNTS.items():
        if actual.get(key) != expected:
            failures.append(f"{key}: expected {expected}, got {actual.get(key)}")
    if result["interface_live"]:
        failures.append("interface_live must be false")
    if result["autonomous_release"]:
        failures.append("autonomous_release must be false")
    if len(result["accession_ids"]) != len(set(result["accession_ids"])):
        failures.append("accession_ids not unique")
    if len(result["submission_ids"]) != len(set(result["submission_ids"])):
        failures.append("submission_ids not unique")
    for acc in result["accessions"]:
        if acc["reported_duration_hours"] < acc["regulated_biological_hours"]:
            failures.append(
                f"rush shortened {acc['accession_id']}: "
                f"{acc['reported_duration_hours']} < {acc['regulated_biological_hours']}"
            )
        if acc["rush_shortened"]:
            failures.append(f"rush_shortened flag set on {acc['accession_id']}")
        if acc["method_revision"] != METHOD_CATALOG[acc["method"]]["revision"]:
            failures.append(f"method revision mismatch on {acc['accession_id']}")
        if acc["role"] not in ANALYSTS[acc["analyst_id"]]["roles"]:
            failures.append(f"unqualified analyst on {acc['accession_id']}")
    return failures


def expected_actual(result: dict[str, Any]) -> dict[str, Any]:
    actual = {
        "input_rows": result["input_rows"],
        "accessioned": result["accessioned"],
        "held": result["held"],
        "hold_missing_billing": result["hold_family_counts"].get("MISSING_BILLING", 0),
        "hold_duplicate_bag_barcode": result["hold_family_counts"].get(
            "DUPLICATE_BAG_BARCODE", 0
        ),
        "hold_invalid_rule_certificate": result["hold_family_counts"].get(
            "INVALID_RULE_CERTIFICATE", 0
        ),
        "hold_lot_size_error": result["hold_family_counts"].get("LOT_SIZE_ERROR", 0),
        "hold_unauthorized_ista_sampler": result["hold_family_counts"].get(
            "UNAUTHORIZED_ISTA_SAMPLER", 0
        ),
        "rush_never_shortened": result["rush_never_shortened"],
        "duplicates": result["duplicates"],
        "replay_added_accessions": result["replay_added_accessions"],
        "released_without_named_human": result["released_without_named_human"],
        "released_after_named_human": result["released_after_named_human"],
        "held_released": result["held_released"],
        "production_writes": result["production_writes"],
    }
    return {
        "expected": EXPECTED_COUNTS,
        "actual": actual,
        "match": actual == EXPECTED_COUNTS,
    }


def main(argv: list[str] | None = None) -> int:
    del argv
    result = run_gate()
    failures = pass_contract(result)
    payload = {
        "ok": not failures,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "failures": failures,
        "counts": expected_actual(result),
        "fixture_sha256": result["fixture_sha256"],
        "catalog_sha256": result["catalog_sha256"],
        "manifest_sha256": result["manifest_sha256"],
        "audit_sha256": result["audit_sha256"],
        "accessioned": result["accessioned"],
        "held": result["held"],
        "rush_never_shortened": result["rush_never_shortened"],
        "replay_added_accessions": result["replay_added_accessions"],
        "released_after_named_human": result["released_after_named_human"],
        "interfaces": result["interfaces"],
        "shadowing": result["shadowing"],
        "cash_usd": 0,
        "pre_sale_transport": "NONE",
    }
    print(json.dumps(payload, sort_keys=True, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
