#!/usr/bin/env python3
"""Oregon BrewLab sample/report reconciliation LIMS.

Demand: oregon-brewlab-sample-report-reconciliation-lims-01
Buyer: Oregon BrewLab / Dana Garves

Order/form and container reconciliation. Cold-chain and volume gates.
ASBC method routing. QC. Report-class selection. Simulated status
notification. Staged release until a named human.

Public Oregon BrewLab intake facts (oregonbrewlab.com/sample-submission,
2025 Sample Submission Form, 2025 price list, product pages):
- every sample must travel with a Sample Submission Form
- container label must match the form Sample Name
- standard minimum 4 oz; VDK and FCR require 12 oz+; extra tests need 2x
- micro samples must arrive in an unopened bottle or can
- FCR requires a sealed bottle, can, or crowler
- VDK, microbiological, kombucha, and heavily fruited samples ship
  overnight with ice packs
- ASBC methods and units are taken from the public 2025 catalog
- Analysis Report / Notarized Report are the TTB and state report classes

Acceptance: replay 120 synthetic submissions — 96 valid, 8 form/container
mismatches, 6 duplicate IDs, 5 warm microbiology/VDK shipments,
5 insufficient-volume containers. PASS only if exactly 96 become READY;
all 24 defects receive the correct HOLD; no duplicate jobs;
method/version/unit/source hashes match the golden manifest; replay is
idempotent; reports remain STAGED until named human release.

HOLD / BUILD-AND-VERIFY. Synthetic fixtures only. Adapters stay
simulated/read-only until a buyer/vendor golden round trip. No
production writes, outreach, prospect-facing demo, or automatic
release. PRE-SALE TRANSPORT: NONE.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

DEMAND_ID = "oregon-brewlab-sample-report-reconciliation-lims-01"
SCHEMA = "commons-oregon-brewlab-sample-report-reconciliation-lims/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
BUYER = "Oregon BrewLab / Dana Garves"
HUMAN_RELEASER = "RELEASER"
VALID_COUNT = 96
HOLD_COUNT = 24
INPUT_COUNT = VALID_COUNT + HOLD_COUNT

HOLD_CODES = (
    "FORM_CONTAINER_MISMATCH",
    "DUPLICATE_ID",
    "WARM_MICRO_VDK",
    "INSUFFICIENT_VOLUME",
)
HOLD_CODE_COUNTS = {
    "FORM_CONTAINER_MISMATCH": 8,
    "DUPLICATE_ID": 6,
    "WARM_MICRO_VDK": 5,
    "INSUFFICIENT_VOLUME": 5,
}
REPORT_CLASSES = {
    "STANDARD": {"sku": None, "label": "Standard analysis report"},
    "TTB": {"sku": "550", "label": "Analysis Report — TTB & State Requirements"},
    "NOTARIZED": {"sku": "551", "label": "Notarized Report"},
}
UNOPENED_PACKAGE = frozenset({"unopened_bottle", "unopened_can", "unopened_crowler"})
SEALED_ANY = UNOPENED_PACKAGE | frozenset(
    {"sealed_jar", "mason_jar", "nalgene", "approved_container"}
)
COLD_FAMILIES = frozenset({"micro", "vdk", "kombucha", "fruited"})

# Public ASBC / OBL catalog. Source URLs are the published pages, not live I/O.
ANALYSES: dict[str, dict[str, Any]] = {
    "ABV": {
        "sku": "501",
        "method": "ASBC Beer-4G",
        "version": "Beer-4G",
        "unit": "%ABV",
        "source": "https://oregonbrewlab.com/wp-content/uploads/2025/01/2025-OBL-Price-List.pdf",
        "min_volume_oz": 4.0,
        "requires_cold": False,
        "container_class": "sealed_any",
        "family": "chemistry",
        "route": "ASBC_BEER_4G",
    },
    "IBU": {
        "sku": "502",
        "method": "ASBC Beer-23A",
        "version": "Beer-23A",
        "unit": "IBU",
        "source": "https://oregonbrewlab.com/wp-content/uploads/2025/01/2025-OBL-Price-List.pdf",
        "min_volume_oz": 4.0,
        "requires_cold": False,
        "container_class": "sealed_any",
        "family": "chemistry",
        "route": "ASBC_BEER_23A",
    },
    "PH": {
        "sku": "503",
        "method": "ASBC Beer-9",
        "version": "Beer-9",
        "unit": "pH",
        "source": "https://oregonbrewlab.com/wp-content/uploads/2025/01/2025-OBL-Price-List.pdf",
        "min_volume_oz": 4.0,
        "requires_cold": False,
        "container_class": "sealed_any",
        "family": "chemistry",
        "route": "ASBC_BEER_9",
    },
    "SRM": {
        "sku": "504",
        "method": "ASBC Beer-10A",
        "version": "Beer-10A",
        "unit": "SRM",
        "source": "https://oregonbrewlab.com/wp-content/uploads/2025/01/2025-OBL-Price-List.pdf",
        "min_volume_oz": 4.0,
        "requires_cold": False,
        "container_class": "sealed_any",
        "family": "chemistry",
        "route": "ASBC_BEER_10A",
    },
    "VDK": {
        "sku": "527",
        "method": "ASBC Beer-25B",
        "version": "Beer-25B",
        "unit": "mg/L",
        "source": "https://oregonbrewlab.com/product/vdks/",
        "min_volume_oz": 12.0,
        "requires_cold": True,
        "container_class": "unopened_package",
        "family": "vdk",
        "route": "ASBC_BEER_25B",
    },
    "FCR": {
        "sku": "FCR",
        "method": "ASBC Beer-22A",
        "version": "Beer-22A",
        "unit": "Sigma",
        "source": "https://oregonbrewlab.com/product/fcr/",
        "min_volume_oz": 12.0,
        "requires_cold": False,
        "container_class": "unopened_package",
        "family": "foam",
        "route": "ASBC_BEER_22A",
    },
    "MICRO_UBA": {
        "sku": "UBA",
        "method": "ASBC Microbiological Control-2B",
        "version": "Microbiological Control-2B",
        "unit": "Absent/Present",
        "source": "https://oregonbrewlab.com/product/micro-combo/",
        "min_volume_oz": 4.0,
        "requires_cold": True,
        "container_class": "unopened_package",
        "family": "micro",
        "route": "ASBC_MICRO_2B",
    },
    "MICRO_COMBO": {
        "sku": "MICRO-COMBO",
        "method": "ASBC Microbiological Control-2B+5A",
        "version": "Microbiological Control-2B,5A",
        "unit": "Absent/Present",
        "source": "https://oregonbrewlab.com/product/micro-combo/",
        "min_volume_oz": 4.0,
        "requires_cold": True,
        "container_class": "unopened_package",
        "family": "micro",
        "route": "ASBC_MICRO_COMBO",
    },
    "KOMBUCHA_ABV": {
        "sku": "501",
        "method": "ASBC Beer-4G",
        "version": "Beer-4G",
        "unit": "%ABV",
        "source": "https://oregonbrewlab.com/sample-submission/",
        "min_volume_oz": 4.0,
        "requires_cold": True,
        "container_class": "sealed_any",
        "family": "kombucha",
        "route": "ASBC_BEER_4G_KOMBUCHA",
    },
}

GOLDEN_COUNTS = {
    "input_rows": INPUT_COUNT,
    "ready": VALID_COUNT,
    "held": HOLD_COUNT,
    "duplicate_jobs": 0,
    "staged_reports": VALID_COUNT,
    "released_reports": 0,
    "replay_added_jobs": 0,
    "production_writes": 0,
}

# Locked after the first deterministic PASS of this exact fixture.
GOLDEN_FIXTURE_SHA256 = "e966c3143f9b8edebac7547e46949d7d6444636ecfd4256ae896c081524a09cf"
GOLDEN_CATALOG_SHA256 = "657d60b6f1e1b8ccfe4358950fa93cf21fd741fc714fd3444a6fe2d030f44613"
GOLDEN_AUDIT_SHA256 = "bf5dc68f8f07262e9f195441a84ca54a56d8d86e40e572e9b8768786a7f930ca"
GOLDEN_REPORT_DIGEST = "2e22f1f918744479a2e00b420323f9de02a7d1936e8feb0f0e323efd4bd9ef3a"
HERE = Path(__file__).resolve().parent
FIXTURE_DIR = HERE / "revenue" / "oregon_brewlab_sample_report"

VALID_PLAN: tuple[tuple[str, int, str], ...] = (
    ("ABV", 16, "STANDARD"),
    ("IBU", 12, "STANDARD"),
    ("PH", 12, "STANDARD"),
    ("SRM", 12, "STANDARD"),
    ("VDK", 12, "STANDARD"),
    ("MICRO_UBA", 12, "STANDARD"),
    ("MICRO_COMBO", 8, "STANDARD"),
    ("FCR", 6, "STANDARD"),
    ("KOMBUCHA_ABV", 4, "STANDARD"),
    ("ABV", 2, "TTB"),
)


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


def _volume(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def analysis_spec(analysis: str) -> dict[str, Any] | None:
    return ANALYSES.get(_text(analysis).upper())


def min_volume_oz(analysis: str, additional_testing: bool = False) -> float:
    spec = analysis_spec(analysis)
    if spec is None:
        return 4.0
    minimum = float(spec["min_volume_oz"])
    if additional_testing:
        minimum *= 2.0
    return minimum


def method_field_hashes(analysis: str) -> dict[str, str]:
    spec = analysis_spec(analysis)
    if spec is None:
        return {
            "method_sha256": "",
            "version_sha256": "",
            "unit_sha256": "",
            "source_sha256": "",
        }
    return {
        "method_sha256": sha256_hex(spec["method"]),
        "version_sha256": sha256_hex(spec["version"]),
        "unit_sha256": sha256_hex(spec["unit"]),
        "source_sha256": sha256_hex(spec["source"]),
    }


def golden_catalog() -> dict[str, Any]:
    methods = {}
    for analysis, spec in ANALYSES.items():
        hashes = method_field_hashes(analysis)
        methods[analysis] = {
            "sku": spec["sku"],
            "method": spec["method"],
            "version": spec["version"],
            "unit": spec["unit"],
            "source": spec["source"],
            "min_volume_oz": spec["min_volume_oz"],
            "requires_cold": spec["requires_cold"],
            "container_class": spec["container_class"],
            "family": spec["family"],
            "route": spec["route"],
            **hashes,
        }
    body = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "methods": methods,
    }
    body["catalog_sha256"] = sha256_hex({key: value for key, value in body.items() if key != "catalog_sha256"})
    return body


def job_id(sample_id: str, analysis: str) -> str:
    digest = sha256_hex(
        {
            "demand_id": DEMAND_ID,
            "sample_id": sample_id,
            "analysis": analysis,
        }
    )
    return "OBL-" + digest[:12]


def source_hashes(sample_id: str, analysis: str, form_present: bool) -> dict[str, str]:
    form_hash = (
        sha256_hex({"demand_id": DEMAND_ID, "kind": "FORM", "sample_id": sample_id})
        if form_present
        else ""
    )
    container_hash = sha256_hex(
        {"demand_id": DEMAND_ID, "kind": "CONTAINER", "sample_id": sample_id, "analysis": analysis}
    )
    return {"form": form_hash, "container": container_hash}


def qc_packet(index: int, analysis: str) -> dict[str, Any]:
    spec = analysis_spec(analysis) or {}
    return {
        "qc_id": "SIM-OBL-QC-01",
        "adapter": "SIMULATED",
        "analysis": analysis,
        "check_standard_ok": True,
        "replicate_ok": True,
        "blank_ok": True,
        "qc_index": index,
        "qc_ok": True,
        "unit": spec.get("unit"),
    }


def result_packet(index: int, analysis: str) -> dict[str, Any]:
    spec = analysis_spec(analysis) or {}
    family = spec.get("family")
    if family == "micro":
        value: Any = "Absent"
    elif analysis == "ABV" or analysis == "KOMBUCHA_ABV":
        value = round(4.0 + ((index - 1) % 40) * 0.1, 1)
    elif analysis == "IBU":
        value = round(8.0 + ((index - 1) % 50) * 0.5, 1)
    elif analysis == "PH":
        value = round(3.80 + ((index - 1) % 20) * 0.02, 2)
    elif analysis == "SRM":
        value = round(4.0 + ((index - 1) % 30) * 0.2, 1)
    elif analysis == "VDK":
        value = round(0.05 + ((index - 1) % 10) * 0.01, 2)
    elif analysis == "FCR":
        value = round(110.0 + ((index - 1) % 15) * 1.0, 1)
    else:
        value = index
    return {
        "adapter": "SIMULATED",
        "analysis": analysis,
        "value": value,
        "unit": spec.get("unit"),
        "qualifier": "",
        "method": spec.get("method"),
        "method_version": spec.get("version"),
    }


def _default_container(analysis: str) -> str:
    spec = analysis_spec(analysis) or {}
    if spec.get("container_class") == "unopened_package":
        if spec.get("family") == "micro":
            return "unopened_can"
        if analysis == "FCR":
            return "unopened_crowler"
        return "unopened_bottle"
    if spec.get("family") == "kombucha":
        return "sealed_jar"
    return "sealed_jar"


def _base_row(
    row_id: str,
    sample_id: str,
    analysis: str,
    *,
    volume_oz: float | None = None,
    additional_testing: bool = False,
    form_present: bool = True,
    form_sample_name: str | None = None,
    container_label: str | None = None,
    container_type: str | None = None,
    ice_pack: bool | None = None,
    overnight: bool | None = None,
    beverage: str = "beer",
    report_class: str = "STANDARD",
    valid_index: int | None = None,
    expected_hold: str | None = None,
) -> dict[str, Any]:
    spec = analysis_spec(analysis) or ANALYSES["ABV"]
    needs_cold = bool(spec["requires_cold"])
    name = form_sample_name if form_sample_name is not None else sample_id
    label = container_label if container_label is not None else sample_id
    container = container_type if container_type is not None else _default_container(analysis)
    vol = float(spec["min_volume_oz"] * (2 if additional_testing else 1)) if volume_oz is None else float(volume_oz)
    cold = True if ice_pack is None else bool(ice_pack)
    night = True if overnight is None else bool(overnight)
    if not needs_cold and ice_pack is None:
        cold = False
    if not needs_cold and overnight is None:
        night = False
    hashes = source_hashes(sample_id, analysis, form_present)
    field_hashes = method_field_hashes(analysis)
    row: dict[str, Any] = {
        "row_id": row_id,
        "sample_id": sample_id,
        "analysis": analysis,
        "beverage": beverage,
        "volume_oz": vol,
        "additional_testing": additional_testing,
        "form_present": form_present,
        "form_sample_name": name,
        "container_label": label,
        "container_type": container,
        "ice_pack": cold,
        "overnight": night,
        "report_class": report_class,
        "form_hash": hashes["form"],
        "container_hash": hashes["container"],
        "expected_hold": expected_hold,
        "interface_state": "SIMULATED",
        "interface_live": False,
        **field_hashes,
    }
    if expected_hold is None and valid_index is not None:
        qc = qc_packet(valid_index, analysis)
        result = result_packet(valid_index, analysis)
        row["qc"] = qc
        row["result"] = result
        row["qc_hash"] = sha256_hex(qc)
        row["result_hash"] = sha256_hex(result)
    return row


def build_acceptance_fixture() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    index = 0
    for analysis, count, report_class in VALID_PLAN:
        for _offset in range(count):
            index += 1
            beverage = "kombucha" if analysis == "KOMBUCHA_ABV" else "beer"
            rows.append(
                _base_row(
                    "R%03d" % index,
                    "OBL-V-%03d" % index,
                    analysis,
                    beverage=beverage,
                    report_class=report_class,
                    valid_index=index,
                )
            )
    if index != VALID_COUNT:
        raise RuntimeError("valid plan must total %s rows, got %s" % (VALID_COUNT, index))

    mismatch_specs = (
        {"analysis": "ABV", "form_present": False, "form_sample_name": ""},
        {"analysis": "ABV", "form_sample_name": "FORM-OTHER", "container_label": "OBL-M-02"},
        {"analysis": "MICRO_UBA", "container_type": "mason_jar"},
        {"analysis": "MICRO_UBA", "container_type": "falcon_tube"},
        {"analysis": "VDK", "container_type": "nalgene", "volume_oz": 12.0, "ice_pack": True, "overnight": True},
        {"analysis": "MICRO_UBA", "container_type": "whirlpack"},
        {"analysis": "MICRO_UBA", "container_type": "reused_water_bottle"},
        {"analysis": "ABV", "form_sample_name": "", "container_label": "OBL-M-08"},
    )
    for offset, extra in enumerate(mismatch_specs):
        sample_id = "OBL-M-%02d" % (offset + 1)
        kwargs = dict(extra)
        analysis = kwargs.pop("analysis")
        rows.append(
            _base_row(
                "R%03d" % (97 + offset),
                sample_id,
                analysis,
                expected_hold="FORM_CONTAINER_MISMATCH",
                **kwargs,
            )
        )
    for offset in range(6):
        original = rows[offset]
        rows.append(
            _base_row(
                "R%03d" % (105 + offset),
                original["sample_id"],
                original["analysis"],
                volume_oz=original["volume_oz"],
                report_class=original["report_class"],
                expected_hold="DUPLICATE_ID",
            )
        )
    warm_specs = (
        {"analysis": "VDK", "ice_pack": False, "overnight": True, "volume_oz": 12.0},
        {"analysis": "VDK", "ice_pack": True, "overnight": False, "volume_oz": 12.0},
        {"analysis": "MICRO_UBA", "ice_pack": False, "overnight": True},
        {"analysis": "MICRO_UBA", "ice_pack": True, "overnight": False},
        {"analysis": "MICRO_COMBO", "ice_pack": False, "overnight": False},
    )
    for offset, extra in enumerate(warm_specs):
        kwargs = dict(extra)
        analysis = kwargs.pop("analysis")
        rows.append(
            _base_row(
                "R%03d" % (111 + offset),
                "OBL-W-%02d" % (offset + 1),
                analysis,
                expected_hold="WARM_MICRO_VDK",
                **kwargs,
            )
        )
    volume_specs = (
        {"analysis": "ABV", "volume_oz": 2.0},
        {"analysis": "IBU", "volume_oz": 3.0},
        {"analysis": "VDK", "volume_oz": 4.0, "ice_pack": True, "overnight": True},
        {"analysis": "FCR", "volume_oz": 8.0},
        {"analysis": "VDK", "volume_oz": 12.0, "additional_testing": True, "ice_pack": True, "overnight": True},
    )
    for offset, extra in enumerate(volume_specs):
        kwargs = dict(extra)
        analysis = kwargs.pop("analysis")
        rows.append(
            _base_row(
                "R%03d" % (116 + offset),
                "OBL-U-%02d" % (offset + 1),
                analysis,
                expected_hold="INSUFFICIENT_VOLUME",
                **kwargs,
            )
        )
    if len(rows) != INPUT_COUNT:
        raise RuntimeError("acceptance fixture must be exactly %s rows, got %s" % (INPUT_COUNT, len(rows)))
    return rows


def fixture_manifest(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    catalog = golden_catalog()
    body = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "input_rows": len(inbound),
        "valid_rows": sum(1 for row in inbound if row.get("expected_hold") is None),
        "hold_rows": sum(1 for row in inbound if row.get("expected_hold")),
        "hold_plan": dict(HOLD_CODE_COUNTS),
        "row_ids": [row["row_id"] for row in inbound],
        "sample_ids": [row["sample_id"] for row in inbound],
        "expected_holds": [row.get("expected_hold") for row in inbound],
        "catalog_sha256": catalog["catalog_sha256"],
        "method_hashes": {
            analysis: {
                "method_sha256": spec["method_sha256"],
                "version_sha256": spec["version_sha256"],
                "unit_sha256": spec["unit_sha256"],
                "source_sha256": spec["source_sha256"],
            }
            for analysis, spec in catalog["methods"].items()
        },
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
        "notifications": [],
        "events": [],
    }


def _event(journal: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    journal["events"].append({"seq": len(journal["events"]) + 1, "kind": kind, **deepcopy(payload)})


def _notify(journal: dict[str, Any], payload: dict[str, Any]) -> None:
    note = {
        "adapter": "SIMULATED",
        "live": False,
        **deepcopy(payload),
    }
    fingerprint = sha256_hex(note)
    existing = {sha256_hex(item) for item in journal["notifications"]}
    if fingerprint in existing:
        return
    journal["notifications"].append(note)
    _event(journal, "STATUS_NOTIFY", note)


def container_allowed(analysis: str, container_type: str) -> bool:
    spec = analysis_spec(analysis)
    if spec is None:
        return False
    if spec["container_class"] == "unopened_package":
        return container_type in UNOPENED_PACKAGE
    return container_type in SEALED_ANY


def form_container_ok(row: dict[str, Any]) -> bool:
    form_present = _flag(row.get("form_present"))
    form_name = _text(row.get("form_sample_name"))
    label = _text(row.get("container_label"))
    container = _text(row.get("container_type"))
    analysis = _text(row.get("analysis")).upper()
    if not form_present or not form_name or not label:
        return False
    if form_name != label:
        return False
    return container_allowed(analysis, container)


def classify_submission(row: dict[str, Any], seen_sample_ids: set[str]) -> dict[str, Any]:
    sample_id = _text(row.get("sample_id"))
    analysis = _text(row.get("analysis")).upper()
    spec = analysis_spec(analysis)
    volume_oz = _volume(row.get("volume_oz"))
    additional = _flag(row.get("additional_testing"))
    ice_pack = _flag(row.get("ice_pack"))
    overnight = _flag(row.get("overnight"))

    if sample_id and sample_id in seen_sample_ids:
        return {"ok": False, "code": "DUPLICATE_ID", "sample_id": sample_id, "analysis": analysis}
    if not sample_id or spec is None or not form_container_ok(row):
        return {
            "ok": False,
            "code": "FORM_CONTAINER_MISMATCH",
            "sample_id": sample_id or None,
            "analysis": analysis or None,
        }
    if volume_oz < min_volume_oz(analysis, additional):
        return {
            "ok": False,
            "code": "INSUFFICIENT_VOLUME",
            "sample_id": sample_id,
            "analysis": analysis,
            "volume_oz": volume_oz,
            "min_volume_oz": min_volume_oz(analysis, additional),
        }
    if spec["requires_cold"] and spec["family"] in COLD_FAMILIES and (not ice_pack or not overnight):
        if spec["family"] in {"micro", "vdk"}:
            code = "WARM_MICRO_VDK"
        else:
            code = "WARM_MICRO_VDK"
        return {
            "ok": False,
            "code": code,
            "sample_id": sample_id,
            "analysis": analysis,
            "ice_pack": ice_pack,
            "overnight": overnight,
        }
    hashes = method_field_hashes(analysis)
    return {
        "ok": True,
        "sample_id": sample_id,
        "analysis": analysis,
        "method": spec["method"],
        "method_version": spec["version"],
        "unit": spec["unit"],
        "source": spec["source"],
        "route": spec["route"],
        "family": spec["family"],
        "job_id": job_id(sample_id, analysis),
        **hashes,
    }


def rendered_report(record: dict[str, Any]) -> dict[str, Any]:
    result = record.get("result") or {}
    qc = record.get("qc") or {}
    report_class = _text(record.get("report_class")) or "STANDARD"
    klass = REPORT_CLASSES.get(report_class, REPORT_CLASSES["STANDARD"])
    return {
        "demand_id": DEMAND_ID,
        "job_id": record["job_id"],
        "sample_id": record["sample_id"],
        "analysis": record["analysis"],
        "method": record["method"],
        "method_version": record["method_version"],
        "unit": record["unit"],
        "source": record["source"],
        "report_class": report_class,
        "report_class_sku": klass["sku"],
        "report_class_label": klass["label"],
        "value": result.get("value"),
        "qualifier": result.get("qualifier", ""),
        "qc_ok": qc.get("qc_ok"),
        "source_hashes": {
            "form": record.get("form_hash"),
            "container": record.get("container_hash"),
            "result": record.get("result_hash"),
            "qc": record.get("qc_hash"),
            "method": record.get("method_sha256"),
            "version": record.get("version_sha256"),
            "unit": record.get("unit_sha256"),
            "source": record.get("source_sha256"),
        },
        "status": "RELEASED" if record.get("released") else "STAGED",
        "interface_live": False,
    }


def report_status(record: dict[str, Any]) -> str:
    if record.get("released"):
        return "RELEASED"
    if not record.get("result"):
        return "BLOCKED_MISSING_RESULT"
    if not record.get("qc_signoff"):
        return "BLOCKED_MISSING_QC"
    return "STAGED"


def ingest_row(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    row_id = _text(row.get("row_id"))
    existing_job = next(
        (item for item in journal["jobs"].values() if item["sample_id"] == _text(row.get("sample_id")) and item.get("row_id") == row_id),
        None,
    )
    if existing_job is not None:
        _event(
            journal,
            "REPLAY_NOOP",
            {"job_id": existing_job["job_id"], "sample_id": existing_job["sample_id"]},
        )
        return {
            "kind": "REPLAY_NOOP",
            "job_id": existing_job["job_id"],
            "sample_id": existing_job["sample_id"],
        }
    seen = {item["sample_id"] for item in journal["jobs"].values()}
    verdict = classify_submission(row, seen)
    if not verdict["ok"]:
        hold = {
            "row_id": row_id,
            "sample_id": verdict.get("sample_id"),
            "code": verdict["code"],
            "analysis": _text(row.get("analysis")) or None,
            "ready": False,
        }
        fingerprint = sha256_hex(hold)
        existing = {sha256_hex(item) for item in journal["holds"]}
        if fingerprint not in existing:
            journal["holds"].append(hold)
            _event(journal, "HOLD", hold)
            _notify(
                journal,
                {
                    "kind": "STATUS",
                    "sample_id": hold["sample_id"],
                    "row_id": row_id,
                    "status": "HOLD",
                    "code": hold["code"],
                },
            )
            return {"kind": "HOLD", "duplicate": False, **hold}
        return {"kind": "HOLD", "duplicate": True, **hold}

    acc_id = verdict["job_id"]
    if acc_id in journal["jobs"]:
        _event(journal, "REPLAY_NOOP", {"job_id": acc_id, "sample_id": verdict["sample_id"]})
        return {"kind": "REPLAY_NOOP", "job_id": acc_id, "sample_id": verdict["sample_id"]}

    qc = deepcopy(row.get("qc") or qc_packet(0, verdict["analysis"]))
    result = deepcopy(row.get("result") or result_packet(0, verdict["analysis"]))
    report_class = _text(row.get("report_class")).upper() or "STANDARD"
    if report_class not in REPORT_CLASSES:
        report_class = "STANDARD"
    record = {
        "job_id": acc_id,
        "sample_id": verdict["sample_id"],
        "row_id": row_id,
        "analysis": verdict["analysis"],
        "method": verdict["method"],
        "method_version": verdict["method_version"],
        "unit": verdict["unit"],
        "source": verdict["source"],
        "route": verdict["route"],
        "family": verdict["family"],
        "method_sha256": verdict["method_sha256"],
        "version_sha256": verdict["version_sha256"],
        "unit_sha256": verdict["unit_sha256"],
        "source_sha256": verdict["source_sha256"],
        "volume_oz": _volume(row.get("volume_oz")),
        "container_type": _text(row.get("container_type")),
        "form_hash": _text(row.get("form_hash")),
        "container_hash": _text(row.get("container_hash")),
        "report_class": report_class,
        "qc": qc,
        "qc_hash": _text(row.get("qc_hash")) or sha256_hex(qc),
        "qc_signoff": bool(qc.get("qc_ok")),
        "result": result,
        "result_hash": _text(row.get("result_hash")) or sha256_hex(result),
        "state": "READY",
        "released": False,
        "released_by": None,
        "report_status": "STAGED",
        "interface_state": "SIMULATED",
        "interface_live": False,
    }
    record["report"] = rendered_report(record)
    record["report_digest"] = sha256_hex(record["report"])
    record["report_status"] = report_status(record)
    journal["jobs"][acc_id] = record
    _event(
        journal,
        "READY",
        {"job_id": acc_id, "sample_id": verdict["sample_id"], "route": verdict["route"]},
    )
    _notify(
        journal,
        {
            "kind": "STATUS",
            "sample_id": verdict["sample_id"],
            "row_id": row_id,
            "status": "READY",
            "code": None,
            "job_id": acc_id,
        },
    )
    return {"kind": "READY", "job_id": acc_id, "route": verdict["route"]}


def release_report(
    journal: dict[str, Any],
    job_id_value: str,
    *,
    actor_role: str,
    actor: str,
) -> dict[str, Any]:
    record = journal["jobs"].get(job_id_value)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_JOB"}
    role = _text(actor_role).upper()
    named = _text(actor)
    if role != HUMAN_RELEASER or not named:
        _event(
            journal,
            "RELEASE_DENIED",
            {
                "job_id": job_id_value,
                "code": "AUTONOMOUS_RELEASE_DENIED",
                "actor_role": role or None,
            },
        )
        return {"ok": False, "code": "AUTONOMOUS_RELEASE_DENIED", "report_status": report_status(record)}
    status = report_status(record)
    if status not in {"STAGED", "RELEASED"}:
        _event(
            journal,
            "RELEASE_DENIED",
            {"job_id": job_id_value, "code": "REPORT_BLOCKED", "report_status": status},
        )
        return {"ok": False, "code": "REPORT_BLOCKED", "report_status": status}
    if record["released"]:
        return {"ok": True, "duplicate": True, "report_status": "RELEASED"}
    record["released"] = True
    record["released_by"] = named
    record["report_status"] = "RELEASED"
    record["report"] = rendered_report(record)
    record["report_digest"] = sha256_hex(record["report"])
    _event(journal, "RELEASED", {"job_id": job_id_value, "released_by": record["released_by"]})
    _notify(
        journal,
        {
            "kind": "STATUS",
            "sample_id": record["sample_id"],
            "row_id": record["row_id"],
            "status": "RELEASED",
            "code": None,
            "job_id": job_id_value,
            "released_by": named,
        },
    )
    return {"ok": True, "duplicate": False, "report_status": "RELEASED"}


def run_gate(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    journal = empty_journal()
    effects = [ingest_row(journal, row) for row in inbound]
    autonomous = [
        release_report(journal, job_key, actor_role="SYSTEM", actor="autonomous")
        for job_key in journal["jobs"]
    ]
    jobs = sorted(journal["jobs"].values(), key=lambda item: item["sample_id"])
    hold_codes = [item["code"] for item in journal["holds"]]
    reports = [item["report"] for item in jobs]
    report_digests = [item["report_digest"] for item in jobs]
    catalog = golden_catalog()
    audit = {
        "demand_id": DEMAND_ID,
        "sample_ids": [item["sample_id"] for item in jobs],
        "job_ids": [item["job_id"] for item in jobs],
        "hold_codes": hold_codes,
        "hold_sample_ids": [item["sample_id"] for item in journal["holds"]],
        "routes": {item["sample_id"]: item["route"] for item in jobs},
        "method_hashes": {
            item["sample_id"]: {
                "analysis": item["analysis"],
                "method_sha256": item["method_sha256"],
                "version_sha256": item["version_sha256"],
                "unit_sha256": item["unit_sha256"],
                "source_sha256": item["source_sha256"],
            }
            for item in jobs
        },
        "report_digests": report_digests,
        "ready": [item["sample_id"] for item in jobs if item["state"] == "READY"],
        "staged": [item["sample_id"] for item in jobs if item["report_status"] == "STAGED"],
        "released": [item["sample_id"] for item in jobs if item["released"]],
        "catalog_sha256": catalog["catalog_sha256"],
    }
    body = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "input_rows": len(inbound),
        "ready": sum(1 for item in jobs if item["state"] == "READY"),
        "held": len(journal["holds"]),
        "hold_codes": hold_codes,
        "hold_code_set": sorted(set(hold_codes)),
        "duplicate_jobs": len(jobs) - len({item["sample_id"] for item in jobs}),
        "staged_reports": sum(1 for item in jobs if item["report_status"] == "STAGED"),
        "released_reports": sum(1 for item in jobs if item["released"]),
        "replay_noops": sum(1 for item in effects if item.get("kind") == "REPLAY_NOOP"),
        "effects": effects,
        "autonomous_release_effects": autonomous,
        "jobs": jobs,
        "holds": deepcopy(journal["holds"]),
        "notifications": deepcopy(journal["notifications"]),
        "routes": {item["sample_id"]: item["route"] for item in jobs},
        "job_ids": [item["job_id"] for item in jobs],
        "reports": reports,
        "report_digests": report_digests,
        "report_digest": sha256_hex(reports),
        "catalog": catalog,
        "catalog_sha256": catalog["catalog_sha256"],
        "method_hashes": catalog["methods"],
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
        "duplicate_jobs": result.get("duplicate_jobs"),
        "staged_reports": result.get("staged_reports"),
        "released_reports": result.get("released_reports"),
        "replay_added_jobs": result.get("replay_added_jobs", 0),
        "production_writes": result.get("production_writes"),
    }
    return {"expected": dict(GOLDEN_COUNTS), "actual": actual, "match": actual == GOLDEN_COUNTS}


def hashes_match_catalog(result: dict[str, Any]) -> bool:
    catalog = result.get("catalog") or golden_catalog()
    methods = catalog.get("methods") or {}
    for job in result.get("jobs") or []:
        spec = methods.get(job.get("analysis"))
        if spec is None:
            return False
        if job.get("method_sha256") != spec.get("method_sha256"):
            return False
        if job.get("version_sha256") != spec.get("version_sha256"):
            return False
        if job.get("unit_sha256") != spec.get("unit_sha256"):
            return False
        if job.get("source_sha256") != spec.get("source_sha256"):
            return False
        if job.get("method") != spec.get("method"):
            return False
        if job.get("method_version") != spec.get("version"):
            return False
        if job.get("unit") != spec.get("unit"):
            return False
        if job.get("source") != spec.get("source"):
            return False
    return True


def pass_contract(result: dict[str, Any]) -> list[str]:
    failures = []
    counts = expected_actual(result)
    if not counts["match"]:
        failures.append("counts")
    if result.get("hold_code_set") != sorted(HOLD_CODES):
        failures.append("hold_code_set")
    if Counter(result.get("hold_codes") or []) != Counter(HOLD_CODE_COUNTS):
        failures.append("hold_code_counts")
    if len(set(result.get("job_ids") or [])) != VALID_COUNT:
        failures.append("job_ids_not_unique")
    if result.get("duplicate_jobs") != 0:
        failures.append("duplicate_jobs")
    if any(item.get("ready") for item in result.get("holds") or []):
        failures.append("hold_marked_ready")
    if any(item.get("state") != "READY" for item in result.get("jobs") or []):
        failures.append("job_state")
    if any(item.get("report_status") != "STAGED" for item in result.get("jobs") or []):
        failures.append("report_not_staged")
    if not hashes_match_catalog(result):
        failures.append("method_version_unit_source_hashes")
    if result.get("catalog_sha256") != GOLDEN_CATALOG_SHA256:
        failures.append("catalog_sha256")
    if any(item.get("interface_live") for item in result.get("jobs") or []):
        failures.append("interface_live_job")
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
    if any(item.get("live") for item in result.get("notifications") or []):
        failures.append("live_notification")
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
        "catalog_sha256": result["catalog_sha256"],
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
    if first.get("catalog_sha256") != second.get("catalog_sha256"):
        failures.append("catalog_sha256_mismatch")
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
        "catalog_sha256": first.get("catalog_sha256"),
        "audit_sha256": first.get("audit_sha256"),
        "report_digest": first.get("report_digest"),
        "manifest_sha256": first.get("manifest_sha256"),
        "ready": first.get("ready"),
        "held": first.get("held"),
        "hold_codes": sorted(set(first.get("hold_codes") or [])),
        "staged_reports": first.get("staged_reports"),
        "replay_added_jobs": replay.get("added_job_count"),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
