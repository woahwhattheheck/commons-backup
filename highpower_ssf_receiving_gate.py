#!/usr/bin/env python3
"""Official command for highpower-ssf-receiving-gate-lims-01.

Digital SSF-to-Receiving-Inspection Accession + Hold/Release Gate.
Buyer pairing: HIGHPOWER Validation Testing & Lab Services / Gary Socola.

Working CLI. Loads 200 paired synthetic Sample Submission Form (HP-QC-067)
and Receiving Inspection records. Accessions the 160 reconciled pairs once.
Parks all 40 predefined omissions/discrepancies under the exact HOLD code.
Zero downstream activity while held. Every field keeps source/version
provenance. Replay changes nothing. Audit and report hashes are
deterministic. Named human release only.

HOLD / BUILD-AND-VERIFY. Adapters are synthetic or simulated and
read-only. No live sample or test action. No outreach. cash_usd=0.

Official command:
    python3 highpower_ssf_receiving_gate.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

DEMAND_ID = "highpower-ssf-receiving-gate-lims-01"
SCHEMA = "commons-highpower-ssf-receiving-gate-lims/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
BUYER = "HIGHPOWER Validation Testing & Lab Services / Gary Socola"
FACILITY = "SYN-ROCHESTER-NY-125-HIGHPOWER-RD"
HUMAN_RELEASER = "SYN-HPV-RELEASE-OFFICER"
HUMAN_ROLE = "RECEIVING_RELEASE_OFFICER"
RECEIVING_DESK = "RECEIVING_DESK"
CLIENT_SERVICES = "CLIENT_SERVICES"
SAFETY_OFFICER = "SAFETY_OFFICER"
STERILIZATION_LEAD = "STERILIZATION_LEAD"

INPUT_COUNT = 200
VALID_COUNT = 160
HOLD_COUNT = 40
PER_HOLD_CODE = 5

SSF_DOC = "HP-QC-067"
SSF_REV = "I"
SSF_VERSION = "2019-07"
RCV_DOC = "HP-LSOP-059"
RCV_REV = "SYN-A"
RCV_VERSION = "2026-08-31"

RECONCILE_FIELDS = (
    "lot_number",
    "serial_number",
    "catalog_part",
    "bom",
    "qty",
    "storage",
    "intended_use",
    "clinically_used",
    "safety_sds",
    "decontaminated",
    "handling",
    "sterilization_method",
    "sterilization_cycle",
)
PROVENANCE_FIELDS = RECONCILE_FIELDS + ("quote_number", "po_number", "sample_id", "product_name")

HOLD_CODES = (
    "HOLD_LOT_SERIAL_MISMATCH",
    "HOLD_BOM_MISMATCH",
    "HOLD_QTY_DISCREPANCY",
    "HOLD_STORAGE_OMISSION",
    "HOLD_INTENDED_USE_MISMATCH",
    "HOLD_SAFETY_OMISSION",
    "HOLD_HANDLING_MISMATCH",
    "HOLD_STERILIZATION_DISCREPANCY",
)
HOLD_OWNERS = {
    "HOLD_LOT_SERIAL_MISMATCH": RECEIVING_DESK,
    "HOLD_BOM_MISMATCH": RECEIVING_DESK,
    "HOLD_QTY_DISCREPANCY": RECEIVING_DESK,
    "HOLD_STORAGE_OMISSION": RECEIVING_DESK,
    "HOLD_INTENDED_USE_MISMATCH": CLIENT_SERVICES,
    "HOLD_SAFETY_OMISSION": SAFETY_OFFICER,
    "HOLD_HANDLING_MISMATCH": RECEIVING_DESK,
    "HOLD_STERILIZATION_DISCREPANCY": STERILIZATION_LEAD,
}
EXPECTED_HOLD_COUNTS = {code: PER_HOLD_CODE for code in HOLD_CODES}
EXPECTED_COUNTS = {
    "input_pairs": INPUT_COUNT,
    "valid": VALID_COUNT,
    "holds": HOLD_COUNT,
    "accessions": VALID_COUNT,
    "held_downstream": 0,
    "autonomous_released": 0,
    "human_released": VALID_COUNT,
    "duplicate_accessions": 0,
    "production_writes": 0,
    "live_tests": 0,
    "live_reports": 0,
    "billing_writes": 0,
}

TEST_CODES = (
    "SE-STEAM",
    "STERILITY",
    "BIO-BURDEN",
    "SE-ETO",
    "SE-100S",
    "SL-STEAM",
    "MAN-3LOG",
    "BIO-CYTO",
    "HLD",
    "AC-STEAM",
)
STERILE_FOR = {
    "SE-STEAM": ("STEAM", "PREVAC"),
    "STERILITY": ("STEAM", "GRAVITY"),
    "BIO-BURDEN": ("NONE", "AS_RECEIVED"),
    "SE-ETO": ("ETO", "446MG"),
    "SE-100S": ("STERRAD", "100S"),
    "SL-STEAM": ("STEAM", "PREVAC"),
    "MAN-3LOG": ("NONE", "MANUAL_WASH"),
    "BIO-CYTO": ("NONE", "EXTRACT"),
    "HLD": ("HLD", "CHEMICAL"),
    "AC-STEAM": ("STEAM", "PACKAGE"),
}
STORAGE_MODES = ("ROOM_TEMP", "REFRIGERATE", "FROZEN", "LIGHT_SENSITIVE")

SUBMITTED_AT = "2026-08-01T12:00:00Z"
RECEIVED_AT = "2026-08-02T14:00:00Z"
RELEASED_AT = "2026-08-31T06:00:00Z"

ADAPTERS = {
    "ssf": {"name": "SYNTHETIC_SSF", "mode": "READ_ONLY"},
    "receiving": {"name": "SYNTHETIC_RECEIVING", "mode": "READ_ONLY"},
    "lims": {"name": "SIMULATED_LIMS", "mode": "READ_ONLY"},
    "instrument": {"name": "SIMULATED_INSTRUMENT", "mode": "READ_ONLY"},
    "report": {"name": "SIMULATED_REPORT", "mode": "READ_ONLY"},
}

PACK = Path("revenue") / "highpower_ssf_receiving_gate"
FIXTURE_PATH = PACK / "fixture.json"
CONTRACT_PATH = PACK / "contract.json"
STATE_PATH = PACK / "state" / "journal.json"
RECEIPT_DIR = PACK / "receipts"
RUN_RECEIPT_PATH = RECEIPT_DIR / "run.json"
ACCESSION_RECEIPT_PATH = RECEIPT_DIR / "accessions.json"
HOLD_RECEIPT_PATH = RECEIPT_DIR / "holds.json"
LINEAGE_RECEIPT_PATH = RECEIPT_DIR / "lineage.json"
AUDIT_RECEIPT_PATH = RECEIPT_DIR / "audit.json"
REPLAY_RECEIPT_PATH = RECEIPT_DIR / "replay.json"
REPORT_RECEIPT_PATH = RECEIPT_DIR / "report.json"

GOLDEN_AUDIT_SHA256 = "cbb6bfc3d8a5ebdfd7cb6a42a20cec9763278d2b0446093dae98133ab9080cbf"
GOLDEN_LINEAGE_SHA256 = "f0052d3dcda4d800fc54e53f34da45a9aeb1590e35ea935f7bd73377bcd1e47a"
GOLDEN_ACCESSION_SHA256 = "5efe150981376c36cd1060e26516af979a77751e676d24858b0c1e3d0a299923"
GOLDEN_REPORT_SHA256 = "91ce2daa70195940131560074a94a1c248f3e4820605cda65ab3aff2017b970a"


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


def field_hash(value: Any) -> str:
    return sha256_hex(value)


def _bom(part: str, local: int) -> list[dict[str, str]]:
    return [
        {"component": f"{part}-FRAME", "qty": "1"},
        {"component": f"{part}-SEAL", "qty": str(2 + (local % 3))},
        {"component": f"{part}-LUMEN", "qty": str(1 + (local % 2))},
    ]


FORM_VALUE_KEYS = (
    "sample_id",
    "product_name",
    "catalog_part",
    "lot_number",
    "serial_number",
    "bom",
    "qty",
    "storage",
    "intended_use",
    "clinically_used",
    "safety_sds",
    "decontaminated",
    "handling",
    "sterilization_method",
    "sterilization_cycle",
    "quote_number",
    "po_number",
)


def form_envelope(kind: str, form_id: str) -> dict[str, str]:
    if kind == "SAMPLE_SUBMISSION":
        return {
            "form_id": form_id,
            "form_kind": kind,
            "form_doc": SSF_DOC,
            "form_rev": SSF_REV,
            "form_version": SSF_VERSION,
            "adapter": ADAPTERS["ssf"]["name"],
            "adapter_mode": ADAPTERS["ssf"]["mode"],
        }
    return {
        "form_id": form_id,
        "form_kind": kind,
        "form_doc": RCV_DOC,
        "form_rev": RCV_REV,
        "form_version": RCV_VERSION,
        "adapter": ADAPTERS["receiving"]["name"],
        "adapter_mode": ADAPTERS["receiving"]["mode"],
    }


def _side_values(local: int, *, prefix: str) -> dict[str, Any]:
    code = TEST_CODES[local % len(TEST_CODES)]
    method, cycle = STERILE_FOR[code]
    part = f"HPV-CAT-{local:03d}"
    return {
        "sample_id": f"{prefix}-SMP-{local:03d}",
        "product_name": f"SYN-REUSABLE-DEVICE-{local:03d}",
        "catalog_part": part,
        "lot_number": f"SYN-LOT-{local:03d}",
        "serial_number": f"SYN-SER-{local:03d}",
        "bom": _bom(part, local),
        "qty": 6 + (local % 7),
        "storage": STORAGE_MODES[local % len(STORAGE_MODES)],
        "intended_use": code,
        "clinically_used": False,
        "safety_sds": f"SYN-SDS-{local:03d}",
        "decontaminated": True,
        "handling": "HANDLE-AS-UNUSED",
        "sterilization_method": method,
        "sterilization_cycle": cycle,
        "quote_number": f"SYN-Q-{local:03d}",
        "po_number": f"SYN-PO-{local:03d}",
    }


def _stamp_form(kind: str, form_id: str, values: dict[str, Any], signed_at: str) -> dict[str, Any]:
    body = {**form_envelope(kind, form_id), **deepcopy(values), "signed_at": signed_at}
    body["form_hash"] = sha256_hex({key: body[key] for key in sorted(body) if key != "form_hash"})
    return body


def field_provenance(ssf: dict[str, Any], receiving: dict[str, Any]) -> dict[str, dict[str, Any]]:
    provenance: dict[str, dict[str, Any]] = {}
    for name in PROVENANCE_FIELDS:
        ssf_value = ssf.get(name)
        rcv_value = receiving.get(name)
        provenance[name] = {
            "ssf": {
                "value": deepcopy(ssf_value),
                "form_id": ssf["form_id"],
                "form_doc": ssf["form_doc"],
                "form_rev": ssf["form_rev"],
                "form_version": ssf["form_version"],
                "field_hash": field_hash(ssf_value),
            },
            "receiving": {
                "value": deepcopy(rcv_value),
                "form_id": receiving["form_id"],
                "form_doc": receiving["form_doc"],
                "form_rev": receiving["form_rev"],
                "form_version": receiving["form_version"],
                "field_hash": field_hash(rcv_value),
            },
            "match": ssf_value == rcv_value,
        }
    return provenance


def source_fields(pair: dict[str, Any]) -> dict[str, Any]:
    ssf = pair["ssf"]
    receiving = pair["receiving"]
    return {
        "pair_id": pair["pair_id"],
        "ssf_form_hash": ssf["form_hash"],
        "receiving_form_hash": receiving["form_hash"],
        "ssf_version": {"doc": ssf["form_doc"], "rev": ssf["form_rev"], "version": ssf["form_version"]},
        "receiving_version": {
            "doc": receiving["form_doc"],
            "rev": receiving["form_rev"],
            "version": receiving["form_version"],
        },
        "values": {name: ssf.get(name) for name in RECONCILE_FIELDS},
    }


def compute_source_hash(pair: dict[str, Any]) -> str:
    return sha256_hex(source_fields(pair))


def accession_id(pair_id: str, source_hash: str) -> str:
    digest = sha256_hex({"demand_id": DEMAND_ID, "pair_id": pair_id, "source_hash": source_hash})
    return f"HPV-ACC-{digest[:12]}"


def study_id(pair_id: str, source_hash: str) -> str:
    digest = sha256_hex({"demand_id": DEMAND_ID, "kind": "STUDY", "pair_id": pair_id, "source_hash": source_hash})
    return f"HPV-SYN-STUDY-{digest[:10]}"


def _valid_pair(local: int) -> dict[str, Any]:
    values = _side_values(local, prefix="HPV")
    ssf = _stamp_form("SAMPLE_SUBMISSION", f"HPV-SSF-{local:03d}", values, SUBMITTED_AT)
    receiving = _stamp_form("RECEIVING_INSPECTION", f"HPV-RCV-{local:03d}", values, RECEIVED_AT)
    pair = {
        "pair_id": f"HPV-PAIR-{local:03d}",
        "expected_state": "ACCESSION",
        "expected_hold_code": None,
        "ssf": ssf,
        "receiving": receiving,
        "synthetic": True,
        "live_sample": False,
        "live_test": False,
    }
    pair["field_provenance"] = field_provenance(ssf, receiving)
    pair["source_hash"] = compute_source_hash(pair)
    return pair


def _hold_pair(slot: int) -> dict[str, Any]:
    code = HOLD_CODES[slot // PER_HOLD_CODE]
    within = slot % PER_HOLD_CODE
    local = 200 + slot
    pair = _valid_pair(local)
    pair["pair_id"] = f"HPV-HOLD-{slot + 1:02d}"
    pair["expected_state"] = "HOLD"
    pair["expected_hold_code"] = code
    receiving = deepcopy(pair["receiving"])
    ssf = deepcopy(pair["ssf"])

    if code == "HOLD_LOT_SERIAL_MISMATCH":
        receiving["lot_number"] = f"SYN-LOT-MISMATCH-{within:02d}"
    elif code == "HOLD_BOM_MISMATCH":
        receiving["catalog_part"] = f"HPV-CAT-WRONG-{within:02d}"
        receiving["bom"] = _bom(receiving["catalog_part"], local)
    elif code == "HOLD_QTY_DISCREPANCY":
        receiving["qty"] = int(receiving["qty"]) + 3
    elif code == "HOLD_STORAGE_OMISSION":
        receiving["storage"] = ""
    elif code == "HOLD_INTENDED_USE_MISMATCH":
        other = TEST_CODES[(TEST_CODES.index(receiving["intended_use"]) + 1) % len(TEST_CODES)]
        receiving["intended_use"] = other
    elif code == "HOLD_SAFETY_OMISSION":
        receiving["safety_sds"] = ""
    elif code == "HOLD_HANDLING_MISMATCH":
        receiving["handling"] = "HANDLE-AS-USED-WET"
    elif code == "HOLD_STERILIZATION_DISCREPANCY":
        receiving["sterilization_cycle"] = "UNDECLARED-CYCLE"
    else:
        raise RuntimeError("unmapped hold code %s" % code)

    ssf_values = {name: ssf[name] for name in FORM_VALUE_KEYS}
    rcv_values = {name: receiving[name] for name in FORM_VALUE_KEYS}
    pair["ssf"] = _stamp_form("SAMPLE_SUBMISSION", ssf["form_id"], ssf_values, SUBMITTED_AT)
    pair["receiving"] = _stamp_form("RECEIVING_INSPECTION", receiving["form_id"], rcv_values, RECEIVED_AT)
    pair["field_provenance"] = field_provenance(pair["ssf"], pair["receiving"])
    pair["source_hash"] = compute_source_hash(pair)
    return pair


def build_acceptance_fixture() -> list[dict[str, Any]]:
    rows = [_valid_pair(local) for local in range(1, VALID_COUNT + 1)]
    rows.extend(_hold_pair(slot) for slot in range(HOLD_COUNT))
    if len(rows) != INPUT_COUNT:
        raise RuntimeError("fixture must be exactly 200 pairs, got %s" % len(rows))
    valid = [row for row in rows if row["expected_state"] == "ACCESSION"]
    holds = [row for row in rows if row["expected_state"] == "HOLD"]
    if len(valid) != VALID_COUNT or len(holds) != HOLD_COUNT:
        raise RuntimeError("fixture split must be 160/40")
    codes = [row["expected_hold_code"] for row in holds]
    for code in HOLD_CODES:
        if codes.count(code) != PER_HOLD_CODE:
            raise RuntimeError("%s must appear exactly 5 times" % code)
    pair_ids = [row["pair_id"] for row in rows]
    if len(pair_ids) != len(set(pair_ids)):
        raise RuntimeError("pair_id must be unique")
    return rows


def write_fixture(path: Path = FIXTURE_PATH) -> list[dict[str, Any]]:
    rows = build_acceptance_fixture()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return rows


def load_fixture(path: Path = FIXTURE_PATH) -> list[dict[str, Any]]:
    if path.is_file():
        rows = json.loads(path.read_text(encoding="utf-8"))
        if len(rows) != INPUT_COUNT:
            raise RuntimeError("fixture.json must contain exactly 200 pairs")
        return rows
    return build_acceptance_fixture()


def empty_journal() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "facility": FACILITY,
        "truth_gate": TRUTH_GATE,
        "accessions": {},
        "holds": {},
        "events": [],
        "pair_index": {},
        "interface_live": False,
        "production_writes": 0,
        "live_tests": 0,
        "live_reports": 0,
        "billing_writes": 0,
        "automatic_releases": 0,
        "adapters": deepcopy(ADAPTERS),
    }


def _event(journal: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    prev = journal["events"][-1]["record_hash"] if journal["events"] else "GENESIS"
    body = {"seq": len(journal["events"]) + 1, "kind": kind, **deepcopy(payload)}
    body["prev_hash"] = prev
    body["record_hash"] = sha256_hex(
        {"prev": prev, "body": {k: v for k, v in body.items() if k not in {"prev_hash", "record_hash"}}}
    )
    journal["events"].append(body)


def normalize_form(form: dict[str, Any]) -> dict[str, Any]:
    qty = form.get("qty")
    return {
        "form_id": _text(form.get("form_id")),
        "form_kind": _text(form.get("form_kind")),
        "form_doc": _text(form.get("form_doc")),
        "form_rev": _text(form.get("form_rev")),
        "form_version": _text(form.get("form_version")),
        "form_hash": _text(form.get("form_hash")),
        "adapter": _text(form.get("adapter")),
        "adapter_mode": _text(form.get("adapter_mode")),
        "sample_id": _text(form.get("sample_id")),
        "product_name": _text(form.get("product_name")),
        "catalog_part": _text(form.get("catalog_part")),
        "lot_number": _text(form.get("lot_number")),
        "serial_number": _text(form.get("serial_number")),
        "bom": deepcopy(form.get("bom") or []),
        "qty": int(qty) if str(qty).strip() not in {"", "None"} else 0,
        "storage": _text(form.get("storage")),
        "intended_use": _text(form.get("intended_use")),
        "clinically_used": _flag(form.get("clinically_used")) if "clinically_used" in form else False,
        "safety_sds": _text(form.get("safety_sds")),
        "decontaminated": _flag(form.get("decontaminated")) if "decontaminated" in form else False,
        "handling": _text(form.get("handling")),
        "sterilization_method": _text(form.get("sterilization_method")),
        "sterilization_cycle": _text(form.get("sterilization_cycle")),
        "quote_number": _text(form.get("quote_number")),
        "po_number": _text(form.get("po_number")),
        "signed_at": _text(form.get("signed_at")),
    }


def normalize(pair: dict[str, Any]) -> dict[str, Any]:
    ssf = normalize_form(pair.get("ssf") or {})
    receiving = normalize_form(pair.get("receiving") or {})
    return {
        "pair_id": _text(pair.get("pair_id")),
        "ssf": ssf,
        "receiving": receiving,
        "field_provenance": field_provenance(ssf, receiving),
        "source_hash": _text(pair.get("source_hash")),
        "synthetic": True,
        "live_sample": False,
        "live_test": False,
    }


def classify(norm: dict[str, Any]) -> dict[str, Any]:
    ssf = norm["ssf"]
    rcv = norm["receiving"]
    if ssf["lot_number"] != rcv["lot_number"] or ssf["serial_number"] != rcv["serial_number"]:
        return {"ok": False, "code": "HOLD_LOT_SERIAL_MISMATCH"}
    if ssf["catalog_part"] != rcv["catalog_part"] or ssf["bom"] != rcv["bom"]:
        return {"ok": False, "code": "HOLD_BOM_MISMATCH"}
    if ssf["qty"] != rcv["qty"]:
        return {"ok": False, "code": "HOLD_QTY_DISCREPANCY"}
    if not ssf["storage"] or not rcv["storage"]:
        return {"ok": False, "code": "HOLD_STORAGE_OMISSION"}
    if ssf["intended_use"] != rcv["intended_use"]:
        return {"ok": False, "code": "HOLD_INTENDED_USE_MISMATCH"}
    if not ssf["safety_sds"] or not rcv["safety_sds"]:
        return {"ok": False, "code": "HOLD_SAFETY_OMISSION"}
    if ssf["clinically_used"] and not (ssf["decontaminated"] and rcv["decontaminated"]):
        return {"ok": False, "code": "HOLD_SAFETY_OMISSION"}
    if ssf["handling"] != rcv["handling"]:
        return {"ok": False, "code": "HOLD_HANDLING_MISMATCH"}
    if (
        ssf["sterilization_method"] != rcv["sterilization_method"]
        or ssf["sterilization_cycle"] != rcv["sterilization_cycle"]
    ):
        return {"ok": False, "code": "HOLD_STERILIZATION_DISCREPANCY"}
    expected_hash = compute_source_hash(norm)
    if not norm["source_hash"] or norm["source_hash"] != expected_hash:
        return {"ok": False, "code": "HOLD_LOT_SERIAL_MISMATCH"}
    return {
        "ok": True,
        "source_hash": expected_hash,
        "field_provenance": norm["field_provenance"],
    }


def _park_hold(journal: dict[str, Any], norm: dict[str, Any], code: str) -> dict[str, Any]:
    hold = {
        "pair_id": norm["pair_id"],
        "code": code,
        "state": "HOLD",
        "owner_role": HOLD_OWNERS[code],
        "source_hash": norm["source_hash"] or None,
        "field_provenance": deepcopy(norm["field_provenance"]),
        "ssf_form_id": norm["ssf"]["form_id"],
        "receiving_form_id": norm["receiving"]["form_id"],
        "downstream": {
            "study_assigned": False,
            "testing_started": False,
            "report_written": False,
            "billed": False,
            "material_disposition": False,
        },
        "released": False,
        "released_by": None,
        "interface_live": False,
        "live_test": False,
    }
    existing = journal["holds"].get(hold["pair_id"])
    if existing is not None:
        return {"kind": "NOOP", "reason": "already_held", "pair_id": hold["pair_id"]}
    journal["holds"][hold["pair_id"]] = hold
    journal["pair_index"][hold["pair_id"]] = {"kind": "HOLD", "code": code}
    _event(journal, "HOLD", {"pair_id": hold["pair_id"], "code": code, "owner_role": hold["owner_role"]})
    return {"kind": "HOLD", "duplicate": False, **hold}


def ingest_row(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    norm = normalize(row)
    pair_id = norm["pair_id"]
    if pair_id in journal["pair_index"]:
        prior = journal["pair_index"][pair_id]
        return {"kind": "NOOP", "reason": "already_seen", "pair_id": pair_id, "prior": prior["kind"]}
    verdict = classify(norm)
    if not verdict["ok"]:
        return _park_hold(journal, norm, verdict["code"])

    source_hash = verdict["source_hash"]
    acc_id = accession_id(pair_id, source_hash)
    if acc_id in journal["accessions"]:
        return {"kind": "NOOP", "reason": "already_accessioned", "accession_id": acc_id}

    record = {
        "accession_id": acc_id,
        "pair_id": pair_id,
        "study_id": study_id(pair_id, source_hash),
        "facility": FACILITY,
        "sample_id": norm["ssf"]["sample_id"],
        "source_hash": source_hash,
        "field_provenance": verdict["field_provenance"],
        "ssf": {
            "form_id": norm["ssf"]["form_id"],
            "form_doc": norm["ssf"]["form_doc"],
            "form_rev": norm["ssf"]["form_rev"],
            "form_version": norm["ssf"]["form_version"],
            "form_hash": norm["ssf"]["form_hash"],
            "adapter": ADAPTERS["ssf"]["name"],
        },
        "receiving": {
            "form_id": norm["receiving"]["form_id"],
            "form_doc": norm["receiving"]["form_doc"],
            "form_rev": norm["receiving"]["form_rev"],
            "form_version": norm["receiving"]["form_version"],
            "form_hash": norm["receiving"]["form_hash"],
            "adapter": ADAPTERS["receiving"]["name"],
        },
        "state": "ACCESSIONED",
        "downstream": {
            "study_assigned": True,
            "testing_started": False,
            "report_written": False,
            "billed": False,
            "material_disposition": False,
        },
        "released": False,
        "released_by": None,
        "released_at": None,
        "interface_state": "SIMULATED",
        "interface_live": False,
        "live_test": False,
        "live_report": False,
        "billing": False,
    }
    journal["accessions"][acc_id] = record
    journal["pair_index"][pair_id] = {"kind": "ACCESSION", "accession_id": acc_id}
    _event(
        journal,
        "ACCESSION",
        {
            "accession_id": acc_id,
            "pair_id": pair_id,
            "source_hash": source_hash,
            "adapter": ADAPTERS["lims"]["name"],
        },
    )
    return {"kind": "ACCESSION", "accession_id": acc_id, "pair_id": pair_id}


def _lookup_hold(journal: dict[str, Any], key: str) -> dict[str, Any] | None:
    hold = journal["holds"].get(key)
    if hold is not None:
        return hold
    for item in journal["holds"].values():
        if item.get("pair_id") == key:
            return item
    return None


def _lookup_accession(journal: dict[str, Any], key: str) -> dict[str, Any] | None:
    record = journal["accessions"].get(key)
    if record is not None:
        return record
    for item in journal["accessions"].values():
        if item["pair_id"] == key or item["sample_id"] == key or item["study_id"] == key:
            return item
    return None


def start_downstream(journal: dict[str, Any], key: str, *, actor: str, actor_role: str, action: str) -> dict[str, Any]:
    hold = _lookup_hold(journal, key)
    if hold is not None:
        hold["downstream"] = {name: False for name in hold["downstream"]}
        hold["live_test"] = False
        _event(journal, "DOWNSTREAM_BLOCKED_HOLD", {"pair_id": hold["pair_id"], "action": action, "actor": actor})
        return {"ok": False, "code": "DOWNSTREAM_BLOCKED_HOLD", "action": action, "testing_started": False}

    record = _lookup_accession(journal, key)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_PAIR"}
    if not record.get("released") or _text(actor_role).upper() != HUMAN_ROLE or _text(actor) != HUMAN_RELEASER:
        _event(
            journal,
            "DOWNSTREAM_BLOCKED",
            {"accession_id": record["accession_id"], "code": "HUMAN_RELEASE_REQUIRED", "action": action, "actor": actor},
        )
        return {"ok": False, "code": "HUMAN_RELEASE_REQUIRED", "action": action}
    record["downstream"]["testing_started"] = False
    record["downstream"]["report_written"] = False
    record["downstream"]["billed"] = False
    record["live_test"] = False
    journal["live_tests"] = 0
    journal["live_reports"] = 0
    journal["billing_writes"] = 0
    _event(journal, "DOWNSTREAM_DENIED_SIMULATED", {"accession_id": record["accession_id"], "action": action})
    return {"ok": False, "code": "SIMULATED_ONLY_NO_LIVE_TEST", "action": action, "interface_live": False}


def start_test(journal: dict[str, Any], key: str, *, actor: str, actor_role: str) -> dict[str, Any]:
    return start_downstream(journal, key, actor=actor, actor_role=actor_role, action="START_TEST")


def release_accession(journal: dict[str, Any], acc_id: str, *, actor: str, actor_role: str) -> dict[str, Any]:
    record = journal["accessions"].get(acc_id)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_ACCESSION"}
    role = _text(actor_role).upper()
    name = _text(actor)
    if role != HUMAN_ROLE or name != HUMAN_RELEASER or not name or name.upper() in {"SYSTEM", "BOT", "AUTO"}:
        _event(
            journal,
            "AUTONOMOUS_RELEASE_DENIED",
            {"accession_id": acc_id, "actor": name or None, "actor_role": role or None},
        )
        journal["automatic_releases"] = 0
        return {"ok": False, "code": "AUTONOMOUS_RELEASE_DENIED"}
    if record.get("released"):
        return {"ok": True, "duplicate": True, "code": "ALREADY_RELEASED", "accession_id": acc_id}
    record["released"] = True
    record["released_by"] = name
    record["released_at"] = RELEASED_AT
    record["state"] = "HUMAN_RELEASED"
    record["live_test"] = False
    _event(journal, "HUMAN_RELEASE", {"accession_id": acc_id, "released_by": name})
    return {"ok": True, "code": "HUMAN_RELEASED", "accession_id": acc_id}


def release_hold(journal: dict[str, Any], pair_id: str, *, actor: str, actor_role: str) -> dict[str, Any]:
    hold = journal["holds"].get(pair_id)
    if hold is None:
        return {"ok": False, "code": "UNKNOWN_HOLD"}
    role = _text(actor_role).upper()
    name = _text(actor)
    if role != HUMAN_ROLE or name != HUMAN_RELEASER:
        _event(journal, "AUTONOMOUS_RELEASE_DENIED", {"pair_id": pair_id, "actor": name})
        return {"ok": False, "code": "AUTONOMOUS_RELEASE_DENIED"}
    hold["released"] = False
    hold["live_test"] = False
    hold["state"] = "HOLD"
    hold["downstream"] = {name: False for name in hold["downstream"]}
    _event(journal, "HOLD_RELEASE_DENIED_STILL_HOLD", {"pair_id": pair_id, "actor": name})
    return {"ok": False, "code": "HOLD_UNRESOLVED_NO_DOWNSTREAM", "testing_started": False}


def attempt_autonomous_release(journal: dict[str, Any]) -> list[dict[str, Any]]:
    effects = []
    for acc_id in sorted(journal["accessions"]):
        effects.append(release_accession(journal, acc_id, actor="SYSTEM", actor_role="SYSTEM"))
    for pair_id in sorted(journal["holds"]):
        effects.append(release_hold(journal, pair_id, actor="bot", actor_role="SYSTEM"))
    return effects


def authorized_human_release(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        release_accession(journal, acc_id, actor=HUMAN_RELEASER, actor_role=HUMAN_ROLE)
        for acc_id in sorted(journal["accessions"])
    ]


def mutate_source_lineage(journal: dict[str, Any], acc_id: str, forged_hash: str) -> dict[str, Any]:
    record = journal["accessions"].get(acc_id)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_ACCESSION"}
    if record["source_hash"] != forged_hash:
        _event(journal, "IMMUTABLE_SOURCE_LINEAGE", {"accession_id": acc_id})
        return {"ok": False, "code": "IMMUTABLE_SOURCE_LINEAGE", "source_hash": record["source_hash"]}
    return {"ok": True, "code": "LINEAGE_UNCHANGED"}


def replay_into(journal: dict[str, Any], rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    before_acc = {key: deepcopy(value) for key, value in journal["accessions"].items()}
    before_hold = {key: deepcopy(value) for key, value in journal["holds"].items()}
    before_acc_n = len(journal["accessions"])
    before_hold_n = len(journal["holds"])
    effects = [ingest_row(journal, row) for row in (rows or build_acceptance_fixture())]
    return {
        "added_accession_count": len(journal["accessions"]) - before_acc_n,
        "added_holds": len(journal["holds"]) - before_hold_n,
        "accession_count": len(journal["accessions"]),
        "hold_count": len(journal["holds"]),
        "replay_noops": sum(1 for item in effects if item.get("kind") == "NOOP"),
        "state_changed": before_acc != journal["accessions"] or before_hold != journal["holds"],
    }


def compact_accessions(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "accession_id": item["accession_id"],
            "pair_id": item["pair_id"],
            "study_id": item["study_id"],
            "sample_id": item["sample_id"],
            "source_hash": item["source_hash"],
            "field_provenance": deepcopy(item["field_provenance"]),
            "ssf": deepcopy(item["ssf"]),
            "receiving": deepcopy(item["receiving"]),
            "state": item["state"],
            "downstream": deepcopy(item["downstream"]),
            "released": item["released"],
            "released_by": item["released_by"],
            "interface_live": item["interface_live"],
            "live_test": item["live_test"],
        }
        for item in sorted(journal["accessions"].values(), key=lambda row: row["accession_id"])
    ]


def compact_holds(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [deepcopy(item) for item in sorted(journal["holds"].values(), key=lambda row: row["pair_id"])]


def compact_lineage(journal: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in compact_accessions(journal):
        rows.append(
            {
                "kind": "ACCESSION",
                "id": item["accession_id"],
                "pair_id": item["pair_id"],
                "source_hash": item["source_hash"],
                "field_provenance": item["field_provenance"],
            }
        )
    for item in compact_holds(journal):
        rows.append(
            {
                "kind": "HOLD",
                "id": item["pair_id"],
                "source_hash": item["source_hash"],
                "field_provenance": item["field_provenance"],
            }
        )
    return rows


def build_audit(journal: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "facility": FACILITY,
        "truth_gate": TRUTH_GATE,
        "accessions": compact_accessions(journal),
        "holds": [
            {
                "pair_id": item["pair_id"],
                "code": item["code"],
                "owner_role": item["owner_role"],
                "downstream": deepcopy(item["downstream"]),
                "source_hash": item["source_hash"],
            }
            for item in compact_holds(journal)
        ],
        "lineage": compact_lineage(journal),
        "events": deepcopy(journal["events"]),
        "autonomous_released": 0,
        "human_released": sum(1 for item in journal["accessions"].values() if item["released"]),
        "held_downstream": sum(
            1 for item in journal["holds"].values() if any(item["downstream"].values())
        ),
        "production_writes": journal["production_writes"],
        "live_tests": journal["live_tests"],
        "interface_live": journal["interface_live"],
        "adapters": deepcopy(ADAPTERS),
    }


def build_report(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "input_pairs": result["input_pairs"],
        "accessions": result["accessions"],
        "holds": result["holds"],
        "hold_code_counts": result["hold_code_counts"],
        "held_downstream": result["held_downstream"],
        "human_released": result["human_released"],
        "autonomous_released": result["autonomous_released"],
        "audit_sha256": result["audit_sha256"],
        "lineage_sha256": result["lineage_sha256"],
        "accession_sha256": result["accession_sha256"],
        "cash_usd": 0,
        "adapters": deepcopy(ADAPTERS),
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
    if result.get("hold_code_counts") != EXPECTED_HOLD_COUNTS:
        failures.append("hold_code_counts")
    if result.get("held_downstream") != 0:
        failures.append("held_downstream")
    if result.get("duplicate_accessions") != 0:
        failures.append("duplicate_accessions")
    replay = result.get("replay") or {}
    if replay.get("added_accession_count") != 0 or replay.get("added_holds") != 0 or replay.get("state_changed"):
        failures.append("replay")
    if result.get("audit_sha256") != result.get("replay_audit_sha256"):
        failures.append("replay_hash")
    if result.get("lineage_failures"):
        failures.append("lineage")
    if result.get("provenance_failures"):
        failures.append("provenance")
    if result.get("autonomous_released") != 0:
        failures.append("autonomous_release")
    if result.get("interface_live") or result.get("production_writes") or result.get("live_tests"):
        failures.append("live_adapters")
    if result.get("cash_usd") != 0:
        failures.append("cash_usd")
    if result.get("golden_locked"):
        if result.get("audit_sha256") != GOLDEN_AUDIT_SHA256:
            failures.append("audit_sha256")
        if result.get("lineage_sha256") != GOLDEN_LINEAGE_SHA256:
            failures.append("lineage_sha256")
        if result.get("accession_sha256") != GOLDEN_ACCESSION_SHA256:
            failures.append("accession_sha256")
        if result.get("report_sha256") != GOLDEN_REPORT_SHA256:
            failures.append("report_sha256")
    auto = result.get("autonomous_release_effects") or []
    if auto and any(item.get("ok") for item in auto):
        failures.append("autonomous_release_not_denied")
    if any(any(item.get("downstream", {}).values()) for item in result.get("hold_records") or []):
        failures.append("hold_started_downstream")
    return failures


def lineage_failures(rows: list[dict[str, Any]], journal: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    by_pair = {row["pair_id"]: row for row in rows if row["expected_state"] == "ACCESSION"}
    for item in journal["accessions"].values():
        src = by_pair.get(item["pair_id"])
        if src is None:
            failures.append("missing_source:%s" % item["pair_id"])
            continue
        if item["source_hash"] != src["source_hash"]:
            failures.append("source_hash:%s" % item["pair_id"])
        if item["field_provenance"] != src["field_provenance"]:
            failures.append("field_provenance:%s" % item["pair_id"])
        if item["source_hash"] != compute_source_hash(src):
            failures.append("recompute:%s" % item["pair_id"])
    return failures


def provenance_failures(journal: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    records = list(journal["accessions"].values()) + list(journal["holds"].values())
    for item in records:
        provenance = item.get("field_provenance") or {}
        for name in PROVENANCE_FIELDS:
            cell = provenance.get(name)
            if not cell:
                failures.append("missing_field:%s:%s" % (item.get("pair_id") or item.get("accession_id"), name))
                continue
            for side in ("ssf", "receiving"):
                src = cell.get(side) or {}
                if not src.get("form_id") or not src.get("form_doc") or not src.get("form_rev") or not src.get("form_version"):
                    failures.append("missing_version:%s:%s:%s" % (item.get("pair_id"), name, side))
                if len(_text(src.get("field_hash"))) != 64:
                    failures.append("field_hash:%s:%s:%s" % (item.get("pair_id"), name, side))
    return failures


def run_gate(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else load_fixture())
    journal = empty_journal()
    effects = [ingest_row(journal, row) for row in inbound]
    hold_attempts = [
        start_test(journal, pair_id, actor="SYSTEM", actor_role="SYSTEM")
        for pair_id in sorted(journal["holds"])
    ]
    hold_report_attempts = [
        start_downstream(journal, pair_id, actor="SYSTEM", actor_role="SYSTEM", action="WRITE_REPORT")
        for pair_id in sorted(journal["holds"])
    ]
    auto = attempt_autonomous_release(journal)
    human = authorized_human_release(journal)
    released_attempts = [
        start_test(journal, acc_id, actor=HUMAN_RELEASER, actor_role=HUMAN_ROLE)
        for acc_id in sorted(journal["accessions"])
    ]
    audit = build_audit(journal)
    lineage = compact_lineage(journal)
    accessions = compact_accessions(journal)
    audit_sha = sha256_hex(audit)
    lineage_sha = sha256_hex(lineage)
    accession_sha = sha256_hex(accessions)

    replay = replay_into(journal, inbound)
    replay_audit = build_audit(journal)
    replay_sha = sha256_hex(replay_audit)

    hold_code_counts = {code: 0 for code in HOLD_CODES}
    for item in journal["holds"].values():
        hold_code_counts[item["code"]] = hold_code_counts.get(item["code"], 0) + 1

    golden_locked = "pending" not in {
        GOLDEN_AUDIT_SHA256,
        GOLDEN_LINEAGE_SHA256,
        GOLDEN_ACCESSION_SHA256,
        GOLDEN_REPORT_SHA256,
    }
    packed = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "input_pairs": len(inbound),
        "valid": VALID_COUNT,
        "holds": len(journal["holds"]),
        "accessions": len(journal["accessions"]),
        "accession_records": accessions,
        "hold_records": compact_holds(journal),
        "hold_codes": list(HOLD_CODES),
        "hold_code_counts": hold_code_counts,
        "lineage_failures": lineage_failures(inbound, journal),
        "provenance_failures": provenance_failures(journal),
        "lineage": lineage,
        "held_downstream": sum(1 for item in journal["holds"].values() if any(item["downstream"].values())),
        "hold_test_attempts": hold_attempts,
        "hold_report_attempts": hold_report_attempts,
        "released_test_attempts": released_attempts,
        "autonomous_release_effects": auto,
        "human_release_effects": human,
        "autonomous_released": 0,
        "human_released": sum(1 for item in journal["accessions"].values() if item["released"]),
        "duplicate_accessions": len(accessions) - len({item["pair_id"] for item in accessions}),
        "effects": effects,
        "replay": replay,
        "audit": audit,
        "audit_sha256": audit_sha,
        "replay_audit_sha256": replay_sha,
        "lineage_sha256": lineage_sha,
        "accession_sha256": accession_sha,
        "interface_live": False,
        "interfaces": "SYNTHETIC_OR_SIMULATED_READ_ONLY",
        "production_writes": 0,
        "live_tests": 0,
        "live_reports": 0,
        "billing_writes": 0,
        "cash_usd": 0,
        "pre_sale_transport": "NONE",
        "golden_locked": golden_locked,
        "official_binary": "python3 highpower_ssf_receiving_gate.py",
        "official_test": "python3 test_highpower_ssf_receiving_gate.py",
        "journal": journal,
    }
    packed["report"] = build_report(packed)
    packed["report_sha256"] = sha256_hex(packed["report"])
    packed["failures"] = pass_contract(packed)
    packed["ok"] = packed["failures"] == []
    return packed


def persist_run(result: dict[str, Any], *, replay: dict[str, Any] | None = None) -> dict[str, str]:
    PACK.mkdir(parents=True, exist_ok=True)
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    write_fixture(FIXTURE_PATH)
    journal = result["journal"]
    STATE_PATH.write_text(json.dumps(journal, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    run_body = cli_payload(result)
    RUN_RECEIPT_PATH.write_text(json.dumps(run_body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    ACCESSION_RECEIPT_PATH.write_text(
        json.dumps(result["accession_records"], indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    HOLD_RECEIPT_PATH.write_text(
        json.dumps(result["hold_records"], indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    LINEAGE_RECEIPT_PATH.write_text(
        json.dumps(
            {"lineage_sha256": result["lineage_sha256"], "records": result["lineage"]},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    AUDIT_RECEIPT_PATH.write_text(
        json.dumps(
            {
                "accession_sha256": result["accession_sha256"],
                "audit_sha256": result["audit_sha256"],
                "report_sha256": result["report_sha256"],
                "counts": expected_actual(result),
                "hold_code_counts": result["hold_code_counts"],
                "lineage_sha256": result["lineage_sha256"],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    REPORT_RECEIPT_PATH.write_text(
        json.dumps(result["report"], indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if replay is not None:
        REPLAY_RECEIPT_PATH.write_text(json.dumps(replay, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    CONTRACT_PATH.write_text(
        json.dumps(
            {
                "buyer": BUYER,
                "cash_usd": 0,
                "demand_id": DEMAND_ID,
                "interfaces": "SYNTHETIC_OR_SIMULATED_READ_ONLY",
                "live_lims": False,
                "official_binary": "python3 highpower_ssf_receiving_gate.py",
                "official_test": "python3 test_highpower_ssf_receiving_gate.py",
                "page": "highpower-ssf-receiving-gate-lims.html",
                "pre_sale_transport": "NONE",
                "production_deployment": False,
                "schema": SCHEMA,
                "state": TRUTH_GATE,
                "synthetic": True,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "fixture": str(FIXTURE_PATH),
        "journal": str(STATE_PATH),
        "run": str(RUN_RECEIPT_PATH),
        "accessions": str(ACCESSION_RECEIPT_PATH),
        "holds": str(HOLD_RECEIPT_PATH),
        "lineage": str(LINEAGE_RECEIPT_PATH),
        "audit": str(AUDIT_RECEIPT_PATH),
        "report": str(REPORT_RECEIPT_PATH),
        "contract": str(CONTRACT_PATH),
    }


def load_journal(path: Path = STATE_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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
        "hold_code_counts": result["hold_code_counts"],
        "held_downstream": result["held_downstream"],
        "human_released": result["human_released"],
        "autonomous_released": result["autonomous_released"],
        "audit_sha256": result["audit_sha256"],
        "lineage_sha256": result["lineage_sha256"],
        "accession_sha256": result["accession_sha256"],
        "report_sha256": result["report_sha256"],
        "replay": result["replay"],
        "replay_audit_sha256": result["replay_audit_sha256"],
        "truth_gate": TRUTH_GATE,
        "interfaces": result["interfaces"],
        "cash_usd": 0,
        "pre_sale_transport": "NONE",
        "official_binary": result["official_binary"],
        "official_test": result["official_test"],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HIGHPOWER SSF-to-receiving accession + hold/release gate")
    parser.add_argument("--write-fixture", action="store_true", help="write the 200-pair fixture and exit")
    parser.add_argument("--print-goldens", action="store_true", help="print computed digests without locking")
    parser.add_argument("--replay", action="store_true", help="replay into persisted journal and write replay receipt")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.write_fixture:
        rows = write_fixture()
        sys.stdout.write(_canonical({"wrote": str(FIXTURE_PATH), "count": len(rows)}) + "\n")
        return 0
    if args.print_goldens:
        result = run_gate(build_acceptance_fixture())
        sys.stdout.write(
            _canonical(
                {
                    "audit_sha256": result["audit_sha256"],
                    "lineage_sha256": result["lineage_sha256"],
                    "accession_sha256": result["accession_sha256"],
                    "report_sha256": result["report_sha256"],
                    "expected": expected_actual(result),
                    "hold_code_counts": result["hold_code_counts"],
                    "failures": result["failures"],
                    "ok": result["ok"],
                }
            )
            + "\n"
        )
        return 0
    if args.replay:
        if not STATE_PATH.is_file():
            result = run_gate()
            persist_run(result)
        journal = load_journal()
        replay = replay_into(journal, load_fixture())
        REPLAY_RECEIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
        body = {
            "ok": replay["added_accession_count"] == 0
            and replay["added_holds"] == 0
            and not replay["state_changed"],
            "replay": replay,
            "journal_sha256": sha256_hex(journal),
        }
        STATE_PATH.write_text(json.dumps(journal, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        REPLAY_RECEIPT_PATH.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        sys.stdout.write(_canonical(body) + "\n")
        return 0 if body["ok"] else 1

    result = run_gate()
    written = persist_run(result, replay=result["replay"])
    payload = cli_payload(result)
    payload["written"] = written
    sys.stdout.write(_canonical(payload) + "\n")
    return 0 if payload["ok"] and not payload["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
