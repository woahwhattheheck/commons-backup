#!/usr/bin/env python3
"""Savant FE8 lubricant order-to-report LIMS.

Demand: savant-fe8-order-report-lims-01
Buyer: Savant Labs / Antonino Di Bartolo

Single-method FE8 (DIN 51819 synthetic) lane: Test Authorization Form
plus SDS intake, method assignment, simulated instrument/QC binding,
staged report, named-human release. Replaces repeated TAF/SDS re-entry
and emailed-PDF handoffs without replacing the incumbent workflow.

Acceptance: replay 100 synthetic authorizations — 80 valid, 10 missing
SDS/metadata, 5 duplicate IDs, 5 invalid method selections. PASS only
when 80 accession exactly once; all 20 exceptions carry the expected
HOLD code; nothing schedules without required documents; instrument
and QC values plus the rendered-report digest match the golden set;
retries add no records; a named reviewer is required for release.

AquaTrace HOLD / BUILD-AND-VERIFY. Adapters stay simulated/read-only.
No production writes, outreach, prospect-facing demo, or automatic
release. PRE-SALE TRANSPORT: NONE.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

DEMAND_ID = "savant-fe8-order-report-lims-01"
SCHEMA = "commons-savant-fe8-order-report-lims/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
BUYER = "Savant Labs / Antonino Di Bartolo"
HUMAN_RELEASER = "RELEASER"
METHOD = "FE8"
METHOD_VERSION = "DIN-51819-2022-SYN"
VALID_COUNT = 80
HOLD_COUNT = 20
INPUT_COUNT = VALID_COUNT + HOLD_COUNT
QC_WINDOW_MG = (5.0, 15.0)

HOLD_CODES = (
    "MISSING_SDS",
    "MISSING_METADATA",
    "DUPLICATE_ID",
    "INVALID_METHOD",
)
INVALID_METHODS = ("FE9", "FOUR_BALL", "SRV", "FZG", "RPVOT")
CONDITION_SETS = (
    {
        "load_kn": 80.0,
        "temp_c": 80.0,
        "speed_min": 7.5,
        "duration_h": 80,
        "lubricant_class": "GREASE",
    },
    {
        "load_kn": 80.0,
        "temp_c": 120.0,
        "speed_min": 7.5,
        "duration_h": 80,
        "lubricant_class": "GREASE",
    },
    {
        "load_kn": 10.0,
        "temp_c": 80.0,
        "speed_min": 75.0,
        "duration_h": 80,
        "lubricant_class": "OIL",
    },
    {
        "load_kn": 10.0,
        "temp_c": 120.0,
        "speed_min": 75.0,
        "duration_h": 500,
        "lubricant_class": "OIL",
    },
)
UNITS = {
    "wear": "mg",
    "torque": "N·m",
    "temp": "°C",
    "load": "kN",
    "speed": "min-1",
    "duration": "h",
}
GOLDEN_COUNTS = {
    "input_rows": INPUT_COUNT,
    "accessioned": VALID_COUNT,
    "held": HOLD_COUNT,
    "scheduled": VALID_COUNT,
    "unscheduled_holds": HOLD_COUNT,
    "duplicate_accessions": 0,
    "released_reports": 0,
    "blocked_reports": VALID_COUNT,
    "replay_added_accessions": 0,
    "production_writes": 0,
}

# Locked after the first deterministic PASS of this exact fixture.
GOLDEN_FIXTURE_SHA256 = "2bcac0d66becddbd327a4f478480c77ef4f79305310ff3d7dde3adb2369a8c32"
GOLDEN_AUDIT_SHA256 = "7181103bfe4b466c8472ab9d0fa82c10265e4a120c796aec843dd4be4ae08c57"
GOLDEN_REPORT_DIGEST = "a5853f7e35e396bdd9843053f3f45c14d4a340945996977db0b478921c0941fa"
HERE = Path(__file__).resolve().parent
FIXTURE_DIR = HERE / "revenue" / "savant_fe8_order_report"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str("" if value is None else value).strip()


def _flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "y"}


def _round1(value: float) -> float:
    return float(f"{value:.1f}")


def _round2(value: float) -> float:
    return float(f"{value:.2f}")


def accession_id(auth_id: str) -> str:
    digest = sha256_hex(
        {
            "demand_id": DEMAND_ID,
            "auth_id": auth_id,
            "method": METHOD,
            "method_version": METHOD_VERSION,
        }
    )
    return "FE8-" + digest[:12]


def valid_auth_id(index: int) -> str:
    return "FE8-V%03d" % index


def instrument_packet(index: int, condition: dict[str, Any]) -> dict[str, Any]:
    wear_ring = _round1(3.0 + ((index - 1) % 80) * 0.1)
    wear_cage = _round1(1.0 + ((index - 1) % 40) * 0.1)
    torque = _round2(0.40 + ((index - 1) % 20) * 0.01)
    qc_std = _round1(8.0 + ((index - 1) % 5) * 0.2)
    return {
        "instrument_id": "SIM-FE8-01",
        "adapter": "SIMULATED",
        "wear_ring_mg": wear_ring,
        "wear_cage_mg": wear_cage,
        "torque_nm": torque,
        "temp_actual_c": condition["temp_c"],
        "qc_check_std_wear_mg": qc_std,
        "qc_ok": QC_WINDOW_MG[0] <= qc_std <= QC_WINDOW_MG[1],
        "qualifier": "",
    }


def source_hashes(auth_id: str, sds_present: bool) -> dict[str, str]:
    taf = sha256_hex({"demand_id": DEMAND_ID, "kind": "TAF", "auth_id": auth_id})
    sds = (
        sha256_hex({"demand_id": DEMAND_ID, "kind": "SDS", "auth_id": auth_id})
        if sds_present
        else ""
    )
    return {"taf": taf, "sds": sds}


def _base_row(
    row_id: str,
    auth_id: str,
    *,
    method: str = METHOD,
    sds_present: bool = True,
    customer_code: str | None = None,
    lubricant_code: str | None = None,
    condition_index: int = 0,
    valid_index: int | None = None,
    expected_hold: str | None = None,
) -> dict[str, Any]:
    condition = CONDITION_SETS[condition_index % len(CONDITION_SETS)]
    customer = customer_code if customer_code is not None else "SYN-CUST-%02d" % ((valid_index or 1) % 20 + 1)
    lubricant = lubricant_code if lubricant_code is not None else "SYN-%s-%02d" % (
        condition["lubricant_class"],
        (valid_index or 1) % 10 + 1,
    )
    hashes = source_hashes(auth_id, sds_present)
    row: dict[str, Any] = {
        "row_id": row_id,
        "auth_id": auth_id,
        "customer_code": customer,
        "lubricant_code": lubricant,
        "lubricant_class": condition["lubricant_class"],
        "method": method,
        "method_version": METHOD_VERSION if method == METHOD else "UNKNOWN",
        "load_kn": condition["load_kn"],
        "temp_c": condition["temp_c"],
        "speed_min": condition["speed_min"],
        "duration_h": condition["duration_h"],
        "sds_present": sds_present,
        "sds_hash": hashes["sds"],
        "taf_hash": hashes["taf"],
        "expected_hold": expected_hold,
        "interface_state": "SIMULATED",
        "interface_live": False,
    }
    if expected_hold is None and valid_index is not None:
        packet = instrument_packet(valid_index, condition)
        row["instrument"] = packet
        row["instrument_hash"] = sha256_hex(packet)
    return row


def build_acceptance_fixture() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index in range(1, VALID_COUNT + 1):
        rows.append(
            _base_row(
                "R%03d" % index,
                valid_auth_id(index),
                condition_index=index - 1,
                valid_index=index,
            )
        )
    for offset in range(5):
        rows.append(
            _base_row(
                "R%03d" % (81 + offset),
                "FE8-HSDS%02d" % (offset + 1),
                sds_present=False,
                condition_index=offset,
                expected_hold="MISSING_SDS",
            )
        )
    for offset in range(5):
        empty_customer = offset % 2 == 0
        rows.append(
            _base_row(
                "R%03d" % (86 + offset),
                "FE8-HMETA%02d" % (offset + 1),
                customer_code="" if empty_customer else "SYN-CUST-HOLD",
                lubricant_code="" if not empty_customer else "SYN-GREASE-HOLD",
                condition_index=offset,
                expected_hold="MISSING_METADATA",
            )
        )
    for offset in range(5):
        rows.append(
            _base_row(
                "R%03d" % (91 + offset),
                valid_auth_id(offset + 1),
                condition_index=offset,
                expected_hold="DUPLICATE_ID",
            )
        )
    for offset, method in enumerate(INVALID_METHODS):
        rows.append(
            _base_row(
                "R%03d" % (96 + offset),
                "FE8-HMETHOD%02d" % (offset + 1),
                method=method,
                condition_index=offset,
                expected_hold="INVALID_METHOD",
            )
        )
    if len(rows) != INPUT_COUNT:
        raise RuntimeError("acceptance fixture must be exactly %s rows, got %s" % (INPUT_COUNT, len(rows)))
    return rows


def fixture_manifest(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    body = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "method": METHOD,
        "method_version": METHOD_VERSION,
        "input_rows": len(inbound),
        "valid_rows": sum(1 for row in inbound if row.get("expected_hold") is None),
        "hold_rows": sum(1 for row in inbound if row.get("expected_hold")),
        "hold_plan": {
            "MISSING_SDS": 5,
            "MISSING_METADATA": 5,
            "DUPLICATE_ID": 5,
            "INVALID_METHOD": 5,
        },
        "row_ids": [row["row_id"] for row in inbound],
        "auth_ids": [row["auth_id"] for row in inbound],
        "expected_holds": [row.get("expected_hold") for row in inbound],
        "rows": inbound,
        "interfaces": "SIMULATED",
        "interface_live": False,
        "production_writes": False,
        "autonomous_release": False,
    }
    body["fixture_sha256"] = sha256_hex({key: value for key, value in body.items() if key != "fixture_sha256"})
    return body


def empty_journal() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "accessions": {},
        "holds": [],
        "events": [],
    }


def _event(journal: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    journal["events"].append({"seq": len(journal["events"]) + 1, "kind": kind, **deepcopy(payload)})


def classify_authorization(row: dict[str, Any], seen_auth_ids: set[str]) -> dict[str, Any]:
    auth_id = _text(row.get("auth_id"))
    method = _text(row.get("method")).upper()
    customer = _text(row.get("customer_code"))
    lubricant = _text(row.get("lubricant_code"))
    sds_present = _flag(row.get("sds_present")) and bool(_text(row.get("sds_hash")))

    if not auth_id or not customer or not lubricant:
        return {"ok": False, "code": "MISSING_METADATA", "auth_id": auth_id or None}
    if method != METHOD:
        return {"ok": False, "code": "INVALID_METHOD", "auth_id": auth_id, "method": method}
    if not sds_present:
        return {"ok": False, "code": "MISSING_SDS", "auth_id": auth_id}
    if auth_id in seen_auth_ids:
        return {"ok": False, "code": "DUPLICATE_ID", "auth_id": auth_id}
    return {
        "ok": True,
        "auth_id": auth_id,
        "method": METHOD,
        "method_version": METHOD_VERSION,
        "accession_id": accession_id(auth_id),
        "route": "FE8_WORKLIST",
    }


def rendered_report(record: dict[str, Any]) -> dict[str, Any]:
    instrument = record.get("instrument") or {}
    return {
        "demand_id": DEMAND_ID,
        "accession_id": record["accession_id"],
        "auth_id": record["auth_id"],
        "customer_code": record["customer_code"],
        "lubricant_code": record["lubricant_code"],
        "method": record["method"],
        "method_version": record["method_version"],
        "units": UNITS,
        "load_kn": record["load_kn"],
        "temp_c": record["temp_c"],
        "speed_min": record["speed_min"],
        "duration_h": record["duration_h"],
        "wear_ring_mg": instrument.get("wear_ring_mg"),
        "wear_cage_mg": instrument.get("wear_cage_mg"),
        "torque_nm": instrument.get("torque_nm"),
        "qc_check_std_wear_mg": instrument.get("qc_check_std_wear_mg"),
        "qc_ok": instrument.get("qc_ok"),
        "qualifier": instrument.get("qualifier", ""),
        "source_hashes": {
            "taf": record.get("taf_hash"),
            "sds": record.get("sds_hash"),
            "instrument": record.get("instrument_hash"),
        },
        "released": bool(record.get("released")),
        "interface_live": False,
    }


def report_status(record: dict[str, Any]) -> str:
    if record.get("released"):
        return "RELEASED"
    if not record.get("instrument"):
        return "BLOCKED_MISSING_RESULT"
    if not record.get("qc_signoff"):
        return "BLOCKED_MISSING_QC"
    return "READY_FOR_HUMAN_RELEASE"


def ingest_row(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    row_id = _text(row.get("row_id"))
    existing_acc = next(
        (item for item in journal["accessions"].values() if item["auth_id"] == _text(row.get("auth_id"))),
        None,
    )
    if existing_acc is not None and existing_acc.get("row_id") == row_id:
        _event(
            journal,
            "REPLAY_NOOP",
            {"accession_id": existing_acc["accession_id"], "auth_id": existing_acc["auth_id"]},
        )
        return {
            "kind": "REPLAY_NOOP",
            "accession_id": existing_acc["accession_id"],
            "auth_id": existing_acc["auth_id"],
        }
    seen = {item["auth_id"] for item in journal["accessions"].values()}
    verdict = classify_authorization(row, seen)
    if not verdict["ok"]:
        hold = {
            "row_id": _text(row.get("row_id")),
            "auth_id": verdict.get("auth_id"),
            "code": verdict["code"],
            "method": _text(row.get("method")) or None,
            "scheduled": False,
        }
        fingerprint = sha256_hex(hold)
        existing = {sha256_hex(item) for item in journal["holds"]}
        if fingerprint not in existing:
            journal["holds"].append(hold)
            _event(journal, "HOLD", hold)
            return {"kind": "HOLD", "duplicate": False, **hold}
        return {"kind": "HOLD", "duplicate": True, **hold}

    acc_id = verdict["accession_id"]
    if acc_id in journal["accessions"]:
        _event(journal, "REPLAY_NOOP", {"accession_id": acc_id, "auth_id": verdict["auth_id"]})
        return {"kind": "REPLAY_NOOP", "accession_id": acc_id, "auth_id": verdict["auth_id"]}

    instrument = deepcopy(row.get("instrument") or {})
    record = {
        "accession_id": acc_id,
        "auth_id": verdict["auth_id"],
        "row_id": _text(row.get("row_id")),
        "customer_code": _text(row.get("customer_code")),
        "lubricant_code": _text(row.get("lubricant_code")),
        "lubricant_class": _text(row.get("lubricant_class")),
        "method": verdict["method"],
        "method_version": verdict["method_version"],
        "route": verdict["route"],
        "load_kn": row.get("load_kn"),
        "temp_c": row.get("temp_c"),
        "speed_min": row.get("speed_min"),
        "duration_h": row.get("duration_h"),
        "sds_present": True,
        "sds_hash": _text(row.get("sds_hash")),
        "taf_hash": _text(row.get("taf_hash")),
        "instrument": instrument,
        "instrument_hash": _text(row.get("instrument_hash")) or sha256_hex(instrument),
        "qc_signoff": bool(instrument.get("qc_ok")),
        "state": "ACCESSIONED",
        "scheduled": False,
        "released": False,
        "released_by": None,
        "report_status": "BLOCKED_MISSING_RESULT",
        "interface_state": "SIMULATED",
        "interface_live": False,
    }
    record["report"] = rendered_report(record)
    record["report_digest"] = sha256_hex(record["report"])
    record["report_status"] = report_status(record)
    journal["accessions"][acc_id] = record
    _event(
        journal,
        "ACCESSION",
        {"accession_id": acc_id, "auth_id": verdict["auth_id"], "route": verdict["route"]},
    )
    return {"kind": "ACCESSION", "accession_id": acc_id, "route": verdict["route"]}


def schedule_eligible(journal: dict[str, Any]) -> list[dict[str, Any]]:
    effects = []
    for acc_id, record in journal["accessions"].items():
        if record["scheduled"]:
            effects.append({"ok": True, "duplicate": True, "accession_id": acc_id, "state": "SCHEDULED"})
            continue
        if not record.get("sds_present") or not record.get("taf_hash") or not record.get("sds_hash"):
            _event(journal, "SCHEDULE_BLOCKED", {"accession_id": acc_id, "code": "MISSING_DOCUMENTS"})
            effects.append({"ok": False, "code": "MISSING_DOCUMENTS", "accession_id": acc_id})
            continue
        record["scheduled"] = True
        record["state"] = "SCHEDULED"
        _event(journal, "SCHEDULED", {"accession_id": acc_id})
        effects.append({"ok": True, "duplicate": False, "accession_id": acc_id, "state": "SCHEDULED"})
    return effects


def release_report(
    journal: dict[str, Any],
    accession_id_value: str,
    *,
    actor_role: str,
    actor: str,
) -> dict[str, Any]:
    record = journal["accessions"].get(accession_id_value)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_ACCESSION"}
    role = _text(actor_role).upper()
    if role != HUMAN_RELEASER:
        _event(
            journal,
            "RELEASE_DENIED",
            {
                "accession_id": accession_id_value,
                "code": "AUTONOMOUS_RELEASE_DENIED",
                "actor_role": role or None,
            },
        )
        return {"ok": False, "code": "AUTONOMOUS_RELEASE_DENIED", "report_status": report_status(record)}
    status = report_status(record)
    if status not in {"READY_FOR_HUMAN_RELEASE", "RELEASED"}:
        _event(
            journal,
            "RELEASE_DENIED",
            {"accession_id": accession_id_value, "code": "REPORT_BLOCKED", "report_status": status},
        )
        return {"ok": False, "code": "REPORT_BLOCKED", "report_status": status}
    if record["released"]:
        return {"ok": True, "duplicate": True, "report_status": "RELEASED"}
    record["released"] = True
    record["released_by"] = _text(actor) or "human-releaser"
    record["report_status"] = "RELEASED"
    record["report"] = rendered_report(record)
    record["report_digest"] = sha256_hex(record["report"])
    _event(journal, "RELEASED", {"accession_id": accession_id_value, "released_by": record["released_by"]})
    return {"ok": True, "duplicate": False, "report_status": "RELEASED"}


def run_gate(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    journal = empty_journal()
    effects = [ingest_row(journal, row) for row in inbound]
    schedules = schedule_eligible(journal)
    autonomous = [
        release_report(journal, acc_id, actor_role="SYSTEM", actor="autonomous")
        for acc_id in journal["accessions"]
    ]
    accessioned = sorted(journal["accessions"].values(), key=lambda item: item["auth_id"])
    hold_codes = [item["code"] for item in journal["holds"]]
    reports = [item["report"] for item in accessioned]
    report_digests = [item["report_digest"] for item in accessioned]
    audit = {
        "demand_id": DEMAND_ID,
        "auth_ids": [item["auth_id"] for item in accessioned],
        "accession_ids": [item["accession_id"] for item in accessioned],
        "hold_codes": hold_codes,
        "hold_auth_ids": [item["auth_id"] for item in journal["holds"]],
        "instrument": [
            {
                "auth_id": item["auth_id"],
                "wear_ring_mg": item["instrument"]["wear_ring_mg"],
                "wear_cage_mg": item["instrument"]["wear_cage_mg"],
                "torque_nm": item["instrument"]["torque_nm"],
                "qc_check_std_wear_mg": item["instrument"]["qc_check_std_wear_mg"],
                "qc_ok": item["instrument"]["qc_ok"],
                "instrument_hash": item["instrument_hash"],
            }
            for item in accessioned
        ],
        "report_digests": report_digests,
        "scheduled": [item["auth_id"] for item in accessioned if item["scheduled"]],
        "released": [item["auth_id"] for item in accessioned if item["released"]],
    }
    body = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "method": METHOD,
        "method_version": METHOD_VERSION,
        "input_rows": len(inbound),
        "accessioned": len(accessioned),
        "held": len(journal["holds"]),
        "hold_codes": hold_codes,
        "hold_code_set": sorted(set(hold_codes)),
        "scheduled": sum(1 for item in accessioned if item["scheduled"]),
        "unscheduled_holds": sum(1 for item in journal["holds"] if not item["scheduled"]),
        "duplicate_accessions": 0,
        "released_reports": sum(1 for item in accessioned if item["released"]),
        "blocked_reports": sum(1 for item in accessioned if item["report_status"] != "RELEASED"),
        "replay_noops": sum(1 for item in effects if item.get("kind") == "REPLAY_NOOP"),
        "effects": effects,
        "schedule_effects": schedules,
        "autonomous_release_effects": autonomous,
        "accessions": accessioned,
        "holds": deepcopy(journal["holds"]),
        "routes": {item["auth_id"]: item["route"] for item in accessioned},
        "accession_ids": [item["accession_id"] for item in accessioned],
        "reports": reports,
        "report_digests": report_digests,
        "report_digest": sha256_hex(reports),
        "audit": audit,
        "audit_sha256": sha256_hex(audit),
        "interface_live": False,
        "interfaces": "SIMULATED",
        "autonomous_certification": False,
        "autonomous_release": False,
        "production_writes": 0,
        "pre_sale_transport": "NONE",
        "cash_usd": 0,
    }
    body["manifest_sha256"] = sha256_hex(
        {key: value for key, value in body.items() if key != "manifest_sha256"}
    )
    return body


def replay_into(journal: dict[str, Any], rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    before = set(journal["accessions"])
    before_holds = {sha256_hex(item) for item in journal["holds"]}
    effects = [ingest_row(journal, row) for row in inbound]
    added = set(journal["accessions"]) - before
    added_holds = [item for item in journal["holds"] if sha256_hex(item) not in before_holds]
    return {
        "added_accessions": sorted(added),
        "added_accession_count": len(added),
        "added_holds": len(added_holds),
        "replay_noops": sum(1 for item in effects if item.get("kind") == "REPLAY_NOOP"),
        "accession_count": len(journal["accessions"]),
        "hold_count": len(journal["holds"]),
    }


def expected_actual(result: dict[str, Any]) -> dict[str, Any]:
    actual = {
        "input_rows": result.get("input_rows"),
        "accessioned": result.get("accessioned"),
        "held": result.get("held"),
        "scheduled": result.get("scheduled"),
        "unscheduled_holds": result.get("unscheduled_holds"),
        "duplicate_accessions": result.get("duplicate_accessions"),
        "released_reports": result.get("released_reports"),
        "blocked_reports": result.get("blocked_reports"),
        "replay_added_accessions": result.get("replay_added_accessions", 0),
        "production_writes": result.get("production_writes"),
    }
    return {"expected": dict(GOLDEN_COUNTS), "actual": actual, "match": actual == GOLDEN_COUNTS}


def pass_contract(result: dict[str, Any]) -> list[str]:
    failures = []
    counts = expected_actual(result)
    if not counts["match"]:
        failures.append("counts")
    if result.get("hold_code_set") != sorted(HOLD_CODES):
        failures.append("hold_code_set")
    if Counter(result.get("hold_codes") or []) != Counter(
        {
            "MISSING_SDS": 5,
            "MISSING_METADATA": 5,
            "DUPLICATE_ID": 5,
            "INVALID_METHOD": 5,
        }
    ):
        failures.append("hold_code_counts")
    if len(set(result.get("accession_ids") or [])) != VALID_COUNT:
        failures.append("accession_ids_not_unique")
    if any(item.get("scheduled") for item in result.get("holds") or []):
        failures.append("hold_scheduled")
    if any(item.get("method") != METHOD for item in result.get("accessions") or []):
        failures.append("method_binding")
    if any(item.get("method_version") != METHOD_VERSION for item in result.get("accessions") or []):
        failures.append("method_version")
    if any(not item.get("instrument", {}).get("qc_ok") for item in result.get("accessions") or []):
        failures.append("qc_not_ok")
    if any(item.get("interface_live") for item in result.get("accessions") or []):
        failures.append("interface_live_accession")
    if result.get("interface_live") is not False:
        failures.append("interface_live")
    if result.get("interfaces") != "SIMULATED":
        failures.append("interfaces")
    if result.get("autonomous_certification") is not False:
        failures.append("autonomous_certification")
    if result.get("autonomous_release") is not False:
        failures.append("autonomous_release")
    if not all(
        item.get("code") == "AUTONOMOUS_RELEASE_DENIED"
        for item in result.get("autonomous_release_effects") or []
    ):
        failures.append("autonomous_release_not_denied")
    if result.get("audit_sha256") != GOLDEN_AUDIT_SHA256:
        failures.append("audit_sha256")
    if result.get("report_digest") != GOLDEN_REPORT_DIGEST:
        failures.append("report_digest")
    return failures


def write_fixture_files(directory: Path | None = None) -> dict[str, str]:
    dest = directory or FIXTURE_DIR
    dest.mkdir(parents=True, exist_ok=True)
    manifest = fixture_manifest()
    result = run_gate()
    (dest / "fixture.json").write_text(_canonical(manifest) + "\n", encoding="utf-8")
    return {
        "fixture_sha256": manifest["fixture_sha256"],
        "audit_sha256": result["audit_sha256"],
        "report_digest": result["report_digest"],
        "manifest_sha256": result["manifest_sha256"],
    }


def main() -> int:
    first = run_gate()
    second = run_gate()
    journal = empty_journal()
    for row in build_acceptance_fixture():
        ingest_row(journal, row)
    replay = replay_into(journal)
    failures = pass_contract(first)
    if first.get("audit_sha256") != second.get("audit_sha256"):
        failures.append("replay_mismatch")
    if first.get("report_digest") != second.get("report_digest"):
        failures.append("report_digest_mismatch")
    first["replay_added_accessions"] = replay["added_accession_count"]
    if replay.get("added_accession_count") != 0:
        failures.append("replay_added_accessions")
    if replay.get("added_holds") != 0:
        failures.append("replay_added_holds")
    counts = expected_actual(first)
    report = {
        "ok": not failures,
        "failures": failures,
        "expected": counts["expected"],
        "actual": counts["actual"],
        "fixture_sha256": fixture_manifest()["fixture_sha256"],
        "audit_sha256": first.get("audit_sha256"),
        "report_digest": first.get("report_digest"),
        "manifest_sha256": first.get("manifest_sha256"),
        "accessioned": first.get("accessioned"),
        "held": first.get("held"),
        "hold_codes": sorted(set(first.get("hold_codes") or [])),
        "scheduled": first.get("scheduled"),
        "blocked_reports": first.get("blocked_reports"),
        "replay_added_accessions": replay.get("added_accession_count"),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
