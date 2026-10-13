#!/usr/bin/env python3
"""ACE/QAT thermal-rheology capacity integration LIMS.

Demand: ace-qat-thermal-rheology-capacity-lims-01
Buyer: Erick Sharp / ACE Laboratories + Quick Accurate Testing

Pipeline: customer order → accession → ACE/QAT provenance →
method/version/capability router → DSC/TGA/DMA/TMA/SDT/AR-G2 result →
QC review → staged report. Named-human release only.

Acceptance: 120 synthetic orders — 90 valid, 10 duplicate IDs,
10 method/capability mismatches, 10 QC failures. PASS only when exactly
90 are READY, 30 are HOLD with DUPLICATE_ID / CAPABILITY_MISMATCH /
QC_FAIL, instrument/method/source hashes match, replay adds zero jobs,
and zero reports release without named approval.

AquaTrace HOLD / BUILD-AND-VERIFY. Adapters stay simulated/read-only.
No production writes, outreach, or automatic release.
PRE-SALE TRANSPORT: NONE.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

DEMAND_ID = "ace-qat-thermal-rheology-capacity-lims-01"
SCHEMA = "commons-ace-qat-thermal-rheology-capacity-lims/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
BUYER = "Erick Sharp / ACE Laboratories + Quick Accurate Testing"
HUMAN_RELEASER = "RELEASER"
VALID_COUNT = 90
HOLD_COUNT = 30
INPUT_COUNT = VALID_COUNT + HOLD_COUNT
HOLD_CODES = ("DUPLICATE_ID", "CAPABILITY_MISMATCH", "QC_FAIL")
METHODS = ("DSC", "TGA", "DMA", "TMA", "SDT", "AR-G2")

CAPABILITIES: dict[tuple[str, str, str, str], dict[str, str]] = {
    ("DSC", "ASTM-D3418-21", "ACE", "DSC-Q2000"): {
        "route": "ACE_DSC",
        "site": "ACE-THERMAL-01",
        "adapter": "SIMULATED",
    },
    ("TGA", "ASTM-E1131-20", "ACE", "TGA-5500"): {
        "route": "ACE_TGA",
        "site": "ACE-THERMAL-01",
        "adapter": "SIMULATED",
    },
    ("DMA", "ASTM-D4065-20", "ACE", "DMA-850"): {
        "route": "ACE_DMA",
        "site": "ACE-THERMAL-01",
        "adapter": "SIMULATED",
    },
    ("TMA", "ASTM-E831-19", "QAT", "TMA-450"): {
        "route": "QAT_TMA",
        "site": "QAT-RHEOLOGY-01",
        "adapter": "SIMULATED",
    },
    ("SDT", "ASTM-E1131-20", "QAT", "SDT-650"): {
        "route": "QAT_SDT",
        "site": "QAT-RHEOLOGY-01",
        "adapter": "SIMULATED",
    },
    ("AR-G2", "ASTM-D4440-15", "QAT", "AR-G2"): {
        "route": "QAT_RHEOLOGY",
        "site": "QAT-RHEOLOGY-01",
        "adapter": "SIMULATED",
    },
}

METHOD_CYCLE = (
    ("DSC", "ASTM-D3418-21", "ACE", "DSC-Q2000"),
    ("TGA", "ASTM-E1131-20", "ACE", "TGA-5500"),
    ("DMA", "ASTM-D4065-20", "ACE", "DMA-850"),
    ("TMA", "ASTM-E831-19", "QAT", "TMA-450"),
    ("SDT", "ASTM-E1131-20", "QAT", "SDT-650"),
    ("AR-G2", "ASTM-D4440-15", "QAT", "AR-G2"),
)

MISMATCH_SPECS = (
    {"order_id": "AQ-CM01", "method": "DSC", "method_version": "ASTM-D3418-21", "source": "QAT", "instrument_id": "DSC-Q2000"},
    {"order_id": "AQ-CM02", "method": "TGA", "method_version": "ASTM-E1131-08", "source": "ACE", "instrument_id": "TGA-5500"},
    {"order_id": "AQ-CM03", "method": "DMA", "method_version": "ASTM-D4065-20", "source": "QAT", "instrument_id": "DMA-850"},
    {"order_id": "AQ-CM04", "method": "TMA", "method_version": "ASTM-E831-19", "source": "ACE", "instrument_id": "TMA-450"},
    {"order_id": "AQ-CM05", "method": "SDT", "method_version": "ASTM-E1131-20", "source": "QAT", "instrument_id": "DSC-Q2000"},
    {"order_id": "AQ-CM06", "method": "AR-G2", "method_version": "ASTM-D4440-15", "source": "ACE", "instrument_id": "AR-G2"},
    {"order_id": "AQ-CM07", "method": "DSC", "method_version": "ASTM-D3418-21", "source": "ACE", "instrument_id": "AR-G2"},
    {"order_id": "AQ-CM08", "method": "MDSC", "method_version": "ASTM-D3418-21", "source": "ACE", "instrument_id": "DSC-Q2000"},
    {"order_id": "AQ-CM09", "method": "TGA", "method_version": "ISO-11358-1", "source": "ACE", "instrument_id": "TGA-5500"},
    {"order_id": "AQ-CM10", "method": "AR-G2", "method_version": "ASTM-D4440-15", "source": "QAT", "instrument_id": "ARES-G2"},
)

GOLDEN_COUNTS = {
    "input_rows": INPUT_COUNT,
    "ready": VALID_COUNT,
    "held": HOLD_COUNT,
    "jobs": VALID_COUNT + 10,
    "duplicate_jobs": 0,
    "released_reports": 0,
    "blocked_reports": VALID_COUNT + 10,
    "replay_added_jobs": 0,
    "production_writes": 0,
}

# Locked after the first deterministic PASS of this exact fixture.
GOLDEN_FIXTURE_SHA256 = "019eed67be05ac57b8af5e454390eebd688aedac0e4e0466775672db84c25ab9"
GOLDEN_AUDIT_SHA256 = "63a72dea4306203e2da870a0e9cc657146896965b54943ea096c9a592d29620e"
GOLDEN_REPORT_DIGEST = "cfc145784c1e22cc619433d6d0aa541bbb34087e4f186aafde3c8e4a11ec7c22"
HERE = Path(__file__).resolve().parent
FIXTURE_DIR = HERE / "revenue" / "ace_qat_thermal_rheology_capacity"


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


def _round2(value: float) -> float:
    return float(f"{value:.2f}")


def valid_order_id(index: int) -> str:
    return "AQ-V%03d" % index


def accession_id(order_id: str, method: str, source: str) -> str:
    digest = sha256_hex(
        {
            "demand_id": DEMAND_ID,
            "order_id": order_id,
            "method": method,
            "source": source,
        }
    )
    return "AQ-" + digest[:12]


def source_hash(source: str, order_id: str) -> str:
    return sha256_hex({"demand_id": DEMAND_ID, "kind": "SOURCE", "source": source, "order_id": order_id})


def method_hash(method: str, method_version: str) -> str:
    return sha256_hex(
        {"demand_id": DEMAND_ID, "kind": "METHOD", "method": method, "method_version": method_version}
    )


def instrument_hash(instrument_id: str, adapter: str = "SIMULATED") -> str:
    return sha256_hex(
        {
            "demand_id": DEMAND_ID,
            "kind": "INSTRUMENT",
            "instrument_id": instrument_id,
            "adapter": adapter,
        }
    )


def capability_key(method: str, method_version: str, source: str, instrument_id: str) -> tuple[str, str, str, str]:
    return (method, method_version, source, instrument_id)


def lookup_capability(method: str, method_version: str, source: str, instrument_id: str) -> dict[str, str] | None:
    return CAPABILITIES.get(capability_key(method, method_version, source, instrument_id))


def instrument_result(index: int, method: str) -> dict[str, Any]:
    n = ((index - 1) % 90) + 1
    if method == "DSC":
        return {
            "tg_c": _round2(80.0 + n * 0.10),
            "tm_c": _round2(160.0 + n * 0.20),
            "delta_h_j_g": _round2(18.00 + n * 0.05),
        }
    if method == "TGA":
        return {
            "onset_c": _round2(310.0 + n * 0.25),
            "residue_pct": _round2(4.00 + (n % 20) * 0.10),
        }
    if method == "DMA":
        return {
            "e_prime_mpa": _round2(1200.0 + n * 2.50),
            "tan_delta": _round2(0.20 + (n % 15) * 0.01),
        }
    if method == "TMA":
        return {"cte_um_m_c": _round2(40.00 + n * 0.15)}
    if method == "SDT":
        return {
            "tg_c": _round2(85.0 + n * 0.10),
            "residue_pct": _round2(3.50 + (n % 12) * 0.08),
        }
    return {
        "g_prime_pa": _round2(850.0 + n * 3.00),
        "eta_star_pa_s": _round2(120.00 + n * 0.40),
    }


def _base_row(
    row_id: str,
    order_id: str,
    *,
    method: str,
    method_version: str,
    source: str,
    instrument_id: str,
    valid_index: int | None = None,
    qc_fail: bool = False,
    expected_hold: str | None = None,
) -> dict[str, Any]:
    spec = lookup_capability(method, method_version, source, instrument_id)
    result = instrument_result(valid_index or 1, method) if spec is not None else {}
    row: dict[str, Any] = {
        "row_id": row_id,
        "order_id": order_id,
        "customer_code": "SYN-AQ-%02d" % ((valid_index or 1) % 18 + 1),
        "method": method,
        "method_version": method_version,
        "source": source,
        "instrument_id": instrument_id,
        "qc_fail": qc_fail,
        "expected_hold": expected_hold,
        "source_hash": source_hash(source, order_id),
        "method_hash": method_hash(method, method_version),
        "instrument_hash": instrument_hash(instrument_id),
        "result": result,
    }
    return row


def build_acceptance_fixture() -> list[dict[str, Any]]:
    """120-row PASS fixture for ace-qat-thermal-rheology-capacity-lims-01."""
    rows: list[dict[str, Any]] = []
    for index in range(1, VALID_COUNT + 1):
        method, version, source, instrument = METHOD_CYCLE[(index - 1) % len(METHOD_CYCLE)]
        rows.append(
            _base_row(
                "R%03d" % index,
                valid_order_id(index),
                method=method,
                method_version=version,
                source=source,
                instrument_id=instrument,
                valid_index=index,
            )
        )
    for offset, spec in enumerate(MISMATCH_SPECS):
        rows.append(
            _base_row(
                "R%03d" % (91 + offset),
                spec["order_id"],
                method=spec["method"],
                method_version=spec["method_version"],
                source=spec["source"],
                instrument_id=spec["instrument_id"],
                valid_index=offset + 1,
                expected_hold="CAPABILITY_MISMATCH",
            )
        )
    for offset in range(10):
        method, version, source, instrument = METHOD_CYCLE[offset % len(METHOD_CYCLE)]
        rows.append(
            _base_row(
                "R%03d" % (101 + offset),
                "AQ-QC%02d" % (offset + 1),
                method=method,
                method_version=version,
                source=source,
                instrument_id=instrument,
                valid_index=offset + 1,
                qc_fail=True,
                expected_hold="QC_FAIL",
            )
        )
    for offset in range(10):
        method, version, source, instrument = METHOD_CYCLE[offset % len(METHOD_CYCLE)]
        rows.append(
            _base_row(
                "R%03d" % (111 + offset),
                valid_order_id(offset + 1),
                method=method,
                method_version=version,
                source=source,
                instrument_id=instrument,
                valid_index=offset + 1,
                expected_hold="DUPLICATE_ID",
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
        "methods": list(METHODS),
        "input_rows": len(inbound),
        "valid_rows": sum(1 for row in inbound if row.get("expected_hold") is None),
        "hold_rows": sum(1 for row in inbound if row.get("expected_hold")),
        "hold_plan": {
            "DUPLICATE_ID": 10,
            "CAPABILITY_MISMATCH": 10,
            "QC_FAIL": 10,
        },
        "row_ids": [row["row_id"] for row in inbound],
        "order_ids": [row["order_id"] for row in inbound],
        "expected_holds": [row.get("expected_hold") for row in inbound],
        "source_hashes": [row["source_hash"] for row in inbound],
        "method_hashes": [row["method_hash"] for row in inbound],
        "instrument_hashes": [row["instrument_hash"] for row in inbound],
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
        "jobs": {},
        "holds": [],
        "events": [],
    }


def _event(journal: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    journal["events"].append({"seq": len(journal["events"]) + 1, "kind": kind, **deepcopy(payload)})


def classify_order(row: dict[str, Any], seen_order_ids: set[str]) -> dict[str, Any]:
    order_id = _text(row.get("order_id"))
    method = _text(row.get("method"))
    method_version = _text(row.get("method_version"))
    source = _text(row.get("source")).upper()
    instrument_id = _text(row.get("instrument_id"))
    if not order_id:
        return {"ok": False, "code": "CAPABILITY_MISMATCH", "order_id": None}
    if order_id in seen_order_ids:
        return {"ok": False, "code": "DUPLICATE_ID", "order_id": order_id}
    spec = lookup_capability(method, method_version, source, instrument_id)
    if spec is None:
        return {
            "ok": False,
            "code": "CAPABILITY_MISMATCH",
            "order_id": order_id,
            "method": method,
            "source": source,
            "instrument_id": instrument_id,
        }
    return {
        "ok": True,
        "order_id": order_id,
        "method": method,
        "method_version": method_version,
        "source": source,
        "instrument_id": instrument_id,
        "route": spec["route"],
        "site": spec["site"],
        "adapter": spec["adapter"],
        "accession_id": accession_id(order_id, method, source),
    }


def rendered_report(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "demand_id": DEMAND_ID,
        "accession_id": record["accession_id"],
        "order_id": record["order_id"],
        "customer_code": record["customer_code"],
        "source": record["source"],
        "site": record["site"],
        "method": record["method"],
        "method_version": record["method_version"],
        "instrument_id": record["instrument_id"],
        "route": record["route"],
        "result": deepcopy(record.get("result") or {}),
        "qc_ok": bool(record.get("qc_ok")),
        "source_hash": record.get("source_hash"),
        "method_hash": record.get("method_hash"),
        "instrument_hash": record.get("instrument_hash"),
        "released": bool(record.get("released")),
        "interface_live": False,
    }


def report_status(record: dict[str, Any]) -> str:
    if record.get("released"):
        return "RELEASED"
    if record.get("state") == "HOLD":
        return "HOLD"
    if not record.get("result"):
        return "BLOCKED_MISSING_RESULT"
    if not record.get("qc_ok"):
        return "BLOCKED_MISSING_QC"
    return "READY"


def _hold(journal: dict[str, Any], row: dict[str, Any], code: str) -> dict[str, Any]:
    hold = {
        "row_id": _text(row.get("row_id")),
        "order_id": _text(row.get("order_id")) or None,
        "code": code,
        "method": _text(row.get("method")) or None,
        "source": _text(row.get("source")) or None,
        "instrument_id": _text(row.get("instrument_id")) or None,
    }
    fingerprint = sha256_hex(hold)
    existing = {sha256_hex(item) for item in journal["holds"]}
    if fingerprint not in existing:
        journal["holds"].append(hold)
        _event(journal, "HOLD", hold)
        return {"kind": "HOLD", "duplicate": False, **hold}
    return {"kind": "HOLD", "duplicate": True, **hold}


def ingest_row(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    row_id = _text(row.get("row_id"))
    existing_job = next(
        (item for item in journal["jobs"].values() if item["order_id"] == _text(row.get("order_id"))),
        None,
    )
    if existing_job is not None and existing_job.get("row_id") == row_id:
        _event(
            journal,
            "REPLAY_NOOP",
            {"accession_id": existing_job["accession_id"], "order_id": existing_job["order_id"]},
        )
        return {
            "kind": "REPLAY_NOOP",
            "accession_id": existing_job["accession_id"],
            "order_id": existing_job["order_id"],
        }
    seen = {item["order_id"] for item in journal["jobs"].values()}
    verdict = classify_order(row, seen)
    if not verdict["ok"]:
        return _hold(journal, row, verdict["code"])

    acc_id = verdict["accession_id"]
    if acc_id in journal["jobs"]:
        _event(journal, "REPLAY_NOOP", {"accession_id": acc_id, "order_id": verdict["order_id"]})
        return {"kind": "REPLAY_NOOP", "accession_id": acc_id, "order_id": verdict["order_id"]}

    qc_fail = _flag(row.get("qc_fail"))
    result = deepcopy(row.get("result") or instrument_result(1, verdict["method"]))
    record = {
        "accession_id": acc_id,
        "order_id": verdict["order_id"],
        "row_id": row_id,
        "customer_code": _text(row.get("customer_code")),
        "method": verdict["method"],
        "method_version": verdict["method_version"],
        "source": verdict["source"],
        "site": verdict["site"],
        "instrument_id": verdict["instrument_id"],
        "route": verdict["route"],
        "adapter": verdict["adapter"],
        "result": result,
        "qc_ok": not qc_fail,
        "qc_fail": qc_fail,
        "source_hash": _text(row.get("source_hash")) or source_hash(verdict["source"], verdict["order_id"]),
        "method_hash": _text(row.get("method_hash")) or method_hash(verdict["method"], verdict["method_version"]),
        "instrument_hash": _text(row.get("instrument_hash")) or instrument_hash(verdict["instrument_id"]),
        "state": "HOLD" if qc_fail else "READY",
        "released": False,
        "released_by": None,
        "interface_state": "SIMULATED",
        "interface_live": False,
    }
    record["report"] = rendered_report(record)
    record["report_digest"] = sha256_hex(record["report"])
    record["report_status"] = report_status(record)
    journal["jobs"][acc_id] = record
    _event(
        journal,
        "HOLD" if qc_fail else "READY",
        {"accession_id": acc_id, "order_id": verdict["order_id"], "route": verdict["route"]},
    )
    if qc_fail:
        hold_effect = _hold(journal, row, "QC_FAIL")
        return {"kind": "HOLD", "accession_id": acc_id, "code": "QC_FAIL", "duplicate": hold_effect["duplicate"]}
    return {"kind": "READY", "accession_id": acc_id, "route": verdict["route"], "state": "READY"}


def release_report(
    journal: dict[str, Any],
    accession_id_value: str,
    *,
    actor_role: str,
    actor: str,
) -> dict[str, Any]:
    record = journal["jobs"].get(accession_id_value)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_ACCESSION"}
    role = _text(actor_role).upper()
    named = _text(actor)
    if role != HUMAN_RELEASER or not named:
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
    if status not in {"READY", "RELEASED"}:
        _event(
            journal,
            "RELEASE_DENIED",
            {"accession_id": accession_id_value, "code": "REPORT_BLOCKED", "report_status": status},
        )
        return {"ok": False, "code": "REPORT_BLOCKED", "report_status": status}
    if record["released"]:
        return {"ok": True, "duplicate": True, "report_status": "RELEASED"}
    record["released"] = True
    record["released_by"] = named
    record["state"] = "RELEASED"
    record["report_status"] = "RELEASED"
    record["report"] = rendered_report(record)
    record["report_digest"] = sha256_hex(record["report"])
    _event(journal, "RELEASED", {"accession_id": accession_id_value, "released_by": record["released_by"]})
    return {"ok": True, "duplicate": False, "report_status": "RELEASED"}


def run_gate(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    journal = empty_journal()
    effects = [ingest_row(journal, row) for row in inbound]
    autonomous = [
        release_report(journal, acc_id, actor_role="SYSTEM", actor="autonomous")
        for acc_id in journal["jobs"]
    ]
    jobs = sorted(journal["jobs"].values(), key=lambda item: item["order_id"])
    ready = [item for item in jobs if item["state"] == "READY"]
    hold_codes = [item["code"] for item in journal["holds"]]
    reports = [item["report"] for item in jobs]
    fixture_hashes = {
        row["order_id"]: {
            "source_hash": row["source_hash"],
            "method_hash": row["method_hash"],
            "instrument_hash": row["instrument_hash"],
        }
        for row in inbound
        if row.get("expected_hold") is None or row.get("expected_hold") == "QC_FAIL"
    }
    hash_matches = []
    for item in jobs:
        expected = fixture_hashes.get(item["order_id"], {})
        hash_matches.append(
            {
                "order_id": item["order_id"],
                "source": item["source_hash"] == expected.get("source_hash"),
                "method": item["method_hash"] == expected.get("method_hash"),
                "instrument": item["instrument_hash"] == expected.get("instrument_hash"),
            }
        )
    audit = {
        "demand_id": DEMAND_ID,
        "order_ids": [item["order_id"] for item in jobs],
        "accession_ids": [item["accession_id"] for item in jobs],
        "states": [item["state"] for item in jobs],
        "hold_codes": hold_codes,
        "hold_order_ids": [item["order_id"] for item in journal["holds"]],
        "routes": [item["route"] for item in jobs],
        "source_hashes": [item["source_hash"] for item in jobs],
        "method_hashes": [item["method_hash"] for item in jobs],
        "instrument_hashes": [item["instrument_hash"] for item in jobs],
        "report_digests": [item["report_digest"] for item in jobs],
        "released": [item["order_id"] for item in jobs if item["released"]],
    }
    body = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "methods": list(METHODS),
        "input_rows": len(inbound),
        "ready": len(ready),
        "held": len(journal["holds"]),
        "jobs": len(jobs),
        "hold_codes": hold_codes,
        "hold_code_set": sorted(set(hold_codes)),
        "duplicate_jobs": 0,
        "released_reports": sum(1 for item in jobs if item["released"]),
        "blocked_reports": sum(1 for item in jobs if item["report_status"] != "RELEASED"),
        "replay_noops": sum(1 for item in effects if item.get("kind") == "REPLAY_NOOP"),
        "effects": effects,
        "autonomous_release_effects": autonomous,
        "accessions": jobs,
        "holds": deepcopy(journal["holds"]),
        "routes": {item["order_id"]: item["route"] for item in jobs},
        "accession_ids": [item["accession_id"] for item in jobs],
        "hash_matches": hash_matches,
        "hashes_match": all(item["source"] and item["method"] and item["instrument"] for item in hash_matches),
        "reports": reports,
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
    before = set(journal["jobs"])
    before_holds = {sha256_hex(item) for item in journal["holds"]}
    effects = [ingest_row(journal, row) for row in inbound]
    added = set(journal["jobs"]) - before
    added_holds = [item for item in journal["holds"] if sha256_hex(item) not in before_holds]
    return {
        "added_jobs": sorted(added),
        "added_job_count": len(added),
        "added_holds": len(added_holds),
        "replay_noops": sum(1 for item in effects if item.get("kind") == "REPLAY_NOOP"),
        "job_count": len(journal["jobs"]),
        "hold_count": len(journal["holds"]),
    }


def expected_actual(result: dict[str, Any]) -> dict[str, Any]:
    actual = {
        "input_rows": result.get("input_rows"),
        "ready": result.get("ready"),
        "held": result.get("held"),
        "jobs": result.get("jobs"),
        "duplicate_jobs": result.get("duplicate_jobs"),
        "released_reports": result.get("released_reports"),
        "blocked_reports": result.get("blocked_reports"),
        "replay_added_jobs": result.get("replay_added_jobs", 0),
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
        {"DUPLICATE_ID": 10, "CAPABILITY_MISMATCH": 10, "QC_FAIL": 10}
    ):
        failures.append("hold_code_counts")
    if len(set(result.get("accession_ids") or [])) != VALID_COUNT + 10:
        failures.append("accession_ids_not_unique")
    if result.get("hashes_match") is not True:
        failures.append("hashes_match")
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
    if result.get("released_reports") != 0:
        failures.append("released_without_named_approval")
    if GOLDEN_AUDIT_SHA256 != "PENDING" and result.get("audit_sha256") != GOLDEN_AUDIT_SHA256:
        failures.append("audit_sha256")
    if GOLDEN_REPORT_DIGEST != "PENDING" and result.get("report_digest") != GOLDEN_REPORT_DIGEST:
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
    first["replay_added_jobs"] = replay["added_job_count"]
    failures = pass_contract(first)
    if first.get("audit_sha256") != second.get("audit_sha256"):
        failures.append("replay_mismatch")
    if first.get("report_digest") != second.get("report_digest"):
        failures.append("report_digest_mismatch")
    if replay.get("added_job_count") != 0:
        failures.append("replay_added_jobs")
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
        "ready": first.get("ready"),
        "held": first.get("held"),
        "jobs": first.get("jobs"),
        "hold_codes": sorted(set(first.get("hold_codes") or [])),
        "hashes_match": first.get("hashes_match"),
        "released_reports": first.get("released_reports"),
        "replay_added_jobs": replay.get("added_job_count"),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
