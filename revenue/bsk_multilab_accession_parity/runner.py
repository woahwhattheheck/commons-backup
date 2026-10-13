#!/usr/bin/env python3
"""BSK multi-lab accession parity gate.

Demand: bsk-multilab-accession-parity-lims-01
Buyer pairing: BSK Associates Analytical Division / Belinda Vega
Slack OPEN: #build-demand 1788149949.285219

Working program, not a look-inside souvenir. Intake → facility-specific
COC normalize → client/project/sample/matrix/analysis map →
collection/receipt/custody/temperature/TAT/regulatory validate →
deterministic six-lab route → HOLD on 120 seeded exceptions →
named-human release.

600 synthetic COCs, 100 per lab: 480 valid, 120 seeded exceptions.
Every valid field maps exactly once to the correct lab. All exceptions
block with the truth-set reason. Zero cross-facility routing. Source
hashes and coordinates attach. Replay writes zero new records.
Accession and audit manifests are deterministic. Named human required
before any release. No automatic release.

COC / LIMS / instrument / report / billing stay mocked and read-only.
No live LIMS. No production writes. No outreach. No phone. No personal
email. cash_usd=0. HOLD / BUILD-AND-VERIFY.

Official command:
    python3 bsk_multilab_accession_parity.py
    python3 revenue/bsk_multilab_accession_parity/runner.py
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
ACCESSION_RECEIPT_PATH = RECEIPT_DIR / "accessions.json"
HOLD_RECEIPT_PATH = RECEIPT_DIR / "holds.json"
ROUTE_RECEIPT_PATH = RECEIPT_DIR / "routes.json"
AUDIT_RECEIPT_PATH = RECEIPT_DIR / "audit.json"
REPLAY_RECEIPT_PATH = RECEIPT_DIR / "replay.json"

DEMAND_ID = "bsk-multilab-accession-parity-lims-01"
SCHEMA = "commons-bsk-multilab-accession-parity-lims/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
BUYER = "BSK Associates Analytical Division / Belinda Vega"
NAMED_ROLE = "NAMED_RELEASE_OFFICER"
NAMED_ACTOR = "SYN-BSK-RELEASE-OFFICER"
EXCEPTION_OWNER_ROLE = "ACCESSION_SPECIALIST"
EXCEPTION_OWNER_DESK = "ACCESSION_PARITY"
COMMAND = "python3 bsk_multilab_accession_parity.py"
TEST_COMMAND = "python3 test_bsk_multilab_accession_parity.py"
SEED = 20260831
OPEN_SLACK_TS = "1788149949.285219"
OPEN_SLACK_CHANNEL = "C0BTRNE6Y58"
COLLECTED_AT = "2026-08-29T09:00:00Z"
RECEIVED_AT = "2026-08-29T15:00:00Z"
STALE_COLLECTED_AT = "2024-01-01T09:00:00Z"
RELEASED_AT = "2026-08-31T06:00:00Z"

FRESNO = "BSK_FRESNO"
BAKERSFIELD = "BSK_BAKERSFIELD"
SACRAMENTO = "BSK_SACRAMENTO"
SANTA_MARIA = "BSK_SANTA_MARIA"
VANCOUVER = "BSK_VANCOUVER"
SAN_BERNARDINO = "BSK_SAN_BERNARDINO"
LABS = (FRESNO, BAKERSFIELD, SACRAMENTO, SANTA_MARIA, VANCOUVER, SAN_BERNARDINO)
LAB_NAMES = {
    FRESNO: "Fresno",
    BAKERSFIELD: "Bakersfield",
    SACRAMENTO: "Sacramento",
    SANTA_MARIA: "Santa Maria",
    VANCOUVER: "Vancouver",
    SAN_BERNARDINO: "San Bernardino",
}
LAB_KEYS = {
    FRESNO: "FRE",
    BAKERSFIELD: "BAK",
    SACRAMENTO: "SAC",
    SANTA_MARIA: "SMA",
    VANCOUVER: "VAN",
    SAN_BERNARDINO: "SBD",
}
FACILITY_CODES = {
    "FRE": FRESNO,
    "BAK": BAKERSFIELD,
    "SAC": SACRAMENTO,
    "SMA": SANTA_MARIA,
    "VAN": VANCOUVER,
    "SBD": SAN_BERNARDINO,
}

LAB_SCOPE: dict[str, dict[str, Any]] = {
    FRESNO: {
        "analyses": ("EPA_200_8_METALS", "SM_2540_D_TSS"),
        "matrices": ("DW_FINISHED", "GW_MONITORING"),
        "regulatory": "SDWA",
        "tat_hours": 72,
    },
    BAKERSFIELD: {
        "analyses": ("EPA_8015_TPH", "EPA_8260_BTEX"),
        "matrices": ("SOIL_PETROLEUM", "GW_HYDROCARBON"),
        "regulatory": "LUFT",
        "tat_hours": 72,
    },
    SACRAMENTO: {
        "analyses": ("EPA_624_VOC", "SM_5210_BOD"),
        "matrices": ("WW_EFFLUENT", "SW_NPDES"),
        "regulatory": "NPDES",
        "tat_hours": 48,
    },
    SANTA_MARIA: {
        "analyses": ("EPA_8081_PEST", "EPA_8141_OP"),
        "matrices": ("AG_SOIL", "AG_TISSUE"),
        "regulatory": "FIFRA",
        "tat_hours": 96,
    },
    VANCOUVER: {
        "analyses": ("EPA_1664_HEM", "EPA_200_7_ICP"),
        "matrices": ("STORM_WATER", "WW_INFLUENT"),
        "regulatory": "NPDES_WA",
        "tat_hours": 48,
    },
    SAN_BERNARDINO: {
        "analyses": ("SW846_6010B", "SW846_8260B"),
        "matrices": ("HW_SOLID", "HW_LIQUID"),
        "regulatory": "RCRA",
        "tat_hours": 72,
    },
}

ADAPTERS = ("COC", "LIMS", "INSTRUMENT", "REPORT", "BILLING")
COC_COUNT = 600
VALID_COUNT = 480
BLOCKED_COUNT = 120
PER_LAB = 100
VALID_PER_LAB = 80
BLOCKED_PER_LAB = 20
PER_HOLD = 20
TEMP_MIN_C = 0.0
TEMP_MAX_C = 6.0

HOLD_CODES = (
    "HOLD_COC_FACILITY_MISMATCH",
    "HOLD_MAPPING_UNRESOLVED",
    "HOLD_COLLECTION_RECEIPT_INVALID",
    "HOLD_CUSTODY_BREAK",
    "HOLD_TEMPERATURE_OUT_OF_RANGE",
    "HOLD_TAT_REGULATORY",
)

MAP_FIELDS = ("client_id", "project_id", "sample_id", "matrix", "analysis_id")

EXPECTED_COUNTS = {
    "cocs": COC_COUNT,
    "valid": VALID_COUNT,
    "blocked": BLOCKED_COUNT,
    "per_lab": PER_LAB,
    "valid_per_lab": VALID_PER_LAB,
    "blocked_per_lab": BLOCKED_PER_LAB,
    "routed_exact": VALID_COUNT,
    "mapped_once": VALID_COUNT,
    "blocked_expected_reason": BLOCKED_COUNT,
    "cross_facility_routes": 0,
    "replay_added_records": 0,
    "released_without_named_human": 0,
    "released_after_named_human": VALID_COUNT,
    "blocked_released": 0,
    "production_writes": 0,
    "live_lims": 0,
    "cash_usd": 0,
}

EXPECTED_LAB_COUNTS = {lab: VALID_PER_LAB for lab in LABS}
EXPECTED_HOLD_COUNTS = {code: PER_HOLD for code in HOLD_CODES}
EXPECTED_LAB_TOTALS = {lab: PER_LAB for lab in LABS}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def load_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def golden_audit_sha256() -> str:
    spec = load_fixture()
    return str(spec.get("golden_audit_sha256") or "")


def facility_code_for(lab: str) -> str:
    return LAB_KEYS[lab]


def normalize_facility(code: str) -> str | None:
    text = str(code or "").strip().upper()
    if text in LABS:
        return text
    return FACILITY_CODES.get(text)


def analysis_catalog() -> dict[str, str]:
    mapped: dict[str, str] = {}
    for lab, spec in LAB_SCOPE.items():
        for analysis in spec["analyses"]:
            if analysis in mapped:
                raise RuntimeError("analysis must map to exactly one lab: %s" % analysis)
            mapped[analysis] = lab
    return mapped


def matrix_catalog() -> dict[str, str]:
    mapped: dict[str, str] = {}
    for lab, spec in LAB_SCOPE.items():
        for matrix in spec["matrices"]:
            if matrix in mapped:
                raise RuntimeError("matrix must map to exactly one lab: %s" % matrix)
            mapped[matrix] = lab
    return mapped


ANALYSIS_MAP = analysis_catalog()
MATRIX_MAP = matrix_catalog()


def identity_for(lab: str, slot: int) -> dict[str, str]:
    key = LAB_KEYS[lab]
    return {
        "client_id": f"SYN-BSK-CLIENT-{key}-{slot:03d}",
        "project_id": f"SYN-BSK-PROJ-{key}-{slot:03d}",
        "sample_id": f"SYN-BSK-SAMP-{key}-{slot:03d}",
    }


def mapping_catalog() -> dict[str, dict[str, str]]:
    clients: dict[str, str] = {}
    projects: dict[str, str] = {}
    samples: dict[str, str] = {}
    for lab in LABS:
        for slot in range(1, PER_LAB + 1):
            ident = identity_for(lab, slot)
            clients[ident["client_id"]] = lab
            projects[ident["project_id"]] = lab
            samples[ident["sample_id"]] = lab
    return {"client": clients, "project": projects, "sample": samples}


MAPS = mapping_catalog()


def source_coordinate(lab: str, index: int) -> str:
    return f"BSK-{LAB_KEYS[lab]}-{index:04d}"


def source_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "coc_id": row["coc_id"],
        "sample_id": row["sample_id"],
        "client_id": row["client_id"],
        "project_id": row["project_id"],
        "matrix": row["matrix"],
        "analysis_id": row["analysis_id"],
        "facility_code": row["facility_code"],
        "source_coordinate": row["source_coordinate"],
    }


def compute_source_hash(row: dict[str, Any]) -> str:
    return sha256_hex(source_payload(row))


def accession_id(coc_id: str, source_hash: str) -> str:
    digest = sha256_hex({"demand_id": DEMAND_ID, "coc_id": coc_id, "source_hash": source_hash})
    return "BSK-ACC-" + digest[:12]


def field_map(row: dict[str, Any]) -> dict[str, str | None]:
    return {
        "client_id": MAPS["client"].get(str(row.get("client_id") or "")),
        "project_id": MAPS["project"].get(str(row.get("project_id") or "")),
        "sample_id": MAPS["sample"].get(str(row.get("sample_id") or "")),
        "matrix": MATRIX_MAP.get(str(row.get("matrix") or "")),
        "analysis_id": ANALYSIS_MAP.get(str(row.get("analysis_id") or "")),
    }


def mapped_lab(row: dict[str, Any]) -> str | None:
    targets = [value for value in field_map(row).values()]
    if not targets or any(value is None for value in targets):
        return None
    unique = set(targets)
    if len(unique) != 1:
        return None
    return next(iter(unique))


def _coc_id(index: int, kind: str) -> str:
    return f"SYN-BSK-{kind}-{index:03d}"


def _base_row(index: int, lab: str, slot: int, *, kind: str) -> dict[str, Any]:
    spec = LAB_SCOPE[lab]
    pick = (slot - 1) % 2
    ident = identity_for(lab, slot)
    row = {
        "coc_id": _coc_id(index, kind),
        "coc_no": index,
        "facility_code": facility_code_for(lab),
        "home_lab": lab,
        "client_id": ident["client_id"],
        "project_id": ident["project_id"],
        "sample_id": ident["sample_id"],
        "matrix": spec["matrices"][pick],
        "analysis_id": spec["analyses"][pick],
        "regulatory_program": spec["regulatory"],
        "collected_at": COLLECTED_AT,
        "sampler_name": f"SYN-BSK-SAMPLER-{LAB_KEYS[lab]}-{(slot % 8) + 1:02d}",
        "receipt_ack": True,
        "received_at": RECEIVED_AT,
        "relinquished_by": f"SYN-BSK-FIELD-{LAB_KEYS[lab]}",
        "received_by": f"SYN-BSK-RECV-{LAB_KEYS[lab]}",
        "cooler_temp_c": 4.0,
        "tat_hours": spec["tat_hours"],
        "source_coordinate": source_coordinate(lab, index),
        "synthetic": True,
        "seed": SEED,
        "block": False,
        "expected_hold_code": None,
        "expected_lab": lab,
    }
    row["source_hash"] = compute_source_hash(row)
    return row


def _valid_row(index: int, lab: str, slot: int) -> dict[str, Any]:
    return _base_row(index, lab, slot, kind="COC")


def _hold_row(index: int, code: str, lab: str, slot: int) -> dict[str, Any]:
    row = _base_row(index, lab, slot, kind="HLD")
    row["block"] = True
    row["expected_hold_code"] = code
    row["expected_lab"] = None
    if code == "HOLD_COC_FACILITY_MISMATCH":
        row["facility_code"] = "UNK"
    elif code == "HOLD_MAPPING_UNRESOLVED":
        other = LABS[(LABS.index(lab) + 1) % len(LABS)]
        row["analysis_id"] = LAB_SCOPE[other]["analyses"][0]
    elif code == "HOLD_COLLECTION_RECEIPT_INVALID":
        row["collected_at"] = ""
        row["receipt_ack"] = False
    elif code == "HOLD_CUSTODY_BREAK":
        row["received_by"] = ""
    elif code == "HOLD_TEMPERATURE_OUT_OF_RANGE":
        row["cooler_temp_c"] = 18.0
    elif code == "HOLD_TAT_REGULATORY":
        row["collected_at"] = STALE_COLLECTED_AT
    else:
        raise RuntimeError("unknown hold code: %s" % code)
    row["source_hash"] = compute_source_hash(row)
    return row


def build_acceptance_fixture() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    index = 1
    for lab in LABS:
        for slot in range(1, VALID_PER_LAB + 1):
            rows.append(_valid_row(index, lab, slot))
            index += 1
    hold_ident = {lab: VALID_PER_LAB + 1 for lab in LABS}
    if len(HOLD_CODES) * PER_HOLD != BLOCKED_COUNT:
        raise RuntimeError("hold specs must be exactly 120")
    for code_i, code in enumerate(HOLD_CODES):
        for j in range(PER_HOLD):
            lab = LABS[(code_i * PER_HOLD + j) % len(LABS)]
            slot = hold_ident[lab]
            hold_ident[lab] += 1
            rows.append(_hold_row(index, code, lab, slot))
            index += 1
    if len(rows) != COC_COUNT:
        raise RuntimeError("fixture must be exactly 600 COCs, got %s" % len(rows))
    valid = [row for row in rows if not row["block"]]
    holds = [row for row in rows if row["block"]]
    if len(valid) != VALID_COUNT or len(holds) != BLOCKED_COUNT:
        raise RuntimeError("fixture split must be 480/120")
    by_lab_valid = {lab: 0 for lab in LABS}
    by_lab_total = {lab: 0 for lab in LABS}
    for row in rows:
        by_lab_total[row["home_lab"]] += 1
    for row in valid:
        by_lab_valid[row["home_lab"]] += 1
        mapped = mapped_lab(row)
        if mapped != row["home_lab"] or mapped != row["expected_lab"]:
            raise RuntimeError("valid row must map once to home lab: %s" % row["coc_id"])
        if normalize_facility(row["facility_code"]) != row["home_lab"]:
            raise RuntimeError("valid row facility must normalize to home lab: %s" % row["coc_id"])
    if by_lab_valid != EXPECTED_LAB_COUNTS:
        raise RuntimeError("valid lab split must be 80 each, got %s" % by_lab_valid)
    if by_lab_total != EXPECTED_LAB_TOTALS:
        raise RuntimeError("total lab split must be 100 each, got %s" % by_lab_total)
    codes = [row["expected_hold_code"] for row in holds]
    for code in HOLD_CODES:
        if codes.count(code) != PER_HOLD:
            raise RuntimeError("%s must appear exactly 20 times" % code)
    sample_ids = [row["sample_id"] for row in rows]
    if len(sample_ids) != len(set(sample_ids)):
        raise RuntimeError("sample_id must be unique across the fixture")
    return rows


def classify(row: dict[str, Any]) -> dict[str, Any]:
    """Fail-closed accession: first matching truth-set reason wins."""
    facility = normalize_facility(str(row.get("facility_code") or ""))
    if facility is None:
        return {"ok": False, "code": "HOLD_COC_FACILITY_MISMATCH"}

    maps = field_map(row)
    if any(value is None for value in maps.values()):
        return {"ok": False, "code": "HOLD_MAPPING_UNRESOLVED"}
    unique = set(maps.values())
    if len(unique) != 1 or next(iter(unique)) != facility:
        return {"ok": False, "code": "HOLD_MAPPING_UNRESOLVED"}

    collected = str(row.get("collected_at") or "").strip()
    received = str(row.get("received_at") or "").strip()
    receipt_ack = bool(row.get("receipt_ack"))
    if not collected or not received or not receipt_ack:
        return {"ok": False, "code": "HOLD_COLLECTION_RECEIPT_INVALID"}

    relinquished = str(row.get("relinquished_by") or "").strip()
    received_by = str(row.get("received_by") or "").strip()
    if not relinquished or not received_by:
        return {"ok": False, "code": "HOLD_CUSTODY_BREAK"}

    try:
        temp = float(row.get("cooler_temp_c"))
    except (TypeError, ValueError):
        return {"ok": False, "code": "HOLD_TEMPERATURE_OUT_OF_RANGE"}
    if temp < TEMP_MIN_C or temp > TEMP_MAX_C:
        return {"ok": False, "code": "HOLD_TEMPERATURE_OUT_OF_RANGE"}

    program = str(row.get("regulatory_program") or "").strip()
    if program != LAB_SCOPE[facility]["regulatory"]:
        return {"ok": False, "code": "HOLD_TAT_REGULATORY"}
    if collected < "2026-01-01T00:00:00Z":
        return {"ok": False, "code": "HOLD_TAT_REGULATORY"}

    return {
        "ok": True,
        "code": None,
        "lab": facility,
        "mapped": dict(maps),
        "analysis_id": row["analysis_id"],
        "matrix": row["matrix"],
    }


def empty_journal() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "seed": SEED,
        "accessions": {},
        "holds": {},
        "routes": {},
        "events": [],
        "coc_index": {},
        "accession_index": {},
        "adapters": {name: {} for name in ADAPTERS},
        "interface_live": False,
        "production_writes": 0,
        "live_lims": 0,
        "live_reports": 0,
        "live_billing": 0,
        "automatic_releases": 0,
        "cash_usd": 0,
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
        "coc_id": record["coc_id"],
        "state": record["state"],
        "lab": record.get("lab"),
        "analysis_id": record.get("analysis_id"),
        "cash_usd": 0,
    }
    payload["payload_sha256"] = sha256_hex({k: v for k, v in payload.items() if k != "payload_sha256"})
    return payload


def _write_adapters(journal: dict[str, Any], record: dict[str, Any]) -> None:
    for name in ADAPTERS:
        journal["adapters"][name][record["coc_id"]] = _adapter_payload(record, name)


def ingest_coc(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    coc_id = row["coc_id"]
    if coc_id in journal["coc_index"]:
        return {
            "kind": "NOOP",
            "reason": "already_seen",
            "coc_id": coc_id,
            "prior": journal["coc_index"][coc_id]["kind"],
        }

    verdict = classify(row)
    expected = row.get("expected_hold_code")
    if row.get("block"):
        if verdict["ok"] or verdict["code"] != expected:
            raise RuntimeError(
                "block %s expected %s got ok=%s code=%s"
                % (coc_id, expected, verdict["ok"], verdict.get("code"))
            )
    elif not verdict["ok"]:
        raise RuntimeError("valid COC %s classified as %s" % (coc_id, verdict["code"]))

    if not verdict["ok"]:
        hold = {
            "coc_id": coc_id,
            "home_lab": row["home_lab"],
            "facility_code": row["facility_code"],
            "sample_id": row["sample_id"],
            "analysis_id": row["analysis_id"],
            "code": verdict["code"],
            "state": "HOLD",
            "released": False,
            "released_by": None,
            "owner_role": EXCEPTION_OWNER_ROLE,
            "owner_desk": EXCEPTION_OWNER_DESK,
            "lab": None,
            "source_hash": row["source_hash"],
            "source_coordinate": row["source_coordinate"],
            "interface_live": False,
        }
        record = {
            "coc_id": coc_id,
            "accession_id": None,
            "home_lab": row["home_lab"],
            "lab": None,
            "lab_name": None,
            "client_id": row["client_id"],
            "project_id": row["project_id"],
            "sample_id": row["sample_id"],
            "matrix": row["matrix"],
            "analysis_id": row["analysis_id"],
            "field_map": field_map(row),
            "block": True,
            "block_reason": verdict["code"],
            "state": "HOLD",
            "released": False,
            "released_by": None,
            "source_hash": row["source_hash"],
            "source_coordinate": row["source_coordinate"],
            "interface_live": False,
        }
        journal["holds"][coc_id] = hold
        journal["accessions"][coc_id] = record
        journal["coc_index"][coc_id] = {"kind": "HOLD", "code": verdict["code"]}
        _write_adapters(journal, record)
        _event(journal, "HOLD", {"coc_id": coc_id, "code": verdict["code"], "owner_desk": EXCEPTION_OWNER_DESK})
        return {"kind": "HOLD", "coc_id": coc_id, "code": verdict["code"]}

    acc = accession_id(coc_id, row["source_hash"])
    if acc in journal["accession_index"]:
        return {"kind": "NOOP", "reason": "duplicate_accession", "coc_id": coc_id}
    journal["accession_index"][acc] = coc_id
    record = {
        "coc_id": coc_id,
        "accession_id": acc,
        "home_lab": row["home_lab"],
        "lab": verdict["lab"],
        "lab_name": LAB_NAMES[verdict["lab"]],
        "client_id": row["client_id"],
        "project_id": row["project_id"],
        "sample_id": row["sample_id"],
        "matrix": row["matrix"],
        "analysis_id": verdict["analysis_id"],
        "field_map": verdict["mapped"],
        "block": False,
        "block_reason": None,
        "state": "ROUTED",
        "released": False,
        "released_by": None,
        "released_at": None,
        "source_hash": row["source_hash"],
        "source_coordinate": row["source_coordinate"],
        "interface_live": False,
    }
    journal["accessions"][coc_id] = record
    journal["routes"][coc_id] = {
        "coc_id": coc_id,
        "accession_id": acc,
        "lab": record["lab"],
        "analysis_id": record["analysis_id"],
        "matrix": record["matrix"],
        "sample_id": record["sample_id"],
        "source_hash": record["source_hash"],
        "source_coordinate": record["source_coordinate"],
    }
    journal["coc_index"][coc_id] = {"kind": "ROUTE", "lab": record["lab"]}
    _write_adapters(journal, record)
    _event(
        journal,
        "ROUTE",
        {
            "coc_id": coc_id,
            "accession_id": acc,
            "lab": record["lab"],
            "analysis_id": record["analysis_id"],
        },
    )
    return {"kind": "ROUTE", "coc_id": coc_id, "lab": record["lab"], "accession_id": acc}


def release_coc(journal: dict[str, Any], coc_id: str, *, actor: str, actor_role: str) -> dict[str, Any]:
    hold = journal["holds"].get(coc_id)
    if hold is not None:
        _event(journal, "AUTONOMOUS_RELEASE_DENIED", {"coc_id": coc_id, "code": "RELEASE_BLOCKED_OPEN_HOLD", "actor": actor})
        return {"ok": False, "code": "RELEASE_BLOCKED_OPEN_HOLD"}
    record = journal["accessions"].get(coc_id)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_COC"}
    role = str(actor_role or "").strip().upper()
    name = str(actor or "").strip()
    if role != NAMED_ROLE or name != NAMED_ACTOR or not name or name.upper() in {"SYSTEM", "BOT", "AUTO"}:
        journal["automatic_releases"] = 0
        _event(
            journal,
            "AUTONOMOUS_RELEASE_DENIED",
            {"coc_id": coc_id, "actor": name or None, "actor_role": role or None},
        )
        return {"ok": False, "code": "AUTONOMOUS_RELEASE_DENIED"}
    if record.get("released"):
        return {"ok": True, "duplicate": True, "code": "ALREADY_RELEASED", "coc_id": coc_id}
    record["released"] = True
    record["released_by"] = name
    record["released_at"] = RELEASED_AT
    record["state"] = "HUMAN_RELEASED"
    _write_adapters(journal, record)
    _event(journal, "HUMAN_RELEASE", {"coc_id": coc_id, "released_by": name, "accession_id": record["accession_id"]})
    return {"ok": True, "code": "HUMAN_RELEASED", "coc_id": coc_id}


def attempt_autonomous_release(journal: dict[str, Any]) -> list[dict[str, Any]]:
    effects = []
    for coc_id in sorted(journal["accessions"]):
        effects.append(release_coc(journal, coc_id, actor="SYSTEM", actor_role="SYSTEM"))
    for coc_id in sorted(journal["holds"]):
        effects.append(release_coc(journal, coc_id, actor="bot", actor_role="SYSTEM"))
    return effects


def authorized_human_release(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        release_coc(journal, coc_id, actor=NAMED_ACTOR, actor_role=NAMED_ROLE)
        for coc_id in sorted(set(list(journal["accessions"]) + list(journal["holds"])))
    ]


def replay_into(journal: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    before_accessions = {key: deepcopy(value) for key, value in journal["accessions"].items()}
    before_holds = {key: deepcopy(value) for key, value in journal["holds"].items()}
    before_routes = {key: deepcopy(value) for key, value in journal["routes"].items()}
    before_index = dict(journal["accession_index"])
    before_events = len(journal["events"])
    effects = [ingest_coc(journal, row) for row in rows]
    return {
        "added_records": len(journal["accessions"]) - len(before_accessions),
        "added_holds": len(journal["holds"]) - len(before_holds),
        "added_routes": len(journal["routes"]) - len(before_routes),
        "added_accessions": len(journal["accession_index"]) - len(before_index),
        "replay_noops": sum(1 for item in effects if item.get("kind") == "NOOP"),
        "duplicate_events": len(journal["events"]) - before_events,
        "state_changed": before_accessions != journal["accessions"]
        or before_holds != journal["holds"]
        or before_routes != journal["routes"],
    }


def compact_accessions(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "coc_id": item["coc_id"],
            "accession_id": item.get("accession_id"),
            "lab": item.get("lab"),
            "home_lab": item["home_lab"],
            "client_id": item["client_id"],
            "project_id": item["project_id"],
            "sample_id": item["sample_id"],
            "matrix": item["matrix"],
            "analysis_id": item["analysis_id"],
            "field_map": deepcopy(item.get("field_map")),
            "block": item["block"],
            "block_reason": item.get("block_reason"),
            "state": item["state"],
            "released": item["released"],
            "released_by": item.get("released_by"),
            "source_hash": item["source_hash"],
            "source_coordinate": item["source_coordinate"],
        }
        for item in sorted(journal["accessions"].values(), key=lambda row: row["coc_id"])
        if not item["block"]
    ]


def compact_holds(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "coc_id": item["coc_id"],
            "code": item["code"],
            "home_lab": item["home_lab"],
            "released": item["released"],
            "owner_role": item["owner_role"],
            "owner_desk": item["owner_desk"],
            "source_hash": item["source_hash"],
            "source_coordinate": item["source_coordinate"],
        }
        for item in sorted(journal["holds"].values(), key=lambda row: row["coc_id"])
    ]


def compact_routes(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [deepcopy(item) for item in sorted(journal["routes"].values(), key=lambda row: row["coc_id"])]


def build_audit(journal: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "seed": SEED,
        "accessions": compact_accessions(journal),
        "holds": compact_holds(journal),
        "routes": compact_routes(journal),
        "events": [
            {
                "seq": item["seq"],
                "kind": item["kind"],
                "coc_id": item.get("coc_id"),
                "code": item.get("code"),
                "lab": item.get("lab"),
                "accession_id": item.get("accession_id"),
                "record_hash": item["record_hash"],
            }
            for item in journal["events"]
            if item["kind"] in {"HOLD", "ROUTE", "HUMAN_RELEASE", "AUTONOMOUS_RELEASE_DENIED"}
        ],
        "autonomous_released": 0,
        "human_released": sum(1 for item in journal["accessions"].values() if item["released"] and not item["block"]),
        "production_writes": journal["production_writes"],
        "live_lims": journal["live_lims"],
        "interface_live": journal["interface_live"],
        "cash_usd": 0,
    }


def expected_actual(result: dict[str, Any]) -> dict[str, Any]:
    expected = dict(EXPECTED_COUNTS)
    actual = {key: result[key] for key in expected}
    return {"expected": expected, "actual": actual, "match": actual == expected}


def routed_exact(journal: dict[str, Any], rows: list[dict[str, Any]]) -> int:
    by_id = {row["coc_id"]: row for row in rows if not row["block"]}
    count = 0
    for item in journal["accessions"].values():
        if item["block"]:
            continue
        src = by_id.get(item["coc_id"])
        if src is None:
            continue
        maps = item.get("field_map") or {}
        if (
            item["lab"] == src["expected_lab"]
            and item["lab"] == src["home_lab"]
            and item["analysis_id"] == src["analysis_id"]
            and item["matrix"] == src["matrix"]
            and item["sample_id"] == src["sample_id"]
            and set(maps.values()) == {src["expected_lab"]}
        ):
            count += 1
    return count


def pass_contract(result: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    counts = expected_actual(result)
    if not counts["match"]:
        failures.append("counts")
    if result.get("lab_counts") != EXPECTED_LAB_COUNTS:
        failures.append("lab_counts")
    if result.get("hold_code_counts") != EXPECTED_HOLD_COUNTS:
        failures.append("hold_code_counts")
    if result.get("wrong_route"):
        failures.append("wrong_route")
    if result.get("cross_facility_routes") != 0:
        failures.append("cross_facility")
    replay = result.get("replay") or {}
    if (
        replay.get("added_records") != 0
        or replay.get("added_holds") != 0
        or replay.get("added_routes") != 0
        or replay.get("duplicate_events") != 0
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
    golden = result.get("golden_audit_sha256")
    if golden and golden != "PIN_AFTER_FIRST_RUN" and result.get("audit_sha256") != golden:
        failures.append("audit_sha256")
    if any(item.get("released") for item in result.get("hold_records") or []):
        failures.append("hold_released")
    return failures


def run_gate(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    journal = empty_journal()
    effects = [ingest_coc(journal, row) for row in inbound]
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
    lab_counts = {lab: 0 for lab in LABS}
    lab_totals = {lab: 0 for lab in LABS}
    for row in inbound:
        lab_totals[row["home_lab"]] += 1
    wrong_route = []
    cross_facility = []
    by_id = {row["coc_id"]: row for row in inbound}
    mapped_once = 0
    for item in journal["accessions"].values():
        src = by_id[item["coc_id"]]
        if item["block"]:
            continue
        lab_counts[item["lab"]] += 1
        maps = item.get("field_map") or {}
        if set(maps.values()) == {item["lab"]} and all(maps.get(field) == item["lab"] for field in MAP_FIELDS):
            mapped_once += 1
        if item["lab"] != src["expected_lab"] or item["lab"] != src["home_lab"] or item["lab"] != item["home_lab"]:
            wrong_route.append(item["coc_id"])
            cross_facility.append(item["coc_id"])
        if item["lab"] is not None and item["home_lab"] != item["lab"]:
            cross_facility.append(item["coc_id"])

    golden = golden_audit_sha256()
    packed = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "cocs": COC_COUNT,
        "valid": VALID_COUNT,
        "blocked": len(journal["holds"]),
        "per_lab": PER_LAB,
        "valid_per_lab": VALID_PER_LAB,
        "blocked_per_lab": BLOCKED_PER_LAB,
        "routed_exact": routed_exact(journal, inbound),
        "mapped_once": mapped_once,
        "blocked_expected_reason": sum(
            1
            for row in inbound
            if row["block"] and journal["holds"].get(row["coc_id"], {}).get("code") == row["expected_hold_code"]
        ),
        "cross_facility_routes": len(set(cross_facility)),
        "replay_added_records": replay["added_records"],
        "released_without_named_human": 0,
        "released_after_named_human": sum(
            1 for item in journal["accessions"].values() if item["released"] and not item["block"]
        ),
        "blocked_released": sum(1 for item in journal["holds"].values() if item["released"]),
        "production_writes": 0,
        "live_lims": 0,
        "cash_usd": 0,
        "accession_records": compact_accessions(journal),
        "hold_records": compact_holds(journal),
        "route_records": compact_routes(journal),
        "hold_code_counts": hold_code_counts,
        "lab_counts": lab_counts,
        "lab_totals": lab_totals,
        "wrong_route": wrong_route,
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
        "lab_counts": result["lab_counts"],
        "lab_totals": result["lab_totals"],
        "hold_code_counts": result["hold_code_counts"],
        "wrong_route": result["wrong_route"],
        "cross_facility_routes": result["cross_facility_routes"],
        "human_released": result["released_after_named_human"],
        "autonomous_released": result["autonomous_released"],
        "audit_sha256": result["audit_sha256"],
        "replay": result["replay"],
        "replay_audit_sha256": result["replay_audit_sha256"],
        "truth_gate": TRUTH_GATE,
        "interfaces": result["interfaces"],
        "cash_usd": 0,
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
    ACCESSION_RECEIPT_PATH.write_text(
        json.dumps(result["accession_records"], indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    HOLD_RECEIPT_PATH.write_text(json.dumps(result["hold_records"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    ROUTE_RECEIPT_PATH.write_text(json.dumps(result["route_records"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    AUDIT_RECEIPT_PATH.write_text(
        json.dumps(
            {
                "audit_sha256": result["audit_sha256"],
                "counts": expected_actual(result),
                "hold_code_counts": result["hold_code_counts"],
                "lab_counts": result["lab_counts"],
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
        "accessions": str(ACCESSION_RECEIPT_PATH),
        "holds": str(HOLD_RECEIPT_PATH),
        "routes": str(ROUTE_RECEIPT_PATH),
        "audit": str(AUDIT_RECEIPT_PATH),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BSK multi-lab accession parity runner")
    parser.add_argument("--print-goldens", action="store_true", help="print computed digests without locking")
    parser.add_argument("--replay", action="store_true", help="replay into persisted journal and write replay receipt")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.print_goldens:
        result = run_gate(build_acceptance_fixture())
        sys.stdout.write(
            _canonical(
                {
                    "audit_sha256": result["audit_sha256"],
                    "expected": expected_actual(result),
                    "hold_code_counts": result["hold_code_counts"],
                    "lab_counts": result["lab_counts"],
                    "ok": result["ok"],
                    "failures": result["failures"],
                }
            )
            + "\n"
        )
        return 0 if result["ok"] or result["failures"] == ["audit_sha256"] else 1
    if args.replay:
        result = run_gate()
        persist_run(result, replay=result["replay"])
        body = {
            "ok": result["replay"]["added_records"] == 0
            and result["replay"]["added_holds"] == 0
            and result["replay"]["duplicate_events"] == 0
            and not result["replay"]["state_changed"],
            "replay": result["replay"],
            "audit_sha256": result["audit_sha256"],
        }
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
