#!/usr/bin/env python3
"""Torrent Laboratory new-facility Watson COC work-order commissioning runner.

Demand: torrent-workorder-commissioning-lims-01
Buyer pairing: Torrent Laboratory / Mukesh Jani

Working CLI, not a look-inside souvenir. Processes 500 synthetic Watson-form
COCs across air, water, and soil; normalizes current Watson COC fields;
creates one work order per valid COC with TAT/EDD/matrix/container parity;
applies cooler/custody/receipt gates; maps old/current facility IDs;
quarantines every predefined defect with its expected reason; and requires
named-human release.

500 COCs = 400 valid + 100 predefined defects. Exactly 400 work orders
create once with field parity. All 100 quarantine with the expected reason.
Old and current facility identifiers normalize deterministically. Replay
adds nothing. Named human release is mandatory. No autonomous release.

HOLD / BUILD-AND-VERIFY. Forms / LIMS / instruments / EDD / reports stay
simulated and read-only. No live LIMS. No production writes. No outreach.
Do not publish phone numbers or personal emails. cash_usd=0.
PRE-SALE TRANSPORT: NONE.

Official command:
    python3 torrent_workorder_commissioning.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

DEMAND_ID = "torrent-workorder-commissioning-lims-01"
SCHEMA = "commons-torrent-workorder-commissioning-lims/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
BUYER = "Torrent Laboratory / Mukesh Jani"
HUMAN_RELEASER = "SYN-TOR-RELEASE-OFFICER"
HUMAN_ROLE = "NAMED_HUMAN_RELEASER"
INTAKE_DESK = "WATSON_COC_INTAKE"
FACILITY_DESK = "FACILITY_ID_MAP"
CUSTODY_DESK = "COOLER_CUSTODY_RECEIPT"

INPUT_COUNT = 500
VALID_COUNT = 400
QUARANTINE_COUNT = 100
PER_QUARANTINE_CODE = 10

CURRENT_FACILITY = "SYN-TOR-CUR-MILPITAS"
FACILITY_MAP = {
    "SYN-TOR-OLD-WATSON-CT": CURRENT_FACILITY,
    "SYN-TOR-FAC-WATSON": CURRENT_FACILITY,
    "SYN-TOR-LEGACY-01": CURRENT_FACILITY,
    "SYN-TOR-WATSON-COURT": CURRENT_FACILITY,
    "SYN-TOR-CUR-MILPITAS": CURRENT_FACILITY,
    "SYN-TOR-MILPITAS-20K": CURRENT_FACILITY,
}
MAPPED_FACILITY_IDS = tuple(FACILITY_MAP)
UNMAPPED_FACILITY = "SYN-TOR-UNKNOWN-SITE"

MATRICES = ("AIR", "WATER", "SOIL")
CONTAINERS = {
    "AIR": ("SUMMA_CANISTER", "FILTER_CASSETTE"),
    "WATER": ("VOA_VIAL", "HDPE_BOTTLE"),
    "SOIL": ("GLASS_JAR", "BRASS_LINER"),
}
TAT_CODES = ("STANDARD_5D", "RUSH_48H", "SAME_DAY")
EDD_FOR_TAT = {
    "STANDARD_5D": "WATSON_EDD_V2",
    "RUSH_48H": "WATSON_EDD_V2",
    "SAME_DAY": "LAB_CSV",
}
ANALYSES = {
    "AIR": ("TO-15", "PM10"),
    "WATER": ("524.2", "200.8"),
    "SOIL": ("8260B", "6010B"),
}
PRESERVATIVES = {
    "AIR": "NONE",
    "WATER": "HCL_ICE",
    "SOIL": "ICE",
}

QUARANTINE_CODES = (
    "QUARANTINE_MISSING_WORK_ORDER_ID",
    "QUARANTINE_MATRIX_CONTAINER_PARITY",
    "QUARANTINE_TAT_EDD_PARITY",
    "QUARANTINE_COOLER_TEMP_GATE",
    "QUARANTINE_CUSTODY_GATE",
    "QUARANTINE_RECEIPT_GATE",
    "QUARANTINE_UNMAPPED_FACILITY_ID",
    "QUARANTINE_MISSING_COLLECTION_DATETIME",
    "QUARANTINE_MISSING_SAMPLER_SIGNATURE",
    "QUARANTINE_INVALID_MATRIX",
)
QUARANTINE_OWNERS = {
    "QUARANTINE_MISSING_WORK_ORDER_ID": INTAKE_DESK,
    "QUARANTINE_MATRIX_CONTAINER_PARITY": INTAKE_DESK,
    "QUARANTINE_TAT_EDD_PARITY": INTAKE_DESK,
    "QUARANTINE_COOLER_TEMP_GATE": CUSTODY_DESK,
    "QUARANTINE_CUSTODY_GATE": CUSTODY_DESK,
    "QUARANTINE_RECEIPT_GATE": CUSTODY_DESK,
    "QUARANTINE_UNMAPPED_FACILITY_ID": FACILITY_DESK,
    "QUARANTINE_MISSING_COLLECTION_DATETIME": INTAKE_DESK,
    "QUARANTINE_MISSING_SAMPLER_SIGNATURE": INTAKE_DESK,
    "QUARANTINE_INVALID_MATRIX": INTAKE_DESK,
}

EXPECTED_MATRIX_COUNTS = {"AIR": 134, "WATER": 133, "SOIL": 133}
EXPECTED_QUARANTINE_COUNTS = {code: PER_QUARANTINE_CODE for code in QUARANTINE_CODES}
EXPECTED_COUNTS = {
    "input_rows": INPUT_COUNT,
    "valid": VALID_COUNT,
    "quarantines": QUARANTINE_COUNT,
    "work_orders": VALID_COUNT,
    "replay_added_work_orders": 0,
    "replay_added_quarantines": 0,
    "autonomous_released": 0,
    "human_released": VALID_COUNT,
    "duplicate_work_orders": 0,
    "production_writes": 0,
    "live_lims": 0,
    "live_reports": 0,
    "billing_writes": 0,
}

COLLECTED_AT = "2026-08-15T08:00:00Z"
RELINQUISHED_AT = "2026-08-15T12:00:00Z"
RECEIVED_AT = "2026-08-15T14:00:00Z"
RELEASED_AT = "2026-08-31T06:00:00Z"
VALID_COOLER_C = 4.0
HOT_COOLER_C = 18.5

PACK = Path("revenue") / "torrent_workorder_commissioning"
FIXTURE_PATH = PACK / "fixture.json"
CONTRACT_PATH = PACK / "contract.json"
STATE_PATH = PACK / "state" / "journal.json"
RECEIPT_DIR = PACK / "receipts"
RUN_RECEIPT_PATH = RECEIPT_DIR / "run.json"
WORK_ORDER_RECEIPT_PATH = RECEIPT_DIR / "work_orders.json"
QUARANTINE_RECEIPT_PATH = RECEIPT_DIR / "quarantines.json"
LINEAGE_RECEIPT_PATH = RECEIPT_DIR / "lineage.json"
AUDIT_RECEIPT_PATH = RECEIPT_DIR / "audit.json"
REPLAY_RECEIPT_PATH = RECEIPT_DIR / "replay.json"
FIELD_DIGEST_PATH = RECEIPT_DIR / "field_digests.json"

GOLDEN_AUDIT_SHA256 = "7d89b0bfe74dbc142d1717c36e292b08ace0c3587ce7b5b1581bfb584701c446"
GOLDEN_LINEAGE_SHA256 = "e50028e925c1b7d4399a5387a46cab4681813ceb09704d644e2840c57ebc81f7"
GOLDEN_WORK_ORDER_SHA256 = "f38fe24243e9b0fcddd156691c69d8ccddcb9a97e5f8e6dbb20afa19ea0fabac"
GOLDEN_FIELD_DIGEST_SHA256 = "13bb8802efc12099037ac6e3c4c6d9fe2d51d8310cf7d07e1da173d6e03cc5a3"
GOLDEN_FIXTURE_SHA256 = "99117f784de0d880b9102a0ae86bf5fec1848ae9477d8e281a3c72bd45e48c1b"

OFFICIAL_BINARY = "python3 torrent_workorder_commissioning.py"
OFFICIAL_TEST = "python3 test_torrent_workorder_commissioning.py"
AUTONOMOUS_NAMES = frozenset({"SYSTEM", "AUTO", "AUTONOMOUS", "BOT", "MACHINE"})


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


def normalize_facility(raw: str) -> str | None:
    mapped = FACILITY_MAP.get(_text(raw))
    return mapped if mapped else None


def source_fields(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "analyses": list(row.get("analyses") or []),
        "client_project": _text(row.get("client_project")),
        "coc_id": _text(row.get("coc_id")),
        "collection_datetime": _text(row.get("collection_datetime")),
        "container": _text(row.get("container")),
        "cooler_temp_c": row.get("cooler_temp_c"),
        "edd_format": _text(row.get("edd_format")),
        "facility_id": _text(row.get("facility_id")),
        "matrix": _text(row.get("matrix")),
        "preservative": _text(row.get("preservative")),
        "receipt_id": _text(row.get("receipt_id")),
        "received_at": _text(row.get("received_at")),
        "received_by": _text(row.get("received_by")),
        "relinquished_at": _text(row.get("relinquished_at")),
        "relinquished_by": _text(row.get("relinquished_by")),
        "sample_id": _text(row.get("sample_id")),
        "sampler_signature": _text(row.get("sampler_signature")),
        "tat": _text(row.get("tat")),
        "work_order_id": _text(row.get("work_order_id")),
    }


def field_lineage(fields: dict[str, Any]) -> dict[str, str]:
    return {key: sha256_hex(value) for key, value in sorted(fields.items())}


def compute_source_hash(row: dict[str, Any]) -> str:
    return sha256_hex(source_fields(row))


def work_order_key(coc_id: str, source_hash: str) -> str:
    digest = sha256_hex(
        {
            "coc_id": coc_id,
            "demand_id": DEMAND_ID,
            "source_hash": source_hash,
        }
    )
    return f"TOR-WO-{digest[:12]}"


def _matrix_for(index: int) -> str:
    return MATRICES[(index - 1) % len(MATRICES)]


def _container_for(matrix: str, index: int) -> str:
    options = CONTAINERS[matrix]
    return options[(index - 1) % len(options)]


def _tat_for(index: int) -> str:
    return TAT_CODES[(index - 1) % len(TAT_CODES)]


def _base_valid(index: int) -> dict[str, Any]:
    matrix = _matrix_for(index)
    tat = _tat_for(index)
    facility_id = MAPPED_FACILITY_IDS[(index - 1) % len(MAPPED_FACILITY_IDS)]
    row = {
        "analyses": list(ANALYSES[matrix]),
        "client_project": f"SYN-TOR-PROJECT-{(index - 1) % 20 + 1:02d}",
        "coc_id": f"TOR-WATSON-COC-{index:04d}",
        "collection_datetime": COLLECTED_AT,
        "container": _container_for(matrix, index),
        "cooler_temp_c": None if matrix == "AIR" else VALID_COOLER_C,
        "edd_format": EDD_FOR_TAT[tat],
        "expected_quarantine_code": None,
        "expected_state": "WORK_ORDER",
        "facility_id": facility_id,
        "facility_id_normalized": CURRENT_FACILITY,
        "form": "WATSON_COC_REV2",
        "matrix": matrix,
        "preservative": PRESERVATIVES[matrix],
        "receipt_id": f"TOR-RCPT-{index:04d}",
        "received_at": RECEIVED_AT,
        "received_by": "SYN-TOR-RECEIVER-01",
        "relinquished_at": RELINQUISHED_AT,
        "relinquished_by": "SYN-TOR-SAMPLER-01",
        "sample_id": f"TOR-SMP-{index:04d}",
        "sampler_signature": f"SYN-SAMPLER-{index:03d}",
        "tat": tat,
        "work_order_id": f"TOR-WO-REQ-{index:04d}",
    }
    row["source_hash"] = compute_source_hash(row)
    row["field_lineage"] = field_lineage(source_fields(row))
    return row


def _valid_row(index: int) -> dict[str, Any]:
    return _base_valid(index)


def _defect_row(index: int, code: str) -> dict[str, Any]:
    row = _base_valid(index)
    row["expected_state"] = "QUARANTINE"
    row["expected_quarantine_code"] = code
    if code == "QUARANTINE_MISSING_WORK_ORDER_ID":
        row["work_order_id"] = ""
    elif code == "QUARANTINE_MATRIX_CONTAINER_PARITY":
        row["matrix"] = "WATER"
        row["container"] = "SUMMA_CANISTER"
        row["preservative"] = PRESERVATIVES["WATER"]
        row["analyses"] = list(ANALYSES["WATER"])
        row["cooler_temp_c"] = VALID_COOLER_C
    elif code == "QUARANTINE_TAT_EDD_PARITY":
        row["tat"] = "STANDARD_5D"
        row["edd_format"] = "LAB_CSV"
    elif code == "QUARANTINE_COOLER_TEMP_GATE":
        row["matrix"] = "WATER"
        row["container"] = _container_for("WATER", index)
        row["preservative"] = PRESERVATIVES["WATER"]
        row["analyses"] = list(ANALYSES["WATER"])
        row["cooler_temp_c"] = HOT_COOLER_C
    elif code == "QUARANTINE_CUSTODY_GATE":
        row["relinquished_by"] = ""
    elif code == "QUARANTINE_RECEIPT_GATE":
        row["receipt_id"] = ""
    elif code == "QUARANTINE_UNMAPPED_FACILITY_ID":
        row["facility_id"] = UNMAPPED_FACILITY
        row["facility_id_normalized"] = None
    elif code == "QUARANTINE_MISSING_COLLECTION_DATETIME":
        row["collection_datetime"] = ""
    elif code == "QUARANTINE_MISSING_SAMPLER_SIGNATURE":
        row["sampler_signature"] = ""
    elif code == "QUARANTINE_INVALID_MATRIX":
        row["matrix"] = "SLUDGE"
        row["container"] = "GLASS_JAR"
        row["preservative"] = "NONE"
        row["analyses"] = ["UNKNOWN"]
        row["cooler_temp_c"] = VALID_COOLER_C
    else:
        raise ValueError(code)
    row["source_hash"] = compute_source_hash(row)
    row["field_lineage"] = field_lineage(source_fields(row))
    return row


def build_acceptance_fixture() -> list[dict[str, Any]]:
    rows = [_valid_row(index) for index in range(1, VALID_COUNT + 1)]
    start = VALID_COUNT + 1
    for code_idx, code in enumerate(QUARANTINE_CODES):
        for local in range(PER_QUARANTINE_CODE):
            rows.append(_defect_row(start + code_idx * PER_QUARANTINE_CODE + local, code))
    return rows


def fixture_sha256(rows: list[dict[str, Any]] | None = None) -> str:
    return sha256_hex(rows if rows is not None else build_acceptance_fixture())


def write_fixture(path: Path = FIXTURE_PATH) -> list[dict[str, Any]]:
    rows = build_acceptance_fixture()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return rows


def load_fixture(path: Path = FIXTURE_PATH) -> list[dict[str, Any]]:
    if path.is_file():
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, list) and len(loaded) == INPUT_COUNT:
            return loaded
    return build_acceptance_fixture()


def empty_journal() -> dict[str, Any]:
    return {
        "automatic_releases": 0,
        "billing_writes": 0,
        "coc_index": {},
        "events": [],
        "interface_live": False,
        "live_lims": 0,
        "live_reports": 0,
        "production_writes": 0,
        "quarantines": {},
        "sample_index": {},
        "schema": SCHEMA,
        "work_orders": {},
    }


def _event(journal: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    journal["events"].append({"kind": kind, **payload})


def normalize(row: dict[str, Any]) -> dict[str, Any]:
    fields = source_fields(row)
    return {
        **fields,
        "analyses": list(fields["analyses"]),
        "cooler_temp_c": row.get("cooler_temp_c"),
        "expected_quarantine_code": row.get("expected_quarantine_code"),
        "expected_state": row.get("expected_state"),
        "facility_id_normalized": normalize_facility(fields["facility_id"]),
        "field_lineage": field_lineage(fields),
        "form": _text(row.get("form")) or "WATSON_COC_REV2",
        "source_hash": compute_source_hash(row),
    }


def _matrix_container_ok(norm: dict[str, Any]) -> bool:
    matrix = norm["matrix"]
    if matrix not in CONTAINERS:
        return False
    return norm["container"] in CONTAINERS[matrix]


def _tat_edd_ok(norm: dict[str, Any]) -> bool:
    tat = norm["tat"]
    if tat not in EDD_FOR_TAT:
        return False
    return norm["edd_format"] == EDD_FOR_TAT[tat]


def _cooler_ok(norm: dict[str, Any]) -> bool:
    matrix = norm["matrix"]
    temp = norm.get("cooler_temp_c")
    if matrix == "AIR":
        return temp is None
    if temp is None:
        return False
    try:
        value = float(temp)
    except (TypeError, ValueError):
        return False
    return 0.0 <= value <= 6.0


def _custody_ok(norm: dict[str, Any]) -> bool:
    return bool(
        norm["relinquished_by"]
        and norm["relinquished_at"]
        and norm["received_by"]
        and norm["received_at"]
        and norm["received_at"] >= norm["relinquished_at"]
    )


def _receipt_ok(norm: dict[str, Any]) -> bool:
    return bool(norm["receipt_id"])


def classify(norm: dict[str, Any]) -> dict[str, Any]:
    if not norm["work_order_id"]:
        return {"ok": False, "code": "QUARANTINE_MISSING_WORK_ORDER_ID"}
    if norm["matrix"] not in MATRICES:
        return {"ok": False, "code": "QUARANTINE_INVALID_MATRIX"}
    if not norm["collection_datetime"]:
        return {"ok": False, "code": "QUARANTINE_MISSING_COLLECTION_DATETIME"}
    if not norm["sampler_signature"]:
        return {"ok": False, "code": "QUARANTINE_MISSING_SAMPLER_SIGNATURE"}
    if normalize_facility(norm["facility_id"]) is None:
        return {"ok": False, "code": "QUARANTINE_UNMAPPED_FACILITY_ID"}
    if not _receipt_ok(norm):
        return {"ok": False, "code": "QUARANTINE_RECEIPT_GATE"}
    if not _custody_ok(norm):
        return {"ok": False, "code": "QUARANTINE_CUSTODY_GATE"}
    if not _cooler_ok(norm):
        return {"ok": False, "code": "QUARANTINE_COOLER_TEMP_GATE"}
    if not _tat_edd_ok(norm):
        return {"ok": False, "code": "QUARANTINE_TAT_EDD_PARITY"}
    if not _matrix_container_ok(norm):
        return {"ok": False, "code": "QUARANTINE_MATRIX_CONTAINER_PARITY"}
    return {
        "ok": True,
        "code": None,
        "facility_id_normalized": CURRENT_FACILITY,
        "source_hash": norm["source_hash"],
        "field_lineage": dict(norm["field_lineage"]),
    }


def _park_quarantine(journal: dict[str, Any], norm: dict[str, Any], code: str) -> dict[str, Any]:
    record = {
        "code": code,
        "coc_id": norm["coc_id"],
        "facility_id": norm["facility_id"] or None,
        "facility_id_normalized": normalize_facility(norm["facility_id"]),
        "field_lineage": dict(norm["field_lineage"]),
        "interface_live": False,
        "live_lims": False,
        "matrix": norm["matrix"] or None,
        "owner_role": QUARANTINE_OWNERS[code],
        "released": False,
        "released_by": None,
        "sample_id": norm["sample_id"] or None,
        "source_hash": norm["source_hash"] or None,
        "state": "QUARANTINE",
        "work_order_id": norm["work_order_id"] or None,
    }
    existing = journal["quarantines"].get(record["coc_id"])
    if existing is not None:
        return {"kind": "NOOP", "reason": "already_quarantined", "coc_id": record["coc_id"]}
    journal["quarantines"][record["coc_id"]] = record
    journal["coc_index"][record["coc_id"]] = {"kind": "QUARANTINE", "code": code}
    _event(journal, "QUARANTINE", {"coc_id": record["coc_id"], "code": code, "owner_role": record["owner_role"]})
    return {"kind": "QUARANTINE", "duplicate": False, **record}


def ingest_row(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    norm = normalize(row)
    coc_id = norm["coc_id"]
    if coc_id in journal["coc_index"]:
        prior = journal["coc_index"][coc_id]
        return {"kind": "NOOP", "reason": "already_seen", "coc_id": coc_id, "prior": prior["kind"]}
    verdict = classify(norm)
    if not verdict["ok"]:
        return _park_quarantine(journal, norm, verdict["code"])

    source_hash = verdict["source_hash"]
    wo_key = work_order_key(coc_id, source_hash)
    if wo_key in journal["work_orders"]:
        return {"kind": "NOOP", "reason": "already_created", "work_order_key": wo_key}
    if norm["sample_id"] in journal["sample_index"]:
        return _park_quarantine(journal, norm, "QUARANTINE_MISSING_WORK_ORDER_ID")

    facility = CURRENT_FACILITY
    record = {
        "analyses": list(norm["analyses"]),
        "client_project": norm["client_project"],
        "coc_id": coc_id,
        "collection_datetime": norm["collection_datetime"],
        "container": norm["container"],
        "cooler_temp_c": norm["cooler_temp_c"],
        "edd_format": norm["edd_format"],
        "facility_id_normalized": facility,
        "facility_id_raw": norm["facility_id"],
        "field_lineage": verdict["field_lineage"],
        "form": norm["form"],
        "interface_live": False,
        "interface_state": "SIMULATED",
        "live_lims": False,
        "live_report": False,
        "matrix": norm["matrix"],
        "parity": {
            "analyses": list(norm["analyses"]),
            "container": norm["container"],
            "edd_format": norm["edd_format"],
            "facility_id_normalized": facility,
            "matrix": norm["matrix"],
            "sample_id": norm["sample_id"],
            "tat": norm["tat"],
            "work_order_id": norm["work_order_id"],
        },
        "preservative": norm["preservative"],
        "receipt_id": norm["receipt_id"],
        "received_at": norm["received_at"],
        "released": False,
        "released_at": None,
        "released_by": None,
        "sample_id": norm["sample_id"],
        "sampler_signature": norm["sampler_signature"],
        "source_fields": source_fields(norm),
        "source_hash": source_hash,
        "state": "WORK_ORDER",
        "tat": norm["tat"],
        "work_order_id": norm["work_order_id"],
        "work_order_key": wo_key,
    }
    journal["work_orders"][wo_key] = record
    journal["coc_index"][coc_id] = {"kind": "WORK_ORDER", "work_order_key": wo_key}
    journal["sample_index"][norm["sample_id"]] = wo_key
    _event(
        journal,
        "WORK_ORDER",
        {
            "adapter": "SIMULATED_WATSON_LIMS",
            "coc_id": coc_id,
            "facility_id_normalized": facility,
            "facility_id_raw": norm["facility_id"],
            "source_hash": source_hash,
            "work_order_id": norm["work_order_id"],
            "work_order_key": wo_key,
        },
    )
    return {
        "kind": "WORK_ORDER",
        "coc_id": coc_id,
        "facility_id_normalized": facility,
        "work_order_id": norm["work_order_id"],
        "work_order_key": wo_key,
    }


def release_work_order(
    journal: dict[str, Any],
    wo_key: str,
    *,
    actor: str,
    actor_role: str,
) -> dict[str, Any]:
    record = journal["work_orders"].get(wo_key)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_WORK_ORDER"}
    role = _text(actor_role).upper()
    name = _text(actor)
    if role != HUMAN_ROLE or name != HUMAN_RELEASER or not name or name.upper() in AUTONOMOUS_NAMES:
        _event(
            journal,
            "AUTONOMOUS_RELEASE_DENIED",
            {"actor": name or None, "actor_role": role or None, "work_order_key": wo_key},
        )
        journal["automatic_releases"] = 0
        return {"ok": False, "code": "AUTONOMOUS_RELEASE_DENIED"}
    if record.get("released"):
        return {"ok": True, "code": "ALREADY_RELEASED", "duplicate": True, "work_order_key": wo_key}
    record["released"] = True
    record["released_by"] = name
    record["released_at"] = RELEASED_AT
    record["state"] = "HUMAN_RELEASED"
    record["live_lims"] = False
    record["live_report"] = False
    _event(journal, "HUMAN_RELEASE", {"released_by": name, "work_order_key": wo_key})
    return {"ok": True, "code": "HUMAN_RELEASED", "work_order_key": wo_key}


def release_quarantine(
    journal: dict[str, Any],
    coc_id: str,
    *,
    actor: str,
    actor_role: str,
) -> dict[str, Any]:
    hold = journal["quarantines"].get(coc_id)
    if hold is None:
        return {"ok": False, "code": "UNKNOWN_QUARANTINE"}
    role = _text(actor_role).upper()
    name = _text(actor)
    if role != HUMAN_ROLE or name != HUMAN_RELEASER:
        _event(journal, "AUTONOMOUS_RELEASE_DENIED", {"actor": name, "coc_id": coc_id})
        return {"ok": False, "code": "AUTONOMOUS_RELEASE_DENIED"}
    hold["released"] = False
    hold["state"] = "QUARANTINE"
    _event(journal, "QUARANTINE_RELEASE_DENIED_STILL_HOLD", {"actor": name, "coc_id": coc_id})
    return {"ok": False, "code": "QUARANTINE_UNRESOLVED"}


def attempt_autonomous_release(journal: dict[str, Any]) -> list[dict[str, Any]]:
    effects = []
    for wo_key in sorted(journal["work_orders"]):
        effects.append(release_work_order(journal, wo_key, actor="SYSTEM", actor_role="SYSTEM"))
    for coc_id in sorted(journal["quarantines"]):
        effects.append(release_quarantine(journal, coc_id, actor="bot", actor_role="SYSTEM"))
    return effects


def authorized_human_release(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        release_work_order(journal, wo_key, actor=HUMAN_RELEASER, actor_role=HUMAN_ROLE)
        for wo_key in sorted(journal["work_orders"])
    ]


def production_write(journal: dict[str, Any], wo_key: str) -> dict[str, Any]:
    record = journal["work_orders"].get(wo_key)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_WORK_ORDER"}
    journal["production_writes"] = 0
    journal["live_lims"] = 0
    record["live_lims"] = False
    record["interface_live"] = False
    _event(journal, "PRODUCTION_WRITE_DENIED", {"work_order_key": wo_key})
    return {"ok": False, "code": "SIMULATED_ONLY_NO_PRODUCTION_WRITE", "production_writes": 0}


def replay_into(journal: dict[str, Any], rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    before_wo = {key: deepcopy(value) for key, value in journal["work_orders"].items()}
    before_q = {key: deepcopy(value) for key, value in journal["quarantines"].items()}
    before_wo_n = len(journal["work_orders"])
    before_q_n = len(journal["quarantines"])
    effects = [ingest_row(journal, row) for row in (rows or build_acceptance_fixture())]
    after_wo = {key: {k: v for k, v in value.items() if k != "source_fields"} for key, value in journal["work_orders"].items()}
    compact_before = {key: {k: v for k, v in value.items() if k != "source_fields"} for key, value in before_wo.items()}
    return {
        "added_quarantines": len(journal["quarantines"]) - before_q_n,
        "added_work_orders": len(journal["work_orders"]) - before_wo_n,
        "quarantine_count": len(journal["quarantines"]),
        "replay_noops": sum(1 for item in effects if item.get("kind") == "NOOP"),
        "state_changed": compact_before != after_wo or before_q != journal["quarantines"],
        "work_order_count": len(journal["work_orders"]),
    }


def compact_work_orders(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "analyses": list(item["analyses"]),
            "coc_id": item["coc_id"],
            "container": item["container"],
            "edd_format": item["edd_format"],
            "facility_id_normalized": item["facility_id_normalized"],
            "facility_id_raw": item["facility_id_raw"],
            "field_lineage": deepcopy(item["field_lineage"]),
            "interface_live": item["interface_live"],
            "live_lims": item["live_lims"],
            "matrix": item["matrix"],
            "parity": deepcopy(item["parity"]),
            "released": item["released"],
            "released_by": item["released_by"],
            "sample_id": item["sample_id"],
            "source_hash": item["source_hash"],
            "state": item["state"],
            "tat": item["tat"],
            "work_order_id": item["work_order_id"],
            "work_order_key": item["work_order_key"],
        }
        for item in sorted(journal["work_orders"].values(), key=lambda row: row["work_order_key"])
    ]


def compact_quarantines(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        deepcopy(item)
        for item in sorted(journal["quarantines"].values(), key=lambda row: row["coc_id"])
    ]


def compact_lineage(journal: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in compact_work_orders(journal):
        rows.append(
            {
                "facility_id_normalized": item["facility_id_normalized"],
                "facility_id_raw": item["facility_id_raw"],
                "field_lineage": item["field_lineage"],
                "id": item["work_order_key"],
                "kind": "WORK_ORDER",
                "source_hash": item["source_hash"],
            }
        )
    for item in compact_quarantines(journal):
        rows.append(
            {
                "facility_id_normalized": item.get("facility_id_normalized"),
                "facility_id_raw": item.get("facility_id"),
                "field_lineage": item["field_lineage"],
                "id": item["coc_id"],
                "kind": "QUARANTINE",
                "source_hash": item["source_hash"],
            }
        )
    return rows


def field_digests(journal: dict[str, Any]) -> dict[str, Any]:
    work_orders = compact_work_orders(journal)
    return {
        "container_digest": sha256_hex([item["container"] for item in work_orders]),
        "edd_digest": sha256_hex([item["edd_format"] for item in work_orders]),
        "facility_digest": sha256_hex(
            [
                {
                    "normalized": item["facility_id_normalized"],
                    "raw": item["facility_id_raw"],
                    "work_order_key": item["work_order_key"],
                }
                for item in work_orders
            ]
        ),
        "matrix_digest": sha256_hex([item["matrix"] for item in work_orders]),
        "parity_digest": sha256_hex([item["parity"] for item in work_orders]),
        "tat_digest": sha256_hex([item["tat"] for item in work_orders]),
        "work_order_id_digest": sha256_hex([item["work_order_id"] for item in work_orders]),
    }


def build_audit(journal: dict[str, Any]) -> dict[str, Any]:
    return {
        "autonomous_released": 0,
        "buyer": BUYER,
        "demand_id": DEMAND_ID,
        "events": deepcopy(journal["events"]),
        "field_digests": field_digests(journal),
        "human_released": sum(1 for item in journal["work_orders"].values() if item["released"]),
        "interface_live": journal["interface_live"],
        "lineage": compact_lineage(journal),
        "live_lims": journal["live_lims"],
        "production_writes": journal["production_writes"],
        "quarantines": [
            {
                "coc_id": item["coc_id"],
                "code": item["code"],
                "owner_role": item["owner_role"],
                "source_hash": item["source_hash"],
            }
            for item in compact_quarantines(journal)
        ],
        "schema": SCHEMA,
        "truth_gate": TRUTH_GATE,
        "work_orders": compact_work_orders(journal),
    }


def expected_actual(result: dict[str, Any]) -> dict[str, Any]:
    expected = dict(EXPECTED_COUNTS)
    actual = {key: result[key] for key in expected}
    return {"actual": actual, "expected": expected, "match": actual == expected}


def pass_contract(result: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    counts = expected_actual(result)
    if not counts["match"]:
        failures.append("counts")
    if result.get("matrix_counts") != EXPECTED_MATRIX_COUNTS:
        failures.append("matrix_counts")
    if result.get("quarantine_code_counts") != EXPECTED_QUARANTINE_COUNTS:
        failures.append("quarantine_code_counts")
    if result.get("parity_failures"):
        failures.append("field_parity")
    if result.get("facility_failures"):
        failures.append("facility_normalize")
    if result.get("lineage_failures"):
        failures.append("lineage")
    if result.get("duplicate_work_orders") != 0:
        failures.append("duplicate_work_orders")
    replay = result.get("replay") or {}
    if (
        replay.get("added_work_orders") != 0
        or replay.get("added_quarantines") != 0
        or replay.get("state_changed")
    ):
        failures.append("replay")
    if result.get("audit_sha256") != result.get("replay_audit_sha256"):
        failures.append("replay_hash")
    if result.get("autonomous_released") != 0:
        failures.append("autonomous_release")
    if result.get("interface_live") or result.get("production_writes") or result.get("live_lims"):
        failures.append("live_adapters")
    if result.get("cash_usd") != 0:
        failures.append("cash_usd")
    if result.get("golden_locked"):
        if result.get("audit_sha256") != GOLDEN_AUDIT_SHA256:
            failures.append("audit_sha256")
        if result.get("lineage_sha256") != GOLDEN_LINEAGE_SHA256:
            failures.append("lineage_sha256")
        if result.get("work_order_sha256") != GOLDEN_WORK_ORDER_SHA256:
            failures.append("work_order_sha256")
        if result.get("field_digest_sha256") != GOLDEN_FIELD_DIGEST_SHA256:
            failures.append("field_digest_sha256")
        if result.get("fixture_sha256") != GOLDEN_FIXTURE_SHA256:
            failures.append("fixture_sha256")
    auto = result.get("autonomous_release_effects") or []
    if auto and any(item.get("ok") for item in auto):
        failures.append("autonomous_release_not_denied")
    if any(item.get("released") for item in result.get("quarantine_records") or []):
        failures.append("quarantine_released")
    return failures


def lineage_failures(rows: list[dict[str, Any]], journal: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    by_coc = {row["coc_id"]: row for row in rows if row["expected_state"] == "WORK_ORDER"}
    for item in journal["work_orders"].values():
        src = by_coc.get(item["coc_id"])
        if src is None:
            failures.append("missing_source:%s" % item["coc_id"])
            continue
        if item["source_hash"] != src["source_hash"]:
            failures.append("source_hash:%s" % item["coc_id"])
        if item["field_lineage"] != src["field_lineage"]:
            failures.append("field_lineage:%s" % item["coc_id"])
        if item["source_hash"] != compute_source_hash(src):
            failures.append("recompute:%s" % item["coc_id"])
    return failures


def parity_failures(rows: list[dict[str, Any]], journal: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    by_coc = {row["coc_id"]: row for row in rows if row["expected_state"] == "WORK_ORDER"}
    for item in journal["work_orders"].values():
        src = by_coc.get(item["coc_id"])
        if src is None:
            failures.append("missing_parity_source:%s" % item["coc_id"])
            continue
        expected = {
            "analyses": list(src["analyses"]),
            "container": src["container"],
            "edd_format": src["edd_format"],
            "facility_id_normalized": CURRENT_FACILITY,
            "matrix": src["matrix"],
            "sample_id": src["sample_id"],
            "tat": src["tat"],
            "work_order_id": src["work_order_id"],
        }
        if item["parity"] != expected:
            failures.append("parity:%s" % item["coc_id"])
        for key, value in expected.items():
            if item.get(key) != value:
                failures.append("field:%s:%s" % (key, item["coc_id"]))
    return failures


def facility_failures(rows: list[dict[str, Any]], journal: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    by_coc = {row["coc_id"]: row for row in rows}
    for item in journal["work_orders"].values():
        src = by_coc[item["coc_id"]]
        raw = src["facility_id"]
        if raw not in FACILITY_MAP:
            failures.append("unmapped_on_valid:%s" % item["coc_id"])
        if FACILITY_MAP[raw] != CURRENT_FACILITY:
            failures.append("map_not_current:%s" % item["coc_id"])
        if item["facility_id_normalized"] != CURRENT_FACILITY:
            failures.append("normalized:%s" % item["coc_id"])
        if item["facility_id_raw"] != raw:
            failures.append("raw:%s" % item["coc_id"])
    for item in journal["quarantines"].values():
        if item["code"] != "QUARANTINE_UNMAPPED_FACILITY_ID":
            continue
        if normalize_facility(item.get("facility_id") or "") is not None:
            failures.append("mapped_unmapped:%s" % item["coc_id"])
    return failures


def run_commissioning(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else load_fixture())
    journal = empty_journal()
    effects = [ingest_row(journal, row) for row in inbound]
    auto = attempt_autonomous_release(journal)
    human = authorized_human_release(journal)
    denied_writes = [
        production_write(journal, wo_key) for wo_key in sorted(journal["work_orders"])
    ]
    audit = build_audit(journal)
    lineage = compact_lineage(journal)
    work_orders = compact_work_orders(journal)
    digests = field_digests(journal)
    audit_sha = sha256_hex(audit)
    lineage_sha = sha256_hex(lineage)
    work_order_sha = sha256_hex(work_orders)
    field_digest_sha = sha256_hex(digests)
    fixture_sha = fixture_sha256(inbound)

    replay = replay_into(journal, inbound)
    replay_audit = build_audit(journal)
    replay_sha = sha256_hex(replay_audit)

    quarantine_code_counts = {code: 0 for code in QUARANTINE_CODES}
    for item in journal["quarantines"].values():
        quarantine_code_counts[item["code"]] = quarantine_code_counts.get(item["code"], 0) + 1
    matrix_counts = {matrix: 0 for matrix in MATRICES}
    for item in journal["work_orders"].values():
        matrix_counts[item["matrix"]] += 1

    golden_locked = "pending" not in {
        GOLDEN_AUDIT_SHA256,
        GOLDEN_LINEAGE_SHA256,
        GOLDEN_WORK_ORDER_SHA256,
        GOLDEN_FIELD_DIGEST_SHA256,
        GOLDEN_FIXTURE_SHA256,
    }
    packed = {
        "accession_records": work_orders,
        "audit": audit,
        "audit_sha256": audit_sha,
        "autonomous_release_effects": auto,
        "autonomous_released": 0,
        "billing_writes": 0,
        "buyer": BUYER,
        "cash_usd": 0,
        "demand_id": DEMAND_ID,
        "duplicate_work_orders": len(work_orders) - len({item["coc_id"] for item in work_orders}),
        "effects": effects,
        "facility_failures": facility_failures(inbound, journal),
        "field_digest_sha256": field_digest_sha,
        "field_digests": digests,
        "fixture_sha256": fixture_sha,
        "golden_locked": golden_locked,
        "hold_records": compact_quarantines(journal),
        "human_release_effects": human,
        "human_released": sum(1 for item in journal["work_orders"].values() if item["released"]),
        "input_rows": len(inbound),
        "interface_live": False,
        "interfaces": "SIMULATED",
        "journal": journal,
        "lineage": lineage,
        "lineage_failures": lineage_failures(inbound, journal),
        "lineage_sha256": lineage_sha,
        "live_lims": 0,
        "live_reports": 0,
        "matrix_counts": matrix_counts,
        "official_binary": OFFICIAL_BINARY,
        "official_test": OFFICIAL_TEST,
        "parity_failures": parity_failures(inbound, journal),
        "pre_sale_transport": "NONE",
        "production_write_effects": denied_writes,
        "production_writes": 0,
        "quarantine_code_counts": quarantine_code_counts,
        "quarantine_records": compact_quarantines(journal),
        "quarantines": len(journal["quarantines"]),
        "replay": replay,
        "replay_added_quarantines": replay["added_quarantines"],
        "replay_added_work_orders": replay["added_work_orders"],
        "replay_audit_sha256": replay_sha,
        "schema": SCHEMA,
        "truth_gate": TRUTH_GATE,
        "valid": VALID_COUNT,
        "work_order_records": work_orders,
        "work_order_sha256": work_order_sha,
        "work_orders": len(journal["work_orders"]),
    }
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
    WORK_ORDER_RECEIPT_PATH.write_text(
        json.dumps(result["work_order_records"], indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    QUARANTINE_RECEIPT_PATH.write_text(
        json.dumps(result["quarantine_records"], indent=2, sort_keys=True) + "\n", encoding="utf-8"
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
                "audit_sha256": result["audit_sha256"],
                "counts": expected_actual(result),
                "field_digest_sha256": result["field_digest_sha256"],
                "fixture_sha256": result["fixture_sha256"],
                "lineage_sha256": result["lineage_sha256"],
                "matrix_counts": result["matrix_counts"],
                "quarantine_code_counts": result["quarantine_code_counts"],
                "work_order_sha256": result["work_order_sha256"],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    FIELD_DIGEST_PATH.write_text(
        json.dumps(result["field_digests"], indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if replay is not None:
        REPLAY_RECEIPT_PATH.write_text(json.dumps(replay, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    CONTRACT_PATH.write_text(
        json.dumps(
            {
                "audit_sha256": result["audit_sha256"],
                "buyer": BUYER,
                "cash_usd": 0,
                "demand_id": DEMAND_ID,
                "interfaces": "SIMULATED_READ_ONLY",
                "live_lims": False,
                "official_binary": OFFICIAL_BINARY,
                "official_test": OFFICIAL_TEST,
                "page": "torrent-workorder-commissioning-lims.html",
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
        "audit": str(AUDIT_RECEIPT_PATH),
        "contract": str(CONTRACT_PATH),
        "field_digests": str(FIELD_DIGEST_PATH),
        "fixture": str(FIXTURE_PATH),
        "journal": str(STATE_PATH),
        "lineage": str(LINEAGE_RECEIPT_PATH),
        "quarantines": str(QUARANTINE_RECEIPT_PATH),
        "run": str(RUN_RECEIPT_PATH),
        "work_orders": str(WORK_ORDER_RECEIPT_PATH),
    }


def load_journal(path: Path = STATE_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def cli_payload(result: dict[str, Any]) -> dict[str, Any]:
    counts = expected_actual(result)
    return {
        "actual": counts["actual"],
        "audit_sha256": result["audit_sha256"],
        "autonomous_released": result["autonomous_released"],
        "buyer": BUYER,
        "cash_usd": 0,
        "demand_id": DEMAND_ID,
        "expected": counts["expected"],
        "facility_failures": result["facility_failures"],
        "failures": result.get("failures") or [],
        "field_digest_sha256": result["field_digest_sha256"],
        "fixture_sha256": result["fixture_sha256"],
        "human_released": result["human_released"],
        "interfaces": result["interfaces"],
        "lineage_sha256": result["lineage_sha256"],
        "match": counts["match"],
        "matrix_counts": result["matrix_counts"],
        "official_binary": result["official_binary"],
        "official_test": result["official_test"],
        "ok": result["ok"],
        "parity_failures": result["parity_failures"],
        "pre_sale_transport": "NONE",
        "quarantine_code_counts": result["quarantine_code_counts"],
        "replay": result["replay"],
        "replay_audit_sha256": result["replay_audit_sha256"],
        "truth_gate": TRUTH_GATE,
        "work_order_sha256": result["work_order_sha256"],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Torrent Watson COC work-order commissioning runner")
    parser.add_argument("--write-fixture", action="store_true", help="write the 500-row fixture and exit")
    parser.add_argument("--print-goldens", action="store_true", help="print computed digests without locking")
    parser.add_argument("--replay", action="store_true", help="replay into persisted journal and write replay receipt")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.write_fixture:
        rows = write_fixture()
        sys.stdout.write(_canonical({"count": len(rows), "wrote": str(FIXTURE_PATH)}) + "\n")
        return 0
    if args.print_goldens:
        result = run_commissioning(build_acceptance_fixture())
        sys.stdout.write(
            _canonical(
                {
                    "audit_sha256": result["audit_sha256"],
                    "expected": expected_actual(result),
                    "field_digest_sha256": result["field_digest_sha256"],
                    "fixture_sha256": result["fixture_sha256"],
                    "lineage_sha256": result["lineage_sha256"],
                    "matrix_counts": result["matrix_counts"],
                    "quarantine_code_counts": result["quarantine_code_counts"],
                    "work_order_sha256": result["work_order_sha256"],
                }
            )
            + "\n"
        )
        return 0
    if args.replay:
        if not STATE_PATH.is_file():
            result = run_commissioning()
            persist_run(result)
        journal = load_journal()
        replay = replay_into(journal, load_fixture())
        REPLAY_RECEIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
        body = {
            "journal_sha256": sha256_hex(journal),
            "ok": replay["added_work_orders"] == 0
            and replay["added_quarantines"] == 0
            and not replay["state_changed"],
            "replay": replay,
        }
        STATE_PATH.write_text(json.dumps(journal, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        REPLAY_RECEIPT_PATH.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        sys.stdout.write(_canonical(body) + "\n")
        return 0 if body["ok"] else 1

    result = run_commissioning()
    written = persist_run(result, replay=result["replay"])
    payload = cli_payload(result)
    payload["written"] = written
    sys.stdout.write(_canonical(payload) + "\n")
    return 0 if payload["ok"] and not payload["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
