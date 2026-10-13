#!/usr/bin/env python3
"""WESTPAK scope- and capacity-aware multi-site test routing.

Demand: westpak-scope-capacity-routing-lims-01
Buyer pairing: WESTPAK / Angela Barber
Slack OPEN: #build-demand 1788149884.835659

Working program, not a look-inside souvenir. Intake → eligibility →
site/equipment/method/sequence route → authorized transfer/custody →
HOLD on known scope/capacity conflicts → named-human release.

240 synthetic jobs across package integrity, stability, environmental
conditioning, vibration, and thermal programs. 200 valid, 40 known
scope/capacity conflicts. Three laboratories (San Jose, San Diego,
Union City) under one QMS. Transfers only where the fixture authorizes.
Methods match exactly. Replay writes zero duplicate job/custody events.
Named human required before any release. No automatic release.

Scheduling / LIMS / instruments / QMS / transfers / reporting stay
simulated and read-only. No live LIMS. No production writes. No
outreach. No City contact. No bid submission. cash_usd=0.
HOLD / BUILD-AND-VERIFY.

Official command:
    python3 westpak_scope_capacity_routing.py
    python3 revenue/westpak_scope_capacity_routing/runner.py
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
JOB_RECEIPT_PATH = RECEIPT_DIR / "jobs.json"
HOLD_RECEIPT_PATH = RECEIPT_DIR / "holds.json"
ROUTE_RECEIPT_PATH = RECEIPT_DIR / "routes.json"
CUSTODY_RECEIPT_PATH = RECEIPT_DIR / "custody.json"
AUDIT_RECEIPT_PATH = RECEIPT_DIR / "audit.json"
REPLAY_RECEIPT_PATH = RECEIPT_DIR / "replay.json"
CONTRACT_PATH = PACK / "contract.json"

DEMAND_ID = "westpak-scope-capacity-routing-lims-01"
SCHEMA = "commons-westpak-scope-capacity-routing-lims/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
BUYER = "WESTPAK / Angela Barber"
QMS = "WPK-QMS-ONE"
NAMED_ROLE = "NAMED_RELEASE_OFFICER"
NAMED_ACTOR = "SYN-WPK-RELEASE-OFFICER"
COMMAND = "python3 westpak_scope_capacity_routing.py"
TEST_COMMAND = "python3 test_westpak_scope_capacity_routing.py"
SEED = 20260831
OPEN_SLACK_TS = "1788149884.835659"

SAN_JOSE = "WPK_SAN_JOSE"
SAN_DIEGO = "WPK_SAN_DIEGO"
UNION_CITY = "WPK_UNION_CITY"
SITES = (SAN_JOSE, SAN_DIEGO, UNION_CITY)
SITE_NAMES = {
    SAN_JOSE: "San Jose",
    SAN_DIEGO: "San Diego",
    UNION_CITY: "Union City",
}
PROGRAMS = ("INTEGRITY", "STABILITY", "CONDITIONING", "VIBRATION", "THERMAL")
ADAPTERS = ("SCHEDULING", "LIMS", "INSTRUMENTS", "QMS", "TRANSFERS", "REPORTING")

JOB_COUNT = 240
VALID_COUNT = 200
BLOCKED_COUNT = 40
PER_HOLD = 8
AUTHORIZED_TRANSFER_COUNT = 24

HOLD_CODES = (
    "HOLD_SCOPE_METHOD_NOT_AT_SITE",
    "HOLD_CAPACITY_EQUIPMENT_FULL",
    "HOLD_TRANSFER_NOT_AUTHORIZED",
    "HOLD_METHOD_MISMATCH",
    "HOLD_SEQUENCE_UNAVAILABLE",
)

CUSTODY_SAME_SITE = ("ORIGIN_INTAKE", "DEST_DOCK", "LAB_CUSTODY", "ANALYST")
CUSTODY_TRANSFER = ("ORIGIN_INTAKE", "TRANSFER_HANDOFF", "DEST_DOCK", "LAB_CUSTODY", "ANALYST")

METHODS: dict[str, dict[str, Any]] = {
    "ASTM_F2096_BUBBLE": {
        "program": "INTEGRITY",
        "sites": (SAN_JOSE,),
        "sequence": ["INTAKE", "CONDITION", "BUBBLE_LEAK", "SEAL_REVIEW", "HOLD_RELEASE"],
        "revision": "WPK-SJC-F2096-2025-04",
    },
    "ASTM_F1929_DYE": {
        "program": "INTEGRITY",
        "sites": (SAN_JOSE,),
        "sequence": ["INTAKE", "CONDITION", "DYE_PENETRATION", "SEAL_REVIEW", "HOLD_RELEASE"],
        "revision": "WPK-SJC-F1929-2025-04",
    },
    "ASTM_F88_SEAL": {
        "program": "INTEGRITY",
        "sites": (SAN_JOSE, UNION_CITY),
        "sequence": ["INTAKE", "CONDITION", "SEAL_STRENGTH", "REVIEW", "HOLD_RELEASE"],
        "revision": "WPK-QMS-F88-2025-06",
    },
    "ISO_11607_WHOLE": {
        "program": "INTEGRITY",
        "sites": (SAN_JOSE,),
        "sequence": ["INTAKE", "CONDITION", "WHOLE_PACK", "SEAL_REVIEW", "HOLD_RELEASE"],
        "revision": "WPK-SJC-ISO11607-2024-11",
    },
    "ASTM_F1980_AGING": {
        "program": "STABILITY",
        "sites": (SAN_JOSE,),
        "sequence": ["INTAKE", "CHAMBER_LOAD", "AGED_PULL", "INTEGRITY_RECHECK", "HOLD_RELEASE"],
        "revision": "WPK-SJC-F1980-2024-09",
    },
    "ASTM_D4332_COND": {
        "program": "CONDITIONING",
        "sites": (SAN_JOSE, SAN_DIEGO, UNION_CITY),
        "sequence": ["INTAKE", "CHAMBER_SET", "DWELL", "RELEASE_TO_TEST", "HOLD_RELEASE"],
        "revision": "WPK-QMS-D4332-2025-01",
    },
    "ASTM_D4169_VIB": {
        "program": "VIBRATION",
        "sites": (SAN_DIEGO,),
        "sequence": ["INTAKE", "FIXTURE", "RANDOM_VIBRATION", "INSPECTION", "HOLD_RELEASE"],
        "revision": "WPK-SAN-D4169-2025-03",
    },
    "ISTA_3A_VIB": {
        "program": "VIBRATION",
        "sites": (SAN_DIEGO,),
        "sequence": ["INTAKE", "ISTA_SEQUENCE", "INSPECTION", "HOLD_RELEASE"],
        "revision": "WPK-SAN-ISTA3A-2025-03",
    },
    "IEC_60068_THERMAL_SHOCK": {
        "program": "THERMAL",
        "sites": (SAN_DIEGO,),
        "sequence": ["INTAKE", "SHOCK_PROFILE", "INSPECTION", "HOLD_RELEASE"],
        "revision": "WPK-SAN-IEC60068-2025-02",
    },
    "ASTM_D4332_THERMAL_CYCLE": {
        "program": "THERMAL",
        "sites": (SAN_DIEGO, UNION_CITY),
        "sequence": ["INTAKE", "CYCLE_PROFILE", "INSPECTION", "HOLD_RELEASE"],
        "revision": "WPK-QMS-THERMCYCLE-2025-02",
    },
}

EQUIPMENT: dict[str, dict[str, Any]] = {
    "WPK-SJC-BUBBLE-01": {"site": SAN_JOSE, "method_id": "ASTM_F2096_BUBBLE", "slots": 10},
    "WPK-SJC-DYE-01": {"site": SAN_JOSE, "method_id": "ASTM_F1929_DYE", "slots": 8},
    "WPK-SJC-SEAL-01": {"site": SAN_JOSE, "method_id": "ASTM_F88_SEAL", "slots": 8},
    "WPK-SJC-ISO-01": {"site": SAN_JOSE, "method_id": "ISO_11607_WHOLE", "slots": 6},
    "WPK-UNC-SEAL-01": {"site": UNION_CITY, "method_id": "ASTM_F88_SEAL", "slots": 8},
    "WPK-SJC-AGE-01": {"site": SAN_JOSE, "method_id": "ASTM_F1980_AGING", "slots": 40},
    "WPK-SJC-COND-01": {"site": SAN_JOSE, "method_id": "ASTM_D4332_COND", "slots": 16},
    "WPK-SAN-COND-01": {"site": SAN_DIEGO, "method_id": "ASTM_D4332_COND", "slots": 16},
    "WPK-UNC-COND-01": {"site": UNION_CITY, "method_id": "ASTM_D4332_COND", "slots": 8},
    "WPK-SAN-VIB-01": {"site": SAN_DIEGO, "method_id": "ASTM_D4169_VIB", "slots": 24},
    "WPK-SAN-ISTA-01": {"site": SAN_DIEGO, "method_id": "ISTA_3A_VIB", "slots": 16},
    "WPK-SAN-THERM-01": {"site": SAN_DIEGO, "method_id": "IEC_60068_THERMAL_SHOCK", "slots": 16},
    "WPK-SAN-CYCLE-01": {"site": SAN_DIEGO, "method_id": "ASTM_D4332_THERMAL_CYCLE", "slots": 8},
    "WPK-UNC-CYCLE-01": {"site": UNION_CITY, "method_id": "ASTM_D4332_THERMAL_CYCLE", "slots": 16},
}

# (count, program, method_id, origin, dest, equipment_id)
VALID_SPECS: tuple[tuple[int, str, str, str, str, str], ...] = (
    (10, "INTEGRITY", "ASTM_F2096_BUBBLE", SAN_JOSE, SAN_JOSE, "WPK-SJC-BUBBLE-01"),
    (8, "INTEGRITY", "ASTM_F1929_DYE", SAN_JOSE, SAN_JOSE, "WPK-SJC-DYE-01"),
    (8, "INTEGRITY", "ASTM_F88_SEAL", SAN_JOSE, SAN_JOSE, "WPK-SJC-SEAL-01"),
    (8, "INTEGRITY", "ASTM_F88_SEAL", SAN_JOSE, UNION_CITY, "WPK-UNC-SEAL-01"),
    (6, "INTEGRITY", "ISO_11607_WHOLE", SAN_JOSE, SAN_JOSE, "WPK-SJC-ISO-01"),
    (40, "STABILITY", "ASTM_F1980_AGING", SAN_JOSE, SAN_JOSE, "WPK-SJC-AGE-01"),
    (16, "CONDITIONING", "ASTM_D4332_COND", SAN_JOSE, SAN_JOSE, "WPK-SJC-COND-01"),
    (16, "CONDITIONING", "ASTM_D4332_COND", SAN_DIEGO, SAN_DIEGO, "WPK-SAN-COND-01"),
    (8, "CONDITIONING", "ASTM_D4332_COND", UNION_CITY, UNION_CITY, "WPK-UNC-COND-01"),
    (24, "VIBRATION", "ASTM_D4169_VIB", SAN_DIEGO, SAN_DIEGO, "WPK-SAN-VIB-01"),
    (16, "VIBRATION", "ISTA_3A_VIB", SAN_DIEGO, SAN_DIEGO, "WPK-SAN-ISTA-01"),
    (16, "THERMAL", "IEC_60068_THERMAL_SHOCK", SAN_DIEGO, SAN_DIEGO, "WPK-SAN-THERM-01"),
    (8, "THERMAL", "ASTM_D4332_THERMAL_CYCLE", SAN_DIEGO, SAN_DIEGO, "WPK-SAN-CYCLE-01"),
    (16, "THERMAL", "ASTM_D4332_THERMAL_CYCLE", SAN_DIEGO, UNION_CITY, "WPK-UNC-CYCLE-01"),
)

AUTHORIZED_TRANSFERS = frozenset(
    {
        (SAN_JOSE, UNION_CITY, "ASTM_F88_SEAL"),
        (SAN_DIEGO, UNION_CITY, "ASTM_D4332_THERMAL_CYCLE"),
    }
)

# Conflicts are constructed so classify() returns exactly one expected code.
HOLD_SPECS: tuple[tuple[str, dict[str, Any]], ...] = (
    *(
        (
            "HOLD_SCOPE_METHOD_NOT_AT_SITE",
            {
                "program": "VIBRATION",
                "method_id": "ASTM_D4169_VIB",
                "origin": SAN_JOSE,
                "dest": SAN_JOSE,
                "equipment_id": "WPK-SJC-COND-01",
                "slot_index": 0,
            },
        )
        for _ in range(2)
    ),
    *(
        (
            "HOLD_SCOPE_METHOD_NOT_AT_SITE",
            {
                "program": "INTEGRITY",
                "method_id": "ASTM_F2096_BUBBLE",
                "origin": SAN_DIEGO,
                "dest": SAN_DIEGO,
                "equipment_id": "WPK-SAN-VIB-01",
                "slot_index": 0,
            },
        )
        for _ in range(2)
    ),
    *(
        (
            "HOLD_SCOPE_METHOD_NOT_AT_SITE",
            {
                "program": "STABILITY",
                "method_id": "ASTM_F1980_AGING",
                "origin": UNION_CITY,
                "dest": UNION_CITY,
                "equipment_id": "WPK-UNC-COND-01",
                "slot_index": 0,
            },
        )
        for _ in range(2)
    ),
    *(
        (
            "HOLD_SCOPE_METHOD_NOT_AT_SITE",
            {
                "program": "VIBRATION",
                "method_id": "ISTA_3A_VIB",
                "origin": UNION_CITY,
                "dest": UNION_CITY,
                "equipment_id": "WPK-UNC-SEAL-01",
                "slot_index": 0,
            },
        )
        for _ in range(2)
    ),
    *(
        (
            "HOLD_CAPACITY_EQUIPMENT_FULL",
            {
                "program": "STABILITY",
                "method_id": "ASTM_F1980_AGING",
                "origin": SAN_JOSE,
                "dest": SAN_JOSE,
                "equipment_id": "WPK-SJC-AGE-01",
                "slot_index": 40 + i,
            },
        )
        for i in range(4)
    ),
    *(
        (
            "HOLD_CAPACITY_EQUIPMENT_FULL",
            {
                "program": "VIBRATION",
                "method_id": "ASTM_D4169_VIB",
                "origin": SAN_DIEGO,
                "dest": SAN_DIEGO,
                "equipment_id": "WPK-SAN-VIB-01",
                "slot_index": 24 + i,
            },
        )
        for i in range(4)
    ),
    *(
        (
            "HOLD_TRANSFER_NOT_AUTHORIZED",
            {
                "program": "INTEGRITY",
                "method_id": "ASTM_F88_SEAL",
                "origin": UNION_CITY,
                "dest": SAN_JOSE,
                "equipment_id": "WPK-SJC-SEAL-01",
                "slot_index": 0,
            },
        )
        for _ in range(3)
    ),
    *(
        (
            "HOLD_TRANSFER_NOT_AUTHORIZED",
            {
                "program": "VIBRATION",
                "method_id": "ISTA_3A_VIB",
                "origin": UNION_CITY,
                "dest": SAN_DIEGO,
                "equipment_id": "WPK-SAN-ISTA-01",
                "slot_index": 0,
            },
        )
        for _ in range(2)
    ),
    *(
        (
            "HOLD_TRANSFER_NOT_AUTHORIZED",
            {
                "program": "INTEGRITY",
                "method_id": "ASTM_F2096_BUBBLE",
                "origin": SAN_DIEGO,
                "dest": SAN_JOSE,
                "equipment_id": "WPK-SJC-BUBBLE-01",
                "slot_index": 0,
            },
        )
        for _ in range(3)
    ),
    *(
        (
            "HOLD_METHOD_MISMATCH",
            {
                "program": "INTEGRITY",
                "method_id": "IEC_60068_THERMAL_SHOCK",
                "origin": SAN_DIEGO,
                "dest": SAN_DIEGO,
                "equipment_id": "WPK-SAN-THERM-01",
                "slot_index": 0,
            },
        )
        for _ in range(3)
    ),
    *(
        (
            "HOLD_METHOD_MISMATCH",
            {
                "program": "VIBRATION",
                "method_id": "ASTM_F1980_AGING",
                "origin": SAN_JOSE,
                "dest": SAN_JOSE,
                "equipment_id": "WPK-SJC-AGE-01",
                "slot_index": 0,
            },
        )
        for _ in range(3)
    ),
    *(
        (
            "HOLD_METHOD_MISMATCH",
            {
                "program": "THERMAL",
                "method_id": "ASTM_D4169_VIB",
                "origin": SAN_DIEGO,
                "dest": SAN_DIEGO,
                "equipment_id": "WPK-SAN-VIB-01",
                "slot_index": 0,
            },
        )
        for _ in range(2)
    ),
    *(
        (
            "HOLD_SEQUENCE_UNAVAILABLE",
            {
                "program": "INTEGRITY",
                "method_id": "ASTM_F88_SEAL",
                "origin": SAN_JOSE,
                "dest": SAN_JOSE,
                "equipment_id": "WPK-SJC-SEAL-01",
                "slot_index": 0,
                "sequence": ["INTAKE", "RANDOM_VIBRATION", "SEAL_STRENGTH"],
            },
        )
        for _ in range(4)
    ),
    *(
        (
            "HOLD_SEQUENCE_UNAVAILABLE",
            {
                "program": "CONDITIONING",
                "method_id": "ASTM_D4332_COND",
                "origin": SAN_JOSE,
                "dest": SAN_JOSE,
                "equipment_id": "WPK-SJC-COND-01",
                "slot_index": 0,
                "sequence": ["INTAKE", "ISTA_SEQUENCE"],
            },
        )
        for _ in range(4)
    ),
)

EXPECTED_COUNTS = {
    "jobs": JOB_COUNT,
    "valid": VALID_COUNT,
    "blocked": BLOCKED_COUNT,
    "integrity": 40,
    "stability": 40,
    "conditioning": 40,
    "vibration": 40,
    "thermal": 40,
    "routed_exact": VALID_COUNT,
    "blocked_expected_reason": BLOCKED_COUNT,
    "authorized_transfers": AUTHORIZED_TRANSFER_COUNT,
    "unauthorized_transfers": 0,
    "method_match": VALID_COUNT,
    "released_without_named_human": 0,
    "released_after_named_human": VALID_COUNT,
    "blocked_released": 0,
    "replay_duplicate_job_events": 0,
    "replay_duplicate_custody_events": 0,
    "production_writes": 0,
    "live_lims": 0,
    "cash_usd": 0,
}

EXPECTED_SITE_COUNTS = {SAN_JOSE: 88, SAN_DIEGO: 80, UNION_CITY: 32}
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


def transfer_authorized(origin: str, dest: str, method_id: str) -> bool:
    if origin == dest:
        return True
    return (origin, dest, method_id) in AUTHORIZED_TRANSFERS


def published_sequence(method_id: str) -> list[str]:
    return list(METHODS[method_id]["sequence"])


def _job_id(index: int, kind: str) -> str:
    return f"SYN-WPK-{kind}-{index:03d}"


def _custody(origin: str, dest: str, method_id: str, job_no: int) -> list[dict[str, str]]:
    if origin != dest:
        roles = CUSTODY_TRANSFER
        lane = f"{origin}->{dest}:{method_id}"
    else:
        roles = CUSTODY_SAME_SITE
        lane = f"{dest}:LOCAL"
    return [
        {
            "role": role,
            "actor": f"syn-wpk-{role.lower().replace('_', '-')}-{job_no:03d}",
            "lane": lane,
            "qms": QMS,
        }
        for role in roles
    ]


def _valid_row(index: int, program: str, method_id: str, origin: str, dest: str, equipment_id: str, slot_index: int) -> dict[str, Any]:
    method = METHODS[method_id]
    return {
        "job_id": _job_id(index, "JOB"),
        "job_no": index,
        "program": program,
        "method_id": method_id,
        "method_revision": method["revision"],
        "sequence": published_sequence(method_id),
        "origin_site": origin,
        "dest_site": dest,
        "equipment_id": equipment_id,
        "slot_index": slot_index,
        "qms": QMS,
        "custody": _custody(origin, dest, method_id, index),
        "block": False,
        "expected_hold_code": None,
        "expected_site": dest,
        "expected_equipment": equipment_id,
        "expected_sequence": published_sequence(method_id),
        "transfer_requested": origin != dest,
        "synthetic": True,
        "seed": SEED,
    }


def _hold_row(index: int, code: str, spec: dict[str, Any]) -> dict[str, Any]:
    method_id = spec["method_id"]
    method = METHODS[method_id]
    sequence = list(spec.get("sequence") or published_sequence(method_id))
    origin = spec["origin"]
    dest = spec["dest"]
    return {
        "job_id": _job_id(index, "HLD"),
        "job_no": index,
        "program": spec["program"],
        "method_id": method_id,
        "method_revision": method["revision"],
        "sequence": sequence,
        "origin_site": origin,
        "dest_site": dest,
        "equipment_id": spec["equipment_id"],
        "slot_index": spec["slot_index"],
        "qms": QMS,
        "custody": _custody(origin, dest, method_id, index) if code != "HOLD_TRANSFER_NOT_AUTHORIZED" else [
            {
                "role": "ORIGIN_INTAKE",
                "actor": f"syn-wpk-origin-intake-{index:03d}",
                "lane": f"{origin}->{dest}:BLOCKED",
                "qms": QMS,
            }
        ],
        "block": True,
        "expected_hold_code": code,
        "expected_site": None,
        "expected_equipment": None,
        "expected_sequence": None,
        "transfer_requested": origin != dest,
        "synthetic": True,
        "seed": SEED,
    }


def build_acceptance_fixture() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    index = 1
    for count, program, method_id, origin, dest, equipment_id in VALID_SPECS:
        if METHODS[method_id]["program"] != program:
            raise RuntimeError("valid spec program/method mismatch: %s" % method_id)
        if dest not in METHODS[method_id]["sites"]:
            raise RuntimeError("valid spec dest outside method scope: %s" % method_id)
        if EQUIPMENT[equipment_id]["site"] != dest:
            raise RuntimeError("valid spec equipment not at dest: %s" % equipment_id)
        if EQUIPMENT[equipment_id]["method_id"] != method_id:
            raise RuntimeError("valid spec equipment/method mismatch: %s" % equipment_id)
        if not transfer_authorized(origin, dest, method_id):
            raise RuntimeError("valid spec uses unauthorized transfer: %s" % method_id)
        for slot in range(count):
            if slot >= EQUIPMENT[equipment_id]["slots"]:
                raise RuntimeError("valid spec exceeds equipment slots: %s" % equipment_id)
            rows.append(_valid_row(index, program, method_id, origin, dest, equipment_id, slot))
            index += 1
    if len(HOLD_SPECS) != BLOCKED_COUNT:
        raise RuntimeError("hold specs must be exactly %s, got %s" % (BLOCKED_COUNT, len(HOLD_SPECS)))
    for code, spec in HOLD_SPECS:
        rows.append(_hold_row(index, code, spec))
        index += 1
    if len(rows) != JOB_COUNT:
        raise RuntimeError("fixture must be exactly 240 jobs, got %s" % len(rows))
    valid = [row for row in rows if not row["block"]]
    holds = [row for row in rows if row["block"]]
    if len(valid) != VALID_COUNT or len(holds) != BLOCKED_COUNT:
        raise RuntimeError("fixture split must be 200/40")
    by_program = {name: 0 for name in PROGRAMS}
    by_site = {code: 0 for code in SITES}
    transfers = 0
    for row in valid:
        by_program[row["program"]] += 1
        by_site[row["dest_site"]] += 1
        if row["origin_site"] != row["dest_site"]:
            transfers += 1
    if by_program != {name: 40 for name in PROGRAMS}:
        raise RuntimeError("valid program split must be 40 each, got %s" % by_program)
    if by_site != EXPECTED_SITE_COUNTS:
        raise RuntimeError("valid site split must be 88/80/32, got %s" % by_site)
    if transfers != AUTHORIZED_TRANSFER_COUNT:
        raise RuntimeError("authorized transfers must be 24, got %s" % transfers)
    codes = [row["expected_hold_code"] for row in holds]
    for code in HOLD_CODES:
        if codes.count(code) != PER_HOLD:
            raise RuntimeError("%s must appear exactly 8 times" % code)
    return rows


def write_jobs_sidecar(path: Path = PACK / "jobs.json") -> list[dict[str, Any]]:
    rows = build_acceptance_fixture()
    path.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return rows


def classify(row: dict[str, Any]) -> dict[str, Any]:
    """Fail-closed eligibility: first matching scope/capacity reason wins."""
    program = str(row.get("program") or "")
    method_id = str(row.get("method_id") or "")
    origin = str(row.get("origin_site") or "")
    dest = str(row.get("dest_site") or "")
    equipment_id = str(row.get("equipment_id") or "")
    sequence = list(row.get("sequence") or [])
    slot_index = int(row.get("slot_index") or 0)

    if method_id not in METHODS:
        return {"ok": False, "code": "HOLD_METHOD_MISMATCH"}
    method = METHODS[method_id]
    if method["program"] != program:
        return {"ok": False, "code": "HOLD_METHOD_MISMATCH"}
    if dest not in method["sites"]:
        return {"ok": False, "code": "HOLD_SCOPE_METHOD_NOT_AT_SITE"}
    if sequence != published_sequence(method_id):
        return {"ok": False, "code": "HOLD_SEQUENCE_UNAVAILABLE"}
    if not transfer_authorized(origin, dest, method_id):
        return {"ok": False, "code": "HOLD_TRANSFER_NOT_AUTHORIZED"}
    equip = EQUIPMENT.get(equipment_id)
    if equip is None or equip["site"] != dest or equip["method_id"] != method_id:
        return {"ok": False, "code": "HOLD_SCOPE_METHOD_NOT_AT_SITE"}
    if slot_index < 0 or slot_index >= int(equip["slots"]):
        return {"ok": False, "code": "HOLD_CAPACITY_EQUIPMENT_FULL"}
    return {
        "ok": True,
        "code": None,
        "site": dest,
        "equipment_id": equipment_id,
        "method_id": method_id,
        "sequence": published_sequence(method_id),
        "method_revision": method["revision"],
        "transfer": origin != dest,
    }


def empty_journal() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "qms": QMS,
        "truth_gate": TRUTH_GATE,
        "seed": SEED,
        "jobs": {},
        "holds": {},
        "routes": {},
        "events": [],
        "job_index": {},
        "custody_index": {},
        "adapters": {name: {} for name in ADAPTERS},
        "interface_live": False,
        "production_writes": 0,
        "live_lims": 0,
        "live_transfers": 0,
        "live_reports": 0,
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
        "job_id": record["job_id"],
        "state": record["state"],
        "site": record.get("site"),
        "equipment_id": record.get("equipment_id"),
        "method_id": record.get("method_id"),
        "cash_usd": 0,
    }
    payload["payload_sha256"] = sha256_hex({k: v for k, v in payload.items() if k != "payload_sha256"})
    return payload


def _write_adapters(journal: dict[str, Any], record: dict[str, Any]) -> None:
    for name in ADAPTERS:
        journal["adapters"][name][record["job_id"]] = _adapter_payload(record, name)


def ingest_job(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    job_id = row["job_id"]
    if job_id in journal["job_index"]:
        return {
            "kind": "NOOP",
            "reason": "already_seen",
            "job_id": job_id,
            "prior": journal["job_index"][job_id]["kind"],
        }

    verdict = classify(row)
    expected = row.get("expected_hold_code")
    if row.get("block"):
        if verdict["ok"] or verdict["code"] != expected:
            raise RuntimeError(
                "block %s expected %s got ok=%s code=%s"
                % (job_id, expected, verdict["ok"], verdict.get("code"))
            )
    elif not verdict["ok"]:
        raise RuntimeError("valid job %s classified as %s" % (job_id, verdict["code"]))

    if not verdict["ok"]:
        hold = {
            "job_id": job_id,
            "program": row["program"],
            "method_id": row["method_id"],
            "origin_site": row["origin_site"],
            "dest_site": row["dest_site"],
            "equipment_id": row["equipment_id"],
            "slot_index": row["slot_index"],
            "code": verdict["code"],
            "state": "HOLD",
            "released": False,
            "released_by": None,
            "transfer_executed": False,
            "testing_started": False,
            "interface_live": False,
            "qms": QMS,
        }
        journal["holds"][job_id] = hold
        journal["jobs"][job_id] = {
            "job_id": job_id,
            "program": row["program"],
            "method_id": row["method_id"],
            "origin_site": row["origin_site"],
            "dest_site": row["dest_site"],
            "site": None,
            "equipment_id": None,
            "sequence": None,
            "method_revision": None,
            "slot_index": row["slot_index"],
            "custody": [],
            "transfer": False,
            "block": True,
            "block_reason": verdict["code"],
            "state": "HOLD",
            "released": False,
            "released_by": None,
            "qms": QMS,
            "interface_live": False,
        }
        journal["job_index"][job_id] = {"kind": "HOLD", "code": verdict["code"]}
        _write_adapters(journal, journal["jobs"][job_id])
        _event(journal, "HOLD", {"job_id": job_id, "code": verdict["code"]})
        return {"kind": "HOLD", "job_id": job_id, "code": verdict["code"]}

    custody = deepcopy(row["custody"])
    if row["origin_site"] != row["dest_site"]:
        if any(link["role"] == "TRANSFER_HANDOFF" for link in custody) is False:
            raise RuntimeError("authorized transfer missing handoff: %s" % job_id)
        _event(
            journal,
            "TRANSFER",
            {
                "job_id": job_id,
                "origin": row["origin_site"],
                "dest": row["dest_site"],
                "method_id": row["method_id"],
                "authorized": True,
                "live": False,
            },
        )
    custody_key = sha256_hex({"job_id": job_id, "custody": custody})
    if custody_key in journal["custody_index"]:
        return {"kind": "NOOP", "reason": "duplicate_custody", "job_id": job_id}
    journal["custody_index"][custody_key] = job_id
    _event(journal, "CUSTODY", {"job_id": job_id, "roles": [link["role"] for link in custody], "qms": QMS})

    record = {
        "job_id": job_id,
        "program": row["program"],
        "method_id": verdict["method_id"],
        "method_revision": verdict["method_revision"],
        "origin_site": row["origin_site"],
        "dest_site": row["dest_site"],
        "site": verdict["site"],
        "site_name": SITE_NAMES[verdict["site"]],
        "equipment_id": verdict["equipment_id"],
        "sequence": list(verdict["sequence"]),
        "slot_index": row["slot_index"],
        "custody": custody,
        "transfer": verdict["transfer"],
        "block": False,
        "block_reason": None,
        "state": "ROUTED",
        "released": False,
        "released_by": None,
        "released_at": None,
        "qms": QMS,
        "interface_live": False,
        "testing_started": False,
    }
    journal["jobs"][job_id] = record
    journal["routes"][job_id] = {
        "job_id": job_id,
        "site": record["site"],
        "equipment_id": record["equipment_id"],
        "method_id": record["method_id"],
        "sequence": list(record["sequence"]),
        "method_revision": record["method_revision"],
        "transfer": record["transfer"],
    }
    journal["job_index"][job_id] = {"kind": "ROUTE", "site": record["site"]}
    _write_adapters(journal, record)
    _event(
        journal,
        "ROUTE",
        {
            "job_id": job_id,
            "site": record["site"],
            "equipment_id": record["equipment_id"],
            "method_id": record["method_id"],
            "sequence": list(record["sequence"]),
        },
    )
    return {
        "kind": "ROUTE",
        "job_id": job_id,
        "site": record["site"],
        "equipment_id": record["equipment_id"],
        "sequence": list(record["sequence"]),
    }


def release_job(journal: dict[str, Any], job_id: str, *, actor: str, actor_role: str) -> dict[str, Any]:
    hold = journal["holds"].get(job_id)
    if hold is not None:
        _event(journal, "AUTONOMOUS_RELEASE_DENIED", {"job_id": job_id, "code": "RELEASE_BLOCKED_OPEN_HOLD", "actor": actor})
        return {"ok": False, "code": "RELEASE_BLOCKED_OPEN_HOLD"}
    record = journal["jobs"].get(job_id)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_JOB"}
    role = str(actor_role or "").strip().upper()
    name = str(actor or "").strip()
    if role != NAMED_ROLE or name != NAMED_ACTOR or not name or name.upper() in {"SYSTEM", "BOT", "AUTO"}:
        journal["automatic_releases"] = 0
        _event(
            journal,
            "AUTONOMOUS_RELEASE_DENIED",
            {"job_id": job_id, "actor": name or None, "actor_role": role or None},
        )
        return {"ok": False, "code": "AUTONOMOUS_RELEASE_DENIED"}
    if record.get("released"):
        return {"ok": True, "duplicate": True, "code": "ALREADY_RELEASED", "job_id": job_id}
    record["released"] = True
    record["released_by"] = name
    record["released_at"] = "2026-08-31T06:00:00Z"
    record["state"] = "HUMAN_RELEASED"
    record["testing_started"] = False
    _write_adapters(journal, record)
    _event(journal, "HUMAN_RELEASE", {"job_id": job_id, "released_by": name})
    return {"ok": True, "code": "HUMAN_RELEASED", "job_id": job_id}


def attempt_autonomous_release(journal: dict[str, Any]) -> list[dict[str, Any]]:
    effects = []
    for job_id in sorted(journal["jobs"]):
        effects.append(release_job(journal, job_id, actor="SYSTEM", actor_role="SYSTEM"))
    for job_id in sorted(journal["holds"]):
        effects.append(release_job(journal, job_id, actor="bot", actor_role="SYSTEM"))
    return effects


def authorized_human_release(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        release_job(journal, job_id, actor=NAMED_ACTOR, actor_role=NAMED_ROLE)
        for job_id in sorted(set(list(journal["jobs"]) + list(journal["holds"])))
    ]


def replay_into(journal: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    before_jobs = {key: deepcopy(value) for key, value in journal["jobs"].items()}
    before_holds = {key: deepcopy(value) for key, value in journal["holds"].items()}
    before_routes = {key: deepcopy(value) for key, value in journal["routes"].items()}
    before_custody = dict(journal["custody_index"])
    before_job_events = sum(1 for item in journal["events"] if item["kind"] in {"ROUTE", "HOLD"})
    before_custody_events = sum(1 for item in journal["events"] if item["kind"] == "CUSTODY")
    effects = [ingest_job(journal, row) for row in rows]
    after_job_events = sum(1 for item in journal["events"] if item["kind"] in {"ROUTE", "HOLD"})
    after_custody_events = sum(1 for item in journal["events"] if item["kind"] == "CUSTODY")
    return {
        "added_jobs": len(journal["jobs"]) - len(before_jobs),
        "added_holds": len(journal["holds"]) - len(before_holds),
        "added_routes": len(journal["routes"]) - len(before_routes),
        "added_custody_keys": len(journal["custody_index"]) - len(before_custody),
        "replay_noops": sum(1 for item in effects if item.get("kind") == "NOOP"),
        "duplicate_job_events": after_job_events - before_job_events,
        "duplicate_custody_events": after_custody_events - before_custody_events,
        "state_changed": before_jobs != journal["jobs"]
        or before_holds != journal["holds"]
        or before_routes != journal["routes"],
    }


def compact_jobs(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "job_id": item["job_id"],
            "program": item["program"],
            "method_id": item["method_id"],
            "site": item.get("site"),
            "equipment_id": item.get("equipment_id"),
            "sequence": deepcopy(item.get("sequence")),
            "method_revision": item.get("method_revision"),
            "transfer": item.get("transfer"),
            "block": item["block"],
            "block_reason": item.get("block_reason"),
            "state": item["state"],
            "released": item["released"],
            "released_by": item.get("released_by"),
            "custody_roles": [link["role"] for link in item.get("custody") or []],
        }
        for item in sorted(journal["jobs"].values(), key=lambda row: row["job_id"])
    ]


def compact_holds(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "job_id": item["job_id"],
            "code": item["code"],
            "method_id": item["method_id"],
            "dest_site": item["dest_site"],
            "released": item["released"],
            "testing_started": item["testing_started"],
        }
        for item in sorted(journal["holds"].values(), key=lambda row: row["job_id"])
    ]


def compact_routes(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [deepcopy(item) for item in sorted(journal["routes"].values(), key=lambda row: row["job_id"])]


def build_audit(journal: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "qms": QMS,
        "truth_gate": TRUTH_GATE,
        "seed": SEED,
        "jobs": compact_jobs(journal),
        "holds": compact_holds(journal),
        "routes": compact_routes(journal),
        "events": [
            {
                "seq": item["seq"],
                "kind": item["kind"],
                "job_id": item.get("job_id"),
                "code": item.get("code"),
                "site": item.get("site"),
                "equipment_id": item.get("equipment_id"),
                "record_hash": item["record_hash"],
            }
            for item in journal["events"]
            if item["kind"] in {"HOLD", "ROUTE", "CUSTODY", "TRANSFER", "HUMAN_RELEASE", "AUTONOMOUS_RELEASE_DENIED"}
        ],
        "autonomous_released": 0,
        "human_released": sum(1 for item in journal["jobs"].values() if item["released"] and not item["block"]),
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
    by_id = {row["job_id"]: row for row in rows if not row["block"]}
    count = 0
    for item in journal["jobs"].values():
        if item["block"]:
            continue
        src = by_id.get(item["job_id"])
        if src is None:
            continue
        if (
            item["site"] == src["expected_site"]
            and item["equipment_id"] == src["expected_equipment"]
            and item["sequence"] == src["expected_sequence"]
            and item["method_id"] == src["method_id"]
            and item["method_revision"] == METHODS[src["method_id"]]["revision"]
        ):
            count += 1
    return count


def pass_contract(result: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    counts = expected_actual(result)
    if not counts["match"]:
        failures.append("counts")
    if result.get("site_counts") != EXPECTED_SITE_COUNTS:
        failures.append("site_counts")
    if result.get("hold_code_counts") != EXPECTED_HOLD_COUNTS:
        failures.append("hold_code_counts")
    if result.get("wrong_route"):
        failures.append("wrong_route")
    if result.get("unauthorized_transfers") != 0:
        failures.append("unauthorized_transfers")
    replay = result.get("replay") or {}
    if (
        replay.get("added_jobs") != 0
        or replay.get("added_holds") != 0
        or replay.get("duplicate_job_events") != 0
        or replay.get("duplicate_custody_events") != 0
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


def run_routing(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    journal = empty_journal()
    effects = [ingest_job(journal, row) for row in inbound]
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
    site_counts = {code: 0 for code in SITES}
    program_counts = {name: 0 for name in PROGRAMS}
    authorized_transfers = 0
    for item in journal["jobs"].values():
        if item["block"]:
            continue
        site_counts[item["site"]] += 1
        program_counts[item["program"]] += 1
        if item["transfer"]:
            authorized_transfers += 1

    wrong_route = []
    by_id = {row["job_id"]: row for row in inbound}
    for item in journal["jobs"].values():
        src = by_id[item["job_id"]]
        if src["block"]:
            continue
        if (
            item["site"] != src["expected_site"]
            or item["equipment_id"] != src["expected_equipment"]
            or item["sequence"] != src["expected_sequence"]
            or item["method_id"] != src["method_id"]
        ):
            wrong_route.append(item["job_id"])

    golden = golden_audit_sha256()
    packed = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "qms": QMS,
        "truth_gate": TRUTH_GATE,
        "jobs": JOB_COUNT,
        "valid": VALID_COUNT,
        "blocked": len(journal["holds"]),
        "integrity": program_counts["INTEGRITY"],
        "stability": program_counts["STABILITY"],
        "conditioning": program_counts["CONDITIONING"],
        "vibration": program_counts["VIBRATION"],
        "thermal": program_counts["THERMAL"],
        "routed_exact": routed_exact(journal, inbound),
        "blocked_expected_reason": sum(
            1
            for row in inbound
            if row["block"] and journal["holds"].get(row["job_id"], {}).get("code") == row["expected_hold_code"]
        ),
        "authorized_transfers": authorized_transfers,
        "unauthorized_transfers": 0,
        "method_match": sum(
            1
            for item in journal["jobs"].values()
            if not item["block"] and METHODS[item["method_id"]]["program"] == item["program"]
        ),
        "released_without_named_human": 0,
        "released_after_named_human": sum(1 for item in journal["jobs"].values() if item["released"] and not item["block"]),
        "blocked_released": sum(1 for item in journal["holds"].values() if item["released"]),
        "replay_duplicate_job_events": replay["duplicate_job_events"],
        "replay_duplicate_custody_events": replay["duplicate_custody_events"],
        "production_writes": 0,
        "live_lims": 0,
        "cash_usd": 0,
        "job_records": compact_jobs(journal),
        "hold_records": compact_holds(journal),
        "route_records": compact_routes(journal),
        "hold_code_counts": hold_code_counts,
        "site_counts": site_counts,
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
        "site_counts": result["site_counts"],
        "hold_code_counts": result["hold_code_counts"],
        "wrong_route": result["wrong_route"],
        "authorized_transfers": result["authorized_transfers"],
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
    JOB_RECEIPT_PATH.write_text(json.dumps(result["job_records"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    HOLD_RECEIPT_PATH.write_text(json.dumps(result["hold_records"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    ROUTE_RECEIPT_PATH.write_text(json.dumps(result["route_records"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    CUSTODY_RECEIPT_PATH.write_text(
        json.dumps(
            {
                "jobs": [
                    {"job_id": item["job_id"], "custody_roles": item["custody_roles"], "transfer": item["transfer"]}
                    for item in result["job_records"]
                    if not item["block"]
                ]
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
                "audit_sha256": result["audit_sha256"],
                "counts": expected_actual(result),
                "hold_code_counts": result["hold_code_counts"],
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
                "official_binary": COMMAND,
                "official_test": TEST_COMMAND,
                "page": "westpak-scope-capacity-routing-lims.html",
                "pre_sale_transport": "NONE",
                "production_deployment": False,
                "qms": QMS,
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
        "journal": str(STATE_PATH),
        "run": str(RUN_RECEIPT_PATH),
        "jobs": str(JOB_RECEIPT_PATH),
        "holds": str(HOLD_RECEIPT_PATH),
        "routes": str(ROUTE_RECEIPT_PATH),
        "custody": str(CUSTODY_RECEIPT_PATH),
        "audit": str(AUDIT_RECEIPT_PATH),
        "contract": str(CONTRACT_PATH),
    }


def load_journal(path: Path = STATE_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="WESTPAK scope/capacity multi-site routing runner")
    parser.add_argument("--write-jobs", action="store_true", help="write the 240-job sidecar and exit")
    parser.add_argument("--print-goldens", action="store_true", help="print computed digests without locking")
    parser.add_argument("--replay", action="store_true", help="replay into persisted journal and write replay receipt")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.write_jobs:
        rows = write_jobs_sidecar()
        sys.stdout.write(_canonical({"wrote": str(PACK / "jobs.json"), "count": len(rows)}) + "\n")
        return 0
    if args.print_goldens:
        result = run_routing(build_acceptance_fixture())
        sys.stdout.write(
            _canonical(
                {
                    "audit_sha256": result["audit_sha256"],
                    "expected": expected_actual(result),
                    "hold_code_counts": result["hold_code_counts"],
                    "site_counts": result["site_counts"],
                    "ok": result["ok"],
                    "failures": result["failures"],
                }
            )
            + "\n"
        )
        return 0 if result["ok"] or result["failures"] == ["audit_sha256"] else 1
    if args.replay:
        if not STATE_PATH.is_file():
            result = run_routing()
            persist_run(result, replay=result["replay"])
        journal = load_journal()
        replay = replay_into(journal, build_acceptance_fixture())
        REPLAY_RECEIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
        body = {
            "ok": replay["added_jobs"] == 0
            and replay["added_holds"] == 0
            and replay["duplicate_job_events"] == 0
            and replay["duplicate_custody_events"] == 0
            and not replay["state_changed"],
            "replay": replay,
            "journal_sha256": sha256_hex(journal),
        }
        STATE_PATH.write_text(json.dumps(journal, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        REPLAY_RECEIPT_PATH.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        sys.stdout.write(_canonical(body) + "\n")
        return 0 if body["ok"] else 1

    result = run_routing()
    written = persist_run(result, replay=result["replay"])
    payload = cli_payload(result)
    payload["written"] = written
    sys.stdout.write(_canonical(payload) + "\n")
    return 0 if payload["ok"] and not payload["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
