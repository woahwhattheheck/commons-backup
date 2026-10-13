#!/usr/bin/env python3
"""Canyon Labs multi-site regulated sample-intake runner.

Demand: canyon-multisite-regulated-intake-lims-01
Buyer pairing: Canyon Labs / Wendy Mach

Working CLI, not a look-inside souvenir. Processes 300 synthetic
submissions across Bluffdale, Rush, and Vista; applies the
complete-form gate, facility/method scope routing, source-field
lineage, custody, exception ownership, and named-human hold/release.

300 submissions = 240 complete + 60 predefined missing/conflicting.
Exactly 240 accession once at the correct site. All 60 HOLD with the
exact reason. Zero held samples start testing. Replay writes the same
state. Named human release is mandatory. No autonomous release.

HOLD / BUILD-AND-VERIFY. Portals / LIMS / instruments / QMS stay
simulated and read-only. No live sample, test, billing, or report
action. No PHI. No outreach. cash_usd=0. PRE-SALE TRANSPORT: NONE.

Official command:
    python3 canyon_multisite_regulated_intake.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

DEMAND_ID = "canyon-multisite-regulated-intake-lims-01"
SCHEMA = "commons-canyon-multisite-regulated-intake-lims/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
BUYER = "Canyon Labs / Wendy Mach"
HUMAN_RELEASER = "SYN-RELEASE-OFFICER"
HUMAN_ROLE = "RELEASE_OFFICER"
INTAKE_DESK = "INTAKE_DESK"
FACILITY_LEAD = "FACILITY_LEAD"
SOURCE_CUSTODY = "SOURCE_CUSTODY"

INPUT_COUNT = 300
COMPLETE_COUNT = 240
HOLD_COUNT = 60
PER_HOLD_CODE = 10
PER_ROUTE = 40

SITES = ("BLF", "RSH", "VST")
SITE_NAMES = {
    "BLF": "SYN-BLUFFDALE-UT-HQ",
    "RSH": "SYN-RUSH-NY-EAST",
    "VST": "SYN-VISTA-CA-THERMAL",
}
NAMESPACE = {code: f"CYN-{code}" for code in SITES}

DISCIPLINES = ("CHEMISTRY", "MICROBIOLOGY", "PACKAGING", "BIOCOMPATIBILITY")
METHODS = {
    "CHEMISTRY": "HPLC-ASSAY",
    "MICROBIOLOGY": "USP-71-STERILITY",
    "PACKAGING": "ASTM-F1980",
    "BIOCOMPATIBILITY": "ISO-10993-5",
}
SITE_SCOPE: dict[str, frozenset[str]] = {
    "BLF": frozenset({"CHEMISTRY", "MICROBIOLOGY", "PACKAGING"}),
    "RSH": frozenset({"BIOCOMPATIBILITY", "MICROBIOLOGY"}),
    "VST": frozenset({"PACKAGING"}),
}
COMPLETE_ROUTES = (
    ("BLF", "CHEMISTRY"),
    ("BLF", "MICROBIOLOGY"),
    ("BLF", "PACKAGING"),
    ("RSH", "BIOCOMPATIBILITY"),
    ("RSH", "MICROBIOLOGY"),
    ("VST", "PACKAGING"),
)
SCOPE_CONFLICTS = (
    ("VST", "CHEMISTRY"),
    ("VST", "MICROBIOLOGY"),
    ("VST", "BIOCOMPATIBILITY"),
    ("BLF", "BIOCOMPATIBILITY"),
    ("RSH", "PACKAGING"),
)
HOLD_CODES = (
    "HOLD_MISSING_SAMPLE_ID",
    "HOLD_MISSING_CUSTODY_SEAL",
    "HOLD_MISSING_COLLECTION_DATETIME",
    "HOLD_MISSING_METHOD",
    "HOLD_CONFLICT_SITE_METHOD_SCOPE",
    "HOLD_CONFLICT_SOURCE_LINEAGE",
)
HOLD_OWNERS = {
    "HOLD_MISSING_SAMPLE_ID": INTAKE_DESK,
    "HOLD_MISSING_CUSTODY_SEAL": INTAKE_DESK,
    "HOLD_MISSING_COLLECTION_DATETIME": INTAKE_DESK,
    "HOLD_MISSING_METHOD": INTAKE_DESK,
    "HOLD_CONFLICT_SITE_METHOD_SCOPE": FACILITY_LEAD,
    "HOLD_CONFLICT_SOURCE_LINEAGE": SOURCE_CUSTODY,
}
EXPECTED_SITE_COUNTS = {"BLF": 120, "RSH": 80, "VST": 40}
EXPECTED_HOLD_COUNTS = {code: PER_HOLD_CODE for code in HOLD_CODES}
EXPECTED_COUNTS = {
    "input_rows": INPUT_COUNT,
    "complete": COMPLETE_COUNT,
    "holds": HOLD_COUNT,
    "accessions": COMPLETE_COUNT,
    "held_testing_started": 0,
    "autonomous_released": 0,
    "human_released": COMPLETE_COUNT,
    "duplicate_accessions": 0,
    "production_writes": 0,
    "live_tests": 0,
    "live_reports": 0,
    "billing_writes": 0,
}

COLLECTED_AT = "2026-08-01T09:00:00Z"
RECEIVED_AT = "2026-08-01T15:00:00Z"
RELEASED_AT = "2026-08-31T04:00:00Z"

PACK = Path("revenue") / "canyon_multisite_regulated_intake"
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

GOLDEN_AUDIT_SHA256 = "d6e4aa3a3161f357c540faf386fcfa0d5c49608f936158d444c646f643fc9213"
GOLDEN_LINEAGE_SHA256 = "43941be44834145fefb3826da12775ed08878cb75d2692932708032ace33380e"
GOLDEN_ACCESSION_SHA256 = "5990a5bb320af57005134c3b4b490f5915a9eb9ad56d6f5abbf31b4a17b98458"


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


def site_namespace(site: str) -> str:
    return NAMESPACE[site]


def source_fields(row: dict[str, Any]) -> dict[str, str]:
    return {
        "sponsor_code": _text(row.get("sponsor_code")),
        "lot_code": _text(row.get("lot_code")),
        "material_family": _text(row.get("material_family")),
        "origin_record": _text(row.get("origin_record")),
    }


def field_lineage(fields: dict[str, str]) -> dict[str, str]:
    return {key: sha256_hex(value) for key, value in sorted(fields.items())}


def compute_source_hash(row: dict[str, Any]) -> str:
    return sha256_hex(source_fields(row))


def accession_id(site: str, submission_id: str, source_hash: str) -> str:
    digest = sha256_hex(
        {
            "demand_id": DEMAND_ID,
            "site": site,
            "submission_id": submission_id,
            "source_hash": source_hash,
        }
    )
    return f"{site_namespace(site)}-ACC-{digest[:12]}"


def _material(discipline: str) -> str:
    return {
        "CHEMISTRY": "PHARMA_API",
        "MICROBIOLOGY": "DEVICE_STERILE",
        "PACKAGING": "PACKAGING_FILM",
        "BIOCOMPATIBILITY": "DEVICE_EXTRACT",
    }[discipline]


def _complete_row(site: str, discipline: str, local: int) -> dict[str, Any]:
    method = METHODS[discipline]
    submission_id = f"{site_namespace(site)}-SUB-{discipline[:3]}-{local:02d}"
    sample_id = f"{site_namespace(site)}-SMP-{discipline[:3]}-{local:02d}"
    row = {
        "submission_id": submission_id,
        "expected_state": "ACCESSION",
        "expected_hold_code": None,
        "sample_id": sample_id,
        "requested_site": site,
        "correct_site": site,
        "discipline": discipline,
        "method_code": method,
        "collection_datetime": COLLECTED_AT,
        "container_type": "SYN-CONTAINER-01",
        "custody_seal": f"SYN-SEAL-{site}-{local:02d}",
        "matrix": _material(discipline),
        "sponsor_code": f"SYN-SPN-{site}-{local:02d}",
        "lot_code": f"SYN-LOT-{site}-{local:02d}",
        "material_family": _material(discipline),
        "origin_record": f"SYN-SRC-{site}-{discipline[:3]}-{local:02d}",
        "relinquished_by": "SYN-FIELD-01",
        "received_by": "SYN-INTAKE-01",
        "received_at": RECEIVED_AT,
        "synthetic": True,
        "phi": False,
    }
    row["source_hash"] = compute_source_hash(row)
    row["field_lineage"] = field_lineage(source_fields(row))
    return row


def _hold_row(slot: int) -> dict[str, Any]:
    code = HOLD_CODES[slot // PER_HOLD_CODE]
    within = slot % PER_HOLD_CODE
    site = SITES[within % 3]
    discipline = DISCIPLINES[within % 4]
    if code == "HOLD_CONFLICT_SITE_METHOD_SCOPE":
        site, discipline = SCOPE_CONFLICTS[within % len(SCOPE_CONFLICTS)]
    elif code == "HOLD_CONFLICT_SOURCE_LINEAGE":
        site, discipline = COMPLETE_ROUTES[within % len(COMPLETE_ROUTES)]
    row = _complete_row(site, discipline, 80 + within)
    row["submission_id"] = f"{site_namespace(site)}-HLD-{slot + 1:02d}"
    row["sample_id"] = f"{site_namespace(site)}-HLD-SMP-{slot + 1:02d}"
    row["expected_state"] = "HOLD"
    row["expected_hold_code"] = code
    row["correct_site"] = None
    row["custody_seal"] = f"SYN-SEAL-HLD-{slot + 1:02d}"
    row["sponsor_code"] = f"SYN-SPN-HLD-{slot + 1:02d}"
    row["lot_code"] = f"SYN-LOT-HLD-{slot + 1:02d}"
    row["origin_record"] = f"SYN-SRC-HLD-{slot + 1:02d}"

    if code == "HOLD_MISSING_SAMPLE_ID":
        row["sample_id"] = ""
    elif code == "HOLD_MISSING_CUSTODY_SEAL":
        row["custody_seal"] = ""
    elif code == "HOLD_MISSING_COLLECTION_DATETIME":
        row["collection_datetime"] = ""
    elif code == "HOLD_MISSING_METHOD":
        row["method_code"] = ""
    elif code == "HOLD_CONFLICT_SITE_METHOD_SCOPE":
        row["requested_site"] = site
        row["discipline"] = discipline
        row["method_code"] = METHODS[discipline]
    elif code == "HOLD_CONFLICT_SOURCE_LINEAGE":
        row["source_hash"] = "0" * 64
        row["field_lineage"] = field_lineage(source_fields(row))
        return row
    else:
        raise RuntimeError("unmapped hold code %s" % code)

    row["source_hash"] = compute_source_hash(row)
    row["field_lineage"] = field_lineage(source_fields(row))
    return row


def build_acceptance_fixture() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for site, discipline in COMPLETE_ROUTES:
        for local in range(1, PER_ROUTE + 1):
            rows.append(_complete_row(site, discipline, local))
    for slot in range(HOLD_COUNT):
        rows.append(_hold_row(slot))
    if len(rows) != INPUT_COUNT:
        raise RuntimeError("fixture must be exactly 300, got %s" % len(rows))
    complete = [row for row in rows if row["expected_state"] == "ACCESSION"]
    holds = [row for row in rows if row["expected_state"] == "HOLD"]
    if len(complete) != COMPLETE_COUNT or len(holds) != HOLD_COUNT:
        raise RuntimeError("fixture split must be 240/60")
    by_site = {code: 0 for code in SITES}
    for row in complete:
        by_site[row["requested_site"]] += 1
    if by_site != EXPECTED_SITE_COUNTS:
        raise RuntimeError("complete site split must be 120/80/40, got %s" % by_site)
    codes = [row["expected_hold_code"] for row in holds]
    for code in HOLD_CODES:
        if codes.count(code) != PER_HOLD_CODE:
            raise RuntimeError("%s must appear exactly 10 times" % code)
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
            raise RuntimeError("fixture.json must contain exactly 300 submissions")
        return rows
    return build_acceptance_fixture()


def empty_journal() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "accessions": {},
        "holds": {},
        "events": [],
        "submission_index": {},
        "sample_index": {},
        "interface_live": False,
        "production_writes": 0,
        "live_tests": 0,
        "live_reports": 0,
        "billing_writes": 0,
        "phi_records": 0,
        "automatic_releases": 0,
    }


def _event(journal: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    prev = journal["events"][-1]["record_hash"] if journal["events"] else "GENESIS"
    body = {"seq": len(journal["events"]) + 1, "kind": kind, **deepcopy(payload)}
    body["prev_hash"] = prev
    body["record_hash"] = sha256_hex(
        {"prev": prev, "body": {k: v for k, v in body.items() if k not in {"prev_hash", "record_hash"}}}
    )
    journal["events"].append(body)


def normalize(row: dict[str, Any]) -> dict[str, Any]:
    site = _text(row.get("requested_site")).upper()
    discipline = _text(row.get("discipline")).upper()
    method = _text(row.get("method_code")).upper()
    return {
        "submission_id": _text(row.get("submission_id")),
        "sample_id": _text(row.get("sample_id")),
        "requested_site": site,
        "discipline": discipline,
        "method_code": method,
        "collection_datetime": _text(row.get("collection_datetime")),
        "container_type": _text(row.get("container_type")),
        "custody_seal": _text(row.get("custody_seal")),
        "matrix": _text(row.get("matrix")),
        "sponsor_code": _text(row.get("sponsor_code")),
        "lot_code": _text(row.get("lot_code")),
        "material_family": _text(row.get("material_family")),
        "origin_record": _text(row.get("origin_record")),
        "source_hash": _text(row.get("source_hash")),
        "field_lineage": dict(row.get("field_lineage") or {}),
        "relinquished_by": _text(row.get("relinquished_by")),
        "received_by": _text(row.get("received_by")),
        "received_at": _text(row.get("received_at")),
        "synthetic": _flag(row.get("synthetic")) if "synthetic" in row else True,
        "phi": _flag(row.get("phi")) if "phi" in row else False,
    }


def classify(norm: dict[str, Any]) -> dict[str, Any]:
    if not norm["sample_id"]:
        return {"ok": False, "code": "HOLD_MISSING_SAMPLE_ID"}
    if not norm["custody_seal"]:
        return {"ok": False, "code": "HOLD_MISSING_CUSTODY_SEAL"}
    if not norm["collection_datetime"]:
        return {"ok": False, "code": "HOLD_MISSING_COLLECTION_DATETIME"}
    if not norm["method_code"]:
        return {"ok": False, "code": "HOLD_MISSING_METHOD"}
    site = norm["requested_site"]
    discipline = norm["discipline"]
    if site not in SITE_SCOPE or discipline not in SITE_SCOPE[site]:
        return {"ok": False, "code": "HOLD_CONFLICT_SITE_METHOD_SCOPE"}
    if METHODS.get(discipline) != norm["method_code"]:
        return {"ok": False, "code": "HOLD_CONFLICT_SITE_METHOD_SCOPE"}
    expected_hash = compute_source_hash(norm)
    expected_lineage = field_lineage(source_fields(norm))
    if not norm["source_hash"] or norm["source_hash"] != expected_hash:
        return {"ok": False, "code": "HOLD_CONFLICT_SOURCE_LINEAGE"}
    if norm["field_lineage"] and norm["field_lineage"] != expected_lineage:
        return {"ok": False, "code": "HOLD_CONFLICT_SOURCE_LINEAGE"}
    return {"ok": True, "correct_site": site, "source_hash": expected_hash, "field_lineage": expected_lineage}


def _park_hold(journal: dict[str, Any], norm: dict[str, Any], code: str) -> dict[str, Any]:
    hold = {
        "submission_id": norm["submission_id"],
        "sample_id": norm["sample_id"] or None,
        "requested_site": norm["requested_site"],
        "discipline": norm["discipline"],
        "method_code": norm["method_code"] or None,
        "code": code,
        "state": "HOLD",
        "owner_role": HOLD_OWNERS[code],
        "source_hash": norm["source_hash"] or None,
        "field_lineage": dict(norm["field_lineage"]),
        "testing_started": False,
        "released": False,
        "released_by": None,
        "interface_live": False,
        "live_test": False,
    }
    existing = journal["holds"].get(hold["submission_id"])
    if existing is not None:
        return {"kind": "NOOP", "reason": "already_held", "submission_id": hold["submission_id"]}
    journal["holds"][hold["submission_id"]] = hold
    journal["submission_index"][hold["submission_id"]] = {"kind": "HOLD", "code": code}
    _event(journal, "HOLD", {"submission_id": hold["submission_id"], "code": code, "owner_role": hold["owner_role"]})
    return {"kind": "HOLD", "duplicate": False, **hold}


def ingest_row(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    norm = normalize(row)
    submission_id = norm["submission_id"]
    if submission_id in journal["submission_index"]:
        prior = journal["submission_index"][submission_id]
        return {"kind": "NOOP", "reason": "already_seen", "submission_id": submission_id, "prior": prior["kind"]}
    verdict = classify(norm)
    if not verdict["ok"]:
        return _park_hold(journal, norm, verdict["code"])

    site = verdict["correct_site"]
    source_hash = verdict["source_hash"]
    acc_id = accession_id(site, submission_id, source_hash)
    if acc_id in journal["accessions"]:
        return {"kind": "NOOP", "reason": "already_accessioned", "accession_id": acc_id}
    if norm["sample_id"] in journal["sample_index"]:
        return _park_hold(journal, norm, "HOLD_CONFLICT_SOURCE_LINEAGE")

    record = {
        "accession_id": acc_id,
        "submission_id": submission_id,
        "sample_id": norm["sample_id"],
        "site": site,
        "site_name": SITE_NAMES[site],
        "namespace": site_namespace(site),
        "discipline": norm["discipline"],
        "method_code": norm["method_code"],
        "collection_datetime": norm["collection_datetime"],
        "container_type": norm["container_type"],
        "custody_seal": norm["custody_seal"],
        "matrix": norm["matrix"],
        "source_hash": source_hash,
        "field_lineage": verdict["field_lineage"],
        "source_fields": source_fields(norm),
        "custody": [
            {"step": "RECEIVED", "actor": norm["received_by"] or "SYN-INTAKE-01", "at": norm["received_at"] or RECEIVED_AT},
            {"step": "FORM_COMPLETE", "actor": INTAKE_DESK, "at": RECEIVED_AT},
            {"step": "SCOPE_ROUTED", "actor": FACILITY_LEAD, "correct_site": site, "at": RECEIVED_AT},
            {"step": "ACCESSIONED", "actor": INTAKE_DESK, "accession_id": acc_id, "at": RECEIVED_AT},
        ],
        "state": "ACCESSIONED",
        "testing_started": False,
        "released": False,
        "released_to_test": False,
        "released_by": None,
        "released_at": None,
        "interface_state": "SIMULATED",
        "interface_live": False,
        "live_test": False,
        "live_report": False,
        "billing": False,
    }
    journal["accessions"][acc_id] = record
    journal["submission_index"][submission_id] = {"kind": "ACCESSION", "accession_id": acc_id}
    journal["sample_index"][norm["sample_id"]] = acc_id
    _event(
        journal,
        "ACCESSION",
        {
            "accession_id": acc_id,
            "submission_id": submission_id,
            "site": site,
            "discipline": norm["discipline"],
            "source_hash": source_hash,
            "adapter": "SIMULATED_SITE_LIMS",
        },
    )
    return {"kind": "ACCESSION", "accession_id": acc_id, "site": site, "submission_id": submission_id}


def start_test(journal: dict[str, Any], key: str, *, actor: str, actor_role: str) -> dict[str, Any]:
    hold = journal["holds"].get(key)
    if hold is None:
        for item in journal["holds"].values():
            if item.get("sample_id") == key or item.get("submission_id") == key:
                hold = item
                break
    if hold is not None:
        _event(journal, "TEST_BLOCKED_HOLD", {"submission_id": hold["submission_id"], "actor": actor})
        hold["testing_started"] = False
        hold["live_test"] = False
        return {"ok": False, "code": "TEST_BLOCKED_HOLD", "testing_started": False}

    record = journal["accessions"].get(key)
    if record is None:
        for item in journal["accessions"].values():
            if item["submission_id"] == key or item["sample_id"] == key:
                record = item
                break
    if record is None:
        return {"ok": False, "code": "UNKNOWN_SAMPLE"}
    if not record.get("released") or _text(actor_role).upper() != HUMAN_ROLE or _text(actor) != HUMAN_RELEASER:
        _event(
            journal,
            "TEST_BLOCKED",
            {"accession_id": record["accession_id"], "code": "HUMAN_RELEASE_REQUIRED", "actor": actor},
        )
        return {"ok": False, "code": "HUMAN_RELEASE_REQUIRED", "testing_started": False}
    record["testing_started"] = False
    record["live_test"] = False
    journal["live_tests"] = 0
    _event(journal, "TEST_DENIED_SIMULATED", {"accession_id": record["accession_id"]})
    return {"ok": False, "code": "SIMULATED_ONLY_NO_LIVE_TEST", "testing_started": False, "interface_live": False}


def release_accession(
    journal: dict[str, Any],
    acc_id: str,
    *,
    actor: str,
    actor_role: str,
) -> dict[str, Any]:
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
    record["released_to_test"] = True
    record["released_by"] = name
    record["released_at"] = RELEASED_AT
    record["state"] = "HUMAN_RELEASED"
    record["testing_started"] = False
    record["live_test"] = False
    _event(journal, "HUMAN_RELEASE", {"accession_id": acc_id, "released_by": name})
    return {"ok": True, "code": "HUMAN_RELEASED", "accession_id": acc_id}


def release_hold(
    journal: dict[str, Any],
    submission_id: str,
    *,
    actor: str,
    actor_role: str,
) -> dict[str, Any]:
    hold = journal["holds"].get(submission_id)
    if hold is None:
        return {"ok": False, "code": "UNKNOWN_HOLD"}
    role = _text(actor_role).upper()
    name = _text(actor)
    if role != HUMAN_ROLE or name != HUMAN_RELEASER:
        _event(journal, "AUTONOMOUS_RELEASE_DENIED", {"submission_id": submission_id, "actor": name})
        return {"ok": False, "code": "AUTONOMOUS_RELEASE_DENIED"}
    hold["released"] = False
    hold["testing_started"] = False
    hold["live_test"] = False
    hold["state"] = "HOLD"
    _event(journal, "HOLD_RELEASE_DENIED_STILL_HOLD", {"submission_id": submission_id, "actor": name})
    return {"ok": False, "code": "HOLD_UNRESOLVED_NO_TEST", "testing_started": False}


def attempt_autonomous_release(journal: dict[str, Any]) -> list[dict[str, Any]]:
    effects = []
    for acc_id in sorted(journal["accessions"]):
        effects.append(release_accession(journal, acc_id, actor="SYSTEM", actor_role="SYSTEM"))
    for submission_id in sorted(journal["holds"]):
        effects.append(release_hold(journal, submission_id, actor="bot", actor_role="SYSTEM"))
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
    after_acc = {key: {k: v for k, v in value.items() if k != "custody"} for key, value in journal["accessions"].items()}
    compact_before = {key: {k: v for k, v in value.items() if k != "custody"} for key, value in before_acc.items()}
    return {
        "added_accession_count": len(journal["accessions"]) - before_acc_n,
        "added_holds": len(journal["holds"]) - before_hold_n,
        "accession_count": len(journal["accessions"]),
        "hold_count": len(journal["holds"]),
        "replay_noops": sum(1 for item in effects if item.get("kind") == "NOOP"),
        "state_changed": compact_before != after_acc or before_hold != journal["holds"],
    }


def compact_accessions(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "accession_id": item["accession_id"],
            "submission_id": item["submission_id"],
            "sample_id": item["sample_id"],
            "site": item["site"],
            "discipline": item["discipline"],
            "method_code": item["method_code"],
            "source_hash": item["source_hash"],
            "field_lineage": deepcopy(item["field_lineage"]),
            "state": item["state"],
            "testing_started": item["testing_started"],
            "released": item["released"],
            "released_by": item["released_by"],
            "interface_live": item["interface_live"],
            "live_test": item["live_test"],
        }
        for item in sorted(journal["accessions"].values(), key=lambda row: row["accession_id"])
    ]


def compact_holds(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        deepcopy(item)
        for item in sorted(journal["holds"].values(), key=lambda row: row["submission_id"])
    ]


def compact_lineage(journal: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in compact_accessions(journal):
        rows.append(
            {
                "kind": "ACCESSION",
                "id": item["accession_id"],
                "source_hash": item["source_hash"],
                "field_lineage": item["field_lineage"],
            }
        )
    for item in compact_holds(journal):
        rows.append(
            {
                "kind": "HOLD",
                "id": item["submission_id"],
                "source_hash": item["source_hash"],
                "field_lineage": item["field_lineage"],
            }
        )
    return rows


def build_audit(journal: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "accessions": compact_accessions(journal),
        "holds": [
            {
                "submission_id": item["submission_id"],
                "code": item["code"],
                "owner_role": item["owner_role"],
                "testing_started": item["testing_started"],
                "source_hash": item["source_hash"],
            }
            for item in compact_holds(journal)
        ],
        "lineage": compact_lineage(journal),
        "events": deepcopy(journal["events"]),
        "autonomous_released": 0,
        "human_released": sum(1 for item in journal["accessions"].values() if item["released"]),
        "held_testing_started": sum(1 for item in journal["holds"].values() if item["testing_started"]),
        "production_writes": journal["production_writes"],
        "live_tests": journal["live_tests"],
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
    if result.get("site_counts") != EXPECTED_SITE_COUNTS:
        failures.append("site_counts")
    if result.get("hold_code_counts") != EXPECTED_HOLD_COUNTS:
        failures.append("hold_code_counts")
    if result.get("wrong_site"):
        failures.append("wrong_site")
    if result.get("held_testing_started") != 0:
        failures.append("held_testing_started")
    if result.get("duplicate_accessions") != 0:
        failures.append("duplicate_accessions")
    replay = result.get("replay") or {}
    if replay.get("added_accession_count") != 0 or replay.get("added_holds") != 0 or replay.get("state_changed"):
        failures.append("replay")
    if result.get("audit_sha256") != result.get("replay_audit_sha256"):
        failures.append("replay_hash")
    if result.get("lineage_failures"):
        failures.append("lineage")
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
    auto = result.get("autonomous_release_effects") or []
    if auto and any(item.get("ok") for item in auto):
        failures.append("autonomous_release_not_denied")
    if any(item.get("testing_started") for item in result.get("hold_records") or []):
        failures.append("hold_started_testing")
    return failures


def lineage_failures(rows: list[dict[str, Any]], journal: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    by_sub = {row["submission_id"]: row for row in rows if row["expected_state"] == "ACCESSION"}
    for item in journal["accessions"].values():
        src = by_sub.get(item["submission_id"])
        if src is None:
            failures.append("missing_source:%s" % item["submission_id"])
            continue
        if item["source_hash"] != src["source_hash"]:
            failures.append("source_hash:%s" % item["submission_id"])
        if item["field_lineage"] != src["field_lineage"]:
            failures.append("field_lineage:%s" % item["submission_id"])
        if item["source_hash"] != compute_source_hash(src):
            failures.append("recompute:%s" % item["submission_id"])
    return failures


def wrong_site_accessions(journal: dict[str, Any]) -> list[str]:
    bad = []
    for item in journal["accessions"].values():
        if item["discipline"] not in SITE_SCOPE[item["site"]]:
            bad.append(item["accession_id"])
        if not item["accession_id"].startswith(item["namespace"] + "-ACC-"):
            bad.append(item["accession_id"])
        if METHODS[item["discipline"]] != item["method_code"]:
            bad.append(item["accession_id"])
    return sorted(set(bad))


def run_intake(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else load_fixture())
    journal = empty_journal()
    effects = [ingest_row(journal, row) for row in inbound]
    hold_attempts = [
        start_test(journal, submission_id, actor="SYSTEM", actor_role="SYSTEM")
        for submission_id in sorted(journal["holds"])
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
    site_counts = {code: 0 for code in SITES}
    for item in journal["accessions"].values():
        site_counts[item["site"]] += 1

    golden_locked = "pending" not in {GOLDEN_AUDIT_SHA256, GOLDEN_LINEAGE_SHA256, GOLDEN_ACCESSION_SHA256}
    packed = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "input_rows": len(inbound),
        "complete": COMPLETE_COUNT,
        "holds": len(journal["holds"]),
        "accessions": len(journal["accessions"]),
        "accession_records": accessions,
        "hold_records": compact_holds(journal),
        "hold_codes": sorted(set(hold_code_counts)),
        "hold_code_counts": hold_code_counts,
        "site_counts": site_counts,
        "wrong_site": wrong_site_accessions(journal),
        "lineage_failures": lineage_failures(inbound, journal),
        "lineage": lineage,
        "held_testing_started": sum(1 for item in journal["holds"].values() if item["testing_started"]),
        "hold_test_attempts": hold_attempts,
        "released_test_attempts": released_attempts,
        "autonomous_release_effects": auto,
        "human_release_effects": human,
        "autonomous_released": 0,
        "human_released": sum(1 for item in journal["accessions"].values() if item["released"]),
        "duplicate_accessions": len(accessions) - len({item["submission_id"] for item in accessions}),
        "effects": effects,
        "replay": replay,
        "audit": audit,
        "audit_sha256": audit_sha,
        "replay_audit_sha256": replay_sha,
        "lineage_sha256": lineage_sha,
        "accession_sha256": accession_sha,
        "interface_live": False,
        "interfaces": "SIMULATED",
        "production_writes": 0,
        "live_tests": 0,
        "live_reports": 0,
        "billing_writes": 0,
        "phi_records": 0,
        "cash_usd": 0,
        "pre_sale_transport": "NONE",
        "golden_locked": golden_locked,
        "official_binary": "python3 canyon_multisite_regulated_intake.py",
        "official_test": "python3 test_canyon_multisite_regulated_intake.py",
        "journal": journal,
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
    ACCESSION_RECEIPT_PATH.write_text(
        json.dumps(result["accession_records"], indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    HOLD_RECEIPT_PATH.write_text(
        json.dumps(result["hold_records"], indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    LINEAGE_RECEIPT_PATH.write_text(
        json.dumps(
            {
                "lineage_sha256": result["lineage_sha256"],
                "records": result["lineage"],
            },
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
                "counts": expected_actual(result),
                "hold_code_counts": result["hold_code_counts"],
                "lineage_sha256": result["lineage_sha256"],
                "site_counts": result["site_counts"],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    if replay is not None:
        REPLAY_RECEIPT_PATH.write_text(json.dumps(replay, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    CONTRACT_PATH.write_text(
        json.dumps(
            {
                "buyer": BUYER,
                "cash_usd": 0,
                "demand_id": DEMAND_ID,
                "interfaces": "SIMULATED_READ_ONLY",
                "live_lims": False,
                "official_binary": "python3 canyon_multisite_regulated_intake.py",
                "official_test": "python3 test_canyon_multisite_regulated_intake.py",
                "page": "canyon-multisite-regulated-intake.html",
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
        "site_counts": result["site_counts"],
        "hold_code_counts": result["hold_code_counts"],
        "wrong_site": result["wrong_site"],
        "held_testing_started": result["held_testing_started"],
        "human_released": result["human_released"],
        "autonomous_released": result["autonomous_released"],
        "audit_sha256": result["audit_sha256"],
        "lineage_sha256": result["lineage_sha256"],
        "accession_sha256": result["accession_sha256"],
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
    parser = argparse.ArgumentParser(description="Canyon multi-site regulated intake runner")
    parser.add_argument("--write-fixture", action="store_true", help="write the 300-row fixture and exit")
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
        result = run_intake(build_acceptance_fixture())
        sys.stdout.write(
            _canonical(
                {
                    "audit_sha256": result["audit_sha256"],
                    "lineage_sha256": result["lineage_sha256"],
                    "accession_sha256": result["accession_sha256"],
                    "expected": expected_actual(result),
                    "hold_code_counts": result["hold_code_counts"],
                    "site_counts": result["site_counts"],
                }
            )
            + "\n"
        )
        return 0
    if args.replay:
        if not STATE_PATH.is_file():
            result = run_intake()
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

    result = run_intake()
    written = persist_run(result, replay=result["replay"])
    payload = cli_payload(result)
    payload["written"] = written
    sys.stdout.write(_canonical(payload) + "\n")
    return 0 if payload["ok"] and not payload["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
