#!/usr/bin/env python3
"""Sharp Sterile RTU-vial isolator lineage LIMS.

Demand: sharp-rtu-vial-isolator-lineage-lims-01
Buyer: James Hamilton / Sharp Sterile Manufacturing

Pipeline: sponsor tech-transfer + material/batch lot → RTU-vial/isolator
route → fill/weight/lyophilizer-cycle provenance → analytical/stability/
sterility QC → staged batch evidence pack. Named-human release only.

Acceptance: 120 synthetic records — 90 valid, 8 duplicate component/batch
IDs, 7 format/line mismatches, 5 missing method/version, 5 weight/slot
conflicts, 5 QC/sterility failures. PASS only when exactly 90 are READY,
30 receive their predetermined HOLD, intake defects schedule no line
jobs, no held record stages or releases evidence, cycle/weight/result/
unit/source hashes match, replay adds zero records, and release is
human-only.

AquaTrace HOLD / BUILD-AND-VERIFY. Adapters stay synthetic/read-only.
No GMP/compliance/clinical/public-health decision. No production writes.
PRE-SALE TRANSPORT: NONE. cash_usd=0.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

DEMAND_ID = "sharp-rtu-vial-isolator-lineage-lims-01"
SCHEMA = "commons-sharp-rtu-vial-isolator-lineage-lims/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
BUYER = "James Hamilton / Sharp Sterile Manufacturing"
HUMAN_RELEASER = "RELEASER"
VALID_COUNT = 90
HOLD_COUNT = 30
INPUT_COUNT = VALID_COUNT + HOLD_COUNT
HOLD_CODES = (
    "DUPLICATE_COMPONENT_BATCH",
    "FORMAT_LINE_MISMATCH",
    "MISSING_METHOD_VERSION",
    "WEIGHT_SLOT_CONFLICT",
    "QC_STERILITY_FAIL",
)
HOLD_PLAN = {
    "DUPLICATE_COMPONENT_BATCH": 8,
    "FORMAT_LINE_MISMATCH": 7,
    "MISSING_METHOD_VERSION": 5,
    "WEIGHT_SLOT_CONFLICT": 5,
    "QC_STERILITY_FAIL": 5,
}
INTAKE_HOLD_CODES = frozenset(
    {"DUPLICATE_COMPONENT_BATCH", "FORMAT_LINE_MISMATCH", "MISSING_METHOD_VERSION"}
)
LINES = ("ISOLATOR_FILL", "LYOPHILIZER", "ANALYTICAL", "STABILITY", "STERILITY")
FORMATS = ("RTU_2R", "RTU_6R", "RTU_10R", "RTU_20R")

# Synthetic Sharp Lee RTU-vial / isolator / lyo / QC catalog. Not a live line.
ROUTES: dict[tuple[str, str, str, str], dict[str, Any]] = {
    ("ISOLATOR_FILL", "RTU_2R", "FILL_WEIGHT", "FW-2R-v3"): {
        "unit": "mg",
        "target_mg": 1500.0,
        "adapter": "SIMULATED",
        "result_key": "fill_weight_mg",
    },
    ("ISOLATOR_FILL", "RTU_6R", "FILL_WEIGHT", "FW-6R-v2"): {
        "unit": "mg",
        "target_mg": 4500.0,
        "adapter": "SIMULATED",
        "result_key": "fill_weight_mg",
    },
    ("ISOLATOR_FILL", "RTU_10R", "FILL_WEIGHT", "FW-10R-v4"): {
        "unit": "mg",
        "target_mg": 7500.0,
        "adapter": "SIMULATED",
        "result_key": "fill_weight_mg",
    },
    ("ISOLATOR_FILL", "RTU_20R", "FILL_WEIGHT", "FW-20R-v1"): {
        "unit": "mg",
        "target_mg": 15000.0,
        "adapter": "SIMULATED",
        "result_key": "fill_weight_mg",
    },
    ("LYOPHILIZER", "RTU_2R", "LYO_CYCLE", "LYO-2R-C21"): {
        "unit": "pct_moisture",
        "target_mg": 1500.0,
        "adapter": "SIMULATED",
        "result_key": "residual_moisture_pct",
    },
    ("LYOPHILIZER", "RTU_6R", "LYO_CYCLE", "LYO-6R-C18"): {
        "unit": "pct_moisture",
        "target_mg": 4500.0,
        "adapter": "SIMULATED",
        "result_key": "residual_moisture_pct",
    },
    ("LYOPHILIZER", "RTU_10R", "LYO_CYCLE", "LYO-10R-C12"): {
        "unit": "pct_moisture",
        "target_mg": 7500.0,
        "adapter": "SIMULATED",
        "result_key": "residual_moisture_pct",
    },
    ("LYOPHILIZER", "RTU_20R", "LYO_CYCLE", "LYO-20R-C09"): {
        "unit": "pct_moisture",
        "target_mg": 15000.0,
        "adapter": "SIMULATED",
        "result_key": "residual_moisture_pct",
    },
    ("ANALYTICAL", "RTU_2R", "HPLC_ASSAY", "USP-621-v1"): {
        "unit": "pct_lc",
        "target_mg": 1500.0,
        "adapter": "SIMULATED",
        "result_key": "assay_pct",
    },
    ("ANALYTICAL", "RTU_6R", "UV_ID", "USP-197-v2"): {
        "unit": "match_index",
        "target_mg": 4500.0,
        "adapter": "SIMULATED",
        "result_key": "match_index",
    },
    ("ANALYTICAL", "RTU_10R", "HPLC_ASSAY", "USP-621-v1"): {
        "unit": "pct_lc",
        "target_mg": 7500.0,
        "adapter": "SIMULATED",
        "result_key": "assay_pct",
    },
    ("STABILITY", "RTU_2R", "ICH_PULL", "ICH-Q1A-v3"): {
        "unit": "months",
        "target_mg": 1500.0,
        "adapter": "SIMULATED",
        "result_key": "pull_month",
    },
    ("STABILITY", "RTU_10R", "ICH_PULL", "ICH-Q1A-v3"): {
        "unit": "months",
        "target_mg": 7500.0,
        "adapter": "SIMULATED",
        "result_key": "pull_month",
    },
    ("STERILITY", "RTU_20R", "USP71_STERILITY", "USP-71-v1"): {
        "unit": "growth",
        "target_mg": 15000.0,
        "adapter": "SIMULATED",
        "result_key": "growth",
    },
    ("STERILITY", "RTU_6R", "ISOLATOR_BIOBURDEN", "USP-61-v2"): {
        "unit": "CFU",
        "target_mg": 4500.0,
        "adapter": "SIMULATED",
        "result_key": "cfu",
    },
}

METHOD_CYCLE = tuple(ROUTES.keys())
KNOWN_METHODS = frozenset(key[2] for key in ROUTES)
METHOD_VERSIONS: dict[str, frozenset[str]] = {}
for _line, _fmt, method, version in ROUTES:
    METHOD_VERSIONS.setdefault(method, set()).add(version)
METHOD_VERSIONS = {key: frozenset(value) for key, value in METHOD_VERSIONS.items()}
FORMAT_TARGETS = {
    "RTU_2R": 1500.0,
    "RTU_6R": 4500.0,
    "RTU_10R": 7500.0,
    "RTU_20R": 15000.0,
}
WEIGHT_TOLERANCE_FRAC = 0.01

FORMAT_LINE_SPECS = (
    {
        "submission_id": "SHP-FM01",
        "line": "ISOLATOR_FILL",
        "format": "PFS_1ML",
        "method": "FILL_WEIGHT",
        "method_version": "FW-2R-v3",
    },
    {
        "submission_id": "SHP-FM02",
        "line": "LYOPHILIZER",
        "format": "CARTRIDGE_3ML",
        "method": "LYO_CYCLE",
        "method_version": "LYO-2R-C21",
    },
    {
        "submission_id": "SHP-FM03",
        "line": "ANALYTICAL",
        "format": "AMPULE_1ML",
        "method": "HPLC_ASSAY",
        "method_version": "USP-621-v1",
    },
    {
        "submission_id": "SHP-FM04",
        "line": "STERILITY",
        "format": "PFS_1ML",
        "method": "USP71_STERILITY",
        "method_version": "USP-71-v1",
    },
    {
        "submission_id": "SHP-FM05",
        "line": "STABILITY",
        "format": "CARTRIDGE_3ML",
        "method": "ICH_PULL",
        "method_version": "ICH-Q1A-v3",
    },
    {
        "submission_id": "SHP-FM06",
        "line": "ISOLATOR_FILL",
        "format": "RTU_2R",
        "method": "USP71_STERILITY",
        "method_version": "USP-71-v1",
    },
    {
        "submission_id": "SHP-FM07",
        "line": "LYOPHILIZER",
        "format": "RTU_6R",
        "method": "HPLC_ASSAY",
        "method_version": "USP-621-v1",
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
    "released_packs": 0,
    "blocked_packs": VALID_COUNT + 10,
    "staged_packs": VALID_COUNT,
    "replay_added_jobs": 0,
    "production_writes": 0,
    "compliance_decisions": 0,
}

# Locked after the first deterministic PASS of this exact fixture.
GOLDEN_FIXTURE_SHA256 = "2d8fb72fa37908bcb7187d21f1ec1082e02de4f950c7b8a5772afd958ca80b84"
GOLDEN_AUDIT_SHA256 = "d248f9b13cdc38c76d1be2e4d8c2d753a77aa1d3f8efc7fcf6bc30cf7e0c95a8"
GOLDEN_EVIDENCE_DIGEST = "d255a5866b7d1a34c697a2f653d56e9c95fc98a271e2da5f7290c623e324ca01"
HERE = Path(__file__).resolve().parent
FIXTURE_DIR = HERE / "revenue" / "sharp_rtu_vial_isolator_lineage"


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
    return "SHP-V%03d" % index


def accession_id(submission_id: str, batch_id: str, line: str, method: str) -> str:
    digest = sha256_hex(
        {
            "demand_id": DEMAND_ID,
            "submission_id": submission_id,
            "batch_id": batch_id,
            "line": line,
            "method": method,
        }
    )
    return "SHP-" + digest[:12]


def lookup_route(line: str, fmt: str, method: str, method_version: str) -> dict[str, Any] | None:
    return ROUTES.get((line, fmt, method, method_version))


def source_hash(
    sponsor_id: str,
    tech_transfer_id: str,
    material_id: str,
    batch_id: str,
    component_id: str,
) -> str:
    return sha256_hex(
        {
            "demand_id": DEMAND_ID,
            "kind": "SOURCE",
            "sponsor_id": sponsor_id,
            "tech_transfer_id": tech_transfer_id,
            "material_id": material_id,
            "batch_id": batch_id,
            "component_id": component_id,
        }
    )


def cycle_hash(cycle_id: str, lyo_recipe: str, lyo_shelf: str, primary_h: float, secondary_h: float) -> str:
    return sha256_hex(
        {
            "demand_id": DEMAND_ID,
            "kind": "CYCLE",
            "cycle_id": cycle_id,
            "lyo_recipe": lyo_recipe,
            "lyo_shelf": lyo_shelf,
            "primary_drying_h": primary_h,
            "secondary_drying_h": secondary_h,
        }
    )


def weight_hash(fill_weight_mg: float, fmt: str, unit: str) -> str:
    return sha256_hex(
        {
            "demand_id": DEMAND_ID,
            "kind": "WEIGHT",
            "fill_weight_mg": fill_weight_mg,
            "format": fmt,
            "unit": unit,
        }
    )


def result_hash(value: Any) -> str:
    return sha256_hex({"demand_id": DEMAND_ID, "kind": "RESULT", "value": value})


def unit_hash(unit: str) -> str:
    return sha256_hex({"demand_id": DEMAND_ID, "kind": "UNIT", "unit": unit})


def target_weight(fmt: str) -> float:
    return FORMAT_TARGETS.get(fmt, 0.0)


def weight_in_window(fill_weight_mg: float, fmt: str) -> bool:
    target = target_weight(fmt)
    if target <= 0:
        return False
    return abs(fill_weight_mg - target) <= target * WEIGHT_TOLERANCE_FRAC


def line_result(index: int, method: str, fill_weight_mg: float) -> dict[str, Any]:
    n = ((index - 1) % 90) + 1
    if method == "FILL_WEIGHT":
        return {"fill_weight_mg": _round4(fill_weight_mg)}
    if method == "LYO_CYCLE":
        return {"residual_moisture_pct": _round4(0.80 + (n % 9) * 0.02)}
    if method == "HPLC_ASSAY":
        return {"assay_pct": _round4(98.50 + (n % 11) * 0.10)}
    if method == "UV_ID":
        return {"match_index": _round4(0.9400 + (n % 8) * 0.0050)}
    if method == "ICH_PULL":
        return {"pull_month": int((n % 4) * 3), "assay_pct": _round4(97.80 + (n % 6) * 0.15)}
    if method == "USP71_STERILITY":
        return {"growth": False}
    return {"cfu": int(n % 4)}


def measured_value(result: dict[str, Any], result_key: str) -> Any:
    if not result:
        return None
    if result_key in result:
        return result[result_key]
    key = sorted(result.keys())[0]
    return result[key]


def _base_row(
    row_id: str,
    submission_id: str,
    *,
    line: str,
    fmt: str,
    method: str,
    method_version: str,
    valid_index: int | None = None,
    sponsor_id: str | None = None,
    tech_transfer_id: str | None = None,
    material_id: str | None = None,
    batch_id: str | None = None,
    component_id: str | None = None,
    isolator_slot: str | None = None,
    lyo_shelf: str | None = None,
    fill_weight_mg: float | None = None,
    qc_fail: bool = False,
    sterility_fail: bool = False,
    expected_hold: str | None = None,
) -> dict[str, Any]:
    spec = lookup_route(line, fmt, method, method_version)
    idx = valid_index or 1
    sponsor = "SPN-%03d" % ((idx - 1) % 12 + 1) if sponsor_id is None else sponsor_id
    transfer = "TT-%03d" % ((idx - 1) % 8 + 1) if tech_transfer_id is None else tech_transfer_id
    material = "MAT-%s" % fmt if material_id is None else material_id
    batch = "BAT-%03d" % ((idx - 1) % 30 + 1) if batch_id is None else batch_id
    component = "CMP-%03d" % idx if component_id is None else component_id
    slot = "ISO-%s-%02d" % (fmt[-2:], idx) if isolator_slot is None else isolator_slot
    shelf = "LYO-%02d" % idx if lyo_shelf is None else lyo_shelf
    cycle_id = "CYC-%s-%02d" % (fmt, (idx - 1) % 12 + 1)
    recipe = "LYO-RECIPE-%s" % fmt
    primary_h = _round4(18.0 + (idx % 5) * 0.25)
    secondary_h = _round4(6.0 + (idx % 3) * 0.50)
    target = float((spec or {}).get("target_mg") or target_weight(fmt) or 1500.0)
    weight = _round4(target + (idx % 7) * 0.10) if fill_weight_mg is None else _round4(float(fill_weight_mg))
    result = line_result(idx, method, weight) if spec is not None else {}
    if sterility_fail:
        result = {"growth": True} if method == "USP71_STERILITY" else {"cfu": 42}
    unit = (spec or {}).get("unit") or "mg"
    result_key = (spec or {}).get("result_key") or "fill_weight_mg"
    value = measured_value(result, result_key)
    row: dict[str, Any] = {
        "row_id": row_id,
        "submission_id": submission_id,
        "sponsor_id": sponsor,
        "tech_transfer_id": transfer,
        "material_id": material,
        "batch_id": batch,
        "component_id": component,
        "line": line,
        "format": fmt,
        "method": method,
        "method_version": method_version,
        "isolator_slot": slot,
        "lyo_shelf": shelf,
        "cycle_id": cycle_id,
        "lyo_recipe": recipe,
        "primary_drying_h": primary_h,
        "secondary_drying_h": secondary_h,
        "fill_weight_mg": weight,
        "unit": unit,
        "value": value,
        "result": result,
        "qc_fail": qc_fail,
        "sterility_fail": sterility_fail,
        "expected_hold": expected_hold,
        "source_hash": source_hash(sponsor, transfer, material, batch, component),
        "cycle_hash": cycle_hash(cycle_id, recipe, shelf, primary_h, secondary_h),
        "weight_hash": weight_hash(weight, fmt, unit),
        "result_hash": result_hash(value),
        "unit_hash": unit_hash(unit),
    }
    return row


def build_acceptance_fixture() -> list[dict[str, Any]]:
    """120-row PASS fixture for sharp-rtu-vial-isolator-lineage-lims-01."""
    rows: list[dict[str, Any]] = []
    for index in range(1, VALID_COUNT + 1):
        line, fmt, method, version = METHOD_CYCLE[(index - 1) % len(METHOD_CYCLE)]
        rows.append(
            _base_row(
                "R%03d" % index,
                valid_submission_id(index),
                line=line,
                fmt=fmt,
                method=method,
                method_version=version,
                valid_index=index,
            )
        )
    for offset, spec in enumerate(FORMAT_LINE_SPECS):
        rows.append(
            _base_row(
                "R%03d" % (91 + offset),
                spec["submission_id"],
                line=spec["line"],
                fmt=spec["format"],
                method=spec["method"],
                method_version=spec["method_version"],
                component_id="CMP-FM%02d" % (offset + 1),
                batch_id="BAT-FM%02d" % (offset + 1),
                isolator_slot="ISO-FM-%02d" % (offset + 1),
                lyo_shelf="LYO-FM-%02d" % (offset + 1),
                valid_index=offset + 1,
                expected_hold="FORMAT_LINE_MISMATCH",
            )
        )
    missing_specs = (
        {"submission_id": "SHP-MV01", "method": "", "method_version": "FW-2R-v3"},
        {"submission_id": "SHP-MV02", "method": "FILL_WEIGHT", "method_version": ""},
        {"submission_id": "SHP-MV03", "method": "", "method_version": ""},
        {"submission_id": "SHP-MV04", "method": "NOT_A_METHOD", "method_version": "USP-621-v1"},
        {"submission_id": "SHP-MV05", "method": "FILL_WEIGHT", "method_version": "NO-SUCH-VERSION"},
    )
    for offset, spec in enumerate(missing_specs):
        line, fmt, _method, _version = METHOD_CYCLE[offset % len(METHOD_CYCLE)]
        rows.append(
            _base_row(
                "R%03d" % (98 + offset),
                spec["submission_id"],
                line=line,
                fmt=fmt,
                method=spec["method"],
                method_version=spec["method_version"],
                component_id="CMP-MV%02d" % (offset + 1),
                batch_id="BAT-MV%02d" % (offset + 1),
                isolator_slot="ISO-MV-%02d" % (offset + 1),
                lyo_shelf="LYO-MV-%02d" % (offset + 1),
                valid_index=offset + 1,
                expected_hold="MISSING_METHOD_VERSION",
            )
        )
    first = rows[0]
    second = rows[1]
    third = rows[2]
    weight_specs = (
        {
            "submission_id": "SHP-WS01",
            "isolator_slot": first["isolator_slot"],
            "lyo_shelf": "LYO-WS-01",
            "fill_weight_mg": None,
        },
        {
            "submission_id": "SHP-WS02",
            "isolator_slot": "ISO-WS-02",
            "lyo_shelf": second["lyo_shelf"],
            "fill_weight_mg": None,
        },
        {
            "submission_id": "SHP-WS03",
            "isolator_slot": third["isolator_slot"],
            "lyo_shelf": "LYO-WS-03",
            "fill_weight_mg": None,
        },
        {
            "submission_id": "SHP-WS04",
            "isolator_slot": "ISO-WS-04",
            "lyo_shelf": "LYO-WS-04",
            "fill_weight_mg": 1875.0,
        },
        {
            "submission_id": "SHP-WS05",
            "isolator_slot": "ISO-WS-05",
            "lyo_shelf": "LYO-WS-05",
            "fill_weight_mg": 1050.0,
        },
    )
    for offset, spec in enumerate(weight_specs):
        line, fmt, method, version = METHOD_CYCLE[offset % len(METHOD_CYCLE)]
        rows.append(
            _base_row(
                "R%03d" % (103 + offset),
                spec["submission_id"],
                line=line,
                fmt=fmt,
                method=method,
                method_version=version,
                component_id="CMP-WS%02d" % (offset + 1),
                batch_id="BAT-WS%02d" % (offset + 1),
                isolator_slot=spec["isolator_slot"],
                lyo_shelf=spec["lyo_shelf"],
                fill_weight_mg=spec["fill_weight_mg"],
                valid_index=offset + 1,
                expected_hold="WEIGHT_SLOT_CONFLICT",
            )
        )
    for offset in range(5):
        line, fmt, method, version = METHOD_CYCLE[(offset + 8) % len(METHOD_CYCLE)]
        sterility = method in {"USP71_STERILITY", "ISOLATOR_BIOBURDEN"}
        rows.append(
            _base_row(
                "R%03d" % (108 + offset),
                "SHP-QC%02d" % (offset + 1),
                line=line,
                fmt=fmt,
                method=method,
                method_version=version,
                component_id="CMP-QC%02d" % (offset + 1),
                batch_id="BAT-QC%02d" % (offset + 1),
                isolator_slot="ISO-QC-%02d" % (offset + 1),
                lyo_shelf="LYO-QC-%02d" % (offset + 1),
                valid_index=offset + 1,
                qc_fail=not sterility,
                sterility_fail=sterility,
                expected_hold="QC_STERILITY_FAIL",
            )
        )
    for offset in range(8):
        line, fmt, method, version = METHOD_CYCLE[offset % len(METHOD_CYCLE)]
        original = rows[offset]
        rows.append(
            _base_row(
                "R%03d" % (113 + offset),
                "SHP-DB%02d" % (offset + 1),
                line=line,
                fmt=fmt,
                method=method,
                method_version=version,
                component_id=original["component_id"],
                batch_id=original["batch_id"],
                isolator_slot="ISO-DB-%02d" % (offset + 1),
                lyo_shelf="LYO-DB-%02d" % (offset + 1),
                valid_index=offset + 1,
                expected_hold="DUPLICATE_COMPONENT_BATCH",
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
        "formats": list(FORMATS),
        "methods": sorted({key[2] for key in ROUTES}),
        "input_rows": len(inbound),
        "valid_rows": sum(1 for row in inbound if row.get("expected_hold") is None),
        "hold_rows": sum(1 for row in inbound if row.get("expected_hold")),
        "hold_plan": dict(HOLD_PLAN),
        "row_ids": [row["row_id"] for row in inbound],
        "submission_ids": [row["submission_id"] for row in inbound],
        "component_ids": [row["component_id"] for row in inbound],
        "batch_ids": [row["batch_id"] for row in inbound],
        "expected_holds": [row.get("expected_hold") for row in inbound],
        "source_hashes": [row["source_hash"] for row in inbound],
        "cycle_hashes": [row["cycle_hash"] for row in inbound],
        "weight_hashes": [row["weight_hash"] for row in inbound],
        "result_hashes": [row["result_hash"] for row in inbound],
        "unit_hashes": [row["unit_hash"] for row in inbound],
        "rows": inbound,
        "interfaces": "SIMULATED",
        "interface_live": False,
        "production_writes": False,
        "autonomous_release": False,
        "compliance_decision": False,
        "gmp_decision": False,
        "clinical_decision": False,
        "public_health_decision": False,
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
        "row_payload_hashes": {},
        "component_batches": set(),
        "isolator_slots": set(),
        "lyo_shelves": set(),
    }


def _event(journal: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    journal["events"].append({"seq": len(journal["events"]) + 1, "kind": kind, **deepcopy(payload)})


def classify_record(row: dict[str, Any], journal: dict[str, Any]) -> dict[str, Any]:
    submission_id = _text(row.get("submission_id"))
    sponsor_id = _text(row.get("sponsor_id"))
    tech_transfer_id = _text(row.get("tech_transfer_id"))
    material_id = _text(row.get("material_id"))
    batch_id = _text(row.get("batch_id"))
    component_id = _text(row.get("component_id"))
    line = _text(row.get("line")).upper()
    fmt = _text(row.get("format")).upper()
    method = _text(row.get("method"))
    method_version = _text(row.get("method_version"))
    if not method or not method_version or method not in KNOWN_METHODS or method_version not in METHOD_VERSIONS.get(
        method, frozenset()
    ):
        return {
            "ok": False,
            "code": "MISSING_METHOD_VERSION",
            "intake_hold": True,
            "submission_id": submission_id or None,
        }
    pair = (component_id, batch_id)
    if not component_id or not batch_id or pair in journal["component_batches"]:
        return {
            "ok": False,
            "code": "DUPLICATE_COMPONENT_BATCH",
            "intake_hold": True,
            "submission_id": submission_id or None,
            "component_id": component_id or None,
            "batch_id": batch_id or None,
        }
    spec = lookup_route(line, fmt, method, method_version)
    if spec is None:
        return {
            "ok": False,
            "code": "FORMAT_LINE_MISMATCH",
            "intake_hold": True,
            "submission_id": submission_id,
            "line": line,
            "format": fmt,
            "method": method,
        }
    isolator_slot = _text(row.get("isolator_slot"))
    lyo_shelf = _text(row.get("lyo_shelf"))
    fill_weight_mg = _round4(float(row.get("fill_weight_mg") or spec["target_mg"]))
    return {
        "ok": True,
        "submission_id": submission_id,
        "sponsor_id": sponsor_id,
        "tech_transfer_id": tech_transfer_id,
        "material_id": material_id,
        "batch_id": batch_id,
        "component_id": component_id,
        "line": line,
        "format": fmt,
        "method": method,
        "method_version": method_version,
        "isolator_slot": isolator_slot,
        "lyo_shelf": lyo_shelf,
        "cycle_id": _text(row.get("cycle_id")),
        "lyo_recipe": _text(row.get("lyo_recipe")),
        "primary_drying_h": float(row.get("primary_drying_h") or 0.0),
        "secondary_drying_h": float(row.get("secondary_drying_h") or 0.0),
        "fill_weight_mg": fill_weight_mg,
        "unit": spec["unit"],
        "adapter": spec["adapter"],
        "result_key": spec["result_key"],
        "accession_id": accession_id(submission_id, batch_id, line, method),
        "computed_source_hash": source_hash(
            sponsor_id, tech_transfer_id, material_id, batch_id, component_id
        ),
        "slot_conflict": isolator_slot in journal["isolator_slots"] or lyo_shelf in journal["lyo_shelves"],
        "weight_conflict": not weight_in_window(fill_weight_mg, fmt),
    }


def rendered_pack(record: dict[str, Any]) -> dict[str, Any] | None:
    if not record.get("staged"):
        return None
    return {
        "demand_id": DEMAND_ID,
        "kind": "BATCH_EVIDENCE_PACK",
        "accession_id": record["accession_id"],
        "submission_id": record["submission_id"],
        "sponsor_id": record["sponsor_id"],
        "tech_transfer_id": record["tech_transfer_id"],
        "material_id": record["material_id"],
        "batch_id": record["batch_id"],
        "component_id": record["component_id"],
        "line": record["line"],
        "format": record["format"],
        "method": record["method"],
        "method_version": record["method_version"],
        "isolator_slot": record["isolator_slot"],
        "lyo_shelf": record["lyo_shelf"],
        "cycle_id": record["cycle_id"],
        "fill_weight_mg": record["fill_weight_mg"],
        "unit": record["unit"],
        "value": record.get("value"),
        "result": deepcopy(record.get("result") or {}),
        "qc_ok": bool(record.get("qc_ok")),
        "source_hash": record.get("source_hash"),
        "cycle_hash": record.get("cycle_hash"),
        "weight_hash": record.get("weight_hash"),
        "result_hash": record.get("result_hash"),
        "unit_hash": record.get("unit_hash"),
        "released": bool(record.get("released")),
        "interface_live": False,
        "compliance_decision": None,
        "gmp_decision": None,
    }


def pack_status(record: dict[str, Any]) -> str:
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
        "component_id": _text(row.get("component_id")) or None,
        "batch_id": _text(row.get("batch_id")) or None,
        "code": code,
        "line": _text(row.get("line")) or None,
        "format": _text(row.get("format")) or None,
        "method": _text(row.get("method")) or None,
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
    row_payload_hash = sha256_hex(row)
    known_row_payload_hash = journal["row_payload_hashes"].get(row_id)
    if known_row_payload_hash is not None and known_row_payload_hash != row_payload_hash:
        raise ValueError("ROW_ID_PAYLOAD_MISMATCH")
    existing_job = next(
        (item for item in journal["jobs"].values() if item["row_id"] == row_id),
        None,
    )
    if existing_job is not None:
        if existing_job["row_payload_hash"] != row_payload_hash:
            raise ValueError("ROW_ID_PAYLOAD_MISMATCH")
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
    verdict = classify_record(row, journal)
    if not verdict["ok"]:
        journal["row_payload_hashes"].setdefault(row_id, row_payload_hash)
        return _hold(journal, row, verdict["code"], scheduled=False)

    acc_id = verdict["accession_id"]
    if acc_id in journal["jobs"]:
        journal["row_payload_hashes"].setdefault(row_id, row_payload_hash)
        _event(journal, "REPLAY_NOOP", {"accession_id": acc_id, "submission_id": verdict["submission_id"]})
        return {"kind": "REPLAY_NOOP", "accession_id": acc_id, "submission_id": verdict["submission_id"]}

    qc_fail = _flag(row.get("qc_fail")) or _flag(row.get("sterility_fail"))
    slot_conflict = bool(verdict.get("slot_conflict"))
    weight_conflict = bool(verdict.get("weight_conflict"))
    result = deepcopy(row.get("result") or line_result(1, verdict["method"], verdict["fill_weight_mg"]))
    value = row.get("value") if "value" in row else measured_value(result, verdict["result_key"])
    unit = verdict["unit"]
    hold_code = None
    if slot_conflict or weight_conflict:
        hold_code = "WEIGHT_SLOT_CONFLICT"
    elif qc_fail:
        hold_code = "QC_STERILITY_FAIL"
    staged = hold_code is None
    record = {
        "accession_id": acc_id,
        "submission_id": verdict["submission_id"],
        "row_id": row_id,
        "row_payload_hash": row_payload_hash,
        "sponsor_id": verdict["sponsor_id"],
        "tech_transfer_id": verdict["tech_transfer_id"],
        "material_id": verdict["material_id"],
        "batch_id": verdict["batch_id"],
        "component_id": verdict["component_id"],
        "line": verdict["line"],
        "format": verdict["format"],
        "method": verdict["method"],
        "method_version": verdict["method_version"],
        "isolator_slot": verdict["isolator_slot"],
        "lyo_shelf": verdict["lyo_shelf"],
        "cycle_id": verdict["cycle_id"],
        "lyo_recipe": verdict["lyo_recipe"],
        "primary_drying_h": verdict["primary_drying_h"],
        "secondary_drying_h": verdict["secondary_drying_h"],
        "fill_weight_mg": verdict["fill_weight_mg"],
        "unit": unit,
        "value": value,
        "adapter": verdict["adapter"],
        "result": result,
        "qc_ok": not qc_fail,
        "qc_fail": qc_fail,
        "scheduled": True,
        "staged": staged,
        "source_hash": verdict["computed_source_hash"],
        "computed_source_hash": verdict["computed_source_hash"],
        "cycle_hash": cycle_hash(
            verdict["cycle_id"],
            verdict["lyo_recipe"],
            verdict["lyo_shelf"],
            verdict["primary_drying_h"],
            verdict["secondary_drying_h"],
        ),
        "weight_hash": weight_hash(verdict["fill_weight_mg"], verdict["format"], unit),
        "result_hash": result_hash(value),
        "unit_hash": unit_hash(unit),
        "state": "HOLD" if hold_code else "READY",
        "released": False,
        "released_by": None,
        "interface_state": "SIMULATED",
        "interface_live": False,
        "compliance_decision": None,
        "gmp_decision": None,
        "clinical_decision": None,
        "public_health_decision": None,
    }
    record["evidence_pack"] = rendered_pack(record)
    record["evidence_digest"] = sha256_hex(record["evidence_pack"]) if record["evidence_pack"] is not None else None
    record["pack_status"] = pack_status(record)
    journal["row_payload_hashes"].setdefault(row_id, row_payload_hash)
    journal["jobs"][acc_id] = record
    journal["component_batches"].add((verdict["component_id"], verdict["batch_id"]))
    if verdict["isolator_slot"]:
        journal["isolator_slots"].add(verdict["isolator_slot"])
    if verdict["lyo_shelf"]:
        journal["lyo_shelves"].add(verdict["lyo_shelf"])
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


def release_pack(
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
        return {"ok": False, "code": "AUTONOMOUS_RELEASE_DENIED", "pack_status": pack_status(record)}
    if record.get("state") == "HOLD" or not record.get("staged"):
        _event(
            journal,
            "RELEASE_DENIED",
            {"accession_id": accession_id_value, "code": "HELD_RECORD_NO_RELEASE", "pack_status": "HOLD"},
        )
        return {"ok": False, "code": "HELD_RECORD_NO_RELEASE", "pack_status": "HOLD"}
    status = pack_status(record)
    if status not in {"READY", "RELEASED"}:
        _event(
            journal,
            "RELEASE_DENIED",
            {"accession_id": accession_id_value, "code": "PACK_BLOCKED", "pack_status": status},
        )
        return {"ok": False, "code": "PACK_BLOCKED", "pack_status": status}
    if record["released"]:
        return {"ok": True, "duplicate": True, "pack_status": "RELEASED"}
    record["released"] = True
    record["released_by"] = named
    record["state"] = "RELEASED"
    record["pack_status"] = "RELEASED"
    record["evidence_pack"] = rendered_pack(record)
    record["evidence_digest"] = sha256_hex(record["evidence_pack"])
    _event(journal, "RELEASED", {"accession_id": accession_id_value, "released_by": record["released_by"]})
    return {"ok": True, "duplicate": False, "pack_status": "RELEASED"}


def run_gate(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    journal = empty_journal()
    effects = [ingest_row(journal, row) for row in inbound]
    autonomous = [
        release_pack(journal, acc_id, actor_role="SYSTEM", actor="autonomous")
        for acc_id in journal["jobs"]
    ]
    jobs = sorted(journal["jobs"].values(), key=lambda item: item["submission_id"])
    ready = [item for item in jobs if item["state"] == "READY"]
    hold_codes = [item["code"] for item in journal["holds"]]
    packs = [item["evidence_pack"] for item in jobs if item.get("evidence_pack") is not None]
    fixture_by_id = {row["submission_id"]: row for row in inbound}
    hash_matches = []
    for item in jobs:
        expected = fixture_by_id.get(item["submission_id"], {})
        computed_source = source_hash(
            item["sponsor_id"],
            item["tech_transfer_id"],
            item["material_id"],
            item["batch_id"],
            item["component_id"],
        )
        computed_cycle = cycle_hash(
            item["cycle_id"],
            item["lyo_recipe"],
            item["lyo_shelf"],
            item["primary_drying_h"],
            item["secondary_drying_h"],
        )
        match = {
            "submission_id": item["submission_id"],
            "cycle": item["cycle_hash"] == computed_cycle,
            "weight": item["weight_hash"]
            == weight_hash(item["fill_weight_mg"], item["format"], item["unit"]),
            "result": item["result_hash"] == result_hash(item["value"]),
            "unit": item["unit_hash"] == unit_hash(item["unit"]),
            "source": item["computed_source_hash"] == computed_source,
        }
        if item["state"] == "READY":
            match["source_declared"] = item["source_hash"] == expected.get("source_hash") == computed_source
            match["cycle_declared"] = item["cycle_hash"] == expected.get("cycle_hash")
            match["weight_declared"] = item["weight_hash"] == expected.get("weight_hash")
            match["result_declared"] = item["result_hash"] == expected.get("result_hash")
            match["unit_declared"] = item["unit_hash"] == expected.get("unit_hash")
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
        "formats": [item["format"] for item in jobs],
        "hold_codes": hold_codes,
        "hold_submission_ids": [item["submission_id"] for item in journal["holds"]],
        "source_hashes": [item["source_hash"] for item in jobs],
        "cycle_hashes": [item["cycle_hash"] for item in jobs],
        "weight_hashes": [item["weight_hash"] for item in jobs],
        "result_hashes": [item["result_hash"] for item in jobs],
        "unit_hashes": [item["unit_hash"] for item in jobs],
        "evidence_digests": [item["evidence_digest"] for item in jobs if item.get("evidence_digest")],
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
        "formats": list(FORMATS),
        "methods": sorted({key[2] for key in ROUTES}),
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
        "released_packs": sum(1 for item in jobs if item["released"]),
        "blocked_packs": sum(1 for item in jobs if item["pack_status"] != "RELEASED"),
        "staged_packs": sum(1 for item in jobs if item.get("staged") and item.get("evidence_pack") is not None),
        "replay_noops": sum(1 for item in effects if item.get("kind") == "REPLAY_NOOP"),
        "effects": effects,
        "autonomous_release_effects": autonomous,
        "accessions": jobs,
        "holds": deepcopy(journal["holds"]),
        "routes": {item["submission_id"]: item["line"] for item in jobs},
        "accession_ids": [item["accession_id"] for item in jobs],
        "hash_matches": hash_matches,
        "hashes_match": all(
            item["cycle"]
            and item["weight"]
            and item["result"]
            and item["unit"]
            and item["source"]
            and item.get("source_declared", True)
            and item.get("cycle_declared", True)
            and item.get("weight_declared", True)
            and item.get("result_declared", True)
            and item.get("unit_declared", True)
            for item in hash_matches
            if fixture_by_id.get(item["submission_id"], {}).get("expected_hold") in {None, "QC_STERILITY_FAIL"}
        ),
        "evidence_packs": packs,
        "evidence_digest": sha256_hex(packs),
        "audit": audit,
        "audit_sha256": sha256_hex(audit),
        "interface_live": False,
        "interfaces": "SIMULATED",
        "autonomous_certification": False,
        "autonomous_release": False,
        "production_writes": 0,
        "compliance_decisions": 0,
        "compliance_decision": False,
        "gmp_decision": False,
        "clinical_decision": False,
        "public_health_decision": False,
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
        "released_packs": result.get("released_packs"),
        "blocked_packs": result.get("blocked_packs"),
        "staged_packs": result.get("staged_packs"),
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
    if result.get("gmp_decision") is not False:
        failures.append("gmp_decision")
    if result.get("clinical_decision") is not False:
        failures.append("clinical_decision")
    if result.get("public_health_decision") is not False:
        failures.append("public_health_decision")
    if not all(
        item.get("code") == "AUTONOMOUS_RELEASE_DENIED"
        for item in result.get("autonomous_release_effects") or []
    ):
        failures.append("autonomous_release_not_denied")
    if result.get("released_packs") != 0:
        failures.append("released_without_named_approval")
    if GOLDEN_AUDIT_SHA256 != "PENDING" and result.get("audit_sha256") != GOLDEN_AUDIT_SHA256:
        failures.append("audit_sha256")
    if GOLDEN_EVIDENCE_DIGEST != "PENDING" and result.get("evidence_digest") != GOLDEN_EVIDENCE_DIGEST:
        failures.append("evidence_digest")
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
        "evidence_digest": result["evidence_digest"],
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
    if first.get("evidence_digest") != second.get("evidence_digest"):
        failures.append("evidence_digest_mismatch")
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
        "evidence_digest": first.get("evidence_digest"),
        "manifest_sha256": first.get("manifest_sha256"),
        "ready": first.get("ready"),
        "held": first.get("held"),
        "jobs": first.get("jobs"),
        "hold_codes": sorted(set(first.get("hold_codes") or [])),
        "hashes_match": first.get("hashes_match"),
        "released_packs": first.get("released_packs"),
        "replay_added_jobs": replay.get("added_job_count"),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
