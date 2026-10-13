#!/usr/bin/env python3
"""Paragon B6–B20 biodiesel sample-to-CoA LIMS.

Demand: paragon-biodiesel-sample-coa-lims-01
Buyer: Paragon Laboratories / Rich McKenzie

Pickup and chain-of-custody through accession, ASTM D7467 method
assignment, simulated results, QA review, and a staged CoA. Named-human
release only.

Frozen 120-row synthetic manifest:
- 100 valid B6–B20 submissions accession once
- 5 HOLD_INCOMPLETE_COC
- 5 HOLD_INCOMPLETE_SDS
- 5 HOLD_DUPLICATE_ID
- 5 HOLD_OOS after results
Replay adds zero records. Values, units, qualifiers, report fields, and
source hashes match the signed golden set.

AquaTrace HOLD / BUILD-AND-VERIFY. Adapters stay simulated/read-only.
No production write, outreach, prospect-facing demo, or automatic release.
PRE-SALE TRANSPORT: NONE.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

DEMAND_ID = "paragon-biodiesel-sample-coa-lims-01"
SCHEMA = "commons-paragon-biodiesel-sample-coa-lims/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
BUYER = "Paragon Laboratories / Rich McKenzie"
HUMAN_RELEASER = "RELEASER"
HUMAN_ACTOR = "rich-mckenzie-reviewer"
SPEC_ID = "ASTM D7467"
SPEC_REVISION = "D7467-23"
BLEND_LANE = "B6-B20"
FIXTURE_DATE = "2026-08-31"

HOLD_CODES = (
    "HOLD_INCOMPLETE_COC",
    "HOLD_INCOMPLETE_SDS",
    "HOLD_DUPLICATE_ID",
    "HOLD_OOS",
)

GOLDEN_COUNTS = {
    "input_rows": 120,
    "accessioned_valid": 100,
    "accessioned_total": 105,
    "hold": 20,
    "incomplete_coc": 5,
    "incomplete_sds": 5,
    "duplicate_id": 5,
    "oos": 5,
    "in_spec": 100,
    "staged_coa": 100,
    "human_released": 100,
    "autonomous_released": 0,
    "duplicate_accessions": 0,
}

# Pinned after first deterministic run of run_gate().
GOLDEN_AUDIT_SHA256 = "70e0875552b9024e42b0117cbcd63fe4d56e7b55277fe2ea700ccfaa9594e8da"
GOLDEN_SET_SHA256 = "13b30045df03d9ac2a8493924bcd5da2a5f51486be77e6a2fb6d4bd109f14275"

BLEND_GRADES = ("B6", "B10", "B15", "B20")

METHODS: dict[str, dict[str, Any]] = {
    "D7371": {
        "name": "ASTM D7371",
        "analyte": "fame",
        "unit": "% vol",
        "spec_min": 6.0,
        "spec_max": 20.0,
        "decimals": 1,
        "in_spec": 11.2,
    },
    "D93": {
        "name": "ASTM D93",
        "analyte": "flash_point",
        "unit": "deg_C",
        "spec_min": 52.0,
        "spec_max": None,
        "decimals": 1,
        "in_spec": 64.0,
    },
    "D445": {
        "name": "ASTM D445",
        "analyte": "viscosity_40c",
        "unit": "mm2_s",
        "spec_min": 1.9,
        "spec_max": 4.1,
        "decimals": 2,
        "in_spec": 2.84,
    },
    "D5453": {
        "name": "ASTM D5453",
        "analyte": "sulfur",
        "unit": "mg_kg",
        "spec_min": None,
        "spec_max": 15.0,
        "decimals": 1,
        "in_spec": 8.4,
    },
    "D664": {
        "name": "ASTM D664",
        "analyte": "acid_number",
        "unit": "mg_KOH_g",
        "spec_min": None,
        "spec_max": 0.3,
        "decimals": 2,
        "in_spec": 0.18,
    },
    "D2709": {
        "name": "ASTM D2709",
        "analyte": "water_sediment",
        "unit": "% vol",
        "spec_min": None,
        "spec_max": 0.05,
        "decimals": 3,
        "in_spec": 0.012,
    },
    "EN15751": {
        "name": "EN 15751",
        "analyte": "oxidation_stability",
        "unit": "h",
        "spec_min": 6.0,
        "spec_max": None,
        "decimals": 1,
        "in_spec": 8.6,
    },
}

PANEL = tuple(METHODS.keys())

OOS_CASES: dict[str, dict[str, Any]] = {
    "PBD-O01": {"method": "D7371", "value": 4.8, "reason": "FAME_BELOW_B6"},
    "PBD-O02": {"method": "D93", "value": 48.0, "reason": "FLASH_BELOW_52C"},
    "PBD-O03": {"method": "D445", "value": 4.52, "reason": "VISCOSITY_ABOVE_4P1"},
    "PBD-O04": {"method": "D5453", "value": 22.0, "reason": "SULFUR_ABOVE_15"},
    "PBD-O05": {"method": "D664", "value": 0.42, "reason": "ACID_ABOVE_0P3"},
}


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


def accession_id(sample_id: str, blend_grade: str, lot_id: str) -> str:
    digest = sha256_hex(
        {
            "demand_id": DEMAND_ID,
            "sample_id": sample_id,
            "blend_grade": blend_grade,
            "lot_id": lot_id,
            "lane": BLEND_LANE,
        }
    )
    return "PBD-" + digest[:12]


def source_hash(row: dict[str, Any]) -> str:
    return sha256_hex(
        {
            "sample_id": row.get("sample_id"),
            "pickup_id": row.get("pickup_id"),
            "coc_id": row.get("coc_id"),
            "sds_id": row.get("sds_id"),
            "blend_grade": row.get("blend_grade"),
            "lot_id": row.get("lot_id"),
            "tank_id": row.get("tank_id"),
        }
    )


def _round(value: float, decimals: int) -> float:
    return round(float(value), decimals)


def _in_spec_value(method_id: str, index: int) -> float:
    spec = METHODS[method_id]
    base = float(spec["in_spec"])
    # Tiny deterministic drift that stays inside D7467 B6–B20 limits.
    wobble = ((index * 17 + len(method_id) * 3) % 7) * 0.01
    if spec["analyte"] == "fame":
        return _round(6.4 + (index % 14) * 0.9, spec["decimals"])
    if spec["analyte"] == "flash_point":
        return _round(base + wobble * 10, spec["decimals"])
    if spec["analyte"] == "viscosity_40c":
        return _round(2.40 + (index % 9) * 0.12, spec["decimals"])
    if spec["analyte"] == "sulfur":
        return _round(4.0 + (index % 8) * 0.8, spec["decimals"])
    if spec["analyte"] == "acid_number":
        return _round(0.10 + (index % 10) * 0.01, spec["decimals"])
    if spec["analyte"] == "water_sediment":
        return _round(0.008 + (index % 5) * 0.003, spec["decimals"])
    return _round(base + wobble, spec["decimals"])


def _qualifier(value: float, method_id: str) -> str:
    spec = METHODS[method_id]
    if spec["spec_min"] is not None and value < float(spec["spec_min"]):
        return "OOS"
    if spec["spec_max"] is not None and value > float(spec["spec_max"]):
        return "OOS"
    return ""


def _valid_row(index: int) -> dict[str, Any]:
    grade = BLEND_GRADES[(index - 1) % len(BLEND_GRADES)]
    sample_id = f"PBD-V{index:03d}"
    return {
        "row_id": f"R{index:03d}",
        "sample_id": sample_id,
        "pickup_id": f"PBD-PU-{index:03d}",
        "coc_id": f"PBD-COC-{index:03d}",
        "sds_id": f"PBD-SDS-{grade}",
        "blend_grade": grade,
        "lot_id": f"PBD-LOT-{index:03d}",
        "tank_id": f"PBD-TANK-{(index % 8) + 1:02d}",
        "courier": "SYN-COURIER-01",
        "custody_seal": f"SEAL-{index:04d}",
        "collected_at": f"{FIXTURE_DATE}T08:00:00Z",
        "received_at": f"{FIXTURE_DATE}T14:00:00Z",
        "relinquisher": "SYN-DRIVER",
        "receiver": "SYN-RECEIVING",
        "coc_complete": True,
        "sds_present": True,
        "container_intact": True,
    }


def build_acceptance_fixture() -> list[dict[str, Any]]:
    """120-row frozen manifest for paragon-biodiesel-sample-coa-lims-01."""
    rows = [_valid_row(index) for index in range(1, 101)]
    for index in range(1, 6):
        row = _valid_row(100 + index)
        row["row_id"] = f"C{index:02d}"
        row["sample_id"] = f"PBD-C{index:02d}"
        row["pickup_id"] = f"PBD-PU-C{index:02d}"
        row["coc_id"] = ""
        row["custody_seal"] = ""
        row["collected_at"] = ""
        row["relinquisher"] = ""
        row["coc_complete"] = False
        rows.append(row)
    for index in range(1, 6):
        row = _valid_row(105 + index)
        row["row_id"] = f"S{index:02d}"
        row["sample_id"] = f"PBD-S{index:02d}"
        row["pickup_id"] = f"PBD-PU-S{index:02d}"
        row["sds_id"] = ""
        row["sds_present"] = False
        rows.append(row)
    for index in range(1, 6):
        original = _valid_row(index)
        dup = deepcopy(original)
        dup["row_id"] = f"D{index:02d}"
        dup["pickup_id"] = f"PBD-PU-DUP-{index:02d}"
        rows.append(dup)
    for index, sample_id in enumerate(sorted(OOS_CASES), start=1):
        row = _valid_row(110 + index)
        row["row_id"] = f"O{index:02d}"
        row["sample_id"] = sample_id
        row["pickup_id"] = f"PBD-PU-O{index:02d}"
        row["coc_id"] = f"PBD-COC-O{index:02d}"
        row["lot_id"] = f"PBD-LOT-O{index:02d}"
        rows.append(row)
    if len(rows) != 120:
        raise RuntimeError("acceptance fixture must be exactly 120 rows, got %s" % len(rows))
    return rows


def empty_journal() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "accessions": {},
        "holds": [],
        "events": [],
        "sample_index": {},
        "interface_live": False,
        "qc_decisions": 0,
        "production_writes": 0,
        "billing_writes": 0,
        "outreach": 0,
        "automatic_releases": 0,
    }


def _event(journal: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    journal["events"].append({"seq": len(journal["events"]) + 1, "kind": kind, **deepcopy(payload)})


def normalize_intake(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "row_id": _text(row.get("row_id")),
        "sample_id": _text(row.get("sample_id")),
        "pickup_id": _text(row.get("pickup_id")),
        "coc_id": _text(row.get("coc_id")),
        "sds_id": _text(row.get("sds_id")),
        "blend_grade": _text(row.get("blend_grade")).upper(),
        "lot_id": _text(row.get("lot_id")),
        "tank_id": _text(row.get("tank_id")),
        "courier": _text(row.get("courier")),
        "custody_seal": _text(row.get("custody_seal")),
        "collected_at": _text(row.get("collected_at")),
        "received_at": _text(row.get("received_at")),
        "relinquisher": _text(row.get("relinquisher")),
        "receiver": _text(row.get("receiver")),
        "coc_complete": _flag(row.get("coc_complete")),
        "sds_present": _flag(row.get("sds_present")),
        "container_intact": _flag(row.get("container_intact")),
        "source_sha256": source_hash(
            {
                "sample_id": _text(row.get("sample_id")),
                "pickup_id": _text(row.get("pickup_id")),
                "coc_id": _text(row.get("coc_id")),
                "sds_id": _text(row.get("sds_id")),
                "blend_grade": _text(row.get("blend_grade")).upper(),
                "lot_id": _text(row.get("lot_id")),
                "tank_id": _text(row.get("tank_id")),
            }
        ),
    }


def classify_intake(norm: dict[str, Any], journal: dict[str, Any]) -> dict[str, Any]:
    if norm["sample_id"] and norm["sample_id"] in journal["sample_index"]:
        return {"ok": False, "code": "HOLD_DUPLICATE_ID"}
    coc_ok = (
        norm["coc_complete"]
        and bool(norm["coc_id"])
        and bool(norm["custody_seal"])
        and bool(norm["collected_at"])
        and bool(norm["relinquisher"])
        and bool(norm["courier"])
        and bool(norm["pickup_id"])
        and bool(norm["received_at"])
        and bool(norm["receiver"])
        and norm["container_intact"]
    )
    if not coc_ok:
        return {"ok": False, "code": "HOLD_INCOMPLETE_COC"}
    if not norm["sds_present"] or not norm["sds_id"]:
        return {"ok": False, "code": "HOLD_INCOMPLETE_SDS"}
    if not norm["sample_id"] or not norm["lot_id"] or norm["blend_grade"] not in BLEND_GRADES:
        return {"ok": False, "code": "HOLD_INCOMPLETE_COC"}
    return {"ok": True}


def _hold(
    journal: dict[str, Any],
    *,
    row_id: str,
    sample_id: str | None,
    code: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    hold = {
        "row_id": row_id,
        "sample_id": sample_id,
        "code": code,
        "state": "HOLD",
        "lane": BLEND_LANE,
    }
    if extra:
        hold.update(extra)
    fingerprint = sha256_hex(hold)
    existing = {sha256_hex(item) for item in journal["holds"]}
    if fingerprint not in existing:
        journal["holds"].append(hold)
        _event(journal, "HOLD", hold)
    return {"kind": "HOLD", "duplicate": fingerprint in existing, **hold}


def ingest_row(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    norm = normalize_intake(row)
    acc_id = None
    if norm["sample_id"] and norm["blend_grade"] and norm["lot_id"]:
        acc_id = accession_id(norm["sample_id"], norm["blend_grade"], norm["lot_id"])
    existing_id = journal["sample_index"].get(norm["sample_id"]) if norm["sample_id"] else None
    if existing_id:
        existing = journal["accessions"][existing_id]
        if existing["row_id"] == norm["row_id"]:
            _event(journal, "REPLAY_NOOP", {"accession_id": existing_id, "sample_id": norm["sample_id"]})
            return {"kind": "REPLAY_NOOP", "accession_id": existing_id, "sample_id": norm["sample_id"]}
        return _hold(
            journal,
            row_id=norm["row_id"],
            sample_id=norm["sample_id"],
            code="HOLD_DUPLICATE_ID",
            extra={"first_accession_id": existing_id},
        )
    if acc_id and acc_id in journal["accessions"]:
        _event(journal, "REPLAY_NOOP", {"accession_id": acc_id, "sample_id": norm["sample_id"]})
        return {"kind": "REPLAY_NOOP", "accession_id": acc_id, "sample_id": norm["sample_id"]}
    verdict = classify_intake(norm, journal)
    if not verdict["ok"]:
        extra = {}
        if verdict["code"] == "HOLD_DUPLICATE_ID":
            extra["first_accession_id"] = journal["sample_index"].get(norm["sample_id"])
        return _hold(
            journal,
            row_id=norm["row_id"],
            sample_id=norm["sample_id"] or None,
            code=verdict["code"],
            extra=extra or None,
        )
    if acc_id is None:
        acc_id = accession_id(norm["sample_id"], norm["blend_grade"], norm["lot_id"])
    record = {
        "accession_id": acc_id,
        "row_id": norm["row_id"],
        "sample_id": norm["sample_id"],
        "pickup_id": norm["pickup_id"],
        "coc_id": norm["coc_id"],
        "sds_id": norm["sds_id"],
        "blend_grade": norm["blend_grade"],
        "lot_id": norm["lot_id"],
        "tank_id": norm["tank_id"],
        "lane": BLEND_LANE,
        "spec_id": SPEC_ID,
        "spec_revision": SPEC_REVISION,
        "methods": list(PANEL),
        "route": "B6_B20_D7467_PANEL",
        "state": "ACCESSIONED",
        "results": None,
        "result_state": None,
        "review_hold": None,
        "qa_review": None,
        "coa": None,
        "coa_status": "BLOCKED_MISSING_RESULT",
        "released": False,
        "released_by": None,
        "source_sha256": norm["source_sha256"],
        "interface_state": "SIMULATED",
        "interface_live": False,
        "adapters": {
            "pickup": "SIMULATED_READ_ONLY",
            "coc": "SIMULATED_READ_ONLY",
            "sds": "SIMULATED_READ_ONLY",
            "lims": "SIMULATED_READ_ONLY",
            "instrument": "SIMULATED_READ_ONLY",
            "qa": "SIMULATED_READ_ONLY",
            "coa": "SIMULATED_READ_ONLY",
        },
    }
    journal["accessions"][acc_id] = record
    journal["sample_index"][norm["sample_id"]] = acc_id
    _event(
        journal,
        "ACCESSION",
        {
            "accession_id": acc_id,
            "sample_id": norm["sample_id"],
            "route": record["route"],
            "source_sha256": norm["source_sha256"],
        },
    )
    assign_methods(journal, acc_id)
    return {"kind": "ACCESSION", "accession_id": acc_id, "route": record["route"]}


def assign_methods(journal: dict[str, Any], accession_id_value: str) -> dict[str, Any]:
    record = journal["accessions"][accession_id_value]
    if record.get("state") == "METHODS_ASSIGNED" and record.get("methods") == list(PANEL):
        return {"ok": True, "duplicate": True}
    record["methods"] = list(PANEL)
    record["state"] = "METHODS_ASSIGNED"
    record["coa_status"] = "BLOCKED_MISSING_RESULT"
    _event(
        journal,
        "METHOD_ASSIGNMENT",
        {
            "accession_id": accession_id_value,
            "sample_id": record["sample_id"],
            "methods": list(PANEL),
            "spec_id": SPEC_ID,
            "spec_revision": SPEC_REVISION,
        },
    )
    return {"ok": True, "duplicate": False, "methods": list(PANEL)}


def _result_rows(record: dict[str, Any]) -> list[dict[str, Any]]:
    index = int("".join(ch for ch in record["sample_id"] if ch.isdigit()) or "0")
    oos = OOS_CASES.get(record["sample_id"])
    rows = []
    for method_id in PANEL:
        spec = METHODS[method_id]
        value = _in_spec_value(method_id, index)
        if oos and oos["method"] == method_id:
            value = _round(float(oos["value"]), spec["decimals"])
        qualifier = _qualifier(value, method_id)
        rows.append(
            {
                "method": spec["name"],
                "method_id": method_id,
                "analyte": spec["analyte"],
                "value": value,
                "unit": spec["unit"],
                "qualifier": qualifier,
                "spec_min": spec["spec_min"],
                "spec_max": spec["spec_max"],
                "spec_id": SPEC_ID,
            }
        )
    return rows


def import_simulated_results(journal: dict[str, Any], accession_id_value: str) -> dict[str, Any]:
    record = journal["accessions"].get(accession_id_value)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_ACCESSION"}
    if record["results"] is not None:
        return {"ok": True, "duplicate": True, "results": record["results"]}
    rows = _result_rows(record)
    oos_rows = [item for item in rows if item["qualifier"] == "OOS"]
    record["results"] = rows
    record["result_hash"] = sha256_hex(rows)
    if oos_rows:
        reason = OOS_CASES.get(record["sample_id"], {}).get("reason", "OOS")
        record["result_state"] = "OOS"
        record["review_hold"] = "HOLD_OOS"
        record["qa_review"] = "HOLD_OOS"
        record["coa_status"] = "HOLD_OOS"
        record["state"] = "HOLD"
        record["coa"] = None
        _hold(
            journal,
            row_id=record["row_id"],
            sample_id=record["sample_id"],
            code="HOLD_OOS",
            extra={
                "accession_id": accession_id_value,
                "reason": reason,
                "oos_analytes": [item["analyte"] for item in oos_rows],
            },
        )
        _event(
            journal,
            "QA_HOLD_OOS",
            {
                "accession_id": accession_id_value,
                "sample_id": record["sample_id"],
                "reason": reason,
            },
        )
        return {"ok": True, "duplicate": False, "disposition": "OOS"}
    record["result_state"] = "IN_SPEC"
    record["review_hold"] = None
    record["qa_review"] = "QA_PASS"
    record["state"] = "QA_REVIEWED"
    record["coa_status"] = "STAGED"
    record["coa"] = _stage_coa(record)
    _event(
        journal,
        "QA_PASS_STAGED_COA",
        {
            "accession_id": accession_id_value,
            "sample_id": record["sample_id"],
            "coa_id": record["coa"]["coa_id"],
            "report_sha256": record["coa"]["report_sha256"],
        },
    )
    return {"ok": True, "duplicate": False, "disposition": "IN_SPEC"}


def _stage_coa(record: dict[str, Any]) -> dict[str, Any]:
    fields = {
        "coa_id": "PBD-COA-" + record["accession_id"][4:],
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "product": "B6-B20 biodiesel blend",
        "spec_id": SPEC_ID,
        "spec_revision": SPEC_REVISION,
        "sample_id": record["sample_id"],
        "accession_id": record["accession_id"],
        "blend_grade": record["blend_grade"],
        "lot_id": record["lot_id"],
        "tank_id": record["tank_id"],
        "pickup_id": record["pickup_id"],
        "coc_id": record["coc_id"],
        "sds_id": record["sds_id"],
        "methods": list(record["methods"]),
        "results": deepcopy(record["results"]),
        "qa_review": "QA_PASS",
        "status": "STAGED",
        "released": False,
        "source_sha256": record["source_sha256"],
        "result_hash": record["result_hash"],
        "adapters": "SIMULATED_READ_ONLY",
    }
    fields["report_sha256"] = sha256_hex(fields)
    return fields


def apply_simulated_results(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [import_simulated_results(journal, acc_id) for acc_id in sorted(journal["accessions"])]


def release_coa(
    journal: dict[str, Any],
    accession_id_value: str,
    *,
    actor_role: str,
    actor: str,
    acknowledge_oos: bool = False,
) -> dict[str, Any]:
    record = journal["accessions"].get(accession_id_value)
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
        return {"ok": False, "code": "AUTONOMOUS_RELEASE_DENIED", "coa_status": record["coa_status"]}
    if record["review_hold"] == "HOLD_OOS" and not acknowledge_oos:
        _event(
            journal,
            "RELEASE_DENIED",
            {
                "accession_id": accession_id_value,
                "code": "HOLD_OOS",
                "coa_status": "HOLD_OOS",
            },
        )
        return {"ok": False, "code": "HOLD_OOS", "coa_status": "HOLD_OOS"}
    if record["coa_status"] != "STAGED" and not record["released"] and not (
        record["review_hold"] == "HOLD_OOS" and acknowledge_oos
    ):
        return {"ok": False, "code": "COA_BLOCKED", "coa_status": record["coa_status"]}
    if record["released"]:
        return {"ok": True, "duplicate": True, "coa_status": "RELEASED"}
    if record["coa"] is None:
        record["coa"] = _stage_coa(record)
    record["released"] = True
    record["released_by"] = named
    record["coa_status"] = "RELEASED"
    record["state"] = "RELEASED"
    record["coa"]["status"] = "RELEASED"
    record["coa"]["released"] = True
    record["coa"]["released_by"] = named
    record["coa"]["report_sha256"] = sha256_hex(
        {key: value for key, value in record["coa"].items() if key != "report_sha256"}
    )
    _event(
        journal,
        "COA_RELEASED",
        {
            "accession_id": accession_id_value,
            "released_by": named,
            "coa_id": record["coa"]["coa_id"],
        },
    )
    return {"ok": True, "duplicate": False, "coa_status": "RELEASED"}


def attempt_autonomous_release(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        release_coa(journal, acc_id, actor_role="SYSTEM", actor="autonomous")
        for acc_id in sorted(journal["accessions"])
    ]


def authorized_human_release(journal: dict[str, Any], actor: str = HUMAN_ACTOR) -> list[dict[str, Any]]:
    return [
        release_coa(journal, acc_id, actor_role=HUMAN_RELEASER, actor=actor)
        for acc_id in sorted(journal["accessions"])
    ]


def replay_into(journal: dict[str, Any], rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    before = set(journal["accessions"])
    before_holds = len(journal["holds"])
    effects = [ingest_row(journal, row) for row in inbound]
    added = set(journal["accessions"]) - before
    return {
        "added_accessions": sorted(added),
        "added_accession_count": len(added),
        "added_holds": len(journal["holds"]) - before_holds,
        "replay_noops": sum(1 for item in effects if item.get("kind") == "REPLAY_NOOP"),
        "accession_count": len(journal["accessions"]),
        "hold_count": len(journal["holds"]),
    }


def _count_state(journal: dict[str, Any], inbound_len: int) -> dict[str, int]:
    accessioned = list(journal["accessions"].values())
    hold_codes = [item["code"] for item in journal["holds"]]
    in_spec = sum(1 for item in accessioned if item.get("result_state") == "IN_SPEC")
    return {
        "input_rows": inbound_len,
        "accessioned_valid": in_spec,
        "accessioned_total": len(accessioned),
        "hold": len(journal["holds"]),
        "incomplete_coc": hold_codes.count("HOLD_INCOMPLETE_COC"),
        "incomplete_sds": hold_codes.count("HOLD_INCOMPLETE_SDS"),
        "duplicate_id": hold_codes.count("HOLD_DUPLICATE_ID"),
        "oos": hold_codes.count("HOLD_OOS"),
        "in_spec": in_spec,
        "staged_coa": sum(1 for item in accessioned if item.get("coa") and item.get("coa_status") in {"STAGED", "RELEASED"}),
        "human_released": sum(1 for item in accessioned if item.get("released")),
        "autonomous_released": 0,
        "duplicate_accessions": len(accessioned) - len({item["sample_id"] for item in accessioned}),
    }


def golden_set(journal: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in sorted(journal["accessions"].values(), key=lambda rec: rec["sample_id"]):
        if item.get("result_state") != "IN_SPEC" or not item.get("coa"):
            continue
        rows.append(
            {
                "sample_id": item["sample_id"],
                "accession_id": item["accession_id"],
                "source_sha256": item["source_sha256"],
                "result_hash": item["result_hash"],
                "values": [
                    {
                        "analyte": result["analyte"],
                        "value": result["value"],
                        "unit": result["unit"],
                        "qualifier": result["qualifier"],
                        "method": result["method"],
                    }
                    for result in item["results"]
                ],
                "report_fields": {
                    "coa_id": item["coa"]["coa_id"],
                    "product": item["coa"]["product"],
                    "spec_id": item["coa"]["spec_id"],
                    "spec_revision": item["coa"]["spec_revision"],
                    "blend_grade": item["coa"]["blend_grade"],
                    "lot_id": item["coa"]["lot_id"],
                    "status": item["coa"]["status"],
                    "report_sha256": item["coa"]["report_sha256"],
                },
            }
        )
    return rows


def _audit_payload(journal: dict[str, Any], counts: dict[str, Any]) -> dict[str, Any]:
    accessions = sorted(journal["accessions"].values(), key=lambda item: item["sample_id"])
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "counts": counts,
        "holds": deepcopy(journal["holds"]),
        "golden_set": golden_set(journal),
        "accessions": [
            {
                "accession_id": item["accession_id"],
                "sample_id": item["sample_id"],
                "blend_grade": item["blend_grade"],
                "lot_id": item["lot_id"],
                "route": item["route"],
                "methods": item["methods"],
                "state": item["state"],
                "result_state": item["result_state"],
                "review_hold": item["review_hold"],
                "coa_status": item["coa_status"],
                "released": item["released"],
                "released_by": item["released_by"],
                "source_sha256": item["source_sha256"],
                "result_hash": item.get("result_hash"),
                "report_sha256": None if item.get("coa") is None else item["coa"]["report_sha256"],
                "values": None
                if item.get("results") is None
                else [
                    {
                        "analyte": result["analyte"],
                        "value": result["value"],
                        "unit": result["unit"],
                        "qualifier": result["qualifier"],
                    }
                    for result in item["results"]
                ],
            }
            for item in accessions
        ],
        "events": deepcopy(journal["events"]),
        "adapters": {
            "pickup": "SIMULATED_READ_ONLY",
            "coc": "SIMULATED_READ_ONLY",
            "sds": "SIMULATED_READ_ONLY",
            "lims": "SIMULATED_READ_ONLY",
            "instrument": "SIMULATED_READ_ONLY",
            "qa": "SIMULATED_READ_ONLY",
            "coa": "SIMULATED_READ_ONLY",
            "qc_decision": "NOT_WRITTEN",
            "production_write": "NOT_SENT",
            "outreach": "NOT_SENT",
        },
    }


def run_gate(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    journal = empty_journal()
    effects = [ingest_row(journal, row) for row in inbound]
    result_effects = apply_simulated_results(journal)
    autonomous = attempt_autonomous_release(journal)
    human = authorized_human_release(journal)
    accessioned = sorted(journal["accessions"].values(), key=lambda item: item["sample_id"])
    hold_codes = sorted(item["code"] for item in journal["holds"])
    counts = _count_state(journal, len(inbound))
    signed = golden_set(journal)
    audit = _audit_payload(journal, counts)
    audit_sha256 = sha256_hex(audit)
    golden_sha = sha256_hex(signed)
    body = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "lane": BLEND_LANE,
        "spec_id": SPEC_ID,
        "spec_revision": SPEC_REVISION,
        "input_rows": counts["input_rows"],
        "accessioned_valid": counts["accessioned_valid"],
        "accessioned_total": counts["accessioned_total"],
        "hold": counts["hold"],
        "hold_codes": hold_codes,
        "hold_code_set": sorted(set(hold_codes)),
        "incomplete_coc": counts["incomplete_coc"],
        "incomplete_sds": counts["incomplete_sds"],
        "duplicate_id": counts["duplicate_id"],
        "oos": counts["oos"],
        "in_spec": counts["in_spec"],
        "staged_coa": counts["staged_coa"],
        "human_released": counts["human_released"],
        "autonomous_released": 0,
        "duplicate_accessions": counts["duplicate_accessions"],
        "routes": {item["sample_id"]: item["route"] for item in accessioned},
        "accession_ids": [item["accession_id"] for item in accessioned],
        "source_hashes": {item["sample_id"]: item["source_sha256"] for item in accessioned},
        "golden_set": signed,
        "golden_set_sha256": golden_sha,
        "replay_noops": sum(1 for item in effects if item.get("kind") == "REPLAY_NOOP"),
        "effects": effects,
        "result_effects": result_effects,
        "autonomous_release_effects": autonomous,
        "human_release_effects": human,
        "accessions": accessioned,
        "holds": deepcopy(journal["holds"]),
        "events": deepcopy(journal["events"]),
        "interface_live": False,
        "interfaces": "SIMULATED",
        "qc_decisions": 0,
        "production_writes": 0,
        "billing_writes": 0,
        "outreach": 0,
        "autonomous_certification": False,
        "autonomous_release": False,
        "pre_sale_transport": "NONE",
        "cash_usd": 0,
        "audit": audit,
        "audit_sha256": audit_sha256,
    }
    body["manifest_sha256"] = sha256_hex(
        {
            key: value
            for key, value in body.items()
            if key
            not in {
                "manifest_sha256",
                "effects",
                "result_effects",
                "autonomous_release_effects",
                "human_release_effects",
                "accessions",
                "events",
                "golden_set",
                "audit",
            }
        }
    )
    return body


def expected_actual(result: dict[str, Any]) -> dict[str, Any]:
    actual = {key: result.get(key) for key in GOLDEN_COUNTS}
    return {"expected": dict(GOLDEN_COUNTS), "actual": actual, "match": actual == GOLDEN_COUNTS}


def pass_contract(result: dict[str, Any]) -> list[str]:
    failures = []
    for key, expected in GOLDEN_COUNTS.items():
        if result.get(key) != expected:
            failures.append(f"{key}!={expected} actual={result.get(key)}")
    if result.get("hold_code_set") != sorted(HOLD_CODES):
        failures.append("hold_code_set")
    if result.get("interface_live") is not False:
        failures.append("interface_live")
    if result.get("interfaces") != "SIMULATED":
        failures.append("interfaces")
    if result.get("autonomous_release") is not False:
        failures.append("autonomous_release")
    if result.get("qc_decisions") != 0:
        failures.append("qc_decisions")
    if result.get("production_writes") != 0:
        failures.append("production_writes")
    if result.get("outreach") != 0:
        failures.append("outreach")
    if not all(item.get("code") == "AUTONOMOUS_RELEASE_DENIED" for item in result.get("autonomous_release_effects") or []):
        failures.append("autonomous_release_not_denied")
    if len(set(result.get("accession_ids") or [])) != 105:
        failures.append("accession_ids_not_unique")
    if len(result.get("golden_set") or []) != 100:
        failures.append("golden_set_len")
    if any(row["values"] and any(item["qualifier"] for item in row["values"]) for row in result.get("golden_set") or []):
        failures.append("golden_set_has_oos")
    if result.get("audit_sha256") != GOLDEN_AUDIT_SHA256:
        failures.append("audit_sha256")
    if result.get("golden_set_sha256") != GOLDEN_SET_SHA256:
        failures.append("golden_set_sha256")
    released_by = {item.get("released_by") for item in result.get("accessions") or [] if item.get("released")}
    if released_by != {HUMAN_ACTOR}:
        failures.append("released_by")
    return failures


def main() -> int:
    first = run_gate()
    second = run_gate()
    journal = empty_journal()
    for row in build_acceptance_fixture():
        ingest_row(journal, row)
    replay = replay_into(journal)
    failures = pass_contract(first)
    if first.get("audit_sha256") != second.get("audit_sha256"):
        failures.append("audit_sha256_mismatch")
    if first.get("golden_set_sha256") != second.get("golden_set_sha256"):
        failures.append("golden_set_sha256_mismatch")
    if sha256_hex(first["audit"]) != first.get("audit_sha256"):
        failures.append("audit_hash_not_self")
    if sha256_hex(first["golden_set"]) != first.get("golden_set_sha256"):
        failures.append("golden_hash_not_self")
    if replay.get("added_accession_count") != 0:
        failures.append("replay_added_accessions")
    if replay.get("added_holds") != 0:
        failures.append("replay_added_holds")
    report = {
        "ok": not failures,
        "failures": failures,
        "audit_sha256": first.get("audit_sha256"),
        "golden_set_sha256": first.get("golden_set_sha256"),
        "manifest_sha256": first.get("manifest_sha256"),
        "expected": GOLDEN_COUNTS,
        "actual": expected_actual(first)["actual"],
        "hold_code_set": first.get("hold_code_set"),
        "replay_added_accessions": replay.get("added_accession_count"),
        "pin_audit": first.get("audit_sha256") == GOLDEN_AUDIT_SHA256,
        "pin_golden": first.get("golden_set_sha256") == GOLDEN_SET_SHA256,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
