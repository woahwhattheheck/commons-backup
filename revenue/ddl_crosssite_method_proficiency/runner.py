#!/usr/bin/env python3
"""DDL cross-site controlled-method + proficiency-comparison module.

Demand: ddl-crosssite-method-proficiency-lims-01
Buyer pairing: DDL, Inc. / Suzette Glennon
Slack OPEN: #build-demand 1788149883.630329

Working program, not a look-inside souvenir. Intake → facility scope →
controlled method/version → instrument/operator linkage → paired-site
comparison → exception review → evidence pack → HOLD on the 40 invalid
site/method combinations → named-human report release.

160 synthetic studies: 120 valid shared-scope pairs plus 40 deliberately
invalid site/method combinations. Minnesota, California, and New Jersey
under one QMS. Every valid study receives the exact controlled
method/version. All 40 invalid combinations block with the expected
reason. Paired-site results reproduce the signed truth table. Comparison
flags match expected. Every result links facility, instrument, operator,
method, and report. Replay writes zero duplicate study or evidence
events. Named human required before any report release. No automatic
release.

QMS / LIMS / instrument / report adapters stay simulated and read-only.
No live LIMS. No production writes. No accreditation claim. No outreach.
cash_usd=0. HOLD / BUILD-AND-VERIFY.

Official command:
    python3 ddl_crosssite_method_proficiency.py
    python3 revenue/ddl_crosssite_method_proficiency/runner.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

PACK = Path(__file__).resolve().parent
FIXTURE_PATH = PACK / "fixture.json"
STATE_PATH = PACK / "state" / "journal.json"
RECEIPT_DIR = PACK / "receipts"
RUN_RECEIPT_PATH = RECEIPT_DIR / "run.json"
STUDY_RECEIPT_PATH = RECEIPT_DIR / "studies.json"
HOLD_RECEIPT_PATH = RECEIPT_DIR / "holds.json"
COMPARISON_RECEIPT_PATH = RECEIPT_DIR / "comparisons.json"
EVIDENCE_RECEIPT_PATH = RECEIPT_DIR / "evidence.json"
AUDIT_RECEIPT_PATH = RECEIPT_DIR / "audit.json"
REPLAY_RECEIPT_PATH = RECEIPT_DIR / "replay.json"

DEMAND_ID = "ddl-crosssite-method-proficiency-lims-01"
SCHEMA = "commons-ddl-crosssite-method-proficiency-lims/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
BUYER = "DDL, Inc. / Suzette Glennon"
QMS = "DDL-QMS-ONE"
NAMED_ROLE = "NAMED_RELEASE_OFFICER"
NAMED_ACTOR = "SYN-DDL-RELEASE-OFFICER"
COMMAND = "python3 ddl_crosssite_method_proficiency.py"
TEST_COMMAND = "python3 test_ddl_crosssite_method_proficiency.py"
SEED = 20260831
OPEN_SLACK_TS = "1788149883.630329"

MN = "DDL_MN"
CA = "DDL_CA"
NJ = "DDL_NJ"
SITES = (MN, CA, NJ)
SITE_NAMES = {
    MN: "Minnesota",
    CA: "California",
    NJ: "New Jersey",
}
PAIRS = ((MN, CA), (CA, NJ), (MN, NJ))
PROGRAMS = ("SEAL_STRENGTH", "VISUAL", "DYE_PENETRATION", "DISTRIBUTION", "AGING")
ADAPTERS = ("QMS", "LIMS", "INSTRUMENT", "REPORT")
STAGES = (
    "INTAKE",
    "FACILITY_SCOPE",
    "CONTROLLED_METHOD",
    "INSTRUMENT_OPERATOR_LINK",
    "PAIRED_SITE_COMPARISON",
    "EXCEPTION_REVIEW",
    "EVIDENCE_PACK",
    "HUMAN_REPORT_RELEASE",
)

STUDY_COUNT = 160
VALID_COUNT = 120
BLOCKED_COUNT = 40
PER_HOLD = 8

HOLD_CODES = (
    "HOLD_FACILITY_OUT_OF_SCOPE",
    "HOLD_METHOD_VERSION_MISMATCH",
    "HOLD_INSTRUMENT_NOT_LINKED",
    "HOLD_OPERATOR_NOT_QUALIFIED",
    "HOLD_PAIR_NOT_SHARED_SCOPE",
)
FLAGS = ("MATCH", "FLAG_BIAS", "FLAG_PRECISION", "FLAG_OUTLIER")

METHODS: dict[str, dict[str, Any]] = {
    "CM_SEAL_F88": {
        "program": "SEAL_STRENGTH",
        "version": "DDL-QMS-F88-2025-06",
        "sites": (MN, CA, NJ),
        "nominal": 12.0,
        "tolerance": 0.15,
    },
    "CM_VISUAL": {
        "program": "VISUAL",
        "version": "DDL-QMS-VIS-2025-03",
        "sites": (MN, CA, NJ),
        "nominal": 100.0,
        "tolerance": 0.0,
    },
    "CM_DYE_F1929": {
        "program": "DYE_PENETRATION",
        "version": "DDL-QMS-F1929-2025-04",
        "sites": (MN, CA),
        "nominal": 0.0,
        "tolerance": 0.0,
    },
    "CM_DIST_D4169": {
        "program": "DISTRIBUTION",
        "version": "DDL-QMS-D4169-2025-02",
        "sites": (CA, NJ),
        "nominal": 50.0,
        "tolerance": 0.20,
    },
    "CM_AGING_F1980": {
        "program": "AGING",
        "version": "DDL-QMS-F1980-2025-01",
        "sites": (MN, NJ),
        "nominal": 30.0,
        "tolerance": 0.10,
    },
}

INSTRUMENTS: dict[tuple[str, str], str] = {
    (MN, "CM_SEAL_F88"): "DDL-MN-SEAL-01",
    (CA, "CM_SEAL_F88"): "DDL-CA-SEAL-01",
    (NJ, "CM_SEAL_F88"): "DDL-NJ-SEAL-01",
    (MN, "CM_VISUAL"): "DDL-MN-VIS-01",
    (CA, "CM_VISUAL"): "DDL-CA-VIS-01",
    (NJ, "CM_VISUAL"): "DDL-NJ-VIS-01",
    (MN, "CM_DYE_F1929"): "DDL-MN-DYE-01",
    (CA, "CM_DYE_F1929"): "DDL-CA-DYE-01",
    (CA, "CM_DIST_D4169"): "DDL-CA-DIST-01",
    (NJ, "CM_DIST_D4169"): "DDL-NJ-DIST-01",
    (MN, "CM_AGING_F1980"): "DDL-MN-AGE-01",
    (NJ, "CM_AGING_F1980"): "DDL-NJ-AGE-01",
}

OPERATORS: dict[tuple[str, str], str] = {
    (MN, "CM_SEAL_F88"): "SYN-DDL-OP-MN-SEAL",
    (CA, "CM_SEAL_F88"): "SYN-DDL-OP-CA-SEAL",
    (NJ, "CM_SEAL_F88"): "SYN-DDL-OP-NJ-SEAL",
    (MN, "CM_VISUAL"): "SYN-DDL-OP-MN-VIS",
    (CA, "CM_VISUAL"): "SYN-DDL-OP-CA-VIS",
    (NJ, "CM_VISUAL"): "SYN-DDL-OP-NJ-VIS",
    (MN, "CM_DYE_F1929"): "SYN-DDL-OP-MN-DYE",
    (CA, "CM_DYE_F1929"): "SYN-DDL-OP-CA-DYE",
    (CA, "CM_DIST_D4169"): "SYN-DDL-OP-CA-DIST",
    (NJ, "CM_DIST_D4169"): "SYN-DDL-OP-NJ-DIST",
    (MN, "CM_AGING_F1980"): "SYN-DDL-OP-MN-AGE",
    (NJ, "CM_AGING_F1980"): "SYN-DDL-OP-NJ-AGE",
}

SHARED_FLAGS_16 = (
    ("MATCH",) * 12 + ("FLAG_BIAS",) * 2 + ("FLAG_PRECISION",) + ("FLAG_OUTLIER",)
)
PAIR_UNIQUE_FLAGS_8 = ("MATCH",) * 4 + ("FLAG_BIAS",) * 2 + ("FLAG_PRECISION",) * 2

VALID_SPECS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    (MN, CA, "CM_SEAL_F88", SHARED_FLAGS_16),
    (MN, CA, "CM_VISUAL", SHARED_FLAGS_16),
    (MN, CA, "CM_DYE_F1929", PAIR_UNIQUE_FLAGS_8),
    (CA, NJ, "CM_SEAL_F88", SHARED_FLAGS_16),
    (CA, NJ, "CM_VISUAL", SHARED_FLAGS_16),
    (CA, NJ, "CM_DIST_D4169", PAIR_UNIQUE_FLAGS_8),
    (MN, NJ, "CM_SEAL_F88", SHARED_FLAGS_16),
    (MN, NJ, "CM_VISUAL", SHARED_FLAGS_16),
    (MN, NJ, "CM_AGING_F1980", PAIR_UNIQUE_FLAGS_8),
)

HOLD_SPECS: tuple[tuple[str, dict[str, Any]], ...] = (
    *(
        (
            "HOLD_FACILITY_OUT_OF_SCOPE",
            {"site_a": NJ, "site_b": CA, "method_id": "CM_DYE_F1929"},
        )
        for _ in range(4)
    ),
    *(
        (
            "HOLD_FACILITY_OUT_OF_SCOPE",
            {"site_a": MN, "site_b": CA, "method_id": "CM_DIST_D4169"},
        )
        for _ in range(2)
    ),
    *(
        (
            "HOLD_FACILITY_OUT_OF_SCOPE",
            {"site_a": CA, "site_b": MN, "method_id": "CM_AGING_F1980"},
        )
        for _ in range(2)
    ),
    *(
        (
            "HOLD_METHOD_VERSION_MISMATCH",
            {
                "site_a": MN,
                "site_b": CA,
                "method_id": "CM_SEAL_F88",
                "requested_version": "DDL-QMS-F88-2024-01",
            },
        )
        for _ in range(4)
    ),
    *(
        (
            "HOLD_METHOD_VERSION_MISMATCH",
            {
                "site_a": CA,
                "site_b": NJ,
                "method_id": "CM_VISUAL",
                "requested_version": "DDL-QMS-VIS-2023-11",
            },
        )
        for _ in range(4)
    ),
    *(
        (
            "HOLD_INSTRUMENT_NOT_LINKED",
            {
                "site_a": MN,
                "site_b": CA,
                "method_id": "CM_SEAL_F88",
                "instrument_a": "DDL-CA-SEAL-01",
            },
        )
        for _ in range(4)
    ),
    *(
        (
            "HOLD_INSTRUMENT_NOT_LINKED",
            {
                "site_a": MN,
                "site_b": NJ,
                "method_id": "CM_VISUAL",
                "instrument_b": "DDL-CA-VIS-01",
            },
        )
        for _ in range(4)
    ),
    *(
        (
            "HOLD_OPERATOR_NOT_QUALIFIED",
            {
                "site_a": CA,
                "site_b": NJ,
                "method_id": "CM_SEAL_F88",
                "operator_a": "SYN-DDL-OP-MN-SEAL",
            },
        )
        for _ in range(4)
    ),
    *(
        (
            "HOLD_OPERATOR_NOT_QUALIFIED",
            {
                "site_a": MN,
                "site_b": CA,
                "method_id": "CM_VISUAL",
                "operator_b": "SYN-DDL-OP-NJ-VIS",
            },
        )
        for _ in range(4)
    ),
    *(
        (
            "HOLD_PAIR_NOT_SHARED_SCOPE",
            {"site_a": MN, "site_b": NJ, "method_id": "CM_DYE_F1929"},
        )
        for _ in range(4)
    ),
    *(
        (
            "HOLD_PAIR_NOT_SHARED_SCOPE",
            {"site_a": CA, "site_b": MN, "method_id": "CM_DIST_D4169"},
        )
        for _ in range(2)
    ),
    *(
        (
            "HOLD_PAIR_NOT_SHARED_SCOPE",
            {"site_a": MN, "site_b": CA, "method_id": "CM_AGING_F1980"},
        )
        for _ in range(2)
    ),
)

EXPECTED_COUNTS = {
    "studies": STUDY_COUNT,
    "valid": VALID_COUNT,
    "blocked": BLOCKED_COUNT,
    "exact_method_version": VALID_COUNT,
    "blocked_expected_reason": BLOCKED_COUNT,
    "paired_truth_table_match": VALID_COUNT,
    "comparison_flags_expected": VALID_COUNT,
    "linkage_complete": VALID_COUNT,
    "released_without_named_human": 0,
    "released_after_named_human": VALID_COUNT,
    "blocked_released": 0,
    "replay_duplicate_study_events": 0,
    "replay_duplicate_evidence_events": 0,
    "production_writes": 0,
    "live_lims": 0,
    "cash_usd": 0,
}

EXPECTED_PAIR_COUNTS = {(MN, CA): 40, (CA, NJ): 40, (MN, NJ): 40}
EXPECTED_PROGRAM_COUNTS = {
    "SEAL_STRENGTH": 48,
    "VISUAL": 48,
    "DYE_PENETRATION": 8,
    "DISTRIBUTION": 8,
    "AGING": 8,
}
EXPECTED_FLAG_COUNTS = {
    "MATCH": 84,
    "FLAG_BIAS": 18,
    "FLAG_PRECISION": 12,
    "FLAG_OUTLIER": 6,
}
EXPECTED_HOLD_COUNTS = {code: PER_HOLD for code in HOLD_CODES}


def load_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def golden_audit_sha256() -> str:
    spec = load_fixture()
    return str(spec.get("golden_audit_sha256") or "")


def controlled_version(method_id: str) -> str:
    return str(METHODS[method_id]["version"])


def linked_instrument(site: str, method_id: str) -> str | None:
    return INSTRUMENTS.get((site, method_id))


def qualified_operator(site: str, method_id: str) -> str | None:
    return OPERATORS.get((site, method_id))


def shared_scope(method_id: str, site_a: str, site_b: str) -> bool:
    sites = METHODS[method_id]["sites"]
    return site_a in sites and site_b in sites


def signed_results(method_id: str, flag: str) -> tuple[float, float, str | None]:
    method = METHODS[method_id]
    nominal = float(method["nominal"])
    tolerance = float(method["tolerance"])
    if flag == "MATCH":
        return nominal, nominal, None
    if flag == "FLAG_PRECISION":
        return nominal, nominal, "PRECISION"
    if flag == "FLAG_BIAS":
        if tolerance > 0:
            return nominal, round(nominal * (1.0 + 2.0 * tolerance), 4), None
        return nominal, nominal + 2.0, None
    if flag == "FLAG_OUTLIER":
        if nominal == 0:
            return 0.0, 99.0, None
        return nominal, round(nominal * 4.0, 4), None
    raise RuntimeError("unknown comparison flag: %s" % flag)


def compare_pair(
    method_id: str,
    result_a: float,
    result_b: float,
    precision_tag: str | None,
) -> str:
    method = METHODS[method_id]
    nominal = float(method["nominal"])
    tolerance = float(method["tolerance"])
    if precision_tag == "PRECISION":
        return "FLAG_PRECISION"
    span = max(abs(nominal), 1.0)
    outlier_floor = max(3.0 * max(tolerance, 0.05) * span, 10.0)
    if abs(result_a - nominal) > outlier_floor or abs(result_b - nominal) > outlier_floor:
        return "FLAG_OUTLIER"
    if tolerance > 0:
        if abs(result_a - result_b) > tolerance * span:
            return "FLAG_BIAS"
        return "MATCH"
    if result_a != result_b:
        return "FLAG_BIAS"
    return "MATCH"


def _study_id(index: int, kind: str) -> str:
    return f"SYN-DDL-{kind}-{index:03d}"


def _report_id(index: int) -> str:
    return f"SYN-DDL-RPT-{index:03d}"


def _valid_row(
    index: int,
    site_a: str,
    site_b: str,
    method_id: str,
    flag: str,
) -> dict[str, Any]:
    method = METHODS[method_id]
    result_a, result_b, precision_tag = signed_results(method_id, flag)
    return {
        "study_id": _study_id(index, "STD"),
        "study_no": index,
        "program": method["program"],
        "method_id": method_id,
        "requested_version": method["version"],
        "expected_version": method["version"],
        "site_a": site_a,
        "site_b": site_b,
        "facility_a": SITE_NAMES[site_a],
        "facility_b": SITE_NAMES[site_b],
        "instrument_a": INSTRUMENTS[(site_a, method_id)],
        "instrument_b": INSTRUMENTS[(site_b, method_id)],
        "operator_a": OPERATORS[(site_a, method_id)],
        "operator_b": OPERATORS[(site_b, method_id)],
        "result_a": result_a,
        "result_b": result_b,
        "precision_tag": precision_tag,
        "expected_flag": flag,
        "expected_report_id": _report_id(index),
        "qms": QMS,
        "block": False,
        "expected_hold_code": None,
        "synthetic": True,
        "seed": SEED,
    }


def _hold_row(index: int, code: str, spec: dict[str, Any]) -> dict[str, Any]:
    method_id = spec["method_id"]
    method = METHODS[method_id]
    site_a = spec["site_a"]
    site_b = spec["site_b"]
    requested_version = spec.get("requested_version") or method["version"]
    instrument_a = spec.get("instrument_a") or linked_instrument(site_a, method_id) or "DDL-UNLINKED-A"
    instrument_b = spec.get("instrument_b") or linked_instrument(site_b, method_id) or "DDL-UNLINKED-B"
    operator_a = spec.get("operator_a") or qualified_operator(site_a, method_id) or "SYN-DDL-OP-UNQUAL-A"
    operator_b = spec.get("operator_b") or qualified_operator(site_b, method_id) or "SYN-DDL-OP-UNQUAL-B"
    return {
        "study_id": _study_id(index, "HLD"),
        "study_no": index,
        "program": method["program"],
        "method_id": method_id,
        "requested_version": requested_version,
        "expected_version": method["version"],
        "site_a": site_a,
        "site_b": site_b,
        "facility_a": SITE_NAMES[site_a],
        "facility_b": SITE_NAMES[site_b],
        "instrument_a": instrument_a,
        "instrument_b": instrument_b,
        "operator_a": operator_a,
        "operator_b": operator_b,
        "result_a": None,
        "result_b": None,
        "precision_tag": None,
        "expected_flag": None,
        "expected_report_id": None,
        "qms": QMS,
        "block": True,
        "expected_hold_code": code,
        "synthetic": True,
        "seed": SEED,
    }


def build_acceptance_fixture() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    index = 1
    for site_a, site_b, method_id, flags in VALID_SPECS:
        if not shared_scope(method_id, site_a, site_b):
            raise RuntimeError("valid spec is not shared-scope: %s %s/%s" % (method_id, site_a, site_b))
        for flag in flags:
            if flag not in FLAGS:
                raise RuntimeError("unknown flag in valid spec: %s" % flag)
            rows.append(_valid_row(index, site_a, site_b, method_id, flag))
            index += 1
    if len(HOLD_SPECS) != BLOCKED_COUNT:
        raise RuntimeError("hold specs must be exactly %s, got %s" % (BLOCKED_COUNT, len(HOLD_SPECS)))
    for code, spec in HOLD_SPECS:
        rows.append(_hold_row(index, code, spec))
        index += 1
    if len(rows) != STUDY_COUNT:
        raise RuntimeError("fixture must be exactly 160 studies, got %s" % len(rows))
    valid = [row for row in rows if not row["block"]]
    holds = [row for row in rows if row["block"]]
    if len(valid) != VALID_COUNT or len(holds) != BLOCKED_COUNT:
        raise RuntimeError("fixture split must be 120/40")
    pair_counts = {pair: 0 for pair in PAIRS}
    program_counts = {name: 0 for name in PROGRAMS}
    flag_counts = {name: 0 for name in FLAGS}
    for row in valid:
        pair_counts[(row["site_a"], row["site_b"])] += 1
        program_counts[row["program"]] += 1
        flag_counts[row["expected_flag"]] += 1
    if pair_counts != EXPECTED_PAIR_COUNTS:
        raise RuntimeError("valid pair split must be 40/40/40, got %s" % pair_counts)
    if program_counts != EXPECTED_PROGRAM_COUNTS:
        raise RuntimeError("valid program split mismatch: %s" % program_counts)
    if flag_counts != EXPECTED_FLAG_COUNTS:
        raise RuntimeError("valid flag split mismatch: %s" % flag_counts)
    codes = [row["expected_hold_code"] for row in holds]
    for code in HOLD_CODES:
        if codes.count(code) != PER_HOLD:
            raise RuntimeError("%s must appear exactly 8 times" % code)
    return rows


def classify(row: dict[str, Any]) -> dict[str, Any]:
    """Fail-closed facility/method/instrument/operator gate. First reason wins."""
    method_id = str(row.get("method_id") or "")
    site_a = str(row.get("site_a") or "")
    site_b = str(row.get("site_b") or "")
    requested_version = str(row.get("requested_version") or "")
    instrument_a = str(row.get("instrument_a") or "")
    instrument_b = str(row.get("instrument_b") or "")
    operator_a = str(row.get("operator_a") or "")
    operator_b = str(row.get("operator_b") or "")

    if method_id not in METHODS:
        return {"ok": False, "code": "HOLD_METHOD_VERSION_MISMATCH"}
    method = METHODS[method_id]
    if site_a not in method["sites"]:
        return {"ok": False, "code": "HOLD_FACILITY_OUT_OF_SCOPE"}
    if site_b not in method["sites"]:
        return {"ok": False, "code": "HOLD_PAIR_NOT_SHARED_SCOPE"}
    if requested_version != method["version"]:
        return {"ok": False, "code": "HOLD_METHOD_VERSION_MISMATCH"}
    if linked_instrument(site_a, method_id) != instrument_a or linked_instrument(site_b, method_id) != instrument_b:
        return {"ok": False, "code": "HOLD_INSTRUMENT_NOT_LINKED"}
    if qualified_operator(site_a, method_id) != operator_a or qualified_operator(site_b, method_id) != operator_b:
        return {"ok": False, "code": "HOLD_OPERATOR_NOT_QUALIFIED"}
    return {
        "ok": True,
        "code": None,
        "method_id": method_id,
        "method_version": method["version"],
        "site_a": site_a,
        "site_b": site_b,
        "instrument_a": instrument_a,
        "instrument_b": instrument_b,
        "operator_a": operator_a,
        "operator_b": operator_b,
        "program": method["program"],
    }


def empty_journal() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "qms": QMS,
        "truth_gate": TRUTH_GATE,
        "seed": SEED,
        "studies": {},
        "holds": {},
        "comparisons": {},
        "evidence": {},
        "exceptions": {},
        "events": [],
        "study_index": {},
        "evidence_index": {},
        "adapters": {name: {} for name in ADAPTERS},
        "interface_live": False,
        "production_writes": 0,
        "live_lims": 0,
        "live_reports": 0,
        "automatic_releases": 0,
        "cash_usd": 0,
        "accreditation_claim": False,
    }


def _event(journal: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    prev = journal["events"][-1]["record_hash"] if journal["events"] else "GENESIS"
    body = {"seq": len(journal["events"]) + 1, "kind": kind, **deepcopy(payload)}
    body["prev_hash"] = prev
    body["record_hash"] = sha256_hex(
        {"prev": prev, "body": {k: v for k, v in body.items() if k not in {"prev_hash", "record_hash"}}}
    )
    journal["events"].append(body)


def _adapter_payload(record: dict[str, Any], adapter: str) -> dict[str, Any]:
    payload = {
        "adapter": adapter,
        "live": False,
        "readonly": True,
        "study_id": record["study_id"],
        "state": record["state"],
        "method_id": record.get("method_id"),
        "method_version": record.get("method_version"),
        "report_id": record.get("report_id"),
        "cash_usd": 0,
        "accreditation_claim": False,
    }
    payload["payload_sha256"] = sha256_hex({k: v for k, v in payload.items() if k != "payload_sha256"})
    return payload


def _write_adapters(journal: dict[str, Any], record: dict[str, Any]) -> None:
    for name in ADAPTERS:
        journal["adapters"][name][record["study_id"]] = _adapter_payload(record, name)


def intake_study(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    study_id = row["study_id"]
    if study_id in journal["study_index"]:
        return {
            "kind": "NOOP",
            "reason": "already_seen",
            "study_id": study_id,
            "prior": journal["study_index"][study_id]["kind"],
        }

    _event(journal, "INTAKE", {"study_id": study_id, "site_a": row["site_a"], "site_b": row["site_b"]})
    verdict = classify(row)
    expected = row.get("expected_hold_code")
    if row.get("block"):
        if verdict["ok"] or verdict["code"] != expected:
            raise RuntimeError(
                "block %s expected %s got ok=%s code=%s"
                % (study_id, expected, verdict["ok"], verdict.get("code"))
            )
    elif not verdict["ok"]:
        raise RuntimeError("valid study %s classified as %s" % (study_id, verdict["code"]))

    if not verdict["ok"]:
        hold = {
            "study_id": study_id,
            "program": row["program"],
            "method_id": row["method_id"],
            "requested_version": row["requested_version"],
            "site_a": row["site_a"],
            "site_b": row["site_b"],
            "code": verdict["code"],
            "state": "HOLD",
            "released": False,
            "released_by": None,
            "report_released": False,
            "interface_live": False,
            "qms": QMS,
        }
        journal["holds"][study_id] = hold
        journal["studies"][study_id] = {
            "study_id": study_id,
            "program": row["program"],
            "method_id": row["method_id"],
            "method_version": None,
            "site_a": row["site_a"],
            "site_b": row["site_b"],
            "facility_a": row["facility_a"],
            "facility_b": row["facility_b"],
            "instrument_a": None,
            "instrument_b": None,
            "operator_a": None,
            "operator_b": None,
            "result_a": None,
            "result_b": None,
            "comparison_flag": None,
            "report_id": None,
            "block": True,
            "block_reason": verdict["code"],
            "state": "HOLD",
            "released": False,
            "released_by": None,
            "qms": QMS,
            "interface_live": False,
            "stages": ["INTAKE", "FACILITY_SCOPE"],
        }
        journal["study_index"][study_id] = {"kind": "HOLD", "code": verdict["code"]}
        _write_adapters(journal, journal["studies"][study_id])
        _event(journal, "HOLD", {"study_id": study_id, "code": verdict["code"]})
        return {"kind": "HOLD", "study_id": study_id, "code": verdict["code"]}

    flag = compare_pair(row["method_id"], float(row["result_a"]), float(row["result_b"]), row.get("precision_tag"))
    if flag != row["expected_flag"]:
        raise RuntimeError(
            "truth table miss %s expected %s got %s" % (study_id, row["expected_flag"], flag)
        )

    report_id = row["expected_report_id"]
    record = {
        "study_id": study_id,
        "program": verdict["program"],
        "method_id": verdict["method_id"],
        "method_version": verdict["method_version"],
        "site_a": verdict["site_a"],
        "site_b": verdict["site_b"],
        "facility_a": SITE_NAMES[verdict["site_a"]],
        "facility_b": SITE_NAMES[verdict["site_b"]],
        "instrument_a": verdict["instrument_a"],
        "instrument_b": verdict["instrument_b"],
        "operator_a": verdict["operator_a"],
        "operator_b": verdict["operator_b"],
        "result_a": row["result_a"],
        "result_b": row["result_b"],
        "precision_tag": row.get("precision_tag"),
        "comparison_flag": flag,
        "expected_flag": row["expected_flag"],
        "report_id": report_id,
        "block": False,
        "block_reason": None,
        "state": "EVIDENCE_PACKED",
        "released": False,
        "released_by": None,
        "released_at": None,
        "qms": QMS,
        "interface_live": False,
        "stages": list(STAGES[:-1]),
    }
    journal["studies"][study_id] = record
    journal["comparisons"][study_id] = {
        "study_id": study_id,
        "site_a": record["site_a"],
        "site_b": record["site_b"],
        "method_id": record["method_id"],
        "method_version": record["method_version"],
        "result_a": record["result_a"],
        "result_b": record["result_b"],
        "flag": flag,
        "truth_table_flag": row["expected_flag"],
        "match": flag == row["expected_flag"],
    }
    if flag != "MATCH":
        journal["exceptions"][study_id] = {
            "study_id": study_id,
            "flag": flag,
            "reviewed": True,
            "disposition": "HOLD_IN_PACK",
            "auto_released": False,
        }
        _event(journal, "EXCEPTION_REVIEW", {"study_id": study_id, "flag": flag})
    evidence = {
        "study_id": study_id,
        "facility_a": record["facility_a"],
        "facility_b": record["facility_b"],
        "instrument_a": record["instrument_a"],
        "instrument_b": record["instrument_b"],
        "operator_a": record["operator_a"],
        "operator_b": record["operator_b"],
        "method_id": record["method_id"],
        "method_version": record["method_version"],
        "report_id": report_id,
        "comparison_flag": flag,
        "qms": QMS,
        "readonly": True,
        "live": False,
    }
    evidence_key = sha256_hex(evidence)
    if evidence_key in journal["evidence_index"]:
        return {"kind": "NOOP", "reason": "duplicate_evidence", "study_id": study_id}
    journal["evidence_index"][evidence_key] = study_id
    journal["evidence"][study_id] = evidence
    journal["study_index"][study_id] = {"kind": "COMPARE", "flag": flag}
    _write_adapters(journal, record)
    _event(
        journal,
        "CONTROLLED_METHOD",
        {"study_id": study_id, "method_id": record["method_id"], "method_version": record["method_version"]},
    )
    _event(
        journal,
        "LINKAGE",
        {
            "study_id": study_id,
            "instrument_a": record["instrument_a"],
            "instrument_b": record["instrument_b"],
            "operator_a": record["operator_a"],
            "operator_b": record["operator_b"],
        },
    )
    _event(
        journal,
        "COMPARISON",
        {"study_id": study_id, "flag": flag, "result_a": record["result_a"], "result_b": record["result_b"]},
    )
    _event(journal, "EVIDENCE", {"study_id": study_id, "report_id": report_id, "evidence_key": evidence_key})
    return {"kind": "COMPARE", "study_id": study_id, "flag": flag, "report_id": report_id}


def release_report(journal: dict[str, Any], study_id: str, *, actor: str, actor_role: str) -> dict[str, Any]:
    hold = journal["holds"].get(study_id)
    if hold is not None:
        _event(
            journal,
            "AUTONOMOUS_RELEASE_DENIED",
            {"study_id": study_id, "code": "RELEASE_BLOCKED_OPEN_HOLD", "actor": actor},
        )
        return {"ok": False, "code": "RELEASE_BLOCKED_OPEN_HOLD"}
    record = journal["studies"].get(study_id)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_STUDY"}
    role = str(actor_role or "").strip().upper()
    name = str(actor or "").strip()
    if role != NAMED_ROLE or name != NAMED_ACTOR or not name or name.upper() in {"SYSTEM", "BOT", "AUTO"}:
        journal["automatic_releases"] = 0
        _event(
            journal,
            "AUTONOMOUS_RELEASE_DENIED",
            {"study_id": study_id, "actor": name or None, "actor_role": role or None},
        )
        return {"ok": False, "code": "AUTONOMOUS_RELEASE_DENIED"}
    if record.get("released"):
        return {"ok": True, "duplicate": True, "code": "ALREADY_RELEASED", "study_id": study_id}
    if study_id not in journal["evidence"]:
        return {"ok": False, "code": "EVIDENCE_PACK_MISSING"}
    record["released"] = True
    record["released_by"] = name
    record["released_at"] = "2026-08-31T06:00:00Z"
    record["state"] = "HUMAN_RELEASED"
    if "HUMAN_REPORT_RELEASE" not in record["stages"]:
        record["stages"] = list(record["stages"]) + ["HUMAN_REPORT_RELEASE"]
    _write_adapters(journal, record)
    _event(journal, "HUMAN_RELEASE", {"study_id": study_id, "released_by": name, "report_id": record["report_id"]})
    return {"ok": True, "code": "HUMAN_RELEASED", "study_id": study_id}


def attempt_autonomous_release(journal: dict[str, Any]) -> list[dict[str, Any]]:
    effects = []
    for study_id in sorted(journal["studies"]):
        effects.append(release_report(journal, study_id, actor="SYSTEM", actor_role="SYSTEM"))
    for study_id in sorted(journal["holds"]):
        effects.append(release_report(journal, study_id, actor="bot", actor_role="SYSTEM"))
    return effects


def authorized_human_release(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        release_report(journal, study_id, actor=NAMED_ACTOR, actor_role=NAMED_ROLE)
        for study_id in sorted(set(list(journal["studies"]) + list(journal["holds"])))
    ]


def replay_into(journal: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    before_studies = {key: deepcopy(value) for key, value in journal["studies"].items()}
    before_holds = {key: deepcopy(value) for key, value in journal["holds"].items()}
    before_evidence = dict(journal["evidence_index"])
    before_study_events = sum(1 for item in journal["events"] if item["kind"] in {"COMPARE", "HOLD", "COMPARISON"})
    before_evidence_events = sum(1 for item in journal["events"] if item["kind"] == "EVIDENCE")
    effects = [intake_study(journal, row) for row in rows]
    after_study_events = sum(1 for item in journal["events"] if item["kind"] in {"COMPARE", "HOLD", "COMPARISON"})
    after_evidence_events = sum(1 for item in journal["events"] if item["kind"] == "EVIDENCE")
    return {
        "added_studies": len(journal["studies"]) - len(before_studies),
        "added_holds": len(journal["holds"]) - len(before_holds),
        "added_evidence_keys": len(journal["evidence_index"]) - len(before_evidence),
        "replay_noops": sum(1 for item in effects if item.get("kind") == "NOOP"),
        "duplicate_study_events": after_study_events - before_study_events,
        "duplicate_evidence_events": after_evidence_events - before_evidence_events,
        "state_changed": before_studies != journal["studies"] or before_holds != journal["holds"],
    }


def compact_studies(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "study_id": item["study_id"],
            "program": item["program"],
            "method_id": item["method_id"],
            "method_version": item.get("method_version"),
            "site_a": item.get("site_a"),
            "site_b": item.get("site_b"),
            "facility_a": item.get("facility_a"),
            "facility_b": item.get("facility_b"),
            "instrument_a": item.get("instrument_a"),
            "instrument_b": item.get("instrument_b"),
            "operator_a": item.get("operator_a"),
            "operator_b": item.get("operator_b"),
            "comparison_flag": item.get("comparison_flag"),
            "report_id": item.get("report_id"),
            "block": item["block"],
            "block_reason": item.get("block_reason"),
            "state": item["state"],
            "released": item["released"],
            "released_by": item.get("released_by"),
        }
        for item in sorted(journal["studies"].values(), key=lambda row: row["study_id"])
    ]


def compact_holds(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "study_id": item["study_id"],
            "code": item["code"],
            "method_id": item["method_id"],
            "site_a": item["site_a"],
            "site_b": item["site_b"],
            "released": item["released"],
            "report_released": item["report_released"],
        }
        for item in sorted(journal["holds"].values(), key=lambda row: row["study_id"])
    ]


def compact_comparisons(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [deepcopy(item) for item in sorted(journal["comparisons"].values(), key=lambda row: row["study_id"])]


def compact_evidence(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [deepcopy(item) for item in sorted(journal["evidence"].values(), key=lambda row: row["study_id"])]


def build_audit(journal: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "qms": QMS,
        "truth_gate": TRUTH_GATE,
        "seed": SEED,
        "studies": compact_studies(journal),
        "holds": compact_holds(journal),
        "comparisons": compact_comparisons(journal),
        "evidence": compact_evidence(journal),
        "events": [
            {
                "seq": item["seq"],
                "kind": item["kind"],
                "study_id": item.get("study_id"),
                "code": item.get("code"),
                "flag": item.get("flag"),
                "method_id": item.get("method_id"),
                "record_hash": item["record_hash"],
            }
            for item in journal["events"]
            if item["kind"]
            in {
                "INTAKE",
                "HOLD",
                "CONTROLLED_METHOD",
                "LINKAGE",
                "COMPARISON",
                "EXCEPTION_REVIEW",
                "EVIDENCE",
                "HUMAN_RELEASE",
                "AUTONOMOUS_RELEASE_DENIED",
            }
        ],
        "autonomous_released": 0,
        "human_released": sum(1 for item in journal["studies"].values() if item["released"] and not item["block"]),
        "production_writes": journal["production_writes"],
        "live_lims": journal["live_lims"],
        "interface_live": journal["interface_live"],
        "accreditation_claim": False,
        "cash_usd": 0,
    }


def expected_actual(result: dict[str, Any]) -> dict[str, Any]:
    expected = dict(EXPECTED_COUNTS)
    actual = {key: result[key] for key in expected}
    return {"expected": expected, "actual": actual, "match": actual == expected}


def linkage_complete(item: dict[str, Any]) -> bool:
    return all(
        item.get(key)
        for key in (
            "facility_a",
            "facility_b",
            "instrument_a",
            "instrument_b",
            "operator_a",
            "operator_b",
            "method_id",
            "method_version",
            "report_id",
        )
    )


def pass_contract(result: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    counts = expected_actual(result)
    if not counts["match"]:
        failures.append("counts")
    if result.get("pair_counts") != {f"{a}|{b}": n for (a, b), n in EXPECTED_PAIR_COUNTS.items()}:
        failures.append("pair_counts")
    if result.get("hold_code_counts") != EXPECTED_HOLD_COUNTS:
        failures.append("hold_code_counts")
    if result.get("flag_counts") != EXPECTED_FLAG_COUNTS:
        failures.append("flag_counts")
    if result.get("truth_table_misses"):
        failures.append("truth_table")
    if result.get("flag_misses"):
        failures.append("comparison_flags")
    replay = result.get("replay") or {}
    if (
        replay.get("added_studies") != 0
        or replay.get("added_holds") != 0
        or replay.get("duplicate_study_events") != 0
        or replay.get("duplicate_evidence_events") != 0
        or replay.get("state_changed")
    ):
        failures.append("replay")
    if result.get("audit_sha256") != result.get("replay_audit_sha256"):
        failures.append("replay_hash")
    if result.get("autonomous_released") != 0:
        failures.append("autonomous_release")
    auto = result.get("autonomous_release_effects") or []
    if auto and any(item.get("ok") for item in auto):
        failures.append("autonomous_release_not_denied")
    if result.get("interface_live") or result.get("production_writes") or result.get("live_lims"):
        failures.append("live_adapters")
    if result.get("cash_usd") != 0:
        failures.append("cash_usd")
    if result.get("accreditation_claim"):
        failures.append("accreditation_claim")
    golden = result.get("golden_audit_sha256")
    if golden and golden != "PIN_AFTER_FIRST_RUN" and result.get("audit_sha256") != golden:
        failures.append("audit_sha256")
    if any(item.get("released") for item in result.get("hold_records") or []):
        failures.append("hold_released")
    return failures


def run_module(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    journal = empty_journal()
    effects = [intake_study(journal, row) for row in inbound]
    auto = attempt_autonomous_release(journal)
    human = authorized_human_release(journal)
    audit = build_audit(journal)
    audit_sha = sha256_hex(audit)
    replay = replay_into(journal, inbound)
    replay_audit = build_audit(journal)
    replay_sha = sha256_hex(replay_audit)

    hold_code_counts = {code: 0 for code in HOLD_CODES}
    for item in journal["holds"].values():
        hold_code_counts[item["code"]] = hold_code_counts.get(item["code"], 0) + 1
    pair_counts = {f"{a}|{b}": 0 for a, b in PAIRS}
    program_counts = {name: 0 for name in PROGRAMS}
    flag_counts = {name: 0 for name in FLAGS}
    truth_table_misses = []
    flag_misses = []
    by_id = {row["study_id"]: row for row in inbound}
    exact_method_version = 0
    linkage = 0
    for item in journal["studies"].values():
        if item["block"]:
            continue
        src = by_id[item["study_id"]]
        pair_counts[f"{item['site_a']}|{item['site_b']}"] += 1
        program_counts[item["program"]] += 1
        flag_counts[item["comparison_flag"]] += 1
        if item["method_version"] == METHODS[item["method_id"]]["version"] == src["expected_version"]:
            exact_method_version += 1
        if linkage_complete(item):
            linkage += 1
        if item["comparison_flag"] != src["expected_flag"]:
            flag_misses.append(item["study_id"])
        cmp_row = journal["comparisons"][item["study_id"]]
        if not cmp_row["match"] or cmp_row["result_a"] != src["result_a"] or cmp_row["result_b"] != src["result_b"]:
            truth_table_misses.append(item["study_id"])

    golden = golden_audit_sha256()
    packed = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "qms": QMS,
        "truth_gate": TRUTH_GATE,
        "studies": STUDY_COUNT,
        "valid": VALID_COUNT,
        "blocked": len(journal["holds"]),
        "exact_method_version": exact_method_version,
        "blocked_expected_reason": sum(
            1
            for row in inbound
            if row["block"] and journal["holds"].get(row["study_id"], {}).get("code") == row["expected_hold_code"]
        ),
        "paired_truth_table_match": VALID_COUNT - len(truth_table_misses),
        "comparison_flags_expected": VALID_COUNT - len(flag_misses),
        "linkage_complete": linkage,
        "released_without_named_human": 0,
        "released_after_named_human": sum(
            1 for item in journal["studies"].values() if item["released"] and not item["block"]
        ),
        "blocked_released": sum(1 for item in journal["holds"].values() if item["released"]),
        "replay_duplicate_study_events": replay["duplicate_study_events"],
        "replay_duplicate_evidence_events": replay["duplicate_evidence_events"],
        "production_writes": 0,
        "live_lims": 0,
        "cash_usd": 0,
        "accreditation_claim": False,
        "study_records": compact_studies(journal),
        "hold_records": compact_holds(journal),
        "comparison_records": compact_comparisons(journal),
        "evidence_records": compact_evidence(journal),
        "hold_code_counts": hold_code_counts,
        "pair_counts": pair_counts,
        "program_counts": program_counts,
        "flag_counts": flag_counts,
        "truth_table_misses": truth_table_misses,
        "flag_misses": flag_misses,
        "effects": effects,
        "autonomous_release_effects": auto,
        "human_release_effects": human,
        "autonomous_released": 0,
        "replay": replay,
        "audit": audit,
        "audit_sha256": audit_sha,
        "replay_audit_sha256": replay_sha,
        "golden_audit_sha256": golden,
        "interface_live": False,
        "interfaces": "SIMULATED_READ_ONLY",
        "pre_sale_transport": "NONE",
        "official_binary": COMMAND,
        "official_test": TEST_COMMAND,
        "open_slack_ts": OPEN_SLACK_TS,
        "journal": journal,
    }
    packed["failures"] = pass_contract(packed)
    packed["ok"] = packed["failures"] == []
    return packed


def cli_payload(result: dict[str, Any]) -> dict[str, Any]:
    counts = expected_actual(result)
    return {
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "ok": result["ok"],
        "failures": result.get("failures") or [],
        "expected": counts["expected"],
        "actual": counts["actual"],
        "match": counts["match"],
        "pair_counts": result["pair_counts"],
        "program_counts": result["program_counts"],
        "flag_counts": result["flag_counts"],
        "hold_code_counts": result["hold_code_counts"],
        "human_released": result["released_after_named_human"],
        "autonomous_released": result["autonomous_released"],
        "audit_sha256": result["audit_sha256"],
        "replay": result["replay"],
        "replay_audit_sha256": result["replay_audit_sha256"],
        "truth_gate": TRUTH_GATE,
        "interfaces": result["interfaces"],
        "cash_usd": 0,
        "accreditation_claim": False,
        "pre_sale_transport": "NONE",
        "official_binary": result["official_binary"],
        "official_test": result["official_test"],
        "open_slack_ts": OPEN_SLACK_TS,
    }


def persist_run(result: dict[str, Any], *, replay: dict[str, Any] | None = None) -> dict[str, str]:
    PACK.mkdir(parents=True, exist_ok=True)
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    journal = result["journal"]
    STATE_PATH.write_text(json.dumps(journal, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    run_body = cli_payload(result)
    RUN_RECEIPT_PATH.write_text(json.dumps(run_body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    STUDY_RECEIPT_PATH.write_text(json.dumps(result["study_records"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    HOLD_RECEIPT_PATH.write_text(json.dumps(result["hold_records"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    COMPARISON_RECEIPT_PATH.write_text(
        json.dumps(result["comparison_records"], indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    EVIDENCE_RECEIPT_PATH.write_text(
        json.dumps(result["evidence_records"], indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    AUDIT_RECEIPT_PATH.write_text(
        json.dumps(
            {
                "audit_sha256": result["audit_sha256"],
                "counts": expected_actual(result),
                "hold_code_counts": result["hold_code_counts"],
                "pair_counts": result["pair_counts"],
                "flag_counts": result["flag_counts"],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    if replay is not None:
        REPLAY_RECEIPT_PATH.write_text(json.dumps(replay, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "journal": str(STATE_PATH),
        "run": str(RUN_RECEIPT_PATH),
        "studies": str(STUDY_RECEIPT_PATH),
        "holds": str(HOLD_RECEIPT_PATH),
        "comparisons": str(COMPARISON_RECEIPT_PATH),
        "evidence": str(EVIDENCE_RECEIPT_PATH),
        "audit": str(AUDIT_RECEIPT_PATH),
    }


def load_journal(path: Path = STATE_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DDL cross-site controlled-method proficiency runner")
    parser.add_argument("--print-goldens", action="store_true", help="print computed digests without locking")
    parser.add_argument("--replay", action="store_true", help="replay into persisted journal and write replay receipt")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.print_goldens:
        result = run_module(build_acceptance_fixture())
        sys.stdout.write(
            _canonical(
                {
                    "audit_sha256": result["audit_sha256"],
                    "expected": expected_actual(result),
                    "hold_code_counts": result["hold_code_counts"],
                    "pair_counts": result["pair_counts"],
                    "flag_counts": result["flag_counts"],
                    "ok": result["ok"],
                    "failures": result["failures"],
                }
            )
            + "\n"
        )
        return 0 if result["ok"] or result["failures"] == ["audit_sha256"] else 1
    if args.replay:
        if not STATE_PATH.is_file():
            result = run_module()
            persist_run(result, replay=result["replay"])
        journal = load_journal()
        replay = replay_into(journal, build_acceptance_fixture())
        REPLAY_RECEIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
        body = {
            "ok": replay["added_studies"] == 0
            and replay["added_holds"] == 0
            and replay["duplicate_study_events"] == 0
            and replay["duplicate_evidence_events"] == 0
            and not replay["state_changed"],
            "replay": replay,
            "journal_sha256": sha256_hex(journal),
        }
        STATE_PATH.write_text(json.dumps(journal, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        REPLAY_RECEIPT_PATH.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        sys.stdout.write(_canonical(body) + "\n")
        return 0 if body["ok"] else 1

    result = run_module()
    written = persist_run(result, replay=result["replay"])
    payload = cli_payload(result)
    payload["written"] = written
    sys.stdout.write(_canonical(payload) + "\n")
    return 0 if payload["ok"] and not payload["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
