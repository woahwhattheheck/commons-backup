#!/usr/bin/env python3
"""Ward Laboratories feed/forage form to NIRS intake validator LIMS.

Demand: ward-feed-nirs-intake-validator-lims-01
Buyer: Ward Laboratories / Nikki Kuhr

Ingests synthetic feed/forage submission forms, reconciles bag labels,
applies description-to-NIRS calibration rules, routes NIRS vs wet-chemistry,
enforces preparation and time-window gates, opens worksheets only for
READY rows, and stages reports pending named-human release.

Acceptance: replay 400 synthetic submissions — 320 valid and 80 with
missing IDs, missing analyses, description/calibration conflicts,
duplicate bag labels, insufficient preparation, or time-sensitive
receipt violations. PASS only if 320 create one accession with exact
routing; all 80 receive the expected HOLD code; time rules evaluate
exactly; no held work gets a worksheet; source coordinates and hashes
persist; replay creates no accession or test job; human review
controls release.

HOLD / BUILD-AND-VERIFY. Synthetic fixtures only. Simulated/read-only
adapters. No production writes, outreach, or automatic release.
PRE-SALE TRANSPORT: NONE. cash_usd=0.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

DEMAND_ID = "ward-feed-nirs-intake-validator-lims-01"
SCHEMA = "commons-ward-feed-nirs-intake-validator-lims/v1"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
BUYER = "Ward Laboratories / Nikki Kuhr"
HUMAN_RELEASER = "NIKKI-KUHR-RELEASER"
COMMAND = "python3 ward_feed_nirs_intake_validator.py"

VALID_COUNT = 320
HOLD_COUNT = 80
INPUT_COUNT = VALID_COUNT + HOLD_COUNT

HOLD_MISSING_ID = "HOLD_MISSING_ID"
HOLD_MISSING_ANALYSIS = "HOLD_MISSING_ANALYSIS"
HOLD_DESC_CALIBRATION_CONFLICT = "HOLD_DESC_CALIBRATION_CONFLICT"
HOLD_DUPLICATE_BAG_LABEL = "HOLD_DUPLICATE_BAG_LABEL"
HOLD_INSUFFICIENT_PREP = "HOLD_INSUFFICIENT_PREP"
HOLD_TIME_WINDOW_VIOLATION = "HOLD_TIME_WINDOW_VIOLATION"

HOLD_CODES = (
    HOLD_MISSING_ID,
    HOLD_MISSING_ANALYSIS,
    HOLD_DESC_CALIBRATION_CONFLICT,
    HOLD_DUPLICATE_BAG_LABEL,
    HOLD_INSUFFICIENT_PREP,
    HOLD_TIME_WINDOW_VIOLATION,
)

HOLD_DISTRIBUTION = {
    HOLD_MISSING_ID: 14,
    HOLD_MISSING_ANALYSIS: 14,
    HOLD_DESC_CALIBRATION_CONFLICT: 13,
    HOLD_DUPLICATE_BAG_LABEL: 13,
    HOLD_INSUFFICIENT_PREP: 13,
    HOLD_TIME_WINDOW_VIOLATION: 13,
}

ROUTE_NIRS = "NIRS"
ROUTE_WET_CHEM = "WET_CHEM"

NIRS_CALIBRATIONS = {
    "ALFALFA_HAY": "NIRS-CAL-ALFALFA-2024",
    "CORN_SILAGE": "NIRS-CAL-CORNSILAGE-2024",
    "GRASS_HAY": "NIRS-CAL-GRASSHAY-2024",
    "TMR": "NIRS-CAL-TMR-2024",
    "SOYBEAN_MEAL": "NIRS-CAL-SBM-2024",
    "DISTILLERS_GRAINS": "NIRS-CAL-DDGS-2024",
    "WHEAT_MIDDS": "NIRS-CAL-MIDDS-2024",
    "COTTONSEED": "NIRS-CAL-COTTONSEED-2024",
}

WET_CHEM_DESCRIPTIONS = {
    "MINERAL_MIX": "WET-MINERAL-PANEL",
    "WATER_SAMPLE": "WET-WATER-PANEL",
    "MANURE": "WET-MANURE-PANEL",
    "SOIL": "WET-SOIL-PANEL",
}

ANALYSES_NIRS = ("MOISTURE", "CP", "ADF", "NDF", "LIGNIN", "FAT", "ASH")
ANALYSES_WET = ("CA", "P", "MG", "K", "S", "NA")

PREP_REQUIRED = {
    ROUTE_NIRS: "GRIND_1MM",
    ROUTE_WET_CHEM: "DIGEST_PREP",
}
MAX_RECEIPT_HOURS = {
    ROUTE_NIRS: 72,
    ROUTE_WET_CHEM: 48,
}

HERE = Path(__file__).resolve().parent
PACK = HERE / "revenue" / "ward_feed_nirs_intake_validator"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str("" if value is None else value).strip()


def accession_id_for(submission_id: str) -> str:
    digest = sha256_hex(
        {"demand_id": DEMAND_ID, "submission_id": submission_id, "kind": "accession"}
    )
    return "WARD-" + digest[:12]


def source_coords(index: int) -> dict[str, Any]:
    return {
        "lat": round(40.6994 + (index % 40) * 0.001, 6),
        "lon": round(-99.0817 - (index % 40) * 0.001, 6),
        "datum": "WGS84",
        "synthetic": True,
    }


def route_for_description(
    description: str, requested_route: str
) -> tuple[str | None, str | None, str | None]:
    desc = _text(description).upper()
    req = _text(requested_route).upper()
    if desc in NIRS_CALIBRATIONS:
        if req in ("", ROUTE_NIRS, "AUTO"):
            return ROUTE_NIRS, NIRS_CALIBRATIONS[desc], None
        if req == ROUTE_WET_CHEM:
            return ROUTE_WET_CHEM, "WET-FEED-PANEL", None
        return None, None, HOLD_DESC_CALIBRATION_CONFLICT
    if desc in WET_CHEM_DESCRIPTIONS:
        if req in ("", ROUTE_WET_CHEM, "AUTO"):
            return ROUTE_WET_CHEM, WET_CHEM_DESCRIPTIONS[desc], None
        if req == ROUTE_NIRS:
            return None, None, HOLD_DESC_CALIBRATION_CONFLICT
        return None, None, HOLD_DESC_CALIBRATION_CONFLICT
    return None, None, HOLD_DESC_CALIBRATION_CONFLICT


def build_acceptance_fixture() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    nirs_desc = list(NIRS_CALIBRATIONS.keys())
    wet_desc = list(WET_CHEM_DESCRIPTIONS.keys())

    for i in range(1, VALID_COUNT + 1):
        if i <= 240:
            desc = nirs_desc[(i - 1) % len(nirs_desc)]
            route = ROUTE_NIRS
            analyses = list(ANALYSES_NIRS)
            prep = PREP_REQUIRED[ROUTE_NIRS]
            receipt_h = 12 + (i % 40)
        else:
            desc = wet_desc[(i - 1) % len(wet_desc)]
            route = ROUTE_WET_CHEM
            analyses = list(ANALYSES_WET)
            prep = PREP_REQUIRED[ROUTE_WET_CHEM]
            receipt_h = 6 + (i % 30)
        sid = "WARD-V%04d" % i
        bag = "BAG-V%04d" % i
        coords = source_coords(i)
        rows.append(
            {
                "submission_id": sid,
                "bag_label": bag,
                "description": desc,
                "requested_route": route,
                "analyses": analyses,
                "prep_status": prep,
                "receipt_hours": receipt_h,
                "source_coords": coords,
                "source_hash": sha256_hex(
                    {
                        "submission_id": sid,
                        "bag_label": bag,
                        "description": desc,
                        "analyses": analyses,
                        "coords": coords,
                    }
                ),
                "expected_hold": None,
                "expected_route": route,
            }
        )

    hold_rows: list[dict[str, Any]] = []
    h = 0

    for n in range(1, HOLD_DISTRIBUTION[HOLD_MISSING_ID] + 1):
        h += 1
        hold_rows.append(
            {
                "submission_id": "",
                "bag_label": "BAG-HMISS%02d" % n,
                "description": "ALFALFA_HAY",
                "requested_route": ROUTE_NIRS,
                "analyses": list(ANALYSES_NIRS),
                "prep_status": PREP_REQUIRED[ROUTE_NIRS],
                "receipt_hours": 10,
                "source_coords": source_coords(1000 + h),
                "source_hash": sha256_hex({"kind": "missing_id", "n": n}),
                "expected_hold": HOLD_MISSING_ID,
                "expected_route": None,
                "hold_seed_id": "WARD-HMISS%02d" % n,
            }
        )

    for n in range(1, HOLD_DISTRIBUTION[HOLD_MISSING_ANALYSIS] + 1):
        h += 1
        sid = "WARD-HMAN%02d" % n
        hold_rows.append(
            {
                "submission_id": sid,
                "bag_label": "BAG-HMAN%02d" % n,
                "description": "CORN_SILAGE",
                "requested_route": ROUTE_NIRS,
                "analyses": [],
                "prep_status": PREP_REQUIRED[ROUTE_NIRS],
                "receipt_hours": 10,
                "source_coords": source_coords(1000 + h),
                "source_hash": sha256_hex({"submission_id": sid, "analyses": []}),
                "expected_hold": HOLD_MISSING_ANALYSIS,
                "expected_route": None,
            }
        )

    for n in range(1, HOLD_DISTRIBUTION[HOLD_DESC_CALIBRATION_CONFLICT] + 1):
        h += 1
        sid = "WARD-HCAL%02d" % n
        desc = wet_desc[(n - 1) % len(wet_desc)]
        hold_rows.append(
            {
                "submission_id": sid,
                "bag_label": "BAG-HCAL%02d" % n,
                "description": desc,
                "requested_route": ROUTE_NIRS,
                "analyses": list(ANALYSES_NIRS),
                "prep_status": PREP_REQUIRED[ROUTE_NIRS],
                "receipt_hours": 10,
                "source_coords": source_coords(1000 + h),
                "source_hash": sha256_hex(
                    {"submission_id": sid, "description": desc, "req": ROUTE_NIRS}
                ),
                "expected_hold": HOLD_DESC_CALIBRATION_CONFLICT,
                "expected_route": None,
            }
        )

    for n in range(1, HOLD_DISTRIBUTION[HOLD_DUPLICATE_BAG_LABEL] + 1):
        h += 1
        sid = "WARD-HDUP%02d" % n
        hold_rows.append(
            {
                "submission_id": sid,
                "bag_label": "BAG-V%04d" % n,
                "description": "GRASS_HAY",
                "requested_route": ROUTE_NIRS,
                "analyses": list(ANALYSES_NIRS),
                "prep_status": PREP_REQUIRED[ROUTE_NIRS],
                "receipt_hours": 10,
                "source_coords": source_coords(1000 + h),
                "source_hash": sha256_hex(
                    {"submission_id": sid, "bag_label": "BAG-V%04d" % n}
                ),
                "expected_hold": HOLD_DUPLICATE_BAG_LABEL,
                "expected_route": None,
            }
        )

    for n in range(1, HOLD_DISTRIBUTION[HOLD_INSUFFICIENT_PREP] + 1):
        h += 1
        sid = "WARD-HPREP%02d" % n
        hold_rows.append(
            {
                "submission_id": sid,
                "bag_label": "BAG-HPREP%02d" % n,
                "description": "TMR",
                "requested_route": ROUTE_NIRS,
                "analyses": list(ANALYSES_NIRS),
                "prep_status": "WHOLE_BAG_UNGROUND",
                "receipt_hours": 10,
                "source_coords": source_coords(1000 + h),
                "source_hash": sha256_hex(
                    {"submission_id": sid, "prep": "WHOLE_BAG_UNGROUND"}
                ),
                "expected_hold": HOLD_INSUFFICIENT_PREP,
                "expected_route": None,
            }
        )

    for n in range(1, HOLD_DISTRIBUTION[HOLD_TIME_WINDOW_VIOLATION] + 1):
        h += 1
        sid = "WARD-HTIME%02d" % n
        hours = MAX_RECEIPT_HOURS[ROUTE_NIRS] + 6 + n
        hold_rows.append(
            {
                "submission_id": sid,
                "bag_label": "BAG-HTIME%02d" % n,
                "description": "ALFALFA_HAY",
                "requested_route": ROUTE_NIRS,
                "analyses": list(ANALYSES_NIRS),
                "prep_status": PREP_REQUIRED[ROUTE_NIRS],
                "receipt_hours": hours,
                "source_coords": source_coords(1000 + h),
                "source_hash": sha256_hex(
                    {"submission_id": sid, "receipt_hours": hours}
                ),
                "expected_hold": HOLD_TIME_WINDOW_VIOLATION,
                "expected_route": None,
            }
        )

    assert h == HOLD_COUNT
    assert len(hold_rows) == HOLD_COUNT
    rows.extend(hold_rows)
    assert len(rows) == INPUT_COUNT
    return rows


def fixture_manifest(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = rows if rows is not None else build_acceptance_fixture()
    payload = {"demand_id": DEMAND_ID, "rows": rows}
    return {
        "demand_id": DEMAND_ID,
        "input_count": len(rows),
        "fixture_sha256": sha256_hex(payload),
        "hold_distribution": dict(HOLD_DISTRIBUTION),
    }


def empty_journal() -> dict[str, Any]:
    return {
        "accessions": [],
        "holds": [],
        "worksheets": [],
        "staged_reports": [],
        "released_reports": [],
        "bag_index": {},
        "submission_index": {},
        "production_writes": 0,
        "adapter": "SIMULATED",
    }


def classify(row: dict[str, Any], journal: dict[str, Any]) -> dict[str, Any]:
    sid = _text(row.get("submission_id"))
    bag = _text(row.get("bag_label"))
    analyses = row.get("analyses") or []
    desc = _text(row.get("description")).upper()
    req = _text(row.get("requested_route")).upper()
    prep = _text(row.get("prep_status")).upper()
    receipt_hours = int(row.get("receipt_hours") or 0)
    coords = row.get("source_coords") or {}
    source_hash = _text(row.get("source_hash"))

    if not sid:
        return {
            "kind": "HOLD",
            "code": HOLD_MISSING_ID,
            "submission_id": _text(row.get("hold_seed_id")) or bag or "UNKNOWN",
            "bag_label": bag,
            "source_coords": coords,
            "source_hash": source_hash,
            "worksheet": False,
        }
    if not analyses:
        return {
            "kind": "HOLD",
            "code": HOLD_MISSING_ANALYSIS,
            "submission_id": sid,
            "bag_label": bag,
            "source_coords": coords,
            "source_hash": source_hash,
            "worksheet": False,
        }
    if bag and bag in journal["bag_index"]:
        return {
            "kind": "HOLD",
            "code": HOLD_DUPLICATE_BAG_LABEL,
            "submission_id": sid,
            "bag_label": bag,
            "source_coords": coords,
            "source_hash": source_hash,
            "worksheet": False,
        }

    route, panel, conflict = route_for_description(desc, req)
    if conflict:
        return {
            "kind": "HOLD",
            "code": conflict,
            "submission_id": sid,
            "bag_label": bag,
            "source_coords": coords,
            "source_hash": source_hash,
            "worksheet": False,
        }
    assert route is not None and panel is not None

    if prep != PREP_REQUIRED[route]:
        return {
            "kind": "HOLD",
            "code": HOLD_INSUFFICIENT_PREP,
            "submission_id": sid,
            "bag_label": bag,
            "source_coords": coords,
            "source_hash": source_hash,
            "worksheet": False,
            "route": route,
        }

    max_h = MAX_RECEIPT_HOURS[route]
    if receipt_hours > max_h:
        return {
            "kind": "HOLD",
            "code": HOLD_TIME_WINDOW_VIOLATION,
            "submission_id": sid,
            "bag_label": bag,
            "source_coords": coords,
            "source_hash": source_hash,
            "worksheet": False,
            "route": route,
            "receipt_hours": receipt_hours,
            "max_receipt_hours": max_h,
        }

    return {
        "kind": "READY",
        "submission_id": sid,
        "bag_label": bag,
        "accession_id": accession_id_for(sid),
        "route": route,
        "panel": panel,
        "analyses": list(analyses),
        "prep_status": prep,
        "receipt_hours": receipt_hours,
        "source_coords": coords,
        "source_hash": source_hash,
        "worksheet": True,
        "adapter": "SIMULATED",
    }


def ingest_row(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    effect = classify(row, journal)
    if effect["kind"] == "HOLD":
        journal["holds"].append(
            {
                "code": effect["code"],
                "submission_id": effect["submission_id"],
                "bag_label": effect.get("bag_label"),
                "source_coords": effect.get("source_coords"),
                "source_hash": effect.get("source_hash"),
                "scheduled": False,
                "worksheet": False,
            }
        )
        return effect

    journal["accessions"].append(
        {
            "accession_id": effect["accession_id"],
            "submission_id": effect["submission_id"],
            "bag_label": effect["bag_label"],
            "route": effect["route"],
            "panel": effect["panel"],
            "analyses": effect["analyses"],
            "prep_status": effect["prep_status"],
            "receipt_hours": effect["receipt_hours"],
            "source_coords": effect["source_coords"],
            "source_hash": effect["source_hash"],
            "scheduled": True,
            "adapter": "SIMULATED",
            "interface_live": False,
        }
    )
    journal["submission_index"][effect["submission_id"]] = effect["accession_id"]
    journal["bag_index"][effect["bag_label"]] = effect["accession_id"]
    journal["worksheets"].append(
        {
            "worksheet_id": "WS-" + effect["accession_id"],
            "accession_id": effect["accession_id"],
            "route": effect["route"],
            "panel": effect["panel"],
            "analyses": effect["analyses"],
        }
    )
    journal["staged_reports"].append(
        {
            "accession_id": effect["accession_id"],
            "route": effect["route"],
            "panel": effect["panel"],
            "status": "STAGED",
            "release": "PENDING_HUMAN",
            "releaser": None,
            "source_hash": effect["source_hash"],
        }
    )
    return effect


def release_report(
    journal: dict[str, Any], accession: str, releaser: str
) -> dict[str, Any]:
    if _text(releaser) != HUMAN_RELEASER:
        return {"ok": False, "reason": "NAMED_HUMAN_REQUIRED"}
    for report in journal["staged_reports"]:
        if report["accession_id"] == accession and report["status"] == "STAGED":
            report["status"] = "RELEASED"
            report["releaser"] = releaser
            journal["released_reports"].append(deepcopy(report))
            return {"ok": True, "report": report}
    return {"ok": False, "reason": "NOT_FOUND"}


def autonomous_release_denied() -> bool:
    denied = release_report(empty_journal(), "WARD-DOES-NOT-EXIST", "AUTONOMOUS")
    return denied.get("ok") is False and denied.get("reason") == "NAMED_HUMAN_REQUIRED"


def run_once(rows: list[dict[str, Any]]) -> dict[str, Any]:
    journal = empty_journal()
    for row in rows:
        ingest_row(journal, row)
    return journal


def run_gate(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = rows if rows is not None else build_acceptance_fixture()
    manifest = fixture_manifest(rows)
    first = run_once(rows)

    populated = run_once(rows)
    before_acc = len(populated["accessions"])
    before_ws = len(populated["worksheets"])
    for row in rows:
        ingest_row(populated, row)
    replay_new_accessions = len(populated["accessions"]) - before_acc
    replay_new_worksheets = len(populated["worksheets"]) - before_ws

    hold_codes = [h["code"] for h in first["holds"]]
    routes = Counter(a["route"] for a in first["accessions"])
    report_digest = sha256_hex(
        [
            {
                "accession_id": r["accession_id"],
                "route": r["route"],
                "panel": r["panel"],
                "source_hash": r["source_hash"],
                "status": r["status"],
            }
            for r in first["staged_reports"]
        ]
    )
    audit = {
        "demand_id": DEMAND_ID,
        "schema": SCHEMA,
        "truth_gate": TRUTH_GATE,
        "buyer": BUYER,
        "input_count": len(rows),
        "accessioned": len(first["accessions"]),
        "held": len(first["holds"]),
        "worksheet_count": len(first["worksheets"]),
        "staged_report_count": len(first["staged_reports"]),
        "released_reports": len(first["released_reports"]),
        "hold_counter": dict(Counter(hold_codes)),
        "routes": dict(routes),
        "replay_new_accessions": replay_new_accessions,
        "replay_new_worksheets": replay_new_worksheets,
        "production_writes": first["production_writes"],
        "adapter": first["adapter"],
        "fixture_sha256": manifest["fixture_sha256"],
        "report_digest": report_digest,
        "autonomous_release_denied": autonomous_release_denied(),
        "held_with_worksheet": sum(
            1 for h in first["holds"] if h.get("worksheet") or h.get("scheduled")
        ),
    }
    audit["audit_sha256"] = sha256_hex(audit)
    return {
        **audit,
        "accession_rows": first["accessions"],
        "hold_rows": first["holds"],
        "worksheet_rows": first["worksheets"],
        "staged_report_rows": first["staged_reports"],
        "hold_codes": hold_codes,
        "hold_code_set": sorted(set(hold_codes)),
        "manifest": manifest,
    }


def expected_actual(result: dict[str, Any]) -> dict[str, Any]:
    actual = {
        "input_count": result["input_count"],
        "accessioned": result["accessioned"],
        "held": result["held"],
        "worksheet_count": result["worksheet_count"],
        "staged_report_count": result["staged_report_count"],
        "released_reports": result["released_reports"],
        "replay_new_accessions": result["replay_new_accessions"],
        "replay_new_worksheets": result["replay_new_worksheets"],
        "production_writes": result["production_writes"],
        "held_with_worksheet": result["held_with_worksheet"],
    }
    expected = {
        "input_count": INPUT_COUNT,
        "accessioned": VALID_COUNT,
        "held": HOLD_COUNT,
        "worksheet_count": VALID_COUNT,
        "staged_report_count": VALID_COUNT,
        "released_reports": 0,
        "replay_new_accessions": 0,
        "replay_new_worksheets": 0,
        "production_writes": 0,
        "held_with_worksheet": 0,
    }
    return {"expected": expected, "actual": actual, "match": expected == actual}


def pass_contract(result: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    ea = expected_actual(result)
    if not ea["match"]:
        failures.append("count_mismatch")
    if result["hold_counter"] != dict(HOLD_DISTRIBUTION):
        failures.append("hold_distribution:%s" % result["hold_counter"])
    if sorted(result["hold_code_set"]) != sorted(HOLD_CODES):
        failures.append("hold_code_set:%s" % result["hold_code_set"])
    if result["routes"].get(ROUTE_NIRS) != 240:
        failures.append("nirs_route:%s" % result["routes"])
    if result["routes"].get(ROUTE_WET_CHEM) != 80:
        failures.append("wet_route:%s" % result["routes"])
    if not result["autonomous_release_denied"]:
        failures.append("autonomous_release_not_denied")
    if result["adapter"] != "SIMULATED":
        failures.append("adapter")
    for acc in result["accession_rows"]:
        if not acc.get("source_hash") or not acc.get("source_coords"):
            failures.append("missing_source:%s" % acc.get("accession_id"))
            break
    for hold in result["hold_rows"]:
        if hold.get("worksheet") or hold.get("scheduled"):
            failures.append("held_scheduled:%s" % hold.get("submission_id"))
            break
    return failures


def write_pack(result: dict[str, Any]) -> None:
    PACK.mkdir(parents=True, exist_ok=True)
    rows = build_acceptance_fixture()
    (PACK / "fixture.json").write_text(
        _canonical({"demand_id": DEMAND_ID, "rows": rows}) + "\n", encoding="utf-8"
    )
    contract = {
        "id": DEMAND_ID,
        "version": 1,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "schema": SCHEMA,
        "command": COMMAND,
        "acceptance": [
            "400 synthetic submissions",
            "exactly 320 READY with one accession and exact NIRS/WET_CHEM routing",
            "exactly 80 HOLD with predetermined codes",
            "no HOLD receives a worksheet",
            "source coordinates and hashes persist",
            "replay adds zero accessions and zero worksheets",
            "named-human release only",
        ],
        "hold_codes": list(HOLD_CODES),
        "hold_distribution": dict(HOLD_DISTRIBUTION),
        "routes": {ROUTE_NIRS: 240, ROUTE_WET_CHEM: 80},
        "golden": {
            "fixture_sha256": result["fixture_sha256"],
            "audit_sha256": result["audit_sha256"],
            "report_digest": result["report_digest"],
        },
        "exclusions": [
            "no autonomous release",
            "no production writes",
            "no outreach",
            "adapters simulated/read-only",
        ],
        "pre_sale_transport": "NONE",
        "cash_usd": 0,
        "open_door": True,
        "requires_login": False,
    }
    (PACK / "contract.json").write_text(_canonical(contract) + "\n", encoding="utf-8")
    receipt = {
        "demand_id": DEMAND_ID,
        "truth_gate": TRUTH_GATE,
        "pass": pass_contract(result) == [],
        "counts": expected_actual(result),
        "fixture_sha256": result["fixture_sha256"],
        "audit_sha256": result["audit_sha256"],
        "report_digest": result["report_digest"],
        "hold_counter": result["hold_counter"],
        "routes": result["routes"],
        "command": COMMAND,
    }
    (PACK / "receipt.json").write_text(_canonical(receipt) + "\n", encoding="utf-8")
    (PACK / "receipt.md").write_text(
        "\n".join(
            [
                f"# Receipt — {DEMAND_ID}",
                "",
                f"- buyer: {BUYER}",
                f"- gate: {TRUTH_GATE}",
                f"- command: `{COMMAND}`",
                f"- input: {INPUT_COUNT}",
                f"- READY/accessioned: {VALID_COUNT}",
                f"- HOLD: {HOLD_COUNT}",
                f"- fixture_sha256: `{result['fixture_sha256']}`",
                f"- audit_sha256: `{result['audit_sha256']}`",
                f"- report_digest: `{result['report_digest']}`",
                f"- routes: NIRS={result['routes'].get(ROUTE_NIRS)} "
                f"WET_CHEM={result['routes'].get(ROUTE_WET_CHEM)}",
                f"- replay new accessions: {result['replay_new_accessions']}",
                f"- replay new worksheets: {result['replay_new_worksheets']}",
                f"- autonomous release denied: {result['autonomous_release_denied']}",
                "- pre-sale transport: NONE",
                "- cash_usd: 0",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main() -> int:
    result = run_gate()
    failures = pass_contract(result)
    write_pack(result)
    print(
        _canonical(
            {
                "ok": not failures,
                "demand_id": DEMAND_ID,
                "failures": failures,
                "fixture_sha256": result["fixture_sha256"],
                "audit_sha256": result["audit_sha256"],
                "report_digest": result["report_digest"],
                "accessioned": result["accessioned"],
                "held": result["held"],
                "hold_counter": result["hold_counter"],
                "routes": result["routes"],
                "replay_new_accessions": result["replay_new_accessions"],
                "replay_new_worksheets": result["replay_new_worksheets"],
            }
        )
    )
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
