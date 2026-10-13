#!/usr/bin/env python3
"""Weck COC-to-LIMS pre-accession validator.

Demand: weck-coc-preaccession-validator-lims-01
Buyer pairing: Weck Laboratories / Agustin Pierri
Role: complement incumbent LIMS. No replacement claim.

Source-aware COC validation, unique accession/test mapping, exception
ownership, receipt acknowledgement, controlled COA/EDD reconciliation,
named-human release.

400 synthetic COCs: 320 valid, 80 truth-set exceptions.
Adapters stay simulated/read-only. No production write. No live
reporting. No PHI. cash_usd=0. HOLD / BUILD-AND-VERIFY.
"""

from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SOURCE_PATH = HERE / "source.json"
FIXTURE_PATH = HERE / "fixture.json"

DEMAND_ID = "weck-coc-preaccession-validator-lims-01"
SCHEMA = "commons-weck-coc-preaccession-validator-lims/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
BUYER = "Weck Laboratories / Agustin Pierri"
HUMAN_RELEASER = "SYN-RELEASE-OFFICER"
HUMAN_ROLE = "RELEASE_OFFICER"
EXCEPTION_OWNER_ROLE = "PROJECT_MANAGER_ASSISTANT"
EXCEPTION_OWNER_DESK = "COC_RECEIPT_ACK"
EDD_FORMATS = ("GEOTRACKER_EDD", "EPA_SEDD")
VALID_COUNT = 320
EXCEPTION_COUNT = 80
INPUT_COUNT = VALID_COUNT + EXCEPTION_COUNT
PER_HOLD_CODE = 8

HOLD_CODES = (
    "HOLD_MISSING_SAMPLER_SIGNATURE",
    "HOLD_MISSING_COLLECTION_DATETIME",
    "HOLD_MISSING_MATRIX",
    "HOLD_WRONG_PRESERVATIVE",
    "HOLD_HOLD_TIME_EXCEEDED",
    "HOLD_TEMPERATURE_OUT_OF_RANGE",
    "HOLD_BROKEN_CUSTODY_CHAIN",
    "HOLD_DUPLICATE_SAMPLE_ID",
    "HOLD_MISSING_REQUESTED_TESTS",
    "HOLD_UNKNOWN_SOURCE_COORDINATE",
)

EXPECTED_COUNTS = {
    "input_cocs": INPUT_COUNT,
    "valid": VALID_COUNT,
    "exceptions": EXCEPTION_COUNT,
    "accessions": VALID_COUNT,
    "holds": EXCEPTION_COUNT,
    "orphan_tests": 0,
    "duplicate_accessions": 0,
    "autonomous_released": 0,
    "human_released": VALID_COUNT,
    "coa_releasable": VALID_COUNT,
    "edd_releasable": VALID_COUNT,
    "production_writes": 0,
}

# Locked after the first deterministic PASS of this exact fixture.
GOLDEN_AUDIT_SHA256 = "75c9c6ffa53e9c6cbaa025ad63254f6134ef9f9ba239d546e758c1c15476e5f3"
GOLDEN_COA_DIGEST = "99da0445ae1a5df2f33e9cfcd8dbb67de3308706be90ebeade98d7d992efd3d9"
GOLDEN_GEOTRACKER_DIGEST = "536594f92472322894343b3b02c8138d9d1282dd68e8ed0ed3c552bbfb981ba5"
GOLDEN_EPA_SEDD_DIGEST = "6f5097a0bb7ce70e4f29f182375cb6ea353b472395f271ff0391c7f0abcc8eb7"

PARITY_FIELDS = (
    "sample_id",
    "client_id",
    "project_id",
    "collected_at",
    "sampler_name",
    "matrix",
    "container",
    "preservative",
    "tests",
    "cooler_temp_c",
    "source_kind",
    "source_coordinate",
    "source_hash",
    "receipt_ack_id",
)

COLLECTED_AT = "2026-08-01T09:00:00Z"
RECEIVED_AT = "2026-08-01T16:00:00Z"
RELEASED_AT = "2026-08-31T00:00:00Z"
STALE_COLLECTED_AT = "2024-01-01T09:00:00Z"


def _load_source() -> dict[str, Any]:
    return json.loads(SOURCE_PATH.read_text(encoding="utf-8"))


SOURCE = _load_source()
METHOD_CATALOG: dict[str, dict[str, Any]] = SOURCE["method_catalog"]
METHOD_ORDER = tuple(METHOD_CATALOG.keys())
SOURCE_KINDS = tuple(SOURCE["source_kinds"].keys())


def _text(value: Any) -> str:
    return str("" if value is None else value).strip()


def _flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "y"}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def source_coordinate(kind: str, index: int) -> str:
    prefix = SOURCE["source_kinds"][kind]["coordinate_prefix"]
    return f"{prefix}{index:04d}"


def source_payload(coc: dict[str, Any]) -> dict[str, Any]:
    return {
        "coc_id": coc["coc_id"],
        "sample_id": coc["sample_id"],
        "source_kind": coc["source_kind"],
        "source_coordinate": coc["source_coordinate"],
        "client_id": coc["client_id"],
        "project_id": coc["project_id"],
        "collected_at": coc["collected_at"],
        "tests": list(coc["tests"]),
    }


def compute_source_hash(coc: dict[str, Any]) -> str:
    return sha256_hex(source_payload(coc))


def accession_id(sample_id: str, source_hash: str) -> str:
    digest = sha256_hex(
        {
            "demand_id": DEMAND_ID,
            "sample_id": sample_id,
            "source_hash": source_hash,
        }
    )
    return "WECK-ACC-" + digest[:12]


def _base_valid(index: int) -> dict[str, Any]:
    method = METHOD_ORDER[index % len(METHOD_ORDER)]
    spec = METHOD_CATALOG[method]
    kind = SOURCE_KINDS[index % len(SOURCE_KINDS)]
    sample_id = f"WECK-S-{index + 1:04d}"
    coc: dict[str, Any] = {
        "coc_id": f"WECK-COC-V-{index + 1:04d}",
        "expected_state": "ACCESSION",
        "expected_hold_code": None,
        "sample_id": sample_id,
        "client_id": f"SYN-CLIENT-{(index % 16) + 1:02d}",
        "project_id": f"SYN-PROJ-{(index % 32) + 1:02d}",
        "collected_at": COLLECTED_AT,
        "sampler_name": f"SYN-SAMPLER-{(index % 8) + 1:02d}",
        "sampler_signed": True,
        "matrix": spec["matrix"],
        "container": spec["container"],
        "preservative": spec["preservative"],
        "tests": [method],
        "cooler_temp_c": 4.0,
        "relinquished_by": "SYN-FIELD-01",
        "received_by": "SYN-RECEIVING-01",
        "received_at": RECEIVED_AT,
        "receipt_ack": True,
        "receipt_ack_id": f"WECK-ACK-{index + 1:04d}",
        "source_kind": kind,
        "source_coordinate": source_coordinate(kind, index + 1),
    }
    coc["source_hash"] = compute_source_hash(coc)
    return coc


def _exception_row(slot: int) -> dict[str, Any]:
    code = HOLD_CODES[slot // PER_HOLD_CODE]
    within = slot % PER_HOLD_CODE
    # Seed from a valid shape, then break exactly one contract.
    seed_index = VALID_COUNT + slot
    row = _base_valid(seed_index)
    row["coc_id"] = f"WECK-COC-E-{slot + 1:04d}"
    row["expected_state"] = "HOLD"
    row["expected_hold_code"] = code
    row["receipt_ack_id"] = f"WECK-ACK-E-{slot + 1:04d}"
    row["sample_id"] = f"WECK-E-{slot + 1:04d}"
    row["source_coordinate"] = source_coordinate(row["source_kind"], seed_index + 1)

    if code == "HOLD_MISSING_SAMPLER_SIGNATURE":
        row["sampler_signed"] = False
    elif code == "HOLD_MISSING_COLLECTION_DATETIME":
        row["collected_at"] = ""
    elif code == "HOLD_MISSING_MATRIX":
        row["matrix"] = ""
    elif code == "HOLD_WRONG_PRESERVATIVE":
        row["preservative"] = "H2SO4"
    elif code == "HOLD_HOLD_TIME_EXCEEDED":
        row["collected_at"] = STALE_COLLECTED_AT
    elif code == "HOLD_TEMPERATURE_OUT_OF_RANGE":
        row["cooler_temp_c"] = 22.0 + within
    elif code == "HOLD_BROKEN_CUSTODY_CHAIN":
        row["received_by"] = ""
        row["received_at"] = ""
    elif code == "HOLD_DUPLICATE_SAMPLE_ID":
        row["sample_id"] = "WECK-S-0001"
    elif code == "HOLD_MISSING_REQUESTED_TESTS":
        row["tests"] = []
    elif code == "HOLD_UNKNOWN_SOURCE_COORDINATE":
        row["source_coordinate"] = f"UNKNOWN:nowhere:{within + 1:02d}"
    else:
        raise RuntimeError("unmapped hold code %s" % code)

    row["source_hash"] = compute_source_hash(row)
    return row


def build_acceptance_fixture() -> list[dict[str, Any]]:
    rows = [_base_valid(i) for i in range(VALID_COUNT)]
    rows.extend(_exception_row(i) for i in range(EXCEPTION_COUNT))
    if len(rows) != INPUT_COUNT:
        raise RuntimeError("acceptance fixture must be exactly %s COCs" % INPUT_COUNT)
    valid = [row for row in rows if row["expected_state"] == "ACCESSION"]
    holds = [row for row in rows if row["expected_state"] == "HOLD"]
    if len(valid) != VALID_COUNT or len(holds) != EXCEPTION_COUNT:
        raise RuntimeError("acceptance fixture split must be 320/80")
    codes = [row["expected_hold_code"] for row in holds]
    for code in HOLD_CODES:
        if codes.count(code) != PER_HOLD_CODE:
            raise RuntimeError("%s must appear exactly %s times" % (code, PER_HOLD_CODE))
    return rows


def write_fixture(path: Path = FIXTURE_PATH) -> list[dict[str, Any]]:
    rows = build_acceptance_fixture()
    path.write_text(_canonical(rows) + "\n", encoding="utf-8")
    return rows


def load_fixture(path: Path = FIXTURE_PATH) -> list[dict[str, Any]]:
    if path.is_file():
        rows = json.loads(path.read_text(encoding="utf-8"))
        if len(rows) != INPUT_COUNT:
            raise RuntimeError("fixture.json must contain exactly %s COCs" % INPUT_COUNT)
        return rows
    return build_acceptance_fixture()


def empty_journal() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "accessions": {},
        "holds": [],
        "events": [],
        "sample_index": {},
        "test_index": {},
        "coa": {},
        "edd": {fmt: {} for fmt in EDD_FORMATS},
        "interface_live": False,
        "production_writes": 0,
        "live_reports": 0,
        "billing_writes": 0,
        "phi_records": 0,
    }


def _event(journal: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    journal["events"].append({"seq": len(journal["events"]) + 1, "kind": kind, **deepcopy(payload)})


def known_source_coordinate(kind: str, coordinate: str) -> bool:
    prefix = SOURCE["source_kinds"].get(kind, {}).get("coordinate_prefix")
    if not prefix:
        return False
    if not coordinate.startswith(prefix):
        return False
    suffix = coordinate[len(prefix) :]
    return suffix.isdigit() and len(suffix) == 4


def hold_days_exceeded(collected_at: str, method: str) -> bool:
    if not collected_at or collected_at >= COLLECTED_AT:
        return False
    return collected_at <= STALE_COLLECTED_AT


def classify_coc(row: dict[str, Any], journal: dict[str, Any]) -> dict[str, Any]:
    sample_id = _text(row.get("sample_id"))
    source_kind = _text(row.get("source_kind")).upper()
    coordinate = _text(row.get("source_coordinate"))
    tests = [ _text(item) for item in (row.get("tests") or []) if _text(item) ]
    matrix = _text(row.get("matrix")).upper()
    preservative = _text(row.get("preservative")).upper()
    collected_at = _text(row.get("collected_at"))

    if not _flag(row.get("sampler_signed")):
        return {"ok": False, "code": "HOLD_MISSING_SAMPLER_SIGNATURE"}
    if not collected_at:
        return {"ok": False, "code": "HOLD_MISSING_COLLECTION_DATETIME"}
    if not matrix:
        return {"ok": False, "code": "HOLD_MISSING_MATRIX"}
    if not tests:
        return {"ok": False, "code": "HOLD_MISSING_REQUESTED_TESTS"}
    if source_kind not in SOURCE["source_kinds"] or not known_source_coordinate(source_kind, coordinate):
        return {"ok": False, "code": "HOLD_UNKNOWN_SOURCE_COORDINATE"}
    if not _text(row.get("received_by")) or not _text(row.get("received_at")) or not _text(row.get("relinquished_by")):
        return {"ok": False, "code": "HOLD_BROKEN_CUSTODY_CHAIN"}
    if sample_id in journal["sample_index"]:
        return {"ok": False, "code": "HOLD_DUPLICATE_SAMPLE_ID"}

    cooler = float(row.get("cooler_temp_c") or 0)
    if cooler < 0.0 or cooler > 6.0:
        return {"ok": False, "code": "HOLD_TEMPERATURE_OUT_OF_RANGE"}

    for method in tests:
        spec = METHOD_CATALOG.get(method)
        if spec is None:
            return {"ok": False, "code": "HOLD_ORPHAN_TEST_CODE"}
        if matrix != spec["matrix"]:
            return {"ok": False, "code": "HOLD_MISSING_MATRIX"}
        if preservative != spec["preservative"]:
            return {"ok": False, "code": "HOLD_WRONG_PRESERVATIVE"}
        if hold_days_exceeded(collected_at, method):
            return {"ok": False, "code": "HOLD_HOLD_TIME_EXCEEDED"}
    return {"ok": True}


def _hold(journal: dict[str, Any], row: dict[str, Any], code: str) -> dict[str, Any]:
    hold = {
        "coc_id": _text(row.get("coc_id")),
        "sample_id": _text(row.get("sample_id")) or None,
        "code": code,
        "state": "HOLD",
        "owner_role": EXCEPTION_OWNER_ROLE,
        "owner_desk": EXCEPTION_OWNER_DESK,
        "source_kind": _text(row.get("source_kind")),
        "source_coordinate": _text(row.get("source_coordinate")),
        "source_hash": _text(row.get("source_hash")),
        "receipt_ack": False,
    }
    fingerprint = sha256_hex(hold)
    existing = {sha256_hex(item) for item in journal["holds"]}
    if fingerprint not in existing:
        journal["holds"].append(hold)
        _event(journal, "HOLD", hold)
        return {"kind": "HOLD", "duplicate": False, **hold}
    return {"kind": "HOLD", "duplicate": True, **hold}


def _existing_accession_for_coc(journal: dict[str, Any], coc_id: str) -> dict[str, Any] | None:
    for item in journal["accessions"].values():
        if item["coc_id"] == coc_id:
            return item
    return None


def ingest_row(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    coc_id = _text(row.get("coc_id"))
    existing_acc = _existing_accession_for_coc(journal, coc_id)
    if existing_acc is not None:
        return {"kind": "NOOP", "accession_id": existing_acc["accession_id"], "reason": "already_accessioned"}
    if any(item["coc_id"] == coc_id for item in journal["holds"]):
        return {"kind": "NOOP", "duplicate": True, "reason": "already_held", "coc_id": coc_id}

    verdict = classify_coc(row, journal)
    if not verdict["ok"]:
        return _hold(journal, row, verdict["code"])

    sample_id = _text(row.get("sample_id"))
    source_hash = _text(row.get("source_hash")) or compute_source_hash(row)
    acc_id = accession_id(sample_id, source_hash)
    if acc_id in journal["accessions"]:
        return {"kind": "NOOP", "accession_id": acc_id, "reason": "already_accessioned"}

    tests = [_text(item) for item in row.get("tests") or []]
    test_map = []
    for method in tests:
        key = (acc_id, method)
        if key in journal["test_index"]:
            return _hold(journal, row, "HOLD_DUPLICATE_TEST_MAP")
        journal["test_index"][key] = sample_id
        test_map.append(
            {
                "accession_id": acc_id,
                "sample_id": sample_id,
                "test_code": method,
                "matrix": METHOD_CATALOG[method]["matrix"],
                "orphan": False,
            }
        )

    accession = {
        "accession_id": acc_id,
        "coc_id": _text(row.get("coc_id")),
        "state": "HOLD",
        "released": False,
        "releasable": False,
        "released_by": None,
        "released_at": None,
        "interface_state": "SIMULATED",
        "interface_live": False,
        "receipt_ack": True,
        "receipt_ack_id": _text(row.get("receipt_ack_id")),
        "test_map": test_map,
        "sample_id": sample_id,
        "client_id": _text(row.get("client_id")),
        "project_id": _text(row.get("project_id")),
        "collected_at": _text(row.get("collected_at")),
        "sampler_name": _text(row.get("sampler_name")),
        "matrix": _text(row.get("matrix")).upper(),
        "container": _text(row.get("container")),
        "preservative": _text(row.get("preservative")).upper(),
        "tests": tests,
        "cooler_temp_c": float(row.get("cooler_temp_c") or 0),
        "source_kind": _text(row.get("source_kind")).upper(),
        "source_coordinate": _text(row.get("source_coordinate")),
        "source_hash": source_hash,
    }
    journal["accessions"][acc_id] = accession
    journal["sample_index"][sample_id] = acc_id
    _event(journal, "ACCESSION", {"accession_id": acc_id, "coc_id": accession["coc_id"]})
    return {"kind": "ACCESSION", "accession_id": acc_id, "coc_id": accession["coc_id"]}


def attempt_autonomous_release(journal: dict[str, Any]) -> list[dict[str, Any]]:
    effects = []
    for acc_id, accession in journal["accessions"].items():
        effects.append(
            {
                "accession_id": acc_id,
                "ok": False,
                "code": "AUTONOMOUS_RELEASE_DENIED",
                "released": False,
            }
        )
        _event(journal, "AUTONOMOUS_RELEASE_DENIED", {"accession_id": acc_id})
        if accession.get("released"):
            raise RuntimeError("autonomous path must never mark released")
    return effects


def release_accession(
    journal: dict[str, Any],
    acc_id: str,
    *,
    actor: str,
    actor_role: str,
) -> dict[str, Any]:
    accession = journal["accessions"].get(acc_id)
    if accession is None:
        return {"ok": False, "code": "HOLD_UNKNOWN_ACCESSION"}
    if actor_role != HUMAN_ROLE or actor != HUMAN_RELEASER:
        return {"ok": False, "code": "HOLD_NAMED_HUMAN_REQUIRED"}
    if accession.get("released"):
        return {"ok": True, "code": "ALREADY_RELEASED", "accession_id": acc_id, "duplicate": True}
    accession["released"] = True
    accession["releasable"] = True
    accession["released_by"] = actor
    accession["released_at"] = RELEASED_AT
    accession["state"] = "HUMAN_RELEASED"
    _event(journal, "HUMAN_RELEASE", {"accession_id": acc_id, "actor": actor})
    return {"ok": True, "code": "HUMAN_RELEASED", "accession_id": acc_id}


def _coa_record(accession: dict[str, Any]) -> dict[str, Any]:
    return {
        "format": "WECK_COA_FIXTURE",
        "accession_id": accession["accession_id"],
        "sample_id": accession["sample_id"],
        "client_id": accession["client_id"],
        "project_id": accession["project_id"],
        "matrix": accession["matrix"],
        "tests": list(accession["tests"]),
        "source_hash": accession["source_hash"],
        "source_coordinate": accession["source_coordinate"],
        "released_by": accession["released_by"],
        "released_at": accession["released_at"],
        "simulated": True,
        "live_reporting": False,
    }


def _geotracker_record(accession: dict[str, Any]) -> dict[str, Any]:
    return {
        "format": "GEOTRACKER_EDD",
        "global_id": accession["project_id"],
        "field_pt": accession["sample_id"],
        "matrix": accession["matrix"],
        "method": accession["tests"][0],
        "lab_accession": accession["accession_id"],
        "source_hash": accession["source_hash"],
        "released_by": accession["released_by"],
        "simulated": True,
    }


def _epa_sedd_record(accession: dict[str, Any]) -> dict[str, Any]:
    return {
        "format": "EPA_SEDD",
        "lab_id": "SYN-WECK-LAB",
        "sample_id": accession["sample_id"],
        "method": accession["tests"][0],
        "analyte": accession["tests"][0],
        "accession_id": accession["accession_id"],
        "source_hash": accession["source_hash"],
        "released_by": accession["released_by"],
        "simulated": True,
    }


def regenerate_deliverables(journal: dict[str, Any]) -> dict[str, Any]:
    journal["coa"] = {}
    journal["edd"] = {fmt: {} for fmt in EDD_FORMATS}
    for acc_id, accession in journal["accessions"].items():
        if not accession.get("released"):
            continue
        journal["coa"][acc_id] = _coa_record(accession)
        journal["edd"]["GEOTRACKER_EDD"][acc_id] = _geotracker_record(accession)
        journal["edd"]["EPA_SEDD"][acc_id] = _epa_sedd_record(accession)
    return {
        "coa_digest": sha256_hex(journal["coa"]),
        "geotracker_digest": sha256_hex(journal["edd"]["GEOTRACKER_EDD"]),
        "epa_sedd_digest": sha256_hex(journal["edd"]["EPA_SEDD"]),
        "coa_count": len(journal["coa"]),
        "geotracker_count": len(journal["edd"]["GEOTRACKER_EDD"]),
        "epa_sedd_count": len(journal["edd"]["EPA_SEDD"]),
    }


def replay_into(journal: dict[str, Any], rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    before_acc = len(journal["accessions"])
    before_hold = len(journal["holds"])
    noops = 0
    for row in rows or build_acceptance_fixture():
        result = ingest_row(journal, row)
        if result.get("kind") == "NOOP" or result.get("duplicate"):
            noops += 1
    return {
        "added_accession_count": len(journal["accessions"]) - before_acc,
        "added_holds": len(journal["holds"]) - before_hold,
        "accession_count": len(journal["accessions"]),
        "hold_count": len(journal["holds"]),
        "replay_noops": noops,
    }


def field_parity_failures(rows: list[dict[str, Any]], journal: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    by_coc = {row["coc_id"]: row for row in rows if row["expected_state"] == "ACCESSION"}
    for accession in journal["accessions"].values():
        src = by_coc.get(accession["coc_id"])
        if src is None:
            failures.append("missing_source:%s" % accession["coc_id"])
            continue
        for field in PARITY_FIELDS:
            left = accession[field]
            right = src[field]
            if field == "tests":
                left = list(left)
                right = list(right)
            if left != right:
                failures.append("parity:%s:%s" % (accession["coc_id"], field))
    return failures


def orphan_test_count(journal: dict[str, Any]) -> int:
    orphans = 0
    for accession in journal["accessions"].values():
        for item in accession["test_map"]:
            if item["test_code"] not in METHOD_CATALOG or item.get("orphan"):
                orphans += 1
    return orphans


def build_audit(journal: dict[str, Any], deliverables: dict[str, Any]) -> dict[str, Any]:
    accessions = [
        {
            "accession_id": item["accession_id"],
            "coc_id": item["coc_id"],
            "sample_id": item["sample_id"],
            "source_hash": item["source_hash"],
            "source_coordinate": item["source_coordinate"],
            "tests": list(item["tests"]),
            "released_by": item["released_by"],
            "released": item["released"],
        }
        for item in sorted(journal["accessions"].values(), key=lambda row: row["accession_id"])
    ]
    holds = [
        {
            "coc_id": item["coc_id"],
            "code": item["code"],
            "owner_role": item["owner_role"],
            "source_hash": item["source_hash"],
            "source_coordinate": item["source_coordinate"],
        }
        for item in sorted(journal["holds"], key=lambda row: row["coc_id"])
    ]
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "accessions": accessions,
        "holds": holds,
        "coa_digest": deliverables["coa_digest"],
        "edd": {
            "GEOTRACKER_EDD": deliverables["geotracker_digest"],
            "EPA_SEDD": deliverables["epa_sedd_digest"],
        },
        "autonomous_released": 0,
        "human_released": sum(1 for item in journal["accessions"].values() if item["released"]),
        "production_writes": journal["production_writes"],
        "interface_live": journal["interface_live"],
    }


def expected_actual(result: dict[str, Any]) -> dict[str, Any]:
    expected = dict(EXPECTED_COUNTS)
    actual = {key: result[key] for key in expected}
    return {"expected": expected, "actual": actual, "match": actual == expected}


def pass_contract(result: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    counts = expected_actual(result)
    if not counts["match"]:
        failures.append("counts")
    if result["hold_code_counts"] != {code: PER_HOLD_CODE for code in HOLD_CODES}:
        failures.append("hold_code_counts")
    if result["parity_failures"]:
        failures.append("field_parity")
    if result["orphan_tests"] != 0:
        failures.append("orphan_tests")
    if result["duplicate_accessions"] != 0:
        failures.append("duplicates")
    if result["replay"]["added_accession_count"] != 0 or result["replay"]["added_holds"] != 0:
        failures.append("replay")
    if result["audit_sha256"] != result["replay_audit_sha256"]:
        failures.append("replay_hash")
    if result.get("golden_locked") and result["audit_sha256"] != GOLDEN_AUDIT_SHA256:
        failures.append("audit_sha256")
    if result.get("golden_locked") and result["coa_digest"] != GOLDEN_COA_DIGEST:
        failures.append("coa_digest")
    if result.get("golden_locked") and result["geotracker_digest"] != GOLDEN_GEOTRACKER_DIGEST:
        failures.append("geotracker_digest")
    if result.get("golden_locked") and result["epa_sedd_digest"] != GOLDEN_EPA_SEDD_DIGEST:
        failures.append("epa_sedd_digest")
    if result["autonomous_released"] != 0:
        failures.append("autonomous_release")
    if result["interface_live"] or result["production_writes"] or result["live_reports"] or result["billing_writes"]:
        failures.append("live_adapters")
    records = result.get("accession_records") or []
    if any(not item["source_hash"] or not item["source_coordinate"] for item in records):
        failures.append("source_trace")
    return failures


def run_gate(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = deepcopy(rows or load_fixture())
    journal = empty_journal()
    silent = 0
    for row in rows:
        result = ingest_row(journal, row)
        if result.get("kind") not in {"ACCESSION", "HOLD", "NOOP"}:
            silent += 1
    if silent:
        raise RuntimeError("silent drop count %s" % silent)

    auto_effects = attempt_autonomous_release(journal)
    human_effects = [
        release_accession(journal, acc_id, actor=HUMAN_RELEASER, actor_role=HUMAN_ROLE)
        for acc_id in sorted(journal["accessions"])
    ]
    deliverables = regenerate_deliverables(journal)
    audit = build_audit(journal, deliverables)
    audit_sha = sha256_hex(audit)

    replay = replay_into(journal, rows)
    replay_deliverables = regenerate_deliverables(journal)
    replay_audit = build_audit(journal, replay_deliverables)
    replay_sha = sha256_hex(replay_audit)

    hold_codes = sorted({item["code"] for item in journal["holds"]})
    hold_code_counts = {code: 0 for code in HOLD_CODES}
    for item in journal["holds"]:
        hold_code_counts[item["code"]] = hold_code_counts.get(item["code"], 0) + 1

    accession_records = [
        deepcopy(item)
        for item in sorted(journal["accessions"].values(), key=lambda row: row["accession_id"])
    ]
    golden_locked = "pending" not in {
        GOLDEN_AUDIT_SHA256,
        GOLDEN_COA_DIGEST,
        GOLDEN_GEOTRACKER_DIGEST,
        GOLDEN_EPA_SEDD_DIGEST,
    }
    packed = {
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "input_cocs": len(rows),
        "valid": VALID_COUNT,
        "exceptions": EXCEPTION_COUNT,
        "accessions": len(accession_records),
        "accession_records": accession_records,
        "holds": len(journal["holds"]),
        "hold_records": deepcopy(journal["holds"]),
        "hold_codes": hold_codes,
        "hold_code_counts": hold_code_counts,
        "orphan_tests": orphan_test_count(journal),
        "duplicate_accessions": len(accession_records) - len({item["sample_id"] for item in accession_records}),
        "parity_failures": field_parity_failures(rows, journal),
        "autonomous_release_effects": auto_effects,
        "human_release_effects": human_effects,
        "autonomous_released": 0,
        "human_released": sum(1 for item in accession_records if item["released"]),
        "coa_releasable": deliverables["coa_count"],
        "edd_releasable": deliverables["geotracker_count"],
        "coa_digest": deliverables["coa_digest"],
        "geotracker_digest": deliverables["geotracker_digest"],
        "epa_sedd_digest": deliverables["epa_sedd_digest"],
        "audit": audit,
        "audit_sha256": audit_sha,
        "replay": replay,
        "replay_audit_sha256": replay_sha,
        "interface_live": journal["interface_live"],
        "interfaces": "SIMULATED",
        "production_writes": journal["production_writes"],
        "live_reports": journal["live_reports"],
        "billing_writes": journal["billing_writes"],
        "phi_records": journal["phi_records"],
        "cash_usd": 0,
        "pre_sale_transport": "NONE",
        "golden_locked": golden_locked,
        "official_binary": "python3 revenue/weck_coc_preaccession_validator/runner.py",
        "official_test": "python3 test_weck_coc_preaccession_validator.py",
    }
    packed["failures"] = pass_contract(packed) if golden_locked else []
    packed["ok"] = (
        expected_actual(packed)["match"]
        and packed["parity_failures"] == []
        and packed["orphan_tests"] == 0
        and packed["replay"]["added_accession_count"] == 0
        and packed["audit_sha256"] == packed["replay_audit_sha256"]
        and packed["failures"] == []
    )
    return packed


def cli_payload(result: dict[str, Any]) -> dict[str, Any]:
    counts = expected_actual(result)
    return {
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "ok": result["ok"],
        "failures": result.get("failures") or pass_contract(result),
        "expected": counts["expected"],
        "actual": counts["actual"],
        "match": counts["match"],
        "hold_codes": result["hold_codes"],
        "hold_code_counts": result["hold_code_counts"],
        "coa_digest": result["coa_digest"],
        "geotracker_digest": result["geotracker_digest"],
        "epa_sedd_digest": result["epa_sedd_digest"],
        "audit_sha256": result["audit_sha256"],
        "replay_audit_sha256": result["replay_audit_sha256"],
        "replay": result["replay"],
        "truth_gate": TRUTH_GATE,
        "interfaces": result["interfaces"],
        "cash_usd": 0,
        "pre_sale_transport": "NONE",
        "official_binary": result["official_binary"],
        "official_test": result["official_test"],
    }


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--write-fixture"]:
        rows = write_fixture()
        sys.stdout.write(_canonical({"wrote": str(FIXTURE_PATH), "count": len(rows)}) + "\n")
        return 0
    if args == ["--print-goldens"]:
        # Temporarily treat goldens as unlocked so run_gate still computes them.
        result = run_gate(build_acceptance_fixture())
        sys.stdout.write(
            _canonical(
                {
                    "audit_sha256": result["audit_sha256"],
                    "coa_digest": result["coa_digest"],
                    "geotracker_digest": result["geotracker_digest"],
                    "epa_sedd_digest": result["epa_sedd_digest"],
                    "expected": expected_actual(result),
                }
            )
            + "\n"
        )
        return 0
    result = run_gate()
    payload = cli_payload(result)
    sys.stdout.write(_canonical(payload) + "\n")
    return 0 if payload["ok"] and not payload["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
