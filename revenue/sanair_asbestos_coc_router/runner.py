#!/usr/bin/env python3
"""SanAir Rapid-TAT Asbestos COC Router.

Demand: sanair-asbestos-coc-router-lims-01
Buyer pairing: SanAir Technologies / Sandra C. Sobrino

Routes signed synthetic asbestos COCs across Richmond, Cincinnati, and
Boston by lab/method capability, starts TAT clocks from fixture receipt,
preserves recipient permissions and written amendment lineage, and
releases only after a named human. Adapters stay synthetic and
read-only. No live sample or test action. No outreach. cash_usd=0.

Acceptance: 360 frozen synthetic COCs — 300 valid, 60 predefined
missing signatures, duplicate IDs, invalid lab/method combinations, or
cutoff/TAT errors. PASS only when every valid order enters the
designated lab exactly once with field parity, all 60 block with the
exact code, TAT clocks follow receipt rules, permissions match the COC,
replay is idempotent, and release stays named-human only.

Official command:
    python3 sanair_asbestos_coc_router.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SOURCE_PATH = HERE / "source.json"
FIXTURE_PATH = HERE / "fixture.json"
RECEIPT_DIR = HERE / "receipts"

DEMAND_ID = "sanair-asbestos-coc-router-lims-01"
SCHEMA = "commons-sanair-asbestos-coc-router-lims/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
BUYER = "SanAir Technologies / Sandra C. Sobrino"
HUMAN_RELEASER = "SYN-SANAIR-RELEASE-OFFICER"
HUMAN_ROLE = "RELEASE_OFFICER"
EXCEPTION_OWNER_ROLE = "ASBESTOS_INTAKE_LEAD"
EXCEPTION_OWNER_DESK = "RAPID_TAT_COC_ROUTER"

VALID_COUNT = 300
HOLD_PER_CODE = 15
HOLD_CODES = (
    "HOLD_MISSING_SIGNATURE",
    "HOLD_DUPLICATE_SAMPLE_ID",
    "HOLD_INVALID_LAB_METHOD",
    "HOLD_TAT_CUTOFF",
)
EXCEPTION_COUNT = HOLD_PER_CODE * len(HOLD_CODES)
INPUT_COUNT = VALID_COUNT + EXCEPTION_COUNT

RECIPIENT_ROLES = ("CLIENT", "CONSULTANT", "OWNER")
PERMISSION_BY_ROLE = {
    "CLIENT": "VIEW_REPORT",
    "CONSULTANT": "VIEW_REPORT",
    "OWNER": "VIEW_AND_AMEND",
}
SOURCE_KIND_CYCLE = ("COC_PDF", "EMAIL", "FAX")
AUTONOMOUS_ACTORS = frozenset({"SYSTEM", "AUTO", "AUTONOMOUS", "BOT", "MACHINE", "robot"})

GOLDEN_AUDIT_SHA256 = "7e90246b6ab1cfaf8b5fac41669f968fa3cd2c8ed8c27381835387ea407483cf"
GOLDEN_LINEAGE_SHA256 = "1d081f6acc19962337dadba0b2cfbcdb0a1c51e408d54d4533d1695d6b12dd27"
GOLDEN_FIXTURE_SHA256 = "962eca037242f35e8fa3f2253f0d6a4bcdbc983dfca23e41511ba4effcfe4ef7"

EXPECTED_COUNTS = {
    "input_cocs": INPUT_COUNT,
    "valid": VALID_COUNT,
    "exceptions": EXCEPTION_COUNT,
    "routed": VALID_COUNT,
    "holds": EXCEPTION_COUNT,
    "hold_missing_signature": HOLD_PER_CODE,
    "hold_duplicate_sample_id": HOLD_PER_CODE,
    "hold_invalid_lab_method": HOLD_PER_CODE,
    "hold_tat_cutoff": HOLD_PER_CODE,
    "lab_ric": 100,
    "lab_cin": 100,
    "lab_bos": 100,
    "duplicate_routes": 0,
    "permission_mismatches": 0,
    "tat_clock_failures": 0,
    "autonomous_released": 0,
    "human_released": VALID_COUNT,
    "production_writes": 0,
    "live_sample_actions": 0,
    "cash_usd": 0,
}

PARITY_FIELDS = (
    "coc_id",
    "sample_id",
    "client_id",
    "project_id",
    "matrix",
    "method",
    "designated_lab",
    "tat_code",
    "received_at",
    "recipient_name",
    "recipient_role",
    "report_permission",
    "amendment_channel",
    "source_kind",
    "source_coordinate",
    "source_hash",
)

VALID_PLANS = (
    {
        "lab": "RIC",
        "method": "PLM_BULK_EPA600",
        "tat_code": "SAME_DAY",
        "received_at": "2026-08-31T09:00:00-04:00",
        "matrix": "BULK",
    },
    {
        "lab": "RIC",
        "method": "PCM_AIR_NIOSH7400",
        "tat_code": "RUSH_24H",
        "received_at": "2026-08-31T14:00:00-04:00",
        "matrix": "AIR",
    },
    {
        "lab": "CIN",
        "method": "TEM_AIR_AHERA",
        "tat_code": "RUSH_24H",
        "received_at": "2026-08-31T14:00:00-04:00",
        "matrix": "AIR",
    },
    {
        "lab": "CIN",
        "method": "TEM_BULK_CHATFIELD",
        "tat_code": "RUSH_48H",
        "received_at": "2026-08-31T16:00:00-04:00",
        "matrix": "BULK",
    },
    {
        "lab": "BOS",
        "method": "PLM_SOIL_CARB435",
        "tat_code": "RUSH_48H",
        "received_at": "2026-08-31T16:00:00-04:00",
        "matrix": "SOIL",
    },
    {
        "lab": "BOS",
        "method": "TEM_DUST_ASTM_D5755",
        "tat_code": "STANDARD",
        "received_at": "2026-08-31T18:00:00-04:00",
        "matrix": "DUST",
    },
)


def _load_source() -> dict[str, Any]:
    return json.loads(SOURCE_PATH.read_text(encoding="utf-8"))


SOURCE = _load_source()
LABS: dict[str, dict[str, Any]] = SOURCE["labs"]
METHODS: dict[str, dict[str, Any]] = SOURCE["methods"]
TAT_RULES: dict[str, dict[str, Any]] = SOURCE["tat_rules"]
SOURCE_KINDS: dict[str, dict[str, Any]] = SOURCE["source_kinds"]


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


def parse_stamp(value: str) -> datetime:
    return datetime.fromisoformat(_text(value))


def format_stamp(value: datetime) -> str:
    stamp = value.isoformat(timespec="seconds")
    return stamp


def source_coordinate(kind: str, index: int) -> str:
    prefix = SOURCE_KINDS[kind]["coordinate_prefix"]
    return f"{prefix}{index:04d}"


def source_payload(coc: dict[str, Any]) -> dict[str, Any]:
    return {
        "amendment_channel": coc.get("amendment_channel"),
        "client_id": coc.get("client_id"),
        "coc_id": coc.get("coc_id"),
        "designated_lab": coc.get("designated_lab"),
        "method": coc.get("method"),
        "project_id": coc.get("project_id"),
        "received_at": coc.get("received_at"),
        "recipient_name": coc.get("recipient_name"),
        "sample_id": coc.get("sample_id"),
        "source_coordinate": coc.get("source_coordinate"),
        "source_kind": coc.get("source_kind"),
        "tat_code": coc.get("tat_code"),
    }


def compute_source_hash(coc: dict[str, Any]) -> str:
    return sha256_hex(source_payload(coc))


def route_id(sample_id: str, source_hash: str, lab: str) -> str:
    digest = sha256_hex(
        {
            "demand_id": DEMAND_ID,
            "lab": lab,
            "sample_id": sample_id,
            "source_hash": source_hash,
        }
    )
    return f"SANAIR-RTE-{lab}-{digest[:12]}"


def tat_clock(received_at: str, tat_code: str) -> dict[str, Any]:
    rule = TAT_RULES[tat_code]
    start = parse_stamp(received_at)
    due = start + timedelta(hours=int(rule["hours"]))
    return {
        "basis": "FIXTURE_RECEIPT",
        "clock_start": received_at,
        "due_at": format_stamp(due),
        "hours": int(rule["hours"]),
        "tat_code": tat_code,
    }


def local_receipt_minutes(received_at: str) -> int:
    stamp = parse_stamp(received_at)
    return stamp.hour * 60 + stamp.minute


def cutoff_minutes(tat_code: str) -> int | None:
    cutoff = TAT_RULES[tat_code]["cutoff_local"]
    if not cutoff:
        return None
    hour, minute = (int(part) for part in str(cutoff).split(":", 1))
    return hour * 60 + minute


def cutoff_violated(received_at: str, tat_code: str) -> bool:
    limit = cutoff_minutes(tat_code)
    if limit is None:
        return False
    return local_receipt_minutes(received_at) > limit


def permissions_match(row: dict[str, Any]) -> bool:
    role = _text(row.get("recipient_role"))
    return (
        _text(row.get("recipient_name")) == _text(row.get("report_to"))
        and role in PERMISSION_BY_ROLE
        and _text(row.get("report_permission")) == PERMISSION_BY_ROLE[role]
        and _text(row.get("amendment_channel")) in {"EMAIL", "FAX"}
    )


def lab_method_capable(lab: str, method: str, tat_code: str) -> bool:
    lab_spec = LABS.get(lab)
    method_spec = METHODS.get(method)
    tat_spec = TAT_RULES.get(tat_code)
    if lab_spec is None or method_spec is None or tat_spec is None:
        return False
    return (
        method in lab_spec["methods"]
        and tat_code in lab_spec["tat_codes"]
        and lab in method_spec["labs"]
        and tat_code in method_spec["tat_codes"]
        and lab in tat_spec["labs"]
    )


def _recipient(index: int) -> dict[str, str]:
    role = RECIPIENT_ROLES[index % len(RECIPIENT_ROLES)]
    name = f"SYN-SANAIR-RECIPIENT-{(index % 24) + 1:02d}"
    return {
        "recipient_name": name,
        "recipient_role": role,
        "report_permission": PERMISSION_BY_ROLE[role],
        "report_to": name,
        "amendment_channel": "EMAIL" if index % 2 == 0 else "FAX",
    }


def _amendment(index: int, prior_hash: str) -> dict[str, Any] | None:
    if index % 10 != 0:
        return None
    channel = "EMAIL" if index % 20 == 0 else "FAX"
    body = {
        "amendment_id": f"SANAIR-AMD-{index + 1:04d}",
        "channel": channel,
        "kind": "WRITTEN",
        "prior_hash": prior_hash,
        "text": f"SYN written {channel.lower()} amendment for slot {index + 1:04d}",
    }
    body["amendment_hash"] = sha256_hex(body)
    return body


def _base_valid(index: int) -> dict[str, Any]:
    plan = VALID_PLANS[index % len(VALID_PLANS)]
    kind = SOURCE_KIND_CYCLE[index % len(SOURCE_KIND_CYCLE)]
    recipient = _recipient(index)
    row: dict[str, Any] = {
        "coc_id": f"SANAIR-COC-V-{index + 1:04d}",
        "expected_state": "ROUTED",
        "expected_hold_code": None,
        "sample_id": f"SANAIR-S-{index + 1:04d}",
        "client_id": f"SYN-SANAIR-CLIENT-{(index % 20) + 1:02d}",
        "project_id": f"SYN-SANAIR-PROJ-{(index % 30) + 1:02d}",
        "collected_at": "2026-08-30T08:15:00-04:00",
        "sampler_name": f"SYN-SANAIR-SAMPLER-{(index % 9) + 1:02d}",
        "sampler_signed": True,
        "relinquisher_signed": True,
        "matrix": plan["matrix"],
        "method": plan["method"],
        "designated_lab": plan["lab"],
        "tat_code": plan["tat_code"],
        "received_at": plan["received_at"],
        "received_by": "SYN-SANAIR-RECEIVING-01",
        "source_kind": kind,
        "source_coordinate": source_coordinate(kind, index + 1),
        **recipient,
        "amendment": None,
    }
    row["source_hash"] = compute_source_hash(row)
    row["amendment"] = _amendment(index, row["source_hash"])
    return row


def _exception_row(slot: int) -> dict[str, Any]:
    code = HOLD_CODES[slot // HOLD_PER_CODE]
    within = slot % HOLD_PER_CODE
    seed_index = VALID_COUNT + slot
    row = _base_valid(seed_index)
    row["coc_id"] = f"SANAIR-COC-E-{slot + 1:04d}"
    row["expected_state"] = "HOLD"
    row["expected_hold_code"] = code
    row["sample_id"] = f"SANAIR-E-{slot + 1:04d}"
    row["source_coordinate"] = source_coordinate(row["source_kind"], seed_index + 1)
    row["amendment"] = None

    if code == "HOLD_MISSING_SIGNATURE":
        if within % 2 == 0:
            row["sampler_signed"] = False
        else:
            row["relinquisher_signed"] = False
    elif code == "HOLD_DUPLICATE_SAMPLE_ID":
        row["sample_id"] = f"SANAIR-S-{(within % VALID_COUNT) + 1:04d}"
    elif code == "HOLD_INVALID_LAB_METHOD":
        mismatches = (
            {"lab": "RIC", "method": "TEM_AIR_AHERA", "tat_code": "RUSH_24H", "received_at": "2026-08-31T14:00:00-04:00", "matrix": "AIR"},
            {"lab": "CIN", "method": "PLM_SOIL_CARB435", "tat_code": "RUSH_48H", "received_at": "2026-08-31T16:00:00-04:00", "matrix": "SOIL"},
            {"lab": "BOS", "method": "PLM_BULK_EPA600", "tat_code": "STANDARD", "received_at": "2026-08-31T18:00:00-04:00", "matrix": "BULK"},
        )
        chosen = mismatches[within % len(mismatches)]
        row["designated_lab"] = chosen["lab"]
        row["method"] = chosen["method"]
        row["tat_code"] = chosen["tat_code"]
        row["received_at"] = chosen["received_at"]
        row["matrix"] = chosen["matrix"]
    elif code == "HOLD_TAT_CUTOFF":
        late = (
            {"lab": "RIC", "method": "PLM_BULK_EPA600", "tat_code": "SAME_DAY", "received_at": "2026-08-31T11:30:00-04:00", "matrix": "BULK"},
            {"lab": "RIC", "method": "PCM_AIR_NIOSH7400", "tat_code": "RUSH_24H", "received_at": "2026-08-31T16:05:00-04:00", "matrix": "AIR"},
            {"lab": "CIN", "method": "TEM_BULK_CHATFIELD", "tat_code": "RUSH_48H", "received_at": "2026-08-31T18:10:00-04:00", "matrix": "BULK"},
        )
        chosen = late[within % len(late)]
        row["designated_lab"] = chosen["lab"]
        row["method"] = chosen["method"]
        row["tat_code"] = chosen["tat_code"]
        row["received_at"] = chosen["received_at"]
        row["matrix"] = chosen["matrix"]
    else:
        raise RuntimeError("unmapped hold code %s" % code)

    row["source_hash"] = compute_source_hash(row)
    return row


def build_acceptance_fixture() -> list[dict[str, Any]]:
    rows = [_base_valid(i) for i in range(VALID_COUNT)]
    rows.extend(_exception_row(i) for i in range(EXCEPTION_COUNT))
    if len(rows) != INPUT_COUNT:
        raise RuntimeError("acceptance fixture must be exactly %s COCs" % INPUT_COUNT)
    valid = [row for row in rows if row["expected_state"] == "ROUTED"]
    holds = [row for row in rows if row["expected_state"] == "HOLD"]
    if len(valid) != VALID_COUNT or len(holds) != EXCEPTION_COUNT:
        raise RuntimeError("acceptance fixture split must be 300/60")
    codes = [row["expected_hold_code"] for row in holds]
    for code in HOLD_CODES:
        if codes.count(code) != HOLD_PER_CODE:
            raise RuntimeError("%s must appear exactly %s times" % (code, HOLD_PER_CODE))
    labs = [row["designated_lab"] for row in valid]
    if labs.count("RIC") != 100 or labs.count("CIN") != 100 or labs.count("BOS") != 100:
        raise RuntimeError("valid designated labs must be 100/100/100")
    return rows


def write_fixture(path: Path = FIXTURE_PATH) -> list[dict[str, Any]]:
    rows = build_acceptance_fixture()
    path.write_text(_canonical(rows) + "\n", encoding="utf-8")
    return rows


def load_fixture(path: Path = FIXTURE_PATH) -> list[dict[str, Any]]:
    if path.is_file():
        rows = json.loads(path.read_text(encoding="utf-8"))
        if len(rows) != INPUT_COUNT:
            raise RuntimeError("fixture.json must contain exactly %s COCs" % INPUT_COUNT)
        return rows
    return build_acceptance_fixture()


def fixture_sha256(rows: list[dict[str, Any]] | None = None) -> str:
    return sha256_hex(rows or load_fixture())


def empty_ledger() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "routes": {},
        "holds": [],
        "events": [],
        "sample_index": {},
        "source_index": {},
        "interface_live": False,
        "production_writes": 0,
        "live_sample_actions": 0,
        "live_reports": 0,
        "billing_writes": 0,
        "adapters": {
            "coc": "SIMULATED_READONLY",
            "email": "SIMULATED_READONLY",
            "fax": "SIMULATED_READONLY",
            "lims": "SIMULATED_READONLY",
            "instruments": "SIMULATED_READONLY",
            "reports": "SIMULATED_READONLY",
        },
    }


def _event(ledger: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    ledger["events"].append({"seq": len(ledger["events"]) + 1, "kind": kind, **deepcopy(payload)})


def classify_coc(row: dict[str, Any], ledger: dict[str, Any]) -> dict[str, Any]:
    if not _flag(row.get("sampler_signed")) or not _flag(row.get("relinquisher_signed")):
        return {"ok": False, "code": "HOLD_MISSING_SIGNATURE"}
    sample_id = _text(row.get("sample_id"))
    if sample_id in ledger["sample_index"]:
        return {"ok": False, "code": "HOLD_DUPLICATE_SAMPLE_ID"}
    lab = _text(row.get("designated_lab"))
    method = _text(row.get("method"))
    tat_code = _text(row.get("tat_code"))
    if not lab_method_capable(lab, method, tat_code):
        return {"ok": False, "code": "HOLD_INVALID_LAB_METHOD"}
    received_at = _text(row.get("received_at"))
    if not received_at or cutoff_violated(received_at, tat_code):
        return {"ok": False, "code": "HOLD_TAT_CUTOFF"}
    if not permissions_match(row):
        return {"ok": False, "code": "HOLD_PERMISSION_MISMATCH"}
    return {"ok": True}


def _hold(ledger: dict[str, Any], row: dict[str, Any], code: str) -> dict[str, Any]:
    hold = {
        "coc_id": _text(row.get("coc_id")),
        "sample_id": _text(row.get("sample_id")) or None,
        "code": code,
        "state": "HOLD",
        "owner_role": EXCEPTION_OWNER_ROLE,
        "owner_desk": EXCEPTION_OWNER_DESK,
        "designated_lab": _text(row.get("designated_lab")),
        "method": _text(row.get("method")),
        "tat_code": _text(row.get("tat_code")),
        "source_kind": _text(row.get("source_kind")),
        "source_coordinate": _text(row.get("source_coordinate")),
        "source_hash": _text(row.get("source_hash")) or compute_source_hash(row),
        "released": False,
    }
    fingerprint = sha256_hex(
        {key: hold[key] for key in ("coc_id", "code", "sample_id", "source_hash")}
    )
    existing = {
        sha256_hex({key: item[key] for key in ("coc_id", "code", "sample_id", "source_hash")})
        for item in ledger["holds"]
    }
    if fingerprint not in existing:
        ledger["holds"].append(hold)
        _event(ledger, "HOLD", hold)
        return {"kind": "HOLD", "duplicate": False, **hold}
    return {"kind": "HOLD", "duplicate": True, **hold}


def _existing_route_for_coc(ledger: dict[str, Any], coc_id: str) -> dict[str, Any] | None:
    for item in ledger["routes"].values():
        if item["coc_id"] == coc_id:
            return item
    return None


def build_lineage(row: dict[str, Any], routed: dict[str, Any]) -> list[dict[str, Any]]:
    lineage = [
        {
            "kind": "COC_SOURCE",
            "hash": routed["source_hash"],
            "source_kind": row.get("source_kind"),
            "source_coordinate": row.get("source_coordinate"),
        }
    ]
    amendment = row.get("amendment")
    if isinstance(amendment, dict) and amendment.get("amendment_hash"):
        lineage.append(
            {
                "kind": "AMENDMENT",
                "hash": amendment["amendment_hash"],
                "channel": amendment.get("channel"),
                "prior_hash": amendment.get("prior_hash"),
            }
        )
    lineage.append(
        {
            "kind": "ROUTE",
            "hash": routed["route_hash"],
            "lab": routed["lab"],
            "clock_start": routed["clock_start"],
        }
    )
    return lineage


def route_coc(ledger: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    coc_id = _text(row.get("coc_id"))
    existing = _existing_route_for_coc(ledger, coc_id)
    if existing is not None:
        return {"kind": "NOOP", "route_id": existing["route_id"], "reason": "already_routed"}
    if any(item["coc_id"] == coc_id for item in ledger["holds"]):
        return {"kind": "NOOP", "duplicate": True, "reason": "already_held", "coc_id": coc_id}

    source_hash = _text(row.get("source_hash")) or compute_source_hash(row)
    if source_hash in ledger["source_index"]:
        return {"kind": "NOOP", "reason": "source_hash_replay", "source_hash": source_hash}

    verdict = classify_coc(row, ledger)
    if not verdict["ok"]:
        return _hold(ledger, row, verdict["code"])

    sample_id = _text(row.get("sample_id"))
    lab = _text(row.get("designated_lab"))
    rte_id = route_id(sample_id, source_hash, lab)
    if rte_id in ledger["routes"]:
        return {"kind": "NOOP", "route_id": rte_id, "reason": "already_routed"}

    clock = tat_clock(_text(row.get("received_at")), _text(row.get("tat_code")))
    routed = {
        "route_id": rte_id,
        "coc_id": coc_id,
        "sample_id": sample_id,
        "client_id": _text(row.get("client_id")),
        "project_id": _text(row.get("project_id")),
        "matrix": _text(row.get("matrix")),
        "method": _text(row.get("method")),
        "designated_lab": lab,
        "lab": lab,
        "tat_code": _text(row.get("tat_code")),
        "received_at": _text(row.get("received_at")),
        "clock_start": clock["clock_start"],
        "due_at": clock["due_at"],
        "tat_hours": clock["hours"],
        "tat_basis": clock["basis"],
        "recipient_name": _text(row.get("recipient_name")),
        "recipient_role": _text(row.get("recipient_role")),
        "report_permission": _text(row.get("report_permission")),
        "report_to": _text(row.get("report_to")),
        "amendment_channel": _text(row.get("amendment_channel")),
        "source_kind": _text(row.get("source_kind")),
        "source_coordinate": _text(row.get("source_coordinate")),
        "source_hash": source_hash,
        "amendment": deepcopy(row.get("amendment")),
        "released": False,
        "released_by": None,
        "interface_state": "SIMULATED",
        "interface_live": False,
    }
    routed["route_hash"] = sha256_hex(
        {
            "clock_start": routed["clock_start"],
            "due_at": routed["due_at"],
            "lab": lab,
            "method": routed["method"],
            "route_id": rte_id,
            "sample_id": sample_id,
            "source_hash": source_hash,
        }
    )
    routed["lineage"] = build_lineage(row, routed)
    routed["lineage_hash"] = sha256_hex(routed["lineage"])
    ledger["routes"][rte_id] = routed
    ledger["sample_index"][sample_id] = rte_id
    ledger["source_index"][source_hash] = rte_id
    _event(ledger, "ROUTED", {"route_id": rte_id, "lab": lab, "source_hash": source_hash})
    return {"kind": "ROUTED", "duplicate": False, **routed}


def release_order(
    ledger: dict[str, Any],
    rte_id: str,
    actor: str,
    actor_role: str,
) -> dict[str, Any]:
    order = ledger["routes"].get(rte_id)
    if order is None:
        return {"ok": False, "code": "HOLD_UNKNOWN_ROUTE", "route_id": rte_id}
    if order["released"]:
        return {"ok": True, "duplicate": True, "route_id": rte_id, "code": "ALREADY_RELEASED"}
    named = _text(actor) == HUMAN_RELEASER and _text(actor_role) == HUMAN_ROLE
    autonomous = _text(actor) in AUTONOMOUS_ACTORS or _text(actor_role) in {
        "AUTOMATION",
        "SYSTEM",
        "AUTO",
    }
    if autonomous or not named:
        _event(
            ledger,
            "RELEASE_DENIED",
            {"route_id": rte_id, "actor": actor, "actor_role": actor_role},
        )
        return {
            "ok": False,
            "code": "AUTONOMOUS_RELEASE_DENIED" if autonomous else "HOLD_NAMED_HUMAN_REQUIRED",
            "route_id": rte_id,
        }
    order["released"] = True
    order["released_by"] = actor
    _event(ledger, "HUMAN_RELEASE", {"route_id": rte_id, "actor": actor})
    return {"ok": True, "route_id": rte_id, "code": "RELEASED"}


def attempt_autonomous_release(ledger: dict[str, Any]) -> list[dict[str, Any]]:
    effects = []
    for rte_id in sorted(ledger["routes"]):
        effects.append(
            release_order(ledger, rte_id, actor="SYSTEM", actor_role="AUTOMATION")
        )
    return effects


def replay_into(ledger: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    before_routes = len(ledger["routes"])
    before_holds = len(ledger["holds"])
    noops = 0
    for row in rows:
        result = route_coc(ledger, row)
        if result.get("kind") == "NOOP" or result.get("duplicate"):
            noops += 1
    return {
        "added_route_count": len(ledger["routes"]) - before_routes,
        "added_holds": len(ledger["holds"]) - before_holds,
        "replay_noops": noops,
    }


def field_parity_failures(rows: list[dict[str, Any]], ledger: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    by_coc = {item["coc_id"]: item for item in ledger["routes"].values()}
    for row in rows:
        if row.get("expected_state") != "ROUTED":
            continue
        routed = by_coc.get(row["coc_id"])
        if routed is None:
            failures.append(row["coc_id"])
            continue
        for field in PARITY_FIELDS:
            if routed.get(field) != row.get(field):
                failures.append(f"{row['coc_id']}:{field}")
        if routed["lab"] != row["designated_lab"]:
            failures.append(f"{row['coc_id']}:lab")
    return failures


def tat_clock_failures(rows: list[dict[str, Any]], ledger: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    by_coc = {item["coc_id"]: item for item in ledger["routes"].values()}
    for row in rows:
        if row.get("expected_state") != "ROUTED":
            continue
        routed = by_coc.get(row["coc_id"])
        if routed is None:
            failures.append(row["coc_id"])
            continue
        expected = tat_clock(row["received_at"], row["tat_code"])
        if routed["clock_start"] != row["received_at"]:
            failures.append(f"{row['coc_id']}:clock_start")
        if routed["clock_start"] != expected["clock_start"]:
            failures.append(f"{row['coc_id']}:clock_basis")
        if routed["due_at"] != expected["due_at"]:
            failures.append(f"{row['coc_id']}:due_at")
        if routed["tat_basis"] != "FIXTURE_RECEIPT":
            failures.append(f"{row['coc_id']}:basis")
        if routed["received_at"] != row["received_at"]:
            failures.append(f"{row['coc_id']}:received_at")
    return failures


def permission_failures(rows: list[dict[str, Any]], ledger: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    by_coc = {item["coc_id"]: item for item in ledger["routes"].values()}
    for row in rows:
        if row.get("expected_state") != "ROUTED":
            continue
        routed = by_coc.get(row["coc_id"])
        if routed is None or not permissions_match(routed) or not permissions_match(row):
            failures.append(row["coc_id"])
            continue
        if routed["recipient_name"] != row["report_to"] or routed["report_to"] != row["report_to"]:
            failures.append(f"{row['coc_id']}:recipient")
    return failures


def lineage_failures(ledger: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    seen_hashes: set[str] = set()
    for item in ledger["routes"].values():
        if not item.get("source_hash") or not item.get("route_hash") or not item.get("lineage"):
            failures.append(item["coc_id"])
            continue
        kinds = [step["kind"] for step in item["lineage"]]
        if kinds[0] != "COC_SOURCE" or kinds[-1] != "ROUTE":
            failures.append(f"{item['coc_id']}:lineage_order")
        if item["lineage"][0]["hash"] != item["source_hash"]:
            failures.append(f"{item['coc_id']}:source_step")
        if item["lineage"][-1]["hash"] != item["route_hash"]:
            failures.append(f"{item['coc_id']}:route_step")
        if item["lineage_hash"] != sha256_hex(item["lineage"]):
            failures.append(f"{item['coc_id']}:lineage_hash")
        if item["source_hash"] in seen_hashes:
            failures.append(f"{item['coc_id']}:source_dup")
        seen_hashes.add(item["source_hash"])
    return failures


def build_audit(ledger: dict[str, Any]) -> dict[str, Any]:
    routes = [
        {
            "route_id": item["route_id"],
            "coc_id": item["coc_id"],
            "sample_id": item["sample_id"],
            "lab": item["lab"],
            "method": item["method"],
            "tat_code": item["tat_code"],
            "clock_start": item["clock_start"],
            "due_at": item["due_at"],
            "source_hash": item["source_hash"],
            "route_hash": item["route_hash"],
            "lineage_hash": item["lineage_hash"],
            "released": item["released"],
            "released_by": item["released_by"],
        }
        for item in sorted(ledger["routes"].values(), key=lambda row: row["route_id"])
    ]
    holds = [
        {
            "coc_id": item["coc_id"],
            "sample_id": item["sample_id"],
            "code": item["code"],
            "source_hash": item["source_hash"],
            "owner_role": item["owner_role"],
            "owner_desk": item["owner_desk"],
        }
        for item in sorted(ledger["holds"], key=lambda row: (row["code"], row["coc_id"]))
    ]
    return {
        "demand_id": DEMAND_ID,
        "schema": SCHEMA,
        "buyer": BUYER,
        "routes": routes,
        "holds": holds,
        "adapters": ledger["adapters"],
        "production_writes": ledger["production_writes"],
        "live_sample_actions": ledger["live_sample_actions"],
        "cash_usd": 0,
    }


def expected_actual(result: dict[str, Any]) -> dict[str, Any]:
    actual = {
        "input_cocs": result["input_cocs"],
        "valid": result["valid"],
        "exceptions": result["exceptions"],
        "routed": result["routed"],
        "holds": result["holds"],
        "hold_missing_signature": result["hold_code_counts"].get("HOLD_MISSING_SIGNATURE", 0),
        "hold_duplicate_sample_id": result["hold_code_counts"].get("HOLD_DUPLICATE_SAMPLE_ID", 0),
        "hold_invalid_lab_method": result["hold_code_counts"].get("HOLD_INVALID_LAB_METHOD", 0),
        "hold_tat_cutoff": result["hold_code_counts"].get("HOLD_TAT_CUTOFF", 0),
        "lab_ric": result["lab_counts"].get("RIC", 0),
        "lab_cin": result["lab_counts"].get("CIN", 0),
        "lab_bos": result["lab_counts"].get("BOS", 0),
        "duplicate_routes": result["duplicate_routes"],
        "permission_mismatches": len(result["permission_failures"]),
        "tat_clock_failures": len(result["tat_clock_failures"]),
        "autonomous_released": result["autonomous_released"],
        "human_released": result["human_released"],
        "production_writes": result["production_writes"],
        "live_sample_actions": result["live_sample_actions"],
        "cash_usd": result["cash_usd"],
    }
    return {
        "expected": deepcopy(EXPECTED_COUNTS),
        "actual": actual,
        "match": actual == EXPECTED_COUNTS,
    }


def pass_contract(result: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    counts = expected_actual(result)
    if not counts["match"]:
        failures.append("counts")
    if result["parity_failures"]:
        failures.append("field_parity")
    if result["tat_clock_failures"]:
        failures.append("tat_clocks")
    if result["permission_failures"]:
        failures.append("permissions")
    if result["lineage_failures"]:
        failures.append("lineage")
    if result["duplicate_routes"] != 0:
        failures.append("duplicates")
    if result["replay"]["added_route_count"] != 0 or result["replay"]["added_holds"] != 0:
        failures.append("replay")
    if result["audit_sha256"] != result["replay_audit_sha256"]:
        failures.append("replay_hash")
    if result.get("golden_locked") and result["audit_sha256"] != GOLDEN_AUDIT_SHA256:
        failures.append("audit_sha256")
    if result.get("golden_locked") and result["lineage_sha256"] != GOLDEN_LINEAGE_SHA256:
        failures.append("lineage_sha256")
    if result.get("golden_locked") and result["fixture_sha256"] != GOLDEN_FIXTURE_SHA256:
        failures.append("fixture_sha256")
    if result["autonomous_released"] != 0:
        failures.append("autonomous_release")
    if result["interface_live"] or result["production_writes"] or result["live_sample_actions"]:
        failures.append("live_adapters")
    records = result.get("route_records") or []
    if any(not item["source_hash"] or not item["lineage"] for item in records):
        failures.append("source_trace")
    labs = {item["coc_id"]: item["lab"] for item in records}
    for row in result.get("input_rows") or []:
        if row.get("expected_state") == "ROUTED" and labs.get(row["coc_id"]) != row["designated_lab"]:
            failures.append("designated_lab")
            break
    return failures


def run_router(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = deepcopy(rows or load_fixture())
    ledger = empty_ledger()
    silent = 0
    for row in rows:
        result = route_coc(ledger, row)
        if result.get("kind") not in {"ROUTED", "HOLD", "NOOP"}:
            silent += 1
    if silent:
        raise RuntimeError("silent drop count %s" % silent)

    auto_effects = attempt_autonomous_release(ledger)
    human_effects = [
        release_order(ledger, rte_id, actor=HUMAN_RELEASER, actor_role=HUMAN_ROLE)
        for rte_id in sorted(ledger["routes"])
    ]
    audit = build_audit(ledger)
    audit_sha = sha256_hex(audit)
    lineage_sha = sha256_hex(
        [
            {"coc_id": item["coc_id"], "lineage": item["lineage"], "lineage_hash": item["lineage_hash"]}
            for item in sorted(ledger["routes"].values(), key=lambda row: row["route_id"])
        ]
    )

    replay = replay_into(ledger, rows)
    replay_audit = build_audit(ledger)
    replay_sha = sha256_hex(replay_audit)

    hold_code_counts = {code: 0 for code in HOLD_CODES}
    for item in ledger["holds"]:
        hold_code_counts[item["code"]] = hold_code_counts.get(item["code"], 0) + 1

    route_records = [
        deepcopy(item)
        for item in sorted(ledger["routes"].values(), key=lambda row: row["route_id"])
    ]
    lab_counts = {"RIC": 0, "CIN": 0, "BOS": 0}
    for item in route_records:
        lab_counts[item["lab"]] = lab_counts.get(item["lab"], 0) + 1

    golden_locked = "pending" not in {
        GOLDEN_AUDIT_SHA256,
        GOLDEN_LINEAGE_SHA256,
        GOLDEN_FIXTURE_SHA256,
    }
    packed = {
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "input_cocs": len(rows),
        "input_rows": rows,
        "valid": VALID_COUNT,
        "exceptions": EXCEPTION_COUNT,
        "routed": len(route_records),
        "route_records": route_records,
        "holds": len(ledger["holds"]),
        "hold_records": deepcopy(ledger["holds"]),
        "hold_codes": sorted({item["code"] for item in ledger["holds"]}),
        "hold_code_counts": hold_code_counts,
        "lab_counts": lab_counts,
        "duplicate_routes": len(route_records) - len({item["sample_id"] for item in route_records}),
        "parity_failures": field_parity_failures(rows, ledger),
        "tat_clock_failures": tat_clock_failures(rows, ledger),
        "permission_failures": permission_failures(rows, ledger),
        "lineage_failures": lineage_failures(ledger),
        "autonomous_release_effects": auto_effects,
        "human_release_effects": human_effects,
        "autonomous_released": 0,
        "human_released": sum(1 for item in route_records if item["released"]),
        "audit": audit,
        "audit_sha256": audit_sha,
        "lineage_sha256": lineage_sha,
        "fixture_sha256": fixture_sha256(rows),
        "replay": replay,
        "replay_audit_sha256": replay_sha,
        "interface_live": ledger["interface_live"],
        "interfaces": "SIMULATED",
        "adapters": ledger["adapters"],
        "production_writes": ledger["production_writes"],
        "live_sample_actions": ledger["live_sample_actions"],
        "live_reports": ledger["live_reports"],
        "billing_writes": ledger["billing_writes"],
        "cash_usd": 0,
        "pre_sale_transport": "NONE",
        "golden_locked": golden_locked,
        "official_binary": "python3 sanair_asbestos_coc_router.py",
        "official_test": "python3 test_sanair_asbestos_coc_router.py",
    }
    packed["failures"] = pass_contract(packed) if golden_locked else []
    packed["ok"] = (
        expected_actual(packed)["match"]
        and packed["parity_failures"] == []
        and packed["tat_clock_failures"] == []
        and packed["permission_failures"] == []
        and packed["lineage_failures"] == []
        and packed["replay"]["added_route_count"] == 0
        and packed["audit_sha256"] == packed["replay_audit_sha256"]
        and packed["failures"] == []
    )
    return packed


def write_receipts(result: dict[str, Any]) -> None:
    RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    counts = expected_actual(result)
    (RECEIPT_DIR / "run.json").write_text(
        _canonical(
            {
                "demand_id": DEMAND_ID,
                "ok": result["ok"],
                "expected": counts["expected"],
                "actual": counts["actual"],
                "audit_sha256": result["audit_sha256"],
                "lineage_sha256": result["lineage_sha256"],
                "fixture_sha256": result["fixture_sha256"],
                "official_binary": result["official_binary"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (RECEIPT_DIR / "audit.json").write_text(_canonical(result["audit"]) + "\n", encoding="utf-8")
    (RECEIPT_DIR / "replay.json").write_text(_canonical(result["replay"]) + "\n", encoding="utf-8")


def cli_payload(result: dict[str, Any]) -> dict[str, Any]:
    counts = expected_actual(result)
    return {
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "ok": result["ok"],
        "failures": result.get("failures") or pass_contract(result),
        "expected": counts["expected"],
        "actual": counts["actual"],
        "match": counts["match"],
        "hold_codes": result["hold_codes"],
        "hold_code_counts": result["hold_code_counts"],
        "lab_counts": result["lab_counts"],
        "audit_sha256": result["audit_sha256"],
        "lineage_sha256": result["lineage_sha256"],
        "fixture_sha256": result["fixture_sha256"],
        "replay_audit_sha256": result["replay_audit_sha256"],
        "replay": result["replay"],
        "truth_gate": TRUTH_GATE,
        "interfaces": result["interfaces"],
        "cash_usd": 0,
        "pre_sale_transport": "NONE",
        "official_binary": result["official_binary"],
        "official_test": result["official_test"],
    }


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--write-fixture"]:
        rows = write_fixture()
        sys.stdout.write(
            _canonical({"wrote": str(FIXTURE_PATH), "count": len(rows), "sha256": fixture_sha256(rows)})
            + "\n"
        )
        return 0
    if args == ["--print-goldens"]:
        result = run_router(build_acceptance_fixture())
        sys.stdout.write(
            _canonical(
                {
                    "audit_sha256": result["audit_sha256"],
                    "lineage_sha256": result["lineage_sha256"],
                    "fixture_sha256": result["fixture_sha256"],
                    "expected": expected_actual(result),
                    "ok": result["ok"],
                }
            )
            + "\n"
        )
        return 0
    result = run_router()
    write_receipts(result)
    payload = cli_payload(result)
    sys.stdout.write(_canonical(payload) + "\n")
    return 0 if payload["ok"] and not payload["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
