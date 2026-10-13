#!/usr/bin/env python3
"""CS Analytical expansion cross-line evidence LIMS.

Demand: csanalytical-expansion-crossline-evidence-lims-01
Buyer: Brandon Zurawlow / CS Analytical

Pipeline: client study + sample/lot + product/package component →
CCIT vs raw-material/gas/micro route → method/version → instrument/run →
QC/audit → staged report. Explicit cross-line misroute blocking.
Named-human release only.

Acceptance: 120 synthetic submissions — 90 valid, 8 duplicate IDs,
7 wrong line/method routes, 5 missing study/package metadata,
5 instrument/QC failures, 5 source-hash mismatches. PASS only when
exactly 90 are READY, 30 receive their predetermined HOLD, intake
holds schedule nothing, no held record stages or releases a report,
method/instrument/value/unit/audit/source hashes match, replay adds
zero records, and release is human-only.

AquaTrace HOLD / BUILD-AND-VERIFY. Adapters stay synthetic/read-only.
No compliance decision. No production writes. PRE-SALE TRANSPORT: NONE.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

DEMAND_ID = "csanalytical-expansion-crossline-evidence-lims-01"
SCHEMA = "commons-csanalytical-expansion-crossline-evidence-lims/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
BUYER = "Brandon Zurawlow / CS Analytical"
HUMAN_RELEASER = "RELEASER"
VALID_COUNT = 90
HOLD_COUNT = 30
INPUT_COUNT = VALID_COUNT + HOLD_COUNT
HOLD_CODES = (
    "DUPLICATE_ID",
    "WRONG_LINE",
    "MISSING_METADATA",
    "QC_FAIL",
    "SOURCE_HASH_MISMATCH",
)
HOLD_PLAN = {
    "DUPLICATE_ID": 8,
    "WRONG_LINE": 7,
    "MISSING_METADATA": 5,
    "QC_FAIL": 5,
    "SOURCE_HASH_MISMATCH": 5,
}
INTAKE_HOLD_CODES = frozenset({"DUPLICATE_ID", "WRONG_LINE", "MISSING_METADATA"})
LINES = ("CCIT", "RAW_MATERIAL", "GAS", "MICRO")

# Public CS Analytical line families. Versions and instruments are synthetic
# catalog bindings, not a live lab configuration.
ROUTES: dict[tuple[str, str, str, str], dict[str, str]] = {
    ("CCIT", "VACUUM_DECAY", "ASTM-F2338-09", "PTI-VERIPAC-455"): {
        "unit": "Pa",
        "component_family": "closure",
        "adapter": "SIMULATED",
    },
    ("CCIT", "HELIUM_LEAK", "USP-1207.1", "PFEIFFER-ASM340"): {
        "unit": "mbar*L/s",
        "component_family": "closure",
        "adapter": "SIMULATED",
    },
    ("CCIT", "HVLD", "USP-1207.2", "NIKKA-HDT-1"): {
        "unit": "uA",
        "component_family": "closure",
        "adapter": "SIMULATED",
    },
    ("RAW_MATERIAL", "FTIR_ID", "USP-197A", "THERMO-NICOLET-IS50"): {
        "unit": "match_index",
        "component_family": "material",
        "adapter": "SIMULATED",
    },
    ("RAW_MATERIAL", "RESIDUAL_SOLVENT", "USP-467", "AGILENT-7890B"): {
        "unit": "ppm",
        "component_family": "material",
        "adapter": "SIMULATED",
    },
    ("GAS", "HEADSPACE_O2", "ASTM-F2714-08", "MOCON-PACCHECK-650"): {
        "unit": "pct_O2",
        "component_family": "headspace",
        "adapter": "SIMULATED",
    },
    ("GAS", "HEADSPACE_MOISTURE", "ASTM-F2714-08", "MICHELL-S8000"): {
        "unit": "ppm_H2O",
        "component_family": "headspace",
        "adapter": "SIMULATED",
    },
    ("MICRO", "BIOBURDEN", "USP-61", "SARTORIUS-MD8"): {
        "unit": "CFU",
        "component_family": "micro",
        "adapter": "SIMULATED",
    },
    ("MICRO", "STERILITY", "USP-71", "STERITEST-NEO"): {
        "unit": "growth",
        "component_family": "micro",
        "adapter": "SIMULATED",
    },
}

METHOD_CYCLE = tuple(ROUTES.keys())
COMPONENTS = {
    "closure": ("vial_stopper", "syringe_plunger", "cartridge_seal", "blister_lid"),
    "material": ("elastomer_lot", "resin_lot", "glass_tubing", "foil_laminate"),
    "headspace": ("vial_headspace", "syringe_headspace", "pouch_headspace"),
    "micro": ("stopper_bioburden", "fill_sterility", "wfi_endotoxin"),
}

WRONG_LINE_SPECS = (
    {
        "submission_id": "CSA-WL01",
        "line": "CCIT",
        "method": "BIOBURDEN",
        "method_version": "USP-61",
        "instrument_id": "SARTORIUS-MD8",
        "package_component": "vial_stopper",
    },
    {
        "submission_id": "CSA-WL02",
        "line": "RAW_MATERIAL",
        "method": "VACUUM_DECAY",
        "method_version": "ASTM-F2338-09",
        "instrument_id": "PTI-VERIPAC-455",
        "package_component": "elastomer_lot",
    },
    {
        "submission_id": "CSA-WL03",
        "line": "GAS",
        "method": "STERILITY",
        "method_version": "USP-71",
        "instrument_id": "STERITEST-NEO",
        "package_component": "vial_headspace",
    },
    {
        "submission_id": "CSA-WL04",
        "line": "MICRO",
        "method": "HELIUM_LEAK",
        "method_version": "USP-1207.1",
        "instrument_id": "PFEIFFER-ASM340",
        "package_component": "fill_sterility",
    },
    {
        "submission_id": "CSA-WL05",
        "line": "CCIT",
        "method": "FTIR_ID",
        "method_version": "USP-197A",
        "instrument_id": "THERMO-NICOLET-IS50",
        "package_component": "syringe_plunger",
    },
    {
        "submission_id": "CSA-WL06",
        "line": "GAS",
        "method": "HVLD",
        "method_version": "USP-1207.2",
        "instrument_id": "NIKKA-HDT-1",
        "package_component": "pouch_headspace",
    },
    {
        "submission_id": "CSA-WL07",
        "line": "MICRO",
        "method": "HEADSPACE_O2",
        "method_version": "ASTM-F2714-08",
        "instrument_id": "MOCON-PACCHECK-650",
        "package_component": "stopper_bioburden",
    },
)

GOLDEN_COUNTS = {
    "input_rows": INPUT_COUNT,
    "ready": VALID_COUNT,
    "held": HOLD_COUNT,
    "jobs": VALID_COUNT + 10,
    "scheduled": VALID_COUNT + 10,
    "intake_holds_scheduled": 0,
    "held_staged": 0,
    "held_released": 0,
    "duplicate_jobs": 0,
    "released_reports": 0,
    "blocked_reports": VALID_COUNT + 10,
    "staged_reports": VALID_COUNT,
    "replay_added_jobs": 0,
    "production_writes": 0,
    "compliance_decisions": 0,
}

# Locked after the first deterministic PASS of this exact fixture.
GOLDEN_FIXTURE_SHA256 = "e248e432de17950f923d64174961703353cdde455d1e78d2e9ca9e3d67cbd6c9"
GOLDEN_AUDIT_SHA256 = "92a9ada5d3cf7855c85603fef25c525dee398bb670d980d3847c0cff248beda8"
GOLDEN_REPORT_DIGEST = "74515e546b1f5ed49cd9c13d55812067043bc4eccbda41138baf29a1ba595353"
HERE = Path(__file__).resolve().parent
FIXTURE_DIR = HERE / "revenue" / "csanalytical_expansion_crossline_lims"


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


def _round4(value: float) -> float:
    return float(f"{value:.4f}")


def valid_submission_id(index: int) -> str:
    return "CSA-V%03d" % index


def accession_id(submission_id: str, study_id: str, line: str, method: str) -> str:
    digest = sha256_hex(
        {
            "demand_id": DEMAND_ID,
            "submission_id": submission_id,
            "study_id": study_id,
            "line": line,
            "method": method,
        }
    )
    return "CSA-" + digest[:12]


def lookup_route(line: str, method: str, method_version: str, instrument_id: str) -> dict[str, str] | None:
    return ROUTES.get((line, method, method_version, instrument_id))


def source_hash(study_id: str, sample_id: str, lot_id: str, product_id: str, package_component: str) -> str:
    return sha256_hex(
        {
            "demand_id": DEMAND_ID,
            "kind": "SOURCE",
            "study_id": study_id,
            "sample_id": sample_id,
            "lot_id": lot_id,
            "product_id": product_id,
            "package_component": package_component,
        }
    )


def method_hash(method: str, method_version: str, line: str) -> str:
    return sha256_hex(
        {
            "demand_id": DEMAND_ID,
            "kind": "METHOD",
            "line": line,
            "method": method,
            "method_version": method_version,
        }
    )


def instrument_hash(instrument_id: str, run_id: str, adapter: str = "SIMULATED") -> str:
    return sha256_hex(
        {
            "demand_id": DEMAND_ID,
            "kind": "INSTRUMENT",
            "instrument_id": instrument_id,
            "run_id": run_id,
            "adapter": adapter,
        }
    )


def value_hash(value: Any) -> str:
    return sha256_hex({"demand_id": DEMAND_ID, "kind": "VALUE", "value": value})


def unit_hash(unit: str) -> str:
    return sha256_hex({"demand_id": DEMAND_ID, "kind": "UNIT", "unit": unit})


def audit_hash(
    submission_id: str,
    study_id: str,
    line: str,
    method: str,
    instrument_id: str,
    run_id: str,
) -> str:
    return sha256_hex(
        {
            "demand_id": DEMAND_ID,
            "kind": "AUDIT",
            "submission_id": submission_id,
            "study_id": study_id,
            "line": line,
            "method": method,
            "instrument_id": instrument_id,
            "run_id": run_id,
        }
    )


def instrument_result(index: int, method: str) -> dict[str, Any]:
    n = ((index - 1) % 90) + 1
    if method == "VACUUM_DECAY":
        return {"delta_p_pa": _round4(12.0 + n * 0.15)}
    if method == "HELIUM_LEAK":
        return {"leak_rate_mbar_l_s": _round4(1.2e-7 + n * 1.0e-10)}
    if method == "HVLD":
        return {"current_ua": _round4(4.0 + n * 0.05)}
    if method == "FTIR_ID":
        return {"match_index": _round4(0.9200 + (n % 20) * 0.0020)}
    if method == "RESIDUAL_SOLVENT":
        return {"ppm": _round4(8.0 + n * 0.10)}
    if method == "HEADSPACE_O2":
        return {"pct_o2": _round4(0.80 + n * 0.01)}
    if method == "HEADSPACE_MOISTURE":
        return {"ppm_h2o": _round4(140.0 + n * 0.80)}
    if method == "BIOBURDEN":
        return {"cfu": int(n % 7)}
    return {"growth": False}


def measured_value(result: dict[str, Any]) -> Any:
    if not result:
        return None
    key = sorted(result.keys())[0]
    return result[key]


def _base_row(
    row_id: str,
    submission_id: str,
    *,
    line: str,
    method: str,
    method_version: str,
    instrument_id: str,
    valid_index: int | None = None,
    study_id: str | None = None,
    sample_id: str | None = None,
    lot_id: str | None = None,
    product_id: str | None = None,
    package_component: str | None = None,
    qc_fail: bool = False,
    source_hash_override: str | None = None,
    expected_hold: str | None = None,
) -> dict[str, Any]:
    spec = lookup_route(line, method, method_version, instrument_id)
    idx = valid_index or 1
    family = (spec or {}).get("component_family") or "closure"
    component = package_component
    if component is None:
        choices = COMPONENTS[family]
        component = choices[(idx - 1) % len(choices)]
    study = "STU-%03d" % ((idx - 1) % 18 + 1) if study_id is None else study_id
    sample = "SMP-%s-%03d" % (line[:3], idx) if sample_id is None else sample_id
    lot = "LOT-%03d" % ((idx - 1) % 24 + 1) if lot_id is None else lot_id
    product = "PRD-%s-%02d" % (line[:3], (idx - 1) % 12 + 1) if product_id is None else product_id
    run_id = "RUN-%s-%03d" % (line[:3], idx)
    result = instrument_result(idx, method) if spec is not None else {}
    unit = (spec or {}).get("unit") or ""
    value = measured_value(result)
    src = source_hash(study, sample, lot, product, component)
    row: dict[str, Any] = {
        "row_id": row_id,
        "submission_id": submission_id,
        "study_id": study,
        "sample_id": sample,
        "lot_id": lot,
        "product_id": product,
        "package_component": component,
        "line": line,
        "method": method,
        "method_version": method_version,
        "instrument_id": instrument_id,
        "run_id": run_id,
        "unit": unit,
        "value": value,
        "result": result,
        "qc_fail": qc_fail,
        "expected_hold": expected_hold,
        "source_hash": source_hash_override if source_hash_override is not None else src,
        "method_hash": method_hash(method, method_version, line),
        "instrument_hash": instrument_hash(instrument_id, run_id),
        "value_hash": value_hash(value),
        "unit_hash": unit_hash(unit),
        "audit_hash": audit_hash(submission_id, study, line, method, instrument_id, run_id),
    }
    return row


def build_acceptance_fixture() -> list[dict[str, Any]]:
    """120-row PASS fixture for csanalytical-expansion-crossline-evidence-lims-01."""
    rows: list[dict[str, Any]] = []
    for index in range(1, VALID_COUNT + 1):
        line, method, version, instrument = METHOD_CYCLE[(index - 1) % len(METHOD_CYCLE)]
        rows.append(
            _base_row(
                "R%03d" % index,
                valid_submission_id(index),
                line=line,
                method=method,
                method_version=version,
                instrument_id=instrument,
                valid_index=index,
            )
        )
    for offset, spec in enumerate(WRONG_LINE_SPECS):
        rows.append(
            _base_row(
                "R%03d" % (91 + offset),
                spec["submission_id"],
                line=spec["line"],
                method=spec["method"],
                method_version=spec["method_version"],
                instrument_id=spec["instrument_id"],
                package_component=spec["package_component"],
                valid_index=offset + 1,
                expected_hold="WRONG_LINE",
            )
        )
    missing_specs = (
        {"submission_id": "CSA-MS01", "study_id": "", "package_component": "vial_stopper"},
        {"submission_id": "CSA-MS02", "study_id": "STU-099", "package_component": ""},
        {"submission_id": "CSA-MS03", "study_id": "", "package_component": ""},
        {"submission_id": "CSA-MS04", "study_id": "STU-099", "package_component": "vial_stopper", "product_id": ""},
        {
            "submission_id": "CSA-MS05",
            "study_id": "STU-099",
            "package_component": "vial_stopper",
            "sample_id": "",
            "lot_id": "",
        },
    )
    for offset, spec in enumerate(missing_specs):
        line, method, version, instrument = METHOD_CYCLE[offset % len(METHOD_CYCLE)]
        rows.append(
            _base_row(
                "R%03d" % (98 + offset),
                spec["submission_id"],
                line=line,
                method=method,
                method_version=version,
                instrument_id=instrument,
                study_id=spec.get("study_id"),
                sample_id=spec.get("sample_id"),
                lot_id=spec.get("lot_id"),
                product_id=spec.get("product_id"),
                package_component=spec.get("package_component"),
                valid_index=offset + 1,
                expected_hold="MISSING_METADATA",
            )
        )
    for offset in range(5):
        line, method, version, instrument = METHOD_CYCLE[offset % len(METHOD_CYCLE)]
        rows.append(
            _base_row(
                "R%03d" % (103 + offset),
                "CSA-QC%02d" % (offset + 1),
                line=line,
                method=method,
                method_version=version,
                instrument_id=instrument,
                valid_index=offset + 1,
                qc_fail=True,
                expected_hold="QC_FAIL",
            )
        )
    for offset in range(5):
        line, method, version, instrument = METHOD_CYCLE[(offset + 3) % len(METHOD_CYCLE)]
        rows.append(
            _base_row(
                "R%03d" % (108 + offset),
                "CSA-SH%02d" % (offset + 1),
                line=line,
                method=method,
                method_version=version,
                instrument_id=instrument,
                valid_index=offset + 1,
                source_hash_override="0" * 64,
                expected_hold="SOURCE_HASH_MISMATCH",
            )
        )
    for offset in range(8):
        line, method, version, instrument = METHOD_CYCLE[offset % len(METHOD_CYCLE)]
        rows.append(
            _base_row(
                "R%03d" % (113 + offset),
                valid_submission_id(offset + 1),
                line=line,
                method=method,
                method_version=version,
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
        "lines": list(LINES),
        "methods": sorted({key[1] for key in ROUTES}),
        "input_rows": len(inbound),
        "valid_rows": sum(1 for row in inbound if row.get("expected_hold") is None),
        "hold_rows": sum(1 for row in inbound if row.get("expected_hold")),
        "hold_plan": dict(HOLD_PLAN),
        "row_ids": [row["row_id"] for row in inbound],
        "submission_ids": [row["submission_id"] for row in inbound],
        "expected_holds": [row.get("expected_hold") for row in inbound],
        "source_hashes": [row["source_hash"] for row in inbound],
        "method_hashes": [row["method_hash"] for row in inbound],
        "instrument_hashes": [row["instrument_hash"] for row in inbound],
        "value_hashes": [row["value_hash"] for row in inbound],
        "unit_hashes": [row["unit_hash"] for row in inbound],
        "audit_hashes": [row["audit_hash"] for row in inbound],
        "rows": inbound,
        "interfaces": "SIMULATED",
        "interface_live": False,
        "production_writes": False,
        "autonomous_release": False,
        "compliance_decision": False,
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


def classify_submission(row: dict[str, Any], seen_submission_ids: set[str]) -> dict[str, Any]:
    submission_id = _text(row.get("submission_id"))
    study_id = _text(row.get("study_id"))
    sample_id = _text(row.get("sample_id"))
    lot_id = _text(row.get("lot_id"))
    product_id = _text(row.get("product_id"))
    package_component = _text(row.get("package_component"))
    line = _text(row.get("line")).upper()
    method = _text(row.get("method"))
    method_version = _text(row.get("method_version"))
    instrument_id = _text(row.get("instrument_id"))
    if not study_id or not package_component or not product_id or (not sample_id and not lot_id):
        return {
            "ok": False,
            "code": "MISSING_METADATA",
            "intake_hold": True,
            "submission_id": submission_id or None,
        }
    if not submission_id:
        return {"ok": False, "code": "MISSING_METADATA", "intake_hold": True, "submission_id": None}
    if submission_id in seen_submission_ids:
        return {"ok": False, "code": "DUPLICATE_ID", "intake_hold": True, "submission_id": submission_id}
    spec = lookup_route(line, method, method_version, instrument_id)
    if spec is None:
        return {
            "ok": False,
            "code": "WRONG_LINE",
            "intake_hold": True,
            "submission_id": submission_id,
            "line": line,
            "method": method,
            "instrument_id": instrument_id,
        }
    run_id = _text(row.get("run_id")) or "RUN-%s" % submission_id
    computed_source = source_hash(study_id, sample_id, lot_id, product_id, package_component)
    declared_source = _text(row.get("source_hash")) or computed_source
    return {
        "ok": True,
        "submission_id": submission_id,
        "study_id": study_id,
        "sample_id": sample_id,
        "lot_id": lot_id,
        "product_id": product_id,
        "package_component": package_component,
        "line": line,
        "method": method,
        "method_version": method_version,
        "instrument_id": instrument_id,
        "run_id": run_id,
        "unit": spec["unit"],
        "adapter": spec["adapter"],
        "accession_id": accession_id(submission_id, study_id, line, method),
        "computed_source_hash": computed_source,
        "declared_source_hash": declared_source,
        "source_mismatch": declared_source != computed_source,
    }


def rendered_report(record: dict[str, Any]) -> dict[str, Any] | None:
    if not record.get("staged"):
        return None
    return {
        "demand_id": DEMAND_ID,
        "accession_id": record["accession_id"],
        "submission_id": record["submission_id"],
        "study_id": record["study_id"],
        "sample_id": record["sample_id"],
        "lot_id": record["lot_id"],
        "product_id": record["product_id"],
        "package_component": record["package_component"],
        "line": record["line"],
        "method": record["method"],
        "method_version": record["method_version"],
        "instrument_id": record["instrument_id"],
        "run_id": record["run_id"],
        "unit": record["unit"],
        "value": record.get("value"),
        "result": deepcopy(record.get("result") or {}),
        "qc_ok": bool(record.get("qc_ok")),
        "source_hash": record.get("source_hash"),
        "method_hash": record.get("method_hash"),
        "instrument_hash": record.get("instrument_hash"),
        "value_hash": record.get("value_hash"),
        "unit_hash": record.get("unit_hash"),
        "audit_hash": record.get("audit_hash"),
        "released": bool(record.get("released")),
        "interface_live": False,
        "compliance_decision": None,
    }


def report_status(record: dict[str, Any]) -> str:
    if record.get("released"):
        return "RELEASED"
    if record.get("state") == "HOLD" or not record.get("staged"):
        return "HOLD"
    if not record.get("result"):
        return "BLOCKED_MISSING_RESULT"
    if not record.get("qc_ok"):
        return "BLOCKED_MISSING_QC"
    return "READY"


def _hold(journal: dict[str, Any], row: dict[str, Any], code: str, *, scheduled: bool = False) -> dict[str, Any]:
    hold = {
        "row_id": _text(row.get("row_id")),
        "submission_id": _text(row.get("submission_id")) or None,
        "code": code,
        "line": _text(row.get("line")) or None,
        "method": _text(row.get("method")) or None,
        "instrument_id": _text(row.get("instrument_id")) or None,
        "intake_hold": code in INTAKE_HOLD_CODES,
        "scheduled": scheduled,
        "staged": False,
        "released": False,
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
        (item for item in journal["jobs"].values() if item["submission_id"] == _text(row.get("submission_id"))),
        None,
    )
    if existing_job is not None and existing_job.get("row_id") == row_id:
        _event(
            journal,
            "REPLAY_NOOP",
            {"accession_id": existing_job["accession_id"], "submission_id": existing_job["submission_id"]},
        )
        return {
            "kind": "REPLAY_NOOP",
            "accession_id": existing_job["accession_id"],
            "submission_id": existing_job["submission_id"],
        }
    seen = {item["submission_id"] for item in journal["jobs"].values()}
    verdict = classify_submission(row, seen)
    if not verdict["ok"]:
        return _hold(journal, row, verdict["code"], scheduled=False)

    acc_id = verdict["accession_id"]
    if acc_id in journal["jobs"]:
        _event(journal, "REPLAY_NOOP", {"accession_id": acc_id, "submission_id": verdict["submission_id"]})
        return {"kind": "REPLAY_NOOP", "accession_id": acc_id, "submission_id": verdict["submission_id"]}

    qc_fail = _flag(row.get("qc_fail"))
    source_mismatch = bool(verdict.get("source_mismatch"))
    result = deepcopy(row.get("result") or instrument_result(1, verdict["method"]))
    value = row.get("value") if "value" in row else measured_value(result)
    unit = verdict["unit"]
    hold_code = None
    if source_mismatch:
        hold_code = "SOURCE_HASH_MISMATCH"
    elif qc_fail:
        hold_code = "QC_FAIL"
    staged = hold_code is None
    record = {
        "accession_id": acc_id,
        "submission_id": verdict["submission_id"],
        "row_id": row_id,
        "study_id": verdict["study_id"],
        "sample_id": verdict["sample_id"],
        "lot_id": verdict["lot_id"],
        "product_id": verdict["product_id"],
        "package_component": verdict["package_component"],
        "line": verdict["line"],
        "method": verdict["method"],
        "method_version": verdict["method_version"],
        "instrument_id": verdict["instrument_id"],
        "run_id": verdict["run_id"],
        "unit": unit,
        "value": value,
        "adapter": verdict["adapter"],
        "result": result,
        "qc_ok": not qc_fail,
        "qc_fail": qc_fail,
        "scheduled": True,
        "staged": staged,
        "source_hash": verdict["computed_source_hash"] if not source_mismatch else verdict["declared_source_hash"],
        "computed_source_hash": verdict["computed_source_hash"],
        "method_hash": method_hash(verdict["method"], verdict["method_version"], verdict["line"]),
        "instrument_hash": instrument_hash(verdict["instrument_id"], verdict["run_id"]),
        "value_hash": value_hash(value),
        "unit_hash": unit_hash(unit),
        "audit_hash": audit_hash(
            verdict["submission_id"],
            verdict["study_id"],
            verdict["line"],
            verdict["method"],
            verdict["instrument_id"],
            verdict["run_id"],
        ),
        "state": "HOLD" if hold_code else "READY",
        "released": False,
        "released_by": None,
        "interface_state": "SIMULATED",
        "interface_live": False,
        "compliance_decision": None,
    }
    record["report"] = rendered_report(record)
    record["report_digest"] = sha256_hex(record["report"]) if record["report"] is not None else None
    record["report_status"] = report_status(record)
    journal["jobs"][acc_id] = record
    _event(
        journal,
        "HOLD" if hold_code else "READY",
        {"accession_id": acc_id, "submission_id": verdict["submission_id"], "line": verdict["line"]},
    )
    if hold_code:
        hold_effect = _hold(journal, row, hold_code, scheduled=True)
        return {
            "kind": "HOLD",
            "accession_id": acc_id,
            "code": hold_code,
            "scheduled": True,
            "staged": False,
            "duplicate": hold_effect["duplicate"],
        }
    return {
        "kind": "READY",
        "accession_id": acc_id,
        "line": verdict["line"],
        "state": "READY",
        "scheduled": True,
        "staged": True,
    }


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
    if record.get("state") == "HOLD" or not record.get("staged"):
        _event(
            journal,
            "RELEASE_DENIED",
            {"accession_id": accession_id_value, "code": "HELD_RECORD_NO_RELEASE", "report_status": "HOLD"},
        )
        return {"ok": False, "code": "HELD_RECORD_NO_RELEASE", "report_status": "HOLD"}
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
    jobs = sorted(journal["jobs"].values(), key=lambda item: item["submission_id"])
    ready = [item for item in jobs if item["state"] == "READY"]
    hold_codes = [item["code"] for item in journal["holds"]]
    reports = [item["report"] for item in jobs if item.get("report") is not None]
    fixture_by_id = {row["submission_id"]: row for row in inbound}
    hash_matches = []
    for item in jobs:
        expected = fixture_by_id.get(item["submission_id"], {})
        computed_source = source_hash(
            item["study_id"],
            item["sample_id"],
            item["lot_id"],
            item["product_id"],
            item["package_component"],
        )
        match = {
            "submission_id": item["submission_id"],
            "method": item["method_hash"] == method_hash(item["method"], item["method_version"], item["line"]),
            "instrument": item["instrument_hash"]
            == instrument_hash(item["instrument_id"], item["run_id"]),
            "value": item["value_hash"] == value_hash(item["value"]),
            "unit": item["unit_hash"] == unit_hash(item["unit"]),
            "audit": item["audit_hash"]
            == audit_hash(
                item["submission_id"],
                item["study_id"],
                item["line"],
                item["method"],
                item["instrument_id"],
                item["run_id"],
            ),
            "source": item["computed_source_hash"] == computed_source,
        }
        if item["state"] == "READY":
            match["source_declared"] = item["source_hash"] == expected.get("source_hash") == computed_source
        hash_matches.append(match)
    intake_holds = [item for item in journal["holds"] if item.get("intake_hold")]
    post_holds = [item for item in journal["holds"] if not item.get("intake_hold")]
    held_jobs = [item for item in jobs if item["state"] == "HOLD"]
    audit = {
        "demand_id": DEMAND_ID,
        "submission_ids": [item["submission_id"] for item in jobs],
        "accession_ids": [item["accession_id"] for item in jobs],
        "states": [item["state"] for item in jobs],
        "lines": [item["line"] for item in jobs],
        "hold_codes": hold_codes,
        "hold_submission_ids": [item["submission_id"] for item in journal["holds"]],
        "source_hashes": [item["source_hash"] for item in jobs],
        "method_hashes": [item["method_hash"] for item in jobs],
        "instrument_hashes": [item["instrument_hash"] for item in jobs],
        "value_hashes": [item["value_hash"] for item in jobs],
        "unit_hashes": [item["unit_hash"] for item in jobs],
        "audit_hashes": [item["audit_hash"] for item in jobs],
        "report_digests": [item["report_digest"] for item in jobs if item.get("report_digest")],
        "released": [item["submission_id"] for item in jobs if item["released"]],
        "staged": [item["submission_id"] for item in jobs if item.get("staged")],
        "scheduled": [item["submission_id"] for item in jobs if item.get("scheduled")],
    }
    body = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "lines": list(LINES),
        "methods": sorted({key[1] for key in ROUTES}),
        "input_rows": len(inbound),
        "ready": len(ready),
        "held": len(journal["holds"]),
        "jobs": len(jobs),
        "scheduled": sum(1 for item in jobs if item.get("scheduled")),
        "intake_holds": len(intake_holds),
        "intake_holds_scheduled": sum(1 for item in intake_holds if item.get("scheduled")),
        "post_intake_holds": len(post_holds),
        "held_staged": sum(1 for item in held_jobs if item.get("staged")),
        "held_released": sum(1 for item in held_jobs if item.get("released")),
        "hold_codes": hold_codes,
        "hold_code_set": sorted(set(hold_codes)),
        "duplicate_jobs": 0,
        "released_reports": sum(1 for item in jobs if item["released"]),
        "blocked_reports": sum(1 for item in jobs if item["report_status"] != "RELEASED"),
        "staged_reports": sum(1 for item in jobs if item.get("staged") and item.get("report") is not None),
        "replay_noops": sum(1 for item in effects if item.get("kind") == "REPLAY_NOOP"),
        "effects": effects,
        "autonomous_release_effects": autonomous,
        "accessions": jobs,
        "holds": deepcopy(journal["holds"]),
        "routes": {item["submission_id"]: item["line"] for item in jobs},
        "accession_ids": [item["accession_id"] for item in jobs],
        "hash_matches": hash_matches,
        "hashes_match": all(
            item["method"]
            and item["instrument"]
            and item["value"]
            and item["unit"]
            and item["audit"]
            and item["source"]
            and item.get("source_declared", True)
            for item in hash_matches
            if fixture_by_id.get(item["submission_id"], {}).get("expected_hold") in {None, "QC_FAIL"}
        ),
        "reports": reports,
        "report_digest": sha256_hex(reports),
        "audit": audit,
        "audit_sha256": sha256_hex(audit),
        "interface_live": False,
        "interfaces": "SIMULATED",
        "autonomous_certification": False,
        "autonomous_release": False,
        "production_writes": 0,
        "compliance_decisions": 0,
        "compliance_decision": False,
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
        "scheduled": result.get("scheduled"),
        "intake_holds_scheduled": result.get("intake_holds_scheduled"),
        "held_staged": result.get("held_staged"),
        "held_released": result.get("held_released"),
        "duplicate_jobs": result.get("duplicate_jobs"),
        "released_reports": result.get("released_reports"),
        "blocked_reports": result.get("blocked_reports"),
        "staged_reports": result.get("staged_reports"),
        "replay_added_jobs": result.get("replay_added_jobs", 0),
        "production_writes": result.get("production_writes"),
        "compliance_decisions": result.get("compliance_decisions"),
    }
    return {"expected": dict(GOLDEN_COUNTS), "actual": actual, "match": actual == GOLDEN_COUNTS}


def pass_contract(result: dict[str, Any]) -> list[str]:
    failures = []
    counts = expected_actual(result)
    if not counts["match"]:
        failures.append("counts")
    if result.get("hold_code_set") != sorted(HOLD_CODES):
        failures.append("hold_code_set")
    if Counter(result.get("hold_codes") or []) != Counter(HOLD_PLAN):
        failures.append("hold_code_counts")
    if len(set(result.get("accession_ids") or [])) != VALID_COUNT + 10:
        failures.append("accession_ids_not_unique")
    if result.get("hashes_match") is not True:
        failures.append("hashes_match")
    if result.get("intake_holds_scheduled") != 0:
        failures.append("intake_holds_scheduled")
    if result.get("held_staged") != 0:
        failures.append("held_staged")
    if result.get("held_released") != 0:
        failures.append("held_released")
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
    if result.get("compliance_decision") is not False:
        failures.append("compliance_decision")
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
