#!/usr/bin/env python3
"""SGS PSI high-throughput thermal-rheology lineage LIMS.

Demand: sgspsi-high-throughput-thermal-rheology-lineage-lims-01
Buyer: Kyle Copeland / SGS Polymer Solutions

Confirmed requirement/form/payment linkage → accession → DSC-250/HR-20
method/version and autosampler slot → raw-data provenance → QC →
staged formal report. Named-human approval only.

Acceptance: replay 120 synthetic requests — 90 valid, 8 missing
required linkage, 6 duplicate containers, 6 method/instrument
mismatches, 5 slot collisions, 5 QC failures. PASS only when exactly
90 are READY; 30 receive their predetermined HOLD; one sample occupies
each reserved slot; source/method/raw-value/unit/report hashes match;
replay adds zero records; reports stay staged pending named approval.

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

DEMAND_ID = "sgspsi-high-throughput-thermal-rheology-lineage-lims-01"
SCHEMA = "commons-sgspsi-thermal-rheology-lineage-lims/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
BUYER = "Kyle Copeland / SGS Polymer Solutions"
HUMAN_APPROVER = "APPROVER"
VALID_COUNT = 90
HOLD_COUNT = 30
INPUT_COUNT = VALID_COUNT + HOLD_COUNT

HOLD_CODES = (
    "MISSING_LINKAGE",
    "DUPLICATE_CONTAINER",
    "METHOD_INSTRUMENT_MISMATCH",
    "SLOT_COLLISION",
    "QC_FAILURE",
)
HOLD_PLAN = {
    "MISSING_LINKAGE": 8,
    "DUPLICATE_CONTAINER": 6,
    "METHOD_INSTRUMENT_MISMATCH": 6,
    "SLOT_COLLISION": 5,
    "QC_FAILURE": 5,
}

INSTRUMENTS = {
    "DSC-250": {
        "methods": {
            "ASTM-D3418": {"version": "D3418-21-SYN", "kind": "THERMAL"},
            "ISO-11357-2": {"version": "11357-2-2020-SYN", "kind": "THERMAL"},
        },
        "units": {"tg": "°C", "tm": "°C", "delta_h": "J/g", "qc": "°C"},
        "slot_prefix": "DSC",
        "qc_window": (156.4, 156.8),
        "qc_key": "indium_tm_c",
        "worklist": "DSC250_AUTOSAMPLER",
    },
    "HR-20": {
        "methods": {
            "ASTM-D4440": {"version": "D4440-23-SYN", "kind": "RHEOLOGY"},
            "ISO-6721-10": {"version": "6721-10-2015-SYN", "kind": "RHEOLOGY"},
        },
        "units": {"eta_star": "Pa·s", "g_prime": "Pa", "tan_delta": "1", "qc": "Pa·s"},
        "slot_prefix": "HR",
        "qc_window": (9.6, 10.4),
        "qc_key": "viscosity_std_pa_s",
        "worklist": "HR20_AUTOSAMPLER",
    },
}
DSC_METHODS = tuple(INSTRUMENTS["DSC-250"]["methods"])
HR_METHODS = tuple(INSTRUMENTS["HR-20"]["methods"])
MISMATCH_PAIRS = (
    ("DSC-250", "ASTM-D4440"),
    ("DSC-250", "ISO-6721-10"),
    ("DSC-250", "ASTM-D4440"),
    ("HR-20", "ASTM-D3418"),
    ("HR-20", "ISO-11357-2"),
    ("HR-20", "ASTM-D3418"),
)

GOLDEN_COUNTS = {
    "input_rows": INPUT_COUNT,
    "ready": VALID_COUNT,
    "held": HOLD_COUNT,
    "reserved_slots_occupied": VALID_COUNT,
    "duplicate_accessions": 0,
    "released_reports": 0,
    "staged_reports": VALID_COUNT,
    "replay_added_records": 0,
    "production_writes": 0,
}

# Locked after the first deterministic PASS of this exact fixture.
GOLDEN_FIXTURE_SHA256 = "3914c61ed2dfe51c4601c773cc03816e53c13a12cbc9815ec2ddec2e9ac4016b"
GOLDEN_AUDIT_SHA256 = "22c85bf6a5658eb4b2460bca3d07a23e3756590a55cfc336348d4a4cc631565d"
GOLDEN_LINEAGE_SHA256 = "87f0ed13ee7ab7cbbdb30ef9daec7505c61c22ceb57611efb1f0f6be5c2f9e26"
GOLDEN_REPORT_DIGEST = "3341fe765f072d291c9c3422d40651edbb7f2041839d3e103e3b5880de439738"
HERE = Path(__file__).resolve().parent
FIXTURE_DIR = HERE / "revenue" / "sgspsi_thermal_rheology_lineage"


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


def _slot_label(prefix: str, index: int) -> str:
    return "%s-%02d" % (prefix, index)


def valid_request_id(index: int) -> str:
    return "SGS-V%03d" % index


def valid_container_id(index: int) -> str:
    return "CTR-V%03d" % index


def instrument_for_index(index: int) -> str:
    return "DSC-250" if index % 2 == 1 else "HR-20"


def method_for(instrument: str, index: int) -> str:
    names = DSC_METHODS if instrument == "DSC-250" else HR_METHODS
    return names[(index - 1) % len(names)]


def reserved_slot_for(index: int) -> str:
    instrument = instrument_for_index(index)
    prefix = str(INSTRUMENTS[instrument]["slot_prefix"])
    n = (index + 1) // 2
    return _slot_label(prefix, n)


def accession_id(request_id: str, container_id: str) -> str:
    digest = sha256_hex(
        {
            "demand_id": DEMAND_ID,
            "request_id": request_id,
            "container_id": container_id,
        }
    )
    return "SGS-" + digest[:12]


def source_hash(requirement_id: str, form_id: str, payment_id: str) -> str:
    return sha256_hex(
        {
            "demand_id": DEMAND_ID,
            "kind": "SOURCE",
            "requirement_id": requirement_id,
            "form_id": form_id,
            "payment_id": payment_id,
        }
    )


def method_hash(instrument: str, method: str, method_version: str) -> str:
    return sha256_hex(
        {
            "demand_id": DEMAND_ID,
            "kind": "METHOD",
            "instrument": instrument,
            "method": method,
            "method_version": method_version,
        }
    )


def unit_hash(instrument: str) -> str:
    return sha256_hex(
        {
            "demand_id": DEMAND_ID,
            "kind": "UNIT",
            "instrument": instrument,
            "units": INSTRUMENTS[instrument]["units"],
        }
    )


def raw_packet(index: int, instrument: str, *, qc_ok: bool) -> dict[str, Any]:
    if instrument == "DSC-250":
        packet = {
            "instrument_id": "SIM-DSC-250-01",
            "adapter": "SIMULATED",
            "tg_c": _round1(85.0 + ((index - 1) % 30) * 0.4),
            "tm_c": _round1(165.0 + ((index - 1) % 20) * 0.3),
            "delta_h_j_g": _round1(28.0 + ((index - 1) % 15) * 0.2),
            "indium_tm_c": 156.6 if qc_ok else 150.0,
            "qc_ok": qc_ok,
        }
    else:
        packet = {
            "instrument_id": "SIM-HR-20-01",
            "adapter": "SIMULATED",
            "eta_star_pa_s": _round1(1200.0 + ((index - 1) % 25) * 8.0),
            "g_prime_pa": _round1(840.0 + ((index - 1) % 18) * 6.0),
            "tan_delta": _round2(0.80 + ((index - 1) % 10) * 0.02),
            "viscosity_std_pa_s": 10.0 if qc_ok else 4.0,
            "qc_ok": qc_ok,
        }
    return packet


def raw_value_hash(packet: dict[str, Any]) -> str:
    body = {key: value for key, value in packet.items() if key not in {"adapter", "qc_ok"}}
    return sha256_hex({"demand_id": DEMAND_ID, "kind": "RAW", "raw": body})


def qc_ok_for_packet(instrument: str, packet: dict[str, Any]) -> bool:
    spec = INSTRUMENTS[instrument]
    key = str(spec["qc_key"])
    low, high = spec["qc_window"]
    try:
        value = float(packet.get(key))
    except (TypeError, ValueError):
        return False
    return low <= value <= high


def _base_row(
    row_id: str,
    request_id: str,
    *,
    container_id: str,
    instrument: str,
    method: str,
    slot: str,
    valid_index: int | None = None,
    expected_hold: str | None = None,
    requirement_id: str | None = None,
    form_id: str | None = None,
    payment_id: str | None = None,
    qc_ok: bool = True,
) -> dict[str, Any]:
    index = valid_index or 1
    method_spec = INSTRUMENTS.get(instrument, {}).get("methods", {}).get(method)
    method_version = method_spec["version"] if method_spec else "UNKNOWN"
    req = requirement_id if requirement_id is not None else "REQ-%s" % request_id
    form = form_id if form_id is not None else "FORM-%s" % request_id
    pay = payment_id if payment_id is not None else "PAY-%s" % request_id
    packet = raw_packet(index, instrument if instrument in INSTRUMENTS else "DSC-250", qc_ok=qc_ok)
    row: dict[str, Any] = {
        "row_id": row_id,
        "request_id": request_id,
        "container_id": container_id,
        "requirement_id": req,
        "form_id": form,
        "payment_id": pay,
        "instrument": instrument,
        "method": method,
        "method_version": method_version,
        "slot": slot,
        "raw": packet,
        "source_hash": source_hash(req, form, pay) if req and form and pay else "",
        "method_hash": method_hash(instrument, method, method_version) if method_spec else "",
        "raw_value_hash": raw_value_hash(packet),
        "unit_hash": unit_hash(instrument) if instrument in INSTRUMENTS else "",
        "expected_hold": expected_hold,
        "interface_state": "SIMULATED",
        "interface_live": False,
    }
    return row


def build_acceptance_fixture() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index in range(1, VALID_COUNT + 1):
        instrument = instrument_for_index(index)
        rows.append(
            _base_row(
                "R%03d" % index,
                valid_request_id(index),
                container_id=valid_container_id(index),
                instrument=instrument,
                method=method_for(instrument, index),
                slot=reserved_slot_for(index),
                valid_index=index,
            )
        )
    missing = [
        ("requirement_id", ""),
        ("form_id", ""),
        ("payment_id", ""),
        ("requirement_id", ""),
        ("form_id", ""),
        ("payment_id", ""),
        ("requirement_id", ""),
        ("form_id", ""),
    ]
    for offset, (field, value) in enumerate(missing):
        kwargs = {
            "requirement_id": "REQ-HLINK%02d" % (offset + 1),
            "form_id": "FORM-HLINK%02d" % (offset + 1),
            "payment_id": "PAY-HLINK%02d" % (offset + 1),
        }
        kwargs[field] = value
        rows.append(
            _base_row(
                "R%03d" % (91 + offset),
                "SGS-HLINK%02d" % (offset + 1),
                container_id="CTR-HLINK%02d" % (offset + 1),
                instrument="DSC-250",
                method="ASTM-D3418",
                slot=_slot_label("DSC", 51 + offset),
                expected_hold="MISSING_LINKAGE",
                **kwargs,
            )
        )
    for offset in range(6):
        rows.append(
            _base_row(
                "R%03d" % (99 + offset),
                "SGS-HDUP%02d" % (offset + 1),
                container_id=valid_container_id(offset + 1),
                instrument=instrument_for_index(offset + 1),
                method=method_for(instrument_for_index(offset + 1), offset + 1),
                slot=_slot_label("DSC", 60 + offset),
                expected_hold="DUPLICATE_CONTAINER",
            )
        )
    for offset, (instrument, method) in enumerate(MISMATCH_PAIRS):
        rows.append(
            _base_row(
                "R%03d" % (105 + offset),
                "SGS-HMIS%02d" % (offset + 1),
                container_id="CTR-HMIS%02d" % (offset + 1),
                instrument=instrument,
                method=method,
                slot=_slot_label("HR" if instrument == "HR-20" else "DSC", 70 + offset),
                expected_hold="METHOD_INSTRUMENT_MISMATCH",
            )
        )
    for offset in range(5):
        rows.append(
            _base_row(
                "R%03d" % (111 + offset),
                "SGS-HSLOT%02d" % (offset + 1),
                container_id="CTR-HSLOT%02d" % (offset + 1),
                instrument=instrument_for_index(offset + 1),
                method=method_for(instrument_for_index(offset + 1), offset + 1),
                slot=reserved_slot_for(offset + 1),
                expected_hold="SLOT_COLLISION",
            )
        )
    for offset in range(5):
        index = 91 + offset
        instrument = instrument_for_index(index)
        rows.append(
            _base_row(
                "R%03d" % (116 + offset),
                "SGS-HQC%02d" % (offset + 1),
                container_id="CTR-HQC%02d" % (offset + 1),
                instrument=instrument,
                method=method_for(instrument, index),
                slot=_slot_label(str(INSTRUMENTS[instrument]["slot_prefix"]), 46 + offset),
                valid_index=index,
                expected_hold="QC_FAILURE",
                qc_ok=False,
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
        "instruments": ["DSC-250", "HR-20"],
        "input_rows": len(inbound),
        "valid_rows": sum(1 for row in inbound if row.get("expected_hold") is None),
        "hold_rows": sum(1 for row in inbound if row.get("expected_hold")),
        "hold_plan": dict(HOLD_PLAN),
        "row_ids": [row["row_id"] for row in inbound],
        "request_ids": [row["request_id"] for row in inbound],
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
        "slots": {},
    }


def _event(journal: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    journal["events"].append({"seq": len(journal["events"]) + 1, "kind": kind, **deepcopy(payload)})


def classify_request(row: dict[str, Any], journal: dict[str, Any]) -> dict[str, Any]:
    request_id = _text(row.get("request_id"))
    container_id = _text(row.get("container_id"))
    requirement_id = _text(row.get("requirement_id"))
    form_id = _text(row.get("form_id"))
    payment_id = _text(row.get("payment_id"))
    instrument = _text(row.get("instrument"))
    method = _text(row.get("method"))
    slot = _text(row.get("slot"))
    method_spec = INSTRUMENTS.get(instrument, {}).get("methods", {}).get(method)

    if not request_id or not container_id or not requirement_id or not form_id or not payment_id:
        return {"ok": False, "code": "MISSING_LINKAGE", "request_id": request_id or None}
    if any(item["container_id"] == container_id for item in journal["accessions"].values()):
        return {"ok": False, "code": "DUPLICATE_CONTAINER", "request_id": request_id, "container_id": container_id}
    if method_spec is None:
        return {
            "ok": False,
            "code": "METHOD_INSTRUMENT_MISMATCH",
            "request_id": request_id,
            "instrument": instrument,
            "method": method,
        }
    if slot in journal["slots"]:
        return {"ok": False, "code": "SLOT_COLLISION", "request_id": request_id, "slot": slot}
    packet = deepcopy(row.get("raw") or {})
    if not qc_ok_for_packet(instrument, packet) or not _flag(packet.get("qc_ok")):
        return {"ok": False, "code": "QC_FAILURE", "request_id": request_id}
    return {
        "ok": True,
        "request_id": request_id,
        "container_id": container_id,
        "requirement_id": requirement_id,
        "form_id": form_id,
        "payment_id": payment_id,
        "instrument": instrument,
        "method": method,
        "method_version": method_spec["version"],
        "slot": slot,
        "accession_id": accession_id(request_id, container_id),
        "route": INSTRUMENTS[instrument]["worklist"],
    }


def rendered_report(record: dict[str, Any]) -> dict[str, Any]:
    raw = record.get("raw") or {}
    return {
        "demand_id": DEMAND_ID,
        "accession_id": record["accession_id"],
        "request_id": record["request_id"],
        "container_id": record["container_id"],
        "instrument": record["instrument"],
        "method": record["method"],
        "method_version": record["method_version"],
        "slot": record["slot"],
        "units": INSTRUMENTS[record["instrument"]]["units"],
        "raw": deepcopy(raw),
        "source_hash": record.get("source_hash"),
        "method_hash": record.get("method_hash"),
        "raw_value_hash": record.get("raw_value_hash"),
        "unit_hash": record.get("unit_hash"),
        "state": "STAGED",
        "released": bool(record.get("released")),
        "interface_live": False,
    }


def report_status(record: dict[str, Any]) -> str:
    if record.get("released"):
        return "RELEASED"
    if not record.get("raw"):
        return "BLOCKED_MISSING_RESULT"
    if not record.get("qc_signoff"):
        return "BLOCKED_MISSING_QC"
    return "STAGED_PENDING_NAMED_APPROVAL"


def ingest_row(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    row_id = _text(row.get("row_id"))
    existing_acc = next(
        (item for item in journal["accessions"].values() if item["request_id"] == _text(row.get("request_id"))),
        None,
    )
    if existing_acc is not None and existing_acc.get("row_id") == row_id:
        _event(
            journal,
            "REPLAY_NOOP",
            {"accession_id": existing_acc["accession_id"], "request_id": existing_acc["request_id"]},
        )
        return {
            "kind": "REPLAY_NOOP",
            "accession_id": existing_acc["accession_id"],
            "request_id": existing_acc["request_id"],
        }

    verdict = classify_request(row, journal)
    if not verdict["ok"]:
        hold = {
            "row_id": row_id,
            "request_id": verdict.get("request_id"),
            "code": verdict["code"],
            "container_id": _text(row.get("container_id")) or None,
            "instrument": _text(row.get("instrument")) or None,
            "method": _text(row.get("method")) or None,
            "slot": _text(row.get("slot")) or None,
            "state": "HOLD",
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
        _event(journal, "REPLAY_NOOP", {"accession_id": acc_id, "request_id": verdict["request_id"]})
        return {"kind": "REPLAY_NOOP", "accession_id": acc_id, "request_id": verdict["request_id"]}

    raw = deepcopy(row.get("raw") or {})
    record = {
        "accession_id": acc_id,
        "request_id": verdict["request_id"],
        "row_id": row_id,
        "container_id": verdict["container_id"],
        "requirement_id": verdict["requirement_id"],
        "form_id": verdict["form_id"],
        "payment_id": verdict["payment_id"],
        "instrument": verdict["instrument"],
        "method": verdict["method"],
        "method_version": verdict["method_version"],
        "slot": verdict["slot"],
        "route": verdict["route"],
        "raw": raw,
        "source_hash": _text(row.get("source_hash")) or source_hash(
            verdict["requirement_id"], verdict["form_id"], verdict["payment_id"]
        ),
        "method_hash": _text(row.get("method_hash"))
        or method_hash(verdict["instrument"], verdict["method"], verdict["method_version"]),
        "raw_value_hash": _text(row.get("raw_value_hash")) or raw_value_hash(raw),
        "unit_hash": _text(row.get("unit_hash")) or unit_hash(verdict["instrument"]),
        "qc_signoff": True,
        "state": "READY",
        "released": False,
        "released_by": None,
        "report_status": "STAGED_PENDING_NAMED_APPROVAL",
        "interface_state": "SIMULATED",
        "interface_live": False,
    }
    record["report"] = rendered_report(record)
    record["report_hash"] = sha256_hex(record["report"])
    record["report_status"] = report_status(record)
    journal["accessions"][acc_id] = record
    journal["slots"][verdict["slot"]] = acc_id
    _event(
        journal,
        "READY",
        {
            "accession_id": acc_id,
            "request_id": verdict["request_id"],
            "slot": verdict["slot"],
            "route": verdict["route"],
        },
    )
    return {"kind": "READY", "accession_id": acc_id, "slot": verdict["slot"], "route": verdict["route"]}


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
    if role != HUMAN_APPROVER:
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
    if status not in {"STAGED_PENDING_NAMED_APPROVAL", "RELEASED"}:
        _event(
            journal,
            "RELEASE_DENIED",
            {"accession_id": accession_id_value, "code": "REPORT_BLOCKED", "report_status": status},
        )
        return {"ok": False, "code": "REPORT_BLOCKED", "report_status": status}
    if record["released"]:
        return {"ok": True, "duplicate": True, "report_status": "RELEASED"}
    record["released"] = True
    record["released_by"] = _text(actor) or "named-approver"
    record["report_status"] = "RELEASED"
    record["report"] = rendered_report(record)
    record["report_hash"] = sha256_hex(record["report"])
    _event(journal, "RELEASED", {"accession_id": accession_id_value, "released_by": record["released_by"]})
    return {"ok": True, "duplicate": False, "report_status": "RELEASED"}


def run_gate(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    journal = empty_journal()
    effects = [ingest_row(journal, row) for row in inbound]
    autonomous = [
        release_report(journal, acc_id, actor_role="SYSTEM", actor="autonomous")
        for acc_id in journal["accessions"]
    ]
    ready = sorted(journal["accessions"].values(), key=lambda item: item["request_id"])
    hold_codes = [item["code"] for item in journal["holds"]]
    reports = [item["report"] for item in ready]
    lineage = [
        {
            "request_id": item["request_id"],
            "source_hash": item["source_hash"],
            "method_hash": item["method_hash"],
            "raw_value_hash": item["raw_value_hash"],
            "unit_hash": item["unit_hash"],
            "report_hash": item["report_hash"],
        }
        for item in ready
    ]
    slots = {slot: acc_id for slot, acc_id in journal["slots"].items()}
    audit = {
        "demand_id": DEMAND_ID,
        "request_ids": [item["request_id"] for item in ready],
        "accession_ids": [item["accession_id"] for item in ready],
        "hold_codes": hold_codes,
        "hold_request_ids": [item["request_id"] for item in journal["holds"]],
        "slots": [{"slot": item["slot"], "request_id": item["request_id"]} for item in ready],
        "lineage": lineage,
        "released": [item["request_id"] for item in ready if item["released"]],
    }
    body = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "input_rows": len(inbound),
        "ready": len(ready),
        "held": len(journal["holds"]),
        "hold_codes": hold_codes,
        "hold_code_set": sorted(set(hold_codes)),
        "reserved_slots": sorted(slots),
        "reserved_slots_occupied": len(slots),
        "slot_occupancy": {
            item["slot"]: item["request_id"] for item in ready
        },
        "duplicate_accessions": 0,
        "released_reports": sum(1 for item in ready if item["released"]),
        "staged_reports": sum(
            1 for item in ready if item["report_status"] == "STAGED_PENDING_NAMED_APPROVAL"
        ),
        "replay_noops": sum(1 for item in effects if item.get("kind") == "REPLAY_NOOP"),
        "effects": effects,
        "autonomous_release_effects": autonomous,
        "accessions": ready,
        "holds": deepcopy(journal["holds"]),
        "routes": {item["request_id"]: item["route"] for item in ready},
        "accession_ids": [item["accession_id"] for item in ready],
        "reports": reports,
        "report_hashes": [item["report_hash"] for item in ready],
        "report_digest": sha256_hex(reports),
        "lineage": lineage,
        "lineage_sha256": sha256_hex(lineage),
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
    before_slots = set(journal["slots"])
    effects = [ingest_row(journal, row) for row in inbound]
    added = set(journal["accessions"]) - before
    added_holds = [item for item in journal["holds"] if sha256_hex(item) not in before_holds]
    added_slots = set(journal["slots"]) - before_slots
    return {
        "added_accessions": sorted(added),
        "added_accession_count": len(added),
        "added_holds": len(added_holds),
        "added_slots": sorted(added_slots),
        "added_record_count": len(added) + len(added_holds) + len(added_slots),
        "replay_noops": sum(1 for item in effects if item.get("kind") == "REPLAY_NOOP"),
        "accession_count": len(journal["accessions"]),
        "hold_count": len(journal["holds"]),
        "slot_count": len(journal["slots"]),
    }


def expected_actual(result: dict[str, Any]) -> dict[str, Any]:
    actual = {
        "input_rows": result.get("input_rows"),
        "ready": result.get("ready"),
        "held": result.get("held"),
        "reserved_slots_occupied": result.get("reserved_slots_occupied"),
        "duplicate_accessions": result.get("duplicate_accessions"),
        "released_reports": result.get("released_reports"),
        "staged_reports": result.get("staged_reports"),
        "replay_added_records": result.get("replay_added_records", 0),
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
    if Counter(result.get("hold_codes") or []) != Counter(HOLD_PLAN):
        failures.append("hold_code_counts")
    if len(set(result.get("accession_ids") or [])) != VALID_COUNT:
        failures.append("accession_ids_not_unique")
    occupancy = result.get("slot_occupancy") or {}
    if len(occupancy) != VALID_COUNT:
        failures.append("slot_count")
    if len(set(occupancy.values())) != VALID_COUNT:
        failures.append("slot_sample_not_unique")
    if len(set(occupancy)) != VALID_COUNT:
        failures.append("reserved_slot_not_unique")
    expected_slots = {reserved_slot_for(index): valid_request_id(index) for index in range(1, VALID_COUNT + 1)}
    if occupancy != expected_slots:
        failures.append("slot_occupancy")
    for item in result.get("accessions") or []:
        expected_source = source_hash(item["requirement_id"], item["form_id"], item["payment_id"])
        expected_method = method_hash(item["instrument"], item["method"], item["method_version"])
        expected_raw = raw_value_hash(item["raw"])
        expected_unit = unit_hash(item["instrument"])
        expected_report = sha256_hex(item["report"])
        if item.get("source_hash") != expected_source:
            failures.append("source_hash")
            break
        if item.get("method_hash") != expected_method:
            failures.append("method_hash")
            break
        if item.get("raw_value_hash") != expected_raw:
            failures.append("raw_value_hash")
            break
        if item.get("unit_hash") != expected_unit:
            failures.append("unit_hash")
            break
        if item.get("report_hash") != expected_report:
            failures.append("report_hash")
            break
        if item.get("report", {}).get("state") != "STAGED":
            failures.append("report_not_staged")
            break
        if item.get("released"):
            failures.append("released")
            break
        if item.get("interface_live"):
            failures.append("interface_live_accession")
            break
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
    if GOLDEN_AUDIT_SHA256 != "PENDING" and result.get("audit_sha256") != GOLDEN_AUDIT_SHA256:
        failures.append("audit_sha256")
    if GOLDEN_LINEAGE_SHA256 != "PENDING" and result.get("lineage_sha256") != GOLDEN_LINEAGE_SHA256:
        failures.append("lineage_sha256")
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
        "lineage_sha256": result["lineage_sha256"],
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
    first["replay_added_records"] = replay["added_record_count"]
    failures = pass_contract(first)
    if first.get("audit_sha256") != second.get("audit_sha256"):
        failures.append("replay_mismatch")
    if first.get("lineage_sha256") != second.get("lineage_sha256"):
        failures.append("lineage_mismatch")
    if first.get("report_digest") != second.get("report_digest"):
        failures.append("report_digest_mismatch")
    if replay.get("added_record_count") != 0:
        failures.append("replay_added_records")
    counts = expected_actual(first)
    report = {
        "ok": not failures,
        "failures": failures,
        "expected": counts["expected"],
        "actual": counts["actual"],
        "fixture_sha256": fixture_manifest()["fixture_sha256"],
        "audit_sha256": first.get("audit_sha256"),
        "lineage_sha256": first.get("lineage_sha256"),
        "report_digest": first.get("report_digest"),
        "manifest_sha256": first.get("manifest_sha256"),
        "ready": first.get("ready"),
        "held": first.get("held"),
        "hold_codes": sorted(set(first.get("hold_codes") or [])),
        "reserved_slots_occupied": first.get("reserved_slots_occupied"),
        "staged_reports": first.get("staged_reports"),
        "replay_added_records": replay.get("added_record_count"),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
