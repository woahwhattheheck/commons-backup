#!/usr/bin/env python3
"""AquaTrace Work Order C — reporting and offline recovery runner.

Fail-closed synthetic contracts for offline recover vs conflict HOLD,
CMDP / netDMR / Power BI export payloads, named-human release, and
idempotent replay. Adapters stay synthetic and read-only.

Cite, do not inherit: private SHA 7a5ca7fe2856c49abf46bc248654a4d6f7af0335
docs/validation/reporting-offline-test-contract.md (unmerged private-repo docs).
Cite AquaTrace production swarm. Do not remint A / B / field-mobility C / D /
D-QA / sanair / wadsworth / highpower / westpak / ddl / sharp / canyon / pcl /
organabio / billings, or the private acceptance-runner / operations-runner /
instrument-fixtures.

State remains NOT_READY / HOLD / BUILD-AND-VERIFY.
"""

from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SOURCE_PATH = HERE / "source.json"
FIXTURE_PATH = HERE / "fixture.json"
RECEIPT_DIR = HERE / "receipts"

DEMAND_ID = "aquatrace-work-order-c-reporting-offline-20260831-01"
SCHEMA = "commons-aquatrace-work-order-c-reporting-offline/v1"
TRUTH_GATE = "NOT_READY / HOLD / BUILD-AND-VERIFY"
SWARM = "AquaTrace production swarm"
PRODUCT = "AquaTrace reporting and offline recovery runner"
HUMAN_RELEASER = "SYN-AQUATRACE-REPORTING-OFFICER"
HUMAN_ROLE = "RELEASE_OFFICER"
EXCEPTION_OWNER_ROLE = "REPORTING_OFFLINE_LEAD"
EXCEPTION_OWNER_DESK = "AQUATRACE_REPORTING_OFFLINE"

RECOVER_COUNT = 60
HOLD_PER_CODE = 5
HOLD_CODES = (
    "HOLD_VERSION_CONFLICT",
    "HOLD_CHECKSUM_DIVERGENCE",
    "HOLD_CLOCK_SKEW",
    "HOLD_SPLIT_BRAIN",
)
HOLD_COUNT = HOLD_PER_CODE * len(HOLD_CODES)
INPUT_COUNT = RECOVER_COUNT + HOLD_COUNT
EXPORT_CONTRACTS = ("CMDP", "NETDMR", "POWER_BI")
RECOVER_PER_DESTINATION = 20

AUTONOMOUS_ACTORS = frozenset(
    {"SYSTEM", "AUTO", "AUTONOMOUS", "BOT", "MACHINE", "robot", "GROK", "AGENT"}
)

# Pinned after first fail-closed run. Do not weaken.
GOLDEN_AUDIT_SHA256 = "5be4b7ebe6432e675fdb1360ad1125262a014de25eb740dae8ea7aa88c63e51b"
GOLDEN_FIXTURE_SHA256 = "c35a330b712327e6224168614d4097d57adfebd0a64937ced4899b40ef2ec34f"
GOLDEN_CMDP_SHA256 = "ec2af2de146bfe52b9896cad857ef8fe2f6b26ea12d2900b81d4e4a63e3b11ec"
GOLDEN_NETDMR_SHA256 = "71babb70499dc8aa47102d5af05d8f5445d06fec5fe7866dfca9e140b64d48dc"
GOLDEN_POWER_BI_SHA256 = "7ef946b249b9d06c73c4c9a49d8dd6f2be9aee99171a268f04c0ad8c7b67b983"

EXPECTED_COUNTS = {
    "input_events": INPUT_COUNT,
    "recover": RECOVER_COUNT,
    "holds": HOLD_COUNT,
    "hold_version_conflict": HOLD_PER_CODE,
    "hold_checksum_divergence": HOLD_PER_CODE,
    "hold_clock_skew": HOLD_PER_CODE,
    "hold_split_brain": HOLD_PER_CODE,
    "recover_cmdp": RECOVER_PER_DESTINATION,
    "recover_netdmr": RECOVER_PER_DESTINATION,
    "recover_power_bi": RECOVER_PER_DESTINATION,
    "export_contracts": 3,
    "autonomous_released": 0,
    "human_released_exports": 3,
    "replay_added_recover": 0,
    "replay_added_holds": 0,
    "live_submissions": 0,
    "production_writes": 0,
    "city_contacts": 0,
    "cash_usd": 0,
}

CITE_ONLY = {
    "private_repo": "woahwhattheheck/aquatrace-lims",
    "private_sha": "7a5ca7fe2856c49abf46bc248654a4d6f7af0335",
    "private_path": "docs/validation/reporting-offline-test-contract.md",
    "note": "unmerged private-repo docs — cite, do not inherit",
}

HARD_OFF = (
    "aquatrace-work-order-a-architecture-acceptance-20260831-01",
    "aquatrace-work-order-b-production-foundation-20260831-01",
    "aquatrace-work-order-c-field-mobility-20260831-01",
    "aquatrace-work-order-d-municipal-ux-package-20260831-01",
    "sanair-asbestos-coc-router-lims-01",
    "wadsworth-five-site-consolidation-lims-01",
    "highpower-ssf-receiving-gate-lims-01",
    "westpak-scope-capacity-routing-lims-01",
    "ddl-crosssite-method-proficiency-lims-01",
    "sharp-rtu-vial-isolator-lineage-lims-01",
    "canyon-multisite-regulated-intake-lims-01",
    "pcl-scope-sla-routing-lims-01",
    "organabio-multisite-donor-coa-lims-01",
)


def _load_source() -> dict[str, Any]:
    return json.loads(SOURCE_PATH.read_text(encoding="utf-8"))


SOURCE = _load_source()


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def parse_stamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def format_stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def freeze_start() -> datetime:
    return datetime(2026, 8, 1, 8, 0, 0, tzinfo=timezone.utc)


def event_id(index: int) -> str:
    return "AT-OFF-%04d" % index


def sample_id(index: int) -> str:
    return "SYN-SMP-%04d" % index


def device_id(index: int) -> str:
    return ("SYN-DEV-A", "SYN-DEV-B", "SYN-DEV-C")[(index - 1) % 3]


def destination_for_recover(index: int) -> str:
    if index <= 20:
        return "CMDP"
    if index <= 40:
        return "NETDMR"
    return "POWER_BI"


def recover_payload_fields(index: int) -> dict[str, Any]:
    dest = destination_for_recover(index)
    if dest == "CMDP":
        analyte = SOURCE["cmdp_analytes"][(index - 1) % len(SOURCE["cmdp_analytes"])]
        return {
            "destination": dest,
            "analyte_code": analyte["code"],
            "analyte": analyte["name"],
            "unit": analyte["unit"],
            "method": analyte["method"],
            "result_value": "%.3f" % (1.100 + (index * 0.017)),
            "pwsid": "SYN-PWS-%04d" % (((index - 1) % 4) + 1),
            "npdes_id": "",
            "outfall": "",
            "metric": analyte["name"],
        }
    if dest == "NETDMR":
        param = SOURCE["netdmr_parameters"][(index - 1) % len(SOURCE["netdmr_parameters"])]
        return {
            "destination": dest,
            "analyte_code": param["code"],
            "analyte": param["name"],
            "unit": param["unit"],
            "method": "SYN-NPDES-METHOD",
            "result_value": "%.3f" % (4.200 + (index * 0.031)),
            "pwsid": "",
            "npdes_id": "SYN-NPDES-%04d" % (((index - 1) % 3) + 1),
            "outfall": param["outfall"],
            "metric": param["name"],
        }
    metric = SOURCE["power_bi_metrics"][(index - 1) % len(SOURCE["power_bi_metrics"])]
    return {
        "destination": dest,
        "analyte_code": "OPS-%s" % metric["name"],
        "analyte": metric["name"],
        "unit": metric["unit"],
        "method": "SYN-OPS-LOGGER",
        "result_value": "%.3f" % (0.500 + (index * 0.013)),
        "pwsid": "",
        "npdes_id": "",
        "outfall": "",
        "metric": metric["name"],
    }


def source_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": row["event_id"],
        "sample_id": row["sample_id"],
        "device_id": row["device_id"],
        "destination": row["destination"],
        "analyte_code": row["analyte_code"],
        "analyte": row["analyte"],
        "result_value": row["result_value"],
        "unit": row["unit"],
        "method": row["method"],
        "captured_at": row["captured_at"],
        "recovered_at": row["recovered_at"],
        "pwsid": row.get("pwsid", ""),
        "npdes_id": row.get("npdes_id", ""),
        "outfall": row.get("outfall", ""),
        "metric": row.get("metric", ""),
    }


def compute_source_hash(row: dict[str, Any]) -> str:
    return sha256_hex(source_payload(row))


def result_hash(row: dict[str, Any]) -> str:
    return sha256_hex(
        {
            "sample_id": row["sample_id"],
            "analyte": row["analyte"],
            "result_value": row["result_value"],
            "unit": row["unit"],
            "method": row["method"],
        }
    )


def _base_recover(index: int) -> dict[str, Any]:
    captured = freeze_start() + timedelta(hours=index)
    recovered = captured + timedelta(hours=4)
    fields = recover_payload_fields(index)
    row = {
        "event_id": event_id(index),
        "sample_id": sample_id(index),
        "device_id": device_id(index),
        "captured_at": format_stamp(captured),
        "recovered_at": format_stamp(recovered),
        "expected_state": "RECOVER",
        "expected_hold_code": "",
        "conflict_kind": "",
        **fields,
    }
    row["source_hash"] = compute_source_hash(row)
    row["result_hash"] = result_hash(row)
    return row


def _conflict_row(code: str, slot: int) -> dict[str, Any]:
    """Predefined fail-closed conflict against the recover journal."""
    if code == "HOLD_VERSION_CONFLICT":
        base_index = slot
        row = _base_recover(base_index)
        row["event_id"] = event_id(60 + slot)
        row["result_value"] = "%.3f" % (float(row["result_value"]) + 9.001)
        row["expected_state"] = "HOLD"
        row["expected_hold_code"] = code
        row["conflict_kind"] = "VERSION"
        row["source_hash"] = compute_source_hash(row)
        row["result_hash"] = result_hash(row)
        return row
    if code == "HOLD_CHECKSUM_DIVERGENCE":
        base_index = 5 + slot
        row = _base_recover(base_index)
        row["result_value"] = "%.3f" % (float(row["result_value"]) + 3.333)
        row["expected_state"] = "HOLD"
        row["expected_hold_code"] = code
        row["conflict_kind"] = "CHECKSUM"
        row["source_hash"] = compute_source_hash(row)
        row["result_hash"] = result_hash(row)
        return row
    if code == "HOLD_CLOCK_SKEW":
        index = 70 + slot
        captured = freeze_start() + timedelta(hours=index)
        recovered = captured - timedelta(hours=2)
        row = {
            "event_id": event_id(index),
            "sample_id": sample_id(index),
            "device_id": device_id(index),
            "destination": "CMDP",
            "analyte_code": "1040",
            "analyte": "NITRATE",
            "unit": "MG_L",
            "method": "EPA_353.2",
            "result_value": "0.100",
            "pwsid": "SYN-PWS-0099",
            "npdes_id": "",
            "outfall": "",
            "metric": "NITRATE",
            "captured_at": format_stamp(captured),
            "recovered_at": format_stamp(recovered),
            "expected_state": "HOLD",
            "expected_hold_code": code,
            "conflict_kind": "CLOCK",
        }
        row["source_hash"] = compute_source_hash(row)
        row["result_hash"] = result_hash(row)
        return row
    if code == "HOLD_SPLIT_BRAIN":
        base_index = 10 + slot
        row = _base_recover(base_index)
        other = {"SYN-DEV-A": "SYN-DEV-B", "SYN-DEV-B": "SYN-DEV-C", "SYN-DEV-C": "SYN-DEV-A"}
        row["event_id"] = event_id(75 + slot)
        row["device_id"] = other[row["device_id"]]
        row["result_value"] = "%.3f" % (float(row["result_value"]) + 5.555)
        row["expected_state"] = "HOLD"
        row["expected_hold_code"] = code
        row["conflict_kind"] = "SPLIT_BRAIN"
        row["source_hash"] = compute_source_hash(row)
        row["result_hash"] = result_hash(row)
        return row
    raise ValueError("unknown hold code %s" % code)


def build_acceptance_fixture() -> list[dict[str, Any]]:
    rows = [_base_recover(index) for index in range(1, RECOVER_COUNT + 1)]
    for code in HOLD_CODES:
        for slot in range(1, HOLD_PER_CODE + 1):
            rows.append(_conflict_row(code, slot))
    if len(rows) != INPUT_COUNT:
        raise RuntimeError("fixture size %s != %s" % (len(rows), INPUT_COUNT))
    return rows


def write_fixture(path: Path = FIXTURE_PATH) -> list[dict[str, Any]]:
    rows = build_acceptance_fixture()
    path.write_text(_canonical(rows) + "\n", encoding="utf-8")
    return rows


def load_fixture(path: Path = FIXTURE_PATH) -> list[dict[str, Any]]:
    if not path.is_file():
        return write_fixture(path)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, list) or len(loaded) != INPUT_COUNT:
        raise RuntimeError("fixture at %s is not the locked 80-event set" % path)
    return loaded


def fixture_sha256(rows: list[dict[str, Any]] | None = None) -> str:
    return sha256_hex(rows if rows is not None else load_fixture())


def decision_key(row: dict[str, Any]) -> str:
    return "%s:%s" % (row["event_id"], row["source_hash"])


def empty_ledger() -> dict[str, Any]:
    return {
        "recovered": {},
        "holds": [],
        "events_seen": {},
        "decided": {},
        "exports": {},
        "journal": [],
        "adapters": {
            "offline_journal": "SYNTHETIC_READONLY",
            "cmdp": "SYNTHETIC_READONLY",
            "netdmr": "SYNTHETIC_READONLY",
            "power_bi": "SYNTHETIC_READONLY",
            "lims": "SYNTHETIC_READONLY",
        },
        "interface_live": False,
        "production_writes": 0,
        "live_submissions": 0,
        "city_contacts": 0,
        "customer_records": 0,
        "cash_usd": 0,
    }


def _event(ledger: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    ledger["journal"].append({"kind": kind, **deepcopy(payload)})


def clock_skew(row: dict[str, Any]) -> bool:
    return parse_stamp(row["recovered_at"]) < parse_stamp(row["captured_at"])


def classify_event(ledger: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    if decision_key(row) in ledger["decided"]:
        return {"state": "NOOP", "code": ""}
    if clock_skew(row):
        return {"state": "HOLD", "code": "HOLD_CLOCK_SKEW"}
    existing = ledger["events_seen"].get(row["event_id"])
    if existing is not None:
        if existing["source_hash"] != row["source_hash"]:
            return {"state": "HOLD", "code": "HOLD_CHECKSUM_DIVERGENCE"}
        return {"state": "NOOP", "code": ""}
    recovered = ledger["recovered"].get(row["sample_id"])
    if recovered is not None:
        if recovered["device_id"] == row["device_id"] and recovered["result_hash"] != row["result_hash"]:
            return {"state": "HOLD", "code": "HOLD_VERSION_CONFLICT"}
        if (
            recovered["analyte"] == row["analyte"]
            and recovered["device_id"] != row["device_id"]
            and recovered["result_hash"] != row["result_hash"]
        ):
            return {"state": "HOLD", "code": "HOLD_SPLIT_BRAIN"}
        if recovered["result_hash"] != row["result_hash"]:
            return {"state": "HOLD", "code": "HOLD_VERSION_CONFLICT"}
        return {"state": "NOOP", "code": ""}
    return {"state": "RECOVER", "code": ""}


def _hold(ledger: dict[str, Any], row: dict[str, Any], code: str) -> dict[str, Any]:
    record = {
        "kind": "HOLD",
        "event_id": row["event_id"],
        "sample_id": row["sample_id"],
        "device_id": row["device_id"],
        "destination": row["destination"],
        "code": code,
        "state": "HOLD",
        "source_hash": row["source_hash"],
        "result_hash": row["result_hash"],
        "owner_role": EXCEPTION_OWNER_ROLE,
        "owner_desk": EXCEPTION_OWNER_DESK,
        "released": False,
        "submitted": False,
        "live": False,
    }
    ledger["holds"].append(record)
    ledger["decided"][decision_key(row)] = "HOLD"
    _event(ledger, "HOLD", {"event_id": row["event_id"], "code": code})
    return record


def ingest_event(ledger: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    decision = classify_event(ledger, row)
    if decision["state"] == "NOOP":
        _event(ledger, "NOOP", {"event_id": row["event_id"]})
        return {"kind": "NOOP", "event_id": row["event_id"]}
    if decision["state"] == "HOLD":
        return _hold(ledger, row, decision["code"])
    recovered = {
        "kind": "RECOVER",
        "event_id": row["event_id"],
        "sample_id": row["sample_id"],
        "device_id": row["device_id"],
        "destination": row["destination"],
        "analyte_code": row["analyte_code"],
        "analyte": row["analyte"],
        "result_value": row["result_value"],
        "unit": row["unit"],
        "method": row["method"],
        "captured_at": row["captured_at"],
        "recovered_at": row["recovered_at"],
        "pwsid": row.get("pwsid", ""),
        "npdes_id": row.get("npdes_id", ""),
        "outfall": row.get("outfall", ""),
        "metric": row.get("metric", ""),
        "source_hash": row["source_hash"],
        "result_hash": row["result_hash"],
        "state": "RECOVER",
        "released": False,
        "submitted": False,
        "live": False,
        "interface_state": "SYNTHETIC",
        "interface_live": False,
    }
    recovered["recovery_hash"] = sha256_hex(recovered)
    ledger["recovered"][row["sample_id"]] = recovered
    ledger["events_seen"][row["event_id"]] = recovered
    ledger["decided"][decision_key(row)] = "RECOVER"
    _event(ledger, "RECOVER", {"event_id": row["event_id"], "sample_id": row["sample_id"]})
    return recovered


def replay_into(ledger: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    before_recover = len(ledger["recovered"])
    before_holds = len(ledger["holds"])
    noops = 0
    for row in rows:
        result = ingest_event(ledger, row)
        if result.get("kind") == "NOOP":
            noops += 1
    return {
        "added_recover": len(ledger["recovered"]) - before_recover,
        "added_holds": len(ledger["holds"]) - before_holds,
        "replay_noops": noops,
    }


def cmdp_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "pwsid": item["pwsid"],
        "analyte_code": item["analyte_code"],
        "analyte": item["analyte"],
        "result": item["result_value"],
        "unit": item["unit"],
        "method": item["method"],
        "sample_dt": item["captured_at"],
        "sample_id": item["sample_id"],
        "event_id": item["event_id"],
        "source_hash": item["source_hash"],
    }


def netdmr_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "npdes_id": item["npdes_id"],
        "outfall": item["outfall"],
        "parameter_code": item["analyte_code"],
        "parameter": item["analyte"],
        "value": item["result_value"],
        "unit": item["unit"],
        "monitoring_period": item["captured_at"][:7],
        "sample_id": item["sample_id"],
        "event_id": item["event_id"],
        "source_hash": item["source_hash"],
    }


def power_bi_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "dataset": SOURCE["destinations"]["POWER_BI"]["dataset"],
        "site": SOURCE["devices"][item["device_id"]]["site"],
        "device_id": item["device_id"],
        "metric": item["metric"],
        "value": item["result_value"],
        "unit": item["unit"],
        "captured_at": item["captured_at"],
        "recovered_at": item["recovered_at"],
        "sample_id": item["sample_id"],
        "event_id": item["event_id"],
        "source_hash": item["source_hash"],
    }


def build_export_payload(contract: str, recovered: list[dict[str, Any]]) -> dict[str, Any]:
    if contract == "CMDP":
        rows = [cmdp_row(item) for item in recovered if item["destination"] == "CMDP"]
        body = {
            "contract": "CMDP",
            "schema": SOURCE["destinations"]["CMDP"]["schema"],
            "adapter": "SYNTHETIC_READONLY",
            "live_submission": False,
            "city_contact": False,
            "rows": rows,
        }
    elif contract == "NETDMR":
        rows = [netdmr_row(item) for item in recovered if item["destination"] == "NETDMR"]
        body = {
            "contract": "NETDMR",
            "schema": SOURCE["destinations"]["NETDMR"]["schema"],
            "adapter": "SYNTHETIC_READONLY",
            "live_submission": False,
            "city_contact": False,
            "rows": rows,
        }
    elif contract == "POWER_BI":
        rows = [power_bi_row(item) for item in recovered if item["destination"] == "POWER_BI"]
        body = {
            "contract": "POWER_BI",
            "schema": SOURCE["destinations"]["POWER_BI"]["schema"],
            "adapter": "SYNTHETIC_READONLY",
            "live_submission": False,
            "city_contact": False,
            "dataset": SOURCE["destinations"]["POWER_BI"]["dataset"],
            "rows": rows,
        }
    else:
        raise ValueError("unknown export contract %s" % contract)
    body["row_count"] = len(body["rows"])
    body["payload_sha256"] = sha256_hex(body)
    return body


def build_exports(ledger: dict[str, Any]) -> dict[str, dict[str, Any]]:
    recovered = sorted(ledger["recovered"].values(), key=lambda item: item["event_id"])
    exports: dict[str, dict[str, Any]] = {}
    for contract in EXPORT_CONTRACTS:
        payload = build_export_payload(contract, recovered)
        hold_hashes = {item["source_hash"] for item in ledger["holds"]}
        leaked = [
            row["event_id"]
            for row in payload["rows"]
            if row["source_hash"] in hold_hashes
        ]
        exports[contract] = {
            "contract_id": contract,
            "payload": payload,
            "payload_sha256": payload["payload_sha256"],
            "row_count": payload["row_count"],
            "hold_leaks": leaked,
            "state": "HOLD",
            "released": False,
            "released_by": "",
            "released_role": "",
            "submitted": False,
            "live": False,
            "autonomous": False,
        }
    ledger["exports"] = exports
    return exports


def golden_export_sha256(contract: str) -> str:
    return {
        "CMDP": GOLDEN_CMDP_SHA256,
        "NETDMR": GOLDEN_NETDMR_SHA256,
        "POWER_BI": GOLDEN_POWER_BI_SHA256,
    }[contract]


def release_export(
    ledger: dict[str, Any],
    contract_id: str,
    actor: str,
    actor_role: str,
) -> dict[str, Any]:
    export = ledger["exports"].get(contract_id)
    if export is None:
        return {"ok": False, "code": "HOLD_UNKNOWN_EXPORT", "contract_id": contract_id}
    if actor in AUTONOMOUS_ACTORS or actor_role in AUTONOMOUS_ACTORS:
        _event(
            ledger,
            "AUTONOMOUS_RELEASE_DENIED",
            {"contract_id": contract_id, "actor": actor},
        )
        return {
            "ok": False,
            "code": "AUTONOMOUS_RELEASE_DENIED",
            "contract_id": contract_id,
            "actor": actor,
        }
    if actor != HUMAN_RELEASER or actor_role != HUMAN_ROLE:
        return {
            "ok": False,
            "code": "HOLD_NAMED_HUMAN_REQUIRED",
            "contract_id": contract_id,
            "actor": actor,
        }
    export["released"] = True
    export["released_by"] = actor
    export["released_role"] = actor_role
    export["state"] = "HUMAN_RELEASED_SYNTHETIC"
    export["submitted"] = False
    export["live"] = False
    _event(ledger, "HUMAN_RELEASE", {"contract_id": contract_id, "actor": actor})
    return {"ok": True, "code": "HUMAN_RELEASED_SYNTHETIC", "contract_id": contract_id}


def attempt_autonomous_release(ledger: dict[str, Any]) -> list[dict[str, Any]]:
    effects = []
    for contract in EXPORT_CONTRACTS:
        effects.append(release_export(ledger, contract, "robot", "AUTONOMOUS"))
    return effects


def hold_in_exports(ledger: dict[str, Any]) -> list[str]:
    leaks: list[str] = []
    for export in ledger["exports"].values():
        leaks.extend(export.get("hold_leaks") or [])
    return leaks


def build_audit(ledger: dict[str, Any]) -> dict[str, Any]:
    recovered = [
        {
            "event_id": item["event_id"],
            "sample_id": item["sample_id"],
            "device_id": item["device_id"],
            "destination": item["destination"],
            "source_hash": item["source_hash"],
            "result_hash": item["result_hash"],
            "recovery_hash": item["recovery_hash"],
        }
        for item in sorted(ledger["recovered"].values(), key=lambda row: row["event_id"])
    ]
    holds = [
        {
            "event_id": item["event_id"],
            "sample_id": item["sample_id"],
            "code": item["code"],
            "source_hash": item["source_hash"],
            "owner_role": item["owner_role"],
            "owner_desk": item["owner_desk"],
        }
        for item in sorted(ledger["holds"], key=lambda row: (row["code"], row["event_id"]))
    ]
    exports = [
        {
            "contract_id": item["contract_id"],
            "payload_sha256": item["payload_sha256"],
            "row_count": item["row_count"],
            "released": item["released"],
            "released_by": item["released_by"],
            "submitted": item["submitted"],
            "live": item["live"],
        }
        for item in (ledger["exports"][name] for name in EXPORT_CONTRACTS)
    ]
    return {
        "demand_id": DEMAND_ID,
        "schema": SCHEMA,
        "swarm": SWARM,
        "product": PRODUCT,
        "recovered": recovered,
        "holds": holds,
        "exports": exports,
        "adapters": ledger["adapters"],
        "production_writes": ledger["production_writes"],
        "live_submissions": ledger["live_submissions"],
        "city_contacts": ledger["city_contacts"],
        "cash_usd": 0,
        "cite_only": CITE_ONLY,
        "hard_off": list(HARD_OFF),
    }


def expected_actual(result: dict[str, Any]) -> dict[str, Any]:
    actual = {
        "input_events": result["input_events"],
        "recover": result["recover"],
        "holds": result["holds"],
        "hold_version_conflict": result["hold_code_counts"].get("HOLD_VERSION_CONFLICT", 0),
        "hold_checksum_divergence": result["hold_code_counts"].get("HOLD_CHECKSUM_DIVERGENCE", 0),
        "hold_clock_skew": result["hold_code_counts"].get("HOLD_CLOCK_SKEW", 0),
        "hold_split_brain": result["hold_code_counts"].get("HOLD_SPLIT_BRAIN", 0),
        "recover_cmdp": result["destination_counts"].get("CMDP", 0),
        "recover_netdmr": result["destination_counts"].get("NETDMR", 0),
        "recover_power_bi": result["destination_counts"].get("POWER_BI", 0),
        "export_contracts": result["export_contracts"],
        "autonomous_released": result["autonomous_released"],
        "human_released_exports": result["human_released_exports"],
        "replay_added_recover": result["replay"]["added_recover"],
        "replay_added_holds": result["replay"]["added_holds"],
        "live_submissions": result["live_submissions"],
        "production_writes": result["production_writes"],
        "city_contacts": result["city_contacts"],
        "cash_usd": result["cash_usd"],
    }
    return {
        "expected": deepcopy(EXPECTED_COUNTS),
        "actual": actual,
        "match": actual == EXPECTED_COUNTS,
    }


def pass_contract(result: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if not expected_actual(result)["match"]:
        failures.append("counts")
    if result["hold_leaks"]:
        failures.append("hold_leak_into_export")
    if result["replay"]["added_recover"] != 0 or result["replay"]["added_holds"] != 0:
        failures.append("replay")
    if result["audit_sha256"] != result["replay_audit_sha256"]:
        failures.append("replay_hash")
    if result.get("golden_locked") and result["audit_sha256"] != GOLDEN_AUDIT_SHA256:
        failures.append("audit_sha256")
    if result.get("golden_locked") and result["fixture_sha256"] != GOLDEN_FIXTURE_SHA256:
        failures.append("fixture_sha256")
    exports = result.get("export_records") or {}
    for contract in EXPORT_CONTRACTS:
        item = exports.get(contract) or {}
        if item.get("row_count") != RECOVER_PER_DESTINATION:
            failures.append("export_row_count_%s" % contract.lower())
        if result.get("golden_locked") and item.get("payload_sha256") != golden_export_sha256(contract):
            failures.append("export_hash_%s" % contract.lower())
        if item.get("submitted") or item.get("live"):
            failures.append("live_export_%s" % contract.lower())
    if result["autonomous_released"] != 0:
        failures.append("autonomous_release")
    if result["interface_live"] or result["production_writes"] or result["live_submissions"]:
        failures.append("live_adapters")
    if result["city_contacts"] != 0:
        failures.append("city_contact")
    if result["cash_usd"] != 0:
        failures.append("cash")
    if result.get("truth_gate") != TRUTH_GATE:
        failures.append("truth_gate")
    return failures


def run_reporting(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = deepcopy(rows or load_fixture())
    ledger = empty_ledger()
    silent = 0
    for row in rows:
        result = ingest_event(ledger, row)
        if result.get("kind") not in {"RECOVER", "HOLD", "NOOP"}:
            silent += 1
    if silent:
        raise RuntimeError("silent drop count %s" % silent)

    build_exports(ledger)
    auto_effects = attempt_autonomous_release(ledger)
    human_effects = [
        release_export(ledger, contract, HUMAN_RELEASER, HUMAN_ROLE)
        for contract in EXPORT_CONTRACTS
    ]
    audit = build_audit(ledger)
    audit_sha = sha256_hex(audit)

    replay = replay_into(ledger, rows)
    replay_audit = build_audit(ledger)
    replay_sha = sha256_hex(replay_audit)

    hold_code_counts = {code: 0 for code in HOLD_CODES}
    for item in ledger["holds"]:
        hold_code_counts[item["code"]] = hold_code_counts.get(item["code"], 0) + 1

    recovered_records = [
        deepcopy(item)
        for item in sorted(ledger["recovered"].values(), key=lambda row: row["event_id"])
    ]
    destination_counts = {name: 0 for name in EXPORT_CONTRACTS}
    for item in recovered_records:
        destination_counts[item["destination"]] = destination_counts.get(item["destination"], 0) + 1

    export_records = {name: deepcopy(ledger["exports"][name]) for name in EXPORT_CONTRACTS}
    golden_locked = "PIN_AFTER_FIRST_RUN" not in {
        GOLDEN_AUDIT_SHA256,
        GOLDEN_FIXTURE_SHA256,
        GOLDEN_CMDP_SHA256,
        GOLDEN_NETDMR_SHA256,
        GOLDEN_POWER_BI_SHA256,
    }
    packed = {
        "demand_id": DEMAND_ID,
        "product": PRODUCT,
        "swarm": SWARM,
        "truth_gate": TRUTH_GATE,
        "input_events": len(rows),
        "input_rows": rows,
        "recover": len(recovered_records),
        "recover_records": recovered_records,
        "holds": len(ledger["holds"]),
        "hold_records": deepcopy(ledger["holds"]),
        "hold_codes": sorted({item["code"] for item in ledger["holds"]}),
        "hold_code_counts": hold_code_counts,
        "destination_counts": destination_counts,
        "export_contracts": len(export_records),
        "export_records": export_records,
        "hold_leaks": hold_in_exports(ledger),
        "autonomous_release_effects": auto_effects,
        "human_release_effects": human_effects,
        "autonomous_released": 0,
        "human_released_exports": sum(
            1 for item in export_records.values() if item["released"]
        ),
        "audit": audit,
        "audit_sha256": audit_sha,
        "fixture_sha256": fixture_sha256(rows),
        "replay": replay,
        "replay_audit_sha256": replay_sha,
        "interface_live": ledger["interface_live"],
        "interfaces": "SYNTHETIC",
        "adapters": ledger["adapters"],
        "production_writes": ledger["production_writes"],
        "live_submissions": ledger["live_submissions"],
        "city_contacts": ledger["city_contacts"],
        "customer_records": ledger["customer_records"],
        "cash_usd": 0,
        "pre_sale_transport": "NONE",
        "cite_only": CITE_ONLY,
        "hard_off": list(HARD_OFF),
        "golden_locked": golden_locked,
        "official_binary": "python3 aquatrace_work_order_c_reporting_offline.py",
        "official_test": "python3 test_aquatrace_work_order_c_reporting_offline.py",
    }
    packed["failures"] = pass_contract(packed) if golden_locked else []
    packed["ok"] = (
        expected_actual(packed)["match"]
        and packed["hold_leaks"] == []
        and packed["replay"]["added_recover"] == 0
        and packed["replay"]["added_holds"] == 0
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
                "fixture_sha256": result["fixture_sha256"],
                "export_hashes": {
                    name: result["export_records"][name]["payload_sha256"]
                    for name in EXPORT_CONTRACTS
                },
                "official_binary": result["official_binary"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (RECEIPT_DIR / "audit.json").write_text(_canonical(result["audit"]) + "\n", encoding="utf-8")
    (RECEIPT_DIR / "replay.json").write_text(_canonical(result["replay"]) + "\n", encoding="utf-8")
    (RECEIPT_DIR / "exports.json").write_text(
        _canonical(
            {
                name: {
                    "payload_sha256": result["export_records"][name]["payload_sha256"],
                    "row_count": result["export_records"][name]["row_count"],
                    "released": result["export_records"][name]["released"],
                    "submitted": result["export_records"][name]["submitted"],
                    "live": result["export_records"][name]["live"],
                }
                for name in EXPORT_CONTRACTS
            }
        )
        + "\n",
        encoding="utf-8",
    )


def cli_payload(result: dict[str, Any]) -> dict[str, Any]:
    counts = expected_actual(result)
    return {
        "demand_id": DEMAND_ID,
        "product": PRODUCT,
        "swarm": SWARM,
        "ok": result["ok"],
        "failures": result.get("failures") or pass_contract(result),
        "expected": counts["expected"],
        "actual": counts["actual"],
        "match": counts["match"],
        "hold_codes": result["hold_codes"],
        "hold_code_counts": result["hold_code_counts"],
        "destination_counts": result["destination_counts"],
        "export_hashes": {
            name: result["export_records"][name]["payload_sha256"]
            for name in EXPORT_CONTRACTS
        },
        "audit_sha256": result["audit_sha256"],
        "fixture_sha256": result["fixture_sha256"],
        "replay_audit_sha256": result["replay_audit_sha256"],
        "replay": result["replay"],
        "truth_gate": TRUTH_GATE,
        "interfaces": result["interfaces"],
        "cash_usd": 0,
        "pre_sale_transport": "NONE",
        "cite_only": CITE_ONLY,
        "official_binary": result["official_binary"],
        "official_test": result["official_test"],
    }


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--write-fixture"]:
        rows = write_fixture()
        sys.stdout.write(
            _canonical(
                {"wrote": str(FIXTURE_PATH), "count": len(rows), "sha256": fixture_sha256(rows)}
            )
            + "\n"
        )
        return 0
    if args == ["--print-goldens"]:
        result = run_reporting(build_acceptance_fixture())
        sys.stdout.write(
            _canonical(
                {
                    "audit_sha256": result["audit_sha256"],
                    "fixture_sha256": result["fixture_sha256"],
                    "export_hashes": {
                        name: result["export_records"][name]["payload_sha256"]
                        for name in EXPORT_CONTRACTS
                    },
                    "expected": expected_actual(result),
                    "ok": result["ok"],
                }
            )
            + "\n"
        )
        return 0
    result = run_reporting()
    write_receipts(result)
    payload = cli_payload(result)
    sys.stdout.write(_canonical(payload) + "\n")
    return 0 if payload["ok"] and not payload["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
