#!/usr/bin/env python3
"""Cornell Craft Beverage intake LIMS module.

One order per analysis. Matrix-aware volume rules. Frozen-juice next-day
evidence. Immutable accession IDs. Panel routing. QC hold. Human release.

Demand: cornell-craft-beverage-intake-lims-01
Buyer: Cornell Craft Beverage Analytical Lab / Anna Katharine Mansfield

Public volume/shipping facts (CALS sample-submission instructions):
- 750 mL when additional/duplicate tests are requested
- 375 mL when only a single analysis is requested
- 100 mL for distillate or kombucha alcohol-only
- Juice must be frozen and shipped next-day air
- Different tests require a new form (one order per analysis)
- Sample ID is required

AquaTrace HOLD / BUILD-AND-VERIFY. Interfaces stay simulated.
No autonomous certification or release. PRE-SALE TRANSPORT: NONE.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

DEMAND_ID = "cornell-craft-beverage-intake-lims-01"
SCHEMA = "commons-cornell-craft-beverage-intake-lims/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"

PANELS: dict[str, dict[str, Any]] = {
    "WINE_MULTI": {
        "matrix": "grape_wine",
        "analyses": ["so2", "ethanol", "ph", "ta"],
        "min_volume_ml": 750,
        "alcohol_only": False,
    },
    "WINE_SINGLE": {
        "matrix": "grape_wine",
        "analyses": ["ethanol"],
        "min_volume_ml": 375,
        "alcohol_only": False,
    },
    "CIDER_SINGLE": {
        "matrix": "cider",
        "analyses": ["ethanol"],
        "min_volume_ml": 375,
        "alcohol_only": False,
    },
    "SPIRITS_ABV": {
        "matrix": "distillate",
        "analyses": ["ethanol"],
        "min_volume_ml": 100,
        "alcohol_only": True,
    },
    "KOMBUCHA_ABV": {
        "matrix": "kombucha",
        "analyses": ["ethanol"],
        "min_volume_ml": 100,
        "alcohol_only": True,
    },
    "JUICE_PANEL": {
        "matrix": "juice",
        "analyses": ["brix", "ta", "ph", "yeast_assimilable_n"],
        "min_volume_ml": 750,
        "alcohol_only": False,
    },
}

VALID_MATRICES = frozenset(spec["matrix"] for spec in PANELS.values())
REJECT_CODES = ("UNDER_VOLUME", "MISSING_SAMPLE_ID")
HUMAN_RELEASER = "RELEASER"


def _text(value: Any) -> str:
    return str("" if value is None else value).strip()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def accession_id(sample_id: str, panel: str, matrix: str) -> str:
    digest = sha256_hex(
        {
            "demand_id": DEMAND_ID,
            "sample_id": sample_id,
            "panel": panel,
            "matrix": matrix,
        }
    )
    return "CCB-" + digest[:12]


def min_volume_ml(matrix: str, panel: str) -> int:
    spec = PANELS.get(panel)
    if spec is None:
        return 375
    if spec["matrix"] != matrix:
        return int(spec["min_volume_ml"])
    return int(spec["min_volume_ml"])


def _flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "y"}


def _volume(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def build_acceptance_fixture() -> list[dict[str, Any]]:
    """8-row PASS fixture for cornell-craft-beverage-intake-lims-01.

    Six valid one-order-per-analysis submissions plus UNDER_VOLUME and
    MISSING_SAMPLE_ID. Juice row carries both frozen and next-day flags.
    """
    rows = [
        {
            "row_id": "R01",
            "sample_id": "CCB-W01",
            "matrix": "grape_wine",
            "panel": "WINE_MULTI",
            "volume_ml": 750,
            "frozen": False,
            "next_day": False,
            "container_full": True,
        },
        {
            "row_id": "R02",
            "sample_id": "CCB-W02",
            "matrix": "grape_wine",
            "panel": "WINE_SINGLE",
            "volume_ml": 375,
            "frozen": False,
            "next_day": False,
            "container_full": True,
        },
        {
            "row_id": "R03",
            "sample_id": "CCB-S01",
            "matrix": "distillate",
            "panel": "SPIRITS_ABV",
            "volume_ml": 100,
            "frozen": False,
            "next_day": False,
            "sealed": True,
        },
        {
            "row_id": "R04",
            "sample_id": "CCB-K01",
            "matrix": "kombucha",
            "panel": "KOMBUCHA_ABV",
            "volume_ml": 100,
            "frozen": False,
            "next_day": False,
            "chilled": True,
        },
        {
            "row_id": "R05",
            "sample_id": "CCB-J01",
            "matrix": "juice",
            "panel": "JUICE_PANEL",
            "volume_ml": 750,
            "frozen": True,
            "next_day": True,
        },
        {
            "row_id": "R06",
            "sample_id": "CCB-C01",
            "matrix": "cider",
            "panel": "CIDER_SINGLE",
            "volume_ml": 375,
            "frozen": False,
            "next_day": False,
            "container_full": True,
        },
        {
            "row_id": "R07",
            "sample_id": "CCB-W03",
            "matrix": "grape_wine",
            "panel": "WINE_MULTI",
            "volume_ml": 200,
            "frozen": False,
            "next_day": False,
            "container_full": True,
        },
        {
            "row_id": "R08",
            "sample_id": "",
            "matrix": "grape_wine",
            "panel": "WINE_SINGLE",
            "volume_ml": 375,
            "frozen": False,
            "next_day": False,
            "container_full": True,
        },
    ]
    if len(rows) != 8:
        raise RuntimeError("acceptance fixture must be exactly 8 rows, got %s" % len(rows))
    return rows


def empty_journal() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "accessions": {},
        "rejects": [],
        "events": [],
    }


def _event(journal: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    journal["events"].append(
        {
            "seq": len(journal["events"]) + 1,
            "kind": kind,
            **deepcopy(payload),
        }
    )


def classify_submission(row: dict[str, Any]) -> dict[str, Any]:
    sample_id = _text(row.get("sample_id"))
    matrix = _text(row.get("matrix"))
    panel = _text(row.get("panel"))
    volume_ml = _volume(row.get("volume_ml"))
    frozen = _flag(row.get("frozen"))
    next_day = _flag(row.get("next_day"))
    spec = PANELS.get(panel)

    if not sample_id:
        return {
            "ok": False,
            "code": "MISSING_SAMPLE_ID",
            "sample_id": sample_id,
            "matrix": matrix,
            "panel": panel,
            "volume_ml": volume_ml,
        }
    if spec is None or spec["matrix"] != matrix or volume_ml < float(spec["min_volume_ml"]):
        return {
            "ok": False,
            "code": "UNDER_VOLUME",
            "sample_id": sample_id,
            "matrix": matrix,
            "panel": panel,
            "volume_ml": volume_ml,
            "min_volume_ml": None if spec is None else spec["min_volume_ml"],
        }
    return {
        "ok": True,
        "sample_id": sample_id,
        "matrix": matrix,
        "panel": panel,
        "analyses": list(spec["analyses"]),
        "volume_ml": volume_ml,
        "frozen": frozen,
        "next_day": next_day,
        "accession_id": accession_id(sample_id, panel, matrix),
        "route": panel,
    }


def juice_receive_allowed(record: dict[str, Any]) -> bool:
    if _text(record.get("matrix")) != "juice":
        return True
    return bool(record.get("frozen")) and bool(record.get("next_day"))


def report_status(record: dict[str, Any]) -> str:
    if record.get("released"):
        return "RELEASED"
    if not record.get("analyst_result"):
        return "BLOCKED_MISSING_RESULT"
    if not record.get("qc_signoff"):
        return "BLOCKED_MISSING_QC"
    return "READY_FOR_HUMAN_RELEASE"


def ingest_row(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    verdict = classify_submission(row)
    if not verdict["ok"]:
        reject = {
            "row_id": _text(row.get("row_id")),
            "sample_id": verdict.get("sample_id") or None,
            "code": verdict["code"],
            "matrix": verdict.get("matrix"),
            "panel": verdict.get("panel"),
            "volume_ml": verdict.get("volume_ml"),
        }
        fingerprint = sha256_hex(reject)
        existing = {sha256_hex(item) for item in journal["rejects"]}
        if fingerprint not in existing:
            journal["rejects"].append(reject)
            _event(journal, "REJECT", reject)
        return {"kind": "REJECT", "duplicate": fingerprint in existing, **reject}

    acc_id = verdict["accession_id"]
    existing_acc = journal["accessions"].get(acc_id)
    if existing_acc is not None:
        _event(
            journal,
            "REPLAY_NOOP",
            {"accession_id": acc_id, "sample_id": verdict["sample_id"]},
        )
        return {"kind": "REPLAY_NOOP", "accession_id": acc_id, "sample_id": verdict["sample_id"]}

    record = {
        "accession_id": acc_id,
        "sample_id": verdict["sample_id"],
        "matrix": verdict["matrix"],
        "panel": verdict["panel"],
        "route": verdict["route"],
        "analyses": verdict["analyses"],
        "volume_ml": verdict["volume_ml"],
        "frozen": verdict["frozen"],
        "next_day": verdict["next_day"],
        "state": "ACCESSIONED",
        "analyst_result": None,
        "qc_signoff": False,
        "released": False,
        "released_by": None,
        "report_status": "BLOCKED_MISSING_RESULT",
        "interface_state": "SIMULATED",
        "interface_live": False,
    }
    journal["accessions"][acc_id] = record
    _event(
        journal,
        "ACCESSION",
        {
            "accession_id": acc_id,
            "sample_id": verdict["sample_id"],
            "route": verdict["route"],
        },
    )
    return {"kind": "ACCESSION", "accession_id": acc_id, "route": verdict["route"]}


def receive(journal: dict[str, Any], accession_id_value: str) -> dict[str, Any]:
    record = journal["accessions"].get(accession_id_value)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_ACCESSION", "state": None}
    if record["state"] == "RECEIVED":
        return {"ok": True, "duplicate": True, "state": "RECEIVED", "accession_id": accession_id_value}
    if not juice_receive_allowed(record):
        _event(
            journal,
            "RECEIVE_BLOCKED",
            {
                "accession_id": accession_id_value,
                "code": "JUICE_REQUIRES_FROZEN_NEXT_DAY",
            },
        )
        return {
            "ok": False,
            "code": "JUICE_REQUIRES_FROZEN_NEXT_DAY",
            "state": record["state"],
            "accession_id": accession_id_value,
        }
    record["state"] = "RECEIVED"
    _event(journal, "RECEIVED", {"accession_id": accession_id_value})
    return {"ok": True, "duplicate": False, "state": "RECEIVED", "accession_id": accession_id_value}


def record_result(journal: dict[str, Any], accession_id_value: str, result: Any) -> dict[str, Any]:
    record = journal["accessions"].get(accession_id_value)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_ACCESSION"}
    if result in (None, ""):
        return {"ok": False, "code": "EMPTY_RESULT"}
    record["analyst_result"] = deepcopy(result)
    record["report_status"] = report_status(record)
    _event(journal, "ANALYST_RESULT", {"accession_id": accession_id_value})
    return {"ok": True, "report_status": record["report_status"]}


def qc_signoff(journal: dict[str, Any], accession_id_value: str) -> dict[str, Any]:
    record = journal["accessions"].get(accession_id_value)
    if record is None:
        return {"ok": False, "code": "UNKNOWN_ACCESSION"}
    record["qc_signoff"] = True
    record["report_status"] = report_status(record)
    _event(journal, "QC_SIGNOFF", {"accession_id": accession_id_value})
    return {"ok": True, "report_status": record["report_status"]}


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
    if role != HUMAN_RELEASER:
        _event(
            journal,
            "RELEASE_DENIED",
            {
                "accession_id": accession_id_value,
                "code": "AUTONOMOUS_RELEASE_DENIED",
                "actor_role": role or None,
            },
        )
        return {
            "ok": False,
            "code": "AUTONOMOUS_RELEASE_DENIED",
            "report_status": report_status(record),
        }
    status = report_status(record)
    if status != "READY_FOR_HUMAN_RELEASE" and status != "RELEASED":
        _event(
            journal,
            "RELEASE_DENIED",
            {
                "accession_id": accession_id_value,
                "code": "REPORT_BLOCKED",
                "report_status": status,
            },
        )
        return {"ok": False, "code": "REPORT_BLOCKED", "report_status": status}
    if record["released"]:
        return {"ok": True, "duplicate": True, "report_status": "RELEASED"}
    record["released"] = True
    record["released_by"] = _text(actor) or "human-releaser"
    record["report_status"] = "RELEASED"
    _event(
        journal,
        "RELEASED",
        {"accession_id": accession_id_value, "released_by": record["released_by"]},
    )
    return {"ok": True, "duplicate": False, "report_status": "RELEASED"}


def receive_eligible(journal: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for acc_id, record in journal["accessions"].items():
        out.append(receive(journal, acc_id))
    return out


def run_gate(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    journal = empty_journal()
    effects = [ingest_row(journal, row) for row in inbound]
    receives = receive_eligible(journal)
    autonomous = []
    for acc_id in journal["accessions"]:
        autonomous.append(
            release_report(journal, acc_id, actor_role="SYSTEM", actor="autonomous")
        )

    accessioned = sorted(journal["accessions"].values(), key=lambda item: item["sample_id"])
    reject_codes = sorted(item["code"] for item in journal["rejects"])
    routes = {item["sample_id"]: item["route"] for item in accessioned}
    received = [item["accession_id"] for item in accessioned if item["state"] == "RECEIVED"]
    blocked_reports = [item["accession_id"] for item in accessioned if item["report_status"] != "RELEASED"]

    body = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "truth_gate": TRUTH_GATE,
        "input_rows": len(inbound),
        "accessioned": len(accessioned),
        "rejected": len(journal["rejects"]),
        "reject_codes": reject_codes,
        "routes": routes,
        "accession_ids": [item["accession_id"] for item in accessioned],
        "received": sorted(received),
        "received_count": len(received),
        "blocked_reports": len(blocked_reports),
        "released_reports": 0,
        "replay_noops": sum(1 for item in effects if item.get("kind") == "REPLAY_NOOP"),
        "effects": effects,
        "receive_effects": receives,
        "autonomous_release_effects": autonomous,
        "accessions": accessioned,
        "rejects": deepcopy(journal["rejects"]),
        "interface_live": False,
        "interfaces": "SIMULATED",
        "autonomous_certification": False,
        "autonomous_release": False,
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
    before_rejects = len(journal["rejects"])
    effects = [ingest_row(journal, row) for row in inbound]
    added = set(journal["accessions"]) - before
    return {
        "added_accessions": sorted(added),
        "added_accession_count": len(added),
        "added_rejects": len(journal["rejects"]) - before_rejects,
        "replay_noops": sum(1 for item in effects if item.get("kind") == "REPLAY_NOOP"),
        "accession_count": len(journal["accessions"]),
        "reject_count": len(journal["rejects"]),
    }


def pass_contract(result: dict[str, Any]) -> list[str]:
    failures = []
    if result.get("input_rows") != 8:
        failures.append("input_rows!=8")
    if result.get("accessioned") != 6:
        failures.append("accessioned!=6")
    if result.get("rejected") != 2:
        failures.append("rejected!=2")
    if result.get("reject_codes") != ["MISSING_SAMPLE_ID", "UNDER_VOLUME"]:
        failures.append("reject_codes")
    expected_routes = {
        "CCB-C01": "CIDER_SINGLE",
        "CCB-J01": "JUICE_PANEL",
        "CCB-K01": "KOMBUCHA_ABV",
        "CCB-S01": "SPIRITS_ABV",
        "CCB-W01": "WINE_MULTI",
        "CCB-W02": "WINE_SINGLE",
    }
    if result.get("routes") != expected_routes:
        failures.append("routes")
    if len(set(result.get("accession_ids") or [])) != 6:
        failures.append("accession_ids_not_unique")
    if result.get("released_reports") != 0:
        failures.append("released_reports!=0")
    if result.get("blocked_reports") != 6:
        failures.append("blocked_reports!=6")
    if result.get("replay_noops") != 0:
        failures.append("fresh_run_replay_noops")
    if result.get("interface_live") is not False:
        failures.append("interface_live")
    if result.get("interfaces") != "SIMULATED":
        failures.append("interfaces")
    if result.get("autonomous_certification") is not False:
        failures.append("autonomous_certification")
    if result.get("autonomous_release") is not False:
        failures.append("autonomous_release")
    if not all(item.get("code") == "AUTONOMOUS_RELEASE_DENIED" for item in result.get("autonomous_release_effects") or []):
        failures.append("autonomous_release_not_denied")
    juice = next((item for item in result.get("accessions") or [] if item.get("sample_id") == "CCB-J01"), None)
    if juice is None or juice.get("state") != "RECEIVED":
        failures.append("juice_not_received")
    if juice and (not juice.get("frozen") or not juice.get("next_day")):
        failures.append("juice_flags")
    return failures


def main() -> int:
    first = run_gate()
    second = run_gate()
    journal = empty_journal()
    for row in build_acceptance_fixture():
        ingest_row(journal, row)
    replay = replay_into(journal)
    failures = pass_contract(first)
    if sha256_hex(first) != sha256_hex(second):
        failures.append("replay_mismatch")
    if first.get("manifest_sha256") != second.get("manifest_sha256"):
        failures.append("manifest_sha256_mismatch")
    if replay.get("added_accession_count") != 0:
        failures.append("replay_added_accessions")
    if replay.get("added_rejects") != 0:
        failures.append("replay_added_rejects")
    report = {
        "ok": not failures,
        "failures": failures,
        "manifest_sha256": first.get("manifest_sha256"),
        "accessioned": first.get("accessioned"),
        "rejected": first.get("rejected"),
        "reject_codes": first.get("reject_codes"),
        "routes": first.get("routes"),
        "received_count": first.get("received_count"),
        "blocked_reports": first.get("blocked_reports"),
        "replay_added_accessions": replay.get("added_accession_count"),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
