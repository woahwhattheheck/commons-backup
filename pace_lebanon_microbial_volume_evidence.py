#!/usr/bin/env python3
"""Pace Lebanon microbial-volume evidence LIMS.

Demand: pace-lebanon-microbial-volume-evidence-lims-01
Buyer: Pace Life Sciences / Amanda Yoakum

The runner reconciles sample, lot, matrix, specification, controlled method,
route, incubation timepoints, and QC controls into a staged report receipt.
Its 120-row frozen synthetic fixture contains 90 valid submissions and 30
predetermined holds. Adapters are simulated/read-only and release always
requires a named human reviewer.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

DEMAND_ID = "pace-lebanon-microbial-volume-evidence-lims-01"
SCHEMA = "commons-pace-lebanon-microbial-volume-evidence-lims/v1"
BUYER = "Pace Life Sciences / Amanda Yoakum"
TRUTH_GATE = "HOLD / BUILD-AND-VERIFY"
HUMAN_REVIEWER_ROLE = "QUALITY_REVIEWER"

ROUTES = {
    "MICROBIAL_LIMITS": {
        "method": "CTL-ML-001",
        "matrix": "NONSTERILE_PRODUCT",
        "specification": "SPEC-ML-01",
        "duration_hours": 72,
        "timepoints_hours": [0, 24, 48, 72],
        "unit": "CFU/g",
    },
    "STERILITY": {
        "method": "CTL-ST-001",
        "matrix": "STERILE_PRODUCT",
        "specification": "SPEC-ST-01",
        "duration_hours": 336,
        "timepoints_hours": [0, 168, 336],
        "unit": "growth",
    },
    "CCIT": {
        "method": "CTL-CCIT-001",
        "matrix": "CONTAINER_CLOSURE",
        "specification": "SPEC-CCIT-01",
        "duration_hours": 48,
        "timepoints_hours": [0, 24, 48],
        "unit": "pass/fail",
    },
}

HOLD_CODES = (
    "HOLD_DUPLICATE_SUBMISSION_ID",
    "HOLD_MISSING_METHOD_SPEC_MATRIX",
    "HOLD_ROUTE_MISMATCH",
    "HOLD_INCUBATION_WINDOW",
    "HOLD_QC_CONTROL_FAILURE",
)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str("" if value is None else value).strip()


def _base_submission(index: int) -> dict[str, Any]:
    route_name = tuple(ROUTES)[(index - 1) % len(ROUTES)]
    route = ROUTES[route_name]
    token = f"{index:03d}"
    return {
        "row_id": f"PACE-{token}",
        "submission_id": f"SUB-{token}",
        "sample_id": f"SAMPLE-{token}",
        "lot_id": f"LOT-{((index - 1) // 3) + 1:03d}",
        "matrix": route["matrix"],
        "specification": route["specification"],
        "route": route_name,
        "method": route["method"],
        "method_version": "2026.1",
        "planned_duration_hours": route["duration_hours"],
        "timepoints_hours": list(route["timepoints_hours"]),
        "qc_control": "PASS",
        "positive_control": "PASS",
        "count": index * 10 if route_name == "MICROBIAL_LIMITS" else index % 2,
        "unit": route["unit"],
        "source_revision": "PACE-SYNTHETIC-2026-01",
        "rush": index % 5 == 0,
        "exception_type": None,
        "synthetic": True,
        "deidentified": True,
    }


def _exception_submission(index: int) -> dict[str, Any]:
    row = _base_submission(index)
    if index <= 98:
        row["submission_id"] = f"SUB-{index - 90:03d}"
        row["exception_type"] = "DUPLICATE_ID"
    elif index <= 105:
        selector = (index - 99) % 3
        row[("method", "specification", "matrix")[selector]] = ""
        row["exception_type"] = "MISSING_METHOD_SPEC_MATRIX"
    elif index <= 110:
        current = row["route"]
        row["route"] = next(name for name in ROUTES if name != current)
        row["exception_type"] = "WRONG_ROUTE"
    elif index <= 115:
        row["planned_duration_hours"] -= 1
        row["timepoints_hours"] = list(row["timepoints_hours"][:-1])
        row["exception_type"] = "INCUBATION_WINDOW"
    else:
        row["qc_control"] = "FAIL" if index <= 118 else "PASS"
        row["positive_control"] = "FAIL" if index > 118 else "PASS"
        row["exception_type"] = "QC_CONTROL_FAILURE"
    return row


def build_acceptance_fixture() -> list[dict[str, Any]]:
    """Return the frozen 120-row fixture (90 valid, 30 predetermined holds)."""
    rows = [_base_submission(index) for index in range(1, 91)]
    rows.extend(_exception_submission(index) for index in range(91, 121))
    expected = {
        None: 90,
        "DUPLICATE_ID": 8,
        "MISSING_METHOD_SPEC_MATRIX": 7,
        "WRONG_ROUTE": 5,
        "INCUBATION_WINDOW": 5,
        "QC_CONTROL_FAILURE": 5,
    }
    actual = {name: 0 for name in expected}
    for row in rows:
        actual[row["exception_type"]] += 1
    if len(rows) != 120 or actual != expected:
        raise RuntimeError(f"invalid frozen fixture: rows={len(rows)} split={actual}")
    return rows


def empty_journal() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "submissions": {},
        "submission_index": {},
        "jobs": {},
        "holds": [],
        "reports": {},
        "events": [],
        "processed_rows": {},
        "interface_live": False,
        "production_writes": 0,
        "automatic_releases": 0,
    }


def _event(journal: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    journal["events"].append(
        {"seq": len(journal["events"]) + 1, "kind": kind, **deepcopy(payload)}
    )


def normalize_submission(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "row_id": _text(row.get("row_id")),
        "submission_id": _text(row.get("submission_id")),
        "sample_id": _text(row.get("sample_id")),
        "lot_id": _text(row.get("lot_id")),
        "matrix": _text(row.get("matrix")).upper(),
        "specification": _text(row.get("specification")).upper(),
        "route": _text(row.get("route")).upper(),
        "method": _text(row.get("method")).upper(),
        "method_version": _text(row.get("method_version")),
        "planned_duration_hours": int(row.get("planned_duration_hours") or 0),
        "timepoints_hours": [int(value) for value in row.get("timepoints_hours") or []],
        "qc_control": _text(row.get("qc_control")).upper(),
        "positive_control": _text(row.get("positive_control")).upper(),
        "count": row.get("count"),
        "unit": _text(row.get("unit")),
        "source_revision": _text(row.get("source_revision")),
        "rush": bool(row.get("rush")),
        "synthetic": True,
        "deidentified": True,
    }


def classify_submission(
    norm: dict[str, Any], journal: dict[str, Any]
) -> dict[str, Any]:
    if norm["submission_id"] in journal["submission_index"]:
        return {"ok": False, "code": "HOLD_DUPLICATE_SUBMISSION_ID"}
    if (
        not norm["submission_id"]
        or not norm["sample_id"]
        or not norm["lot_id"]
        or not norm["method"]
        or not norm["method_version"]
        or not norm["specification"]
        or not norm["matrix"]
    ):
        return {"ok": False, "code": "HOLD_MISSING_METHOD_SPEC_MATRIX"}
    expected = ROUTES.get(norm["route"])
    if (
        expected is None
        or norm["method"] != expected["method"]
        or norm["matrix"] != expected["matrix"]
        or norm["specification"] != expected["specification"]
        or norm["unit"] != expected["unit"]
    ):
        return {"ok": False, "code": "HOLD_ROUTE_MISMATCH"}
    if (
        norm["planned_duration_hours"] < expected["duration_hours"]
        or norm["timepoints_hours"] != expected["timepoints_hours"]
    ):
        return {"ok": False, "code": "HOLD_INCUBATION_WINDOW"}
    if norm["qc_control"] != "PASS" or norm["positive_control"] != "PASS":
        return {"ok": False, "code": "HOLD_QC_CONTROL_FAILURE"}
    return {"ok": True}


def _hold(
    journal: dict[str, Any], norm: dict[str, Any], code: str
) -> dict[str, Any]:
    hold = {
        "row_id": norm["row_id"],
        "submission_id": norm["submission_id"],
        "sample_id": norm["sample_id"] or None,
        "code": code,
        "state": "HOLD",
        "jobs_created": 0,
        "results_created": 0,
        "reports_staged": 0,
        "released": False,
    }
    journal["holds"].append(hold)
    journal["processed_rows"][norm["row_id"]] = {
        "kind": "HOLD",
        "submission_id": norm["submission_id"],
        "code": code,
    }
    _event(journal, "HOLD", hold)
    return {"kind": "HOLD", **deepcopy(hold)}


def _job_id(submission_id: str) -> str:
    return "PACE-JOB-" + sha256_hex({"demand_id": DEMAND_ID, "submission_id": submission_id})[:12]


def _report_id(submission_id: str) -> str:
    return "PACE-RPT-" + sha256_hex({"demand_id": DEMAND_ID, "submission_id": submission_id})[:12]


def ingest_row(journal: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    norm = normalize_submission(row)
    if norm["row_id"] in journal["processed_rows"]:
        _event(
            journal,
            "REPLAY_NOOP",
            {"row_id": norm["row_id"], "submission_id": norm["submission_id"]},
        )
        return {
            "kind": "REPLAY_NOOP",
            "row_id": norm["row_id"],
            "submission_id": norm["submission_id"],
        }

    verdict = classify_submission(norm, journal)
    if not verdict["ok"]:
        return _hold(journal, norm, verdict["code"])

    route = ROUTES[norm["route"]]
    source_payload = {
        key: norm[key]
        for key in (
            "submission_id",
            "sample_id",
            "lot_id",
            "matrix",
            "specification",
            "route",
            "method",
            "method_version",
            "planned_duration_hours",
            "timepoints_hours",
            "count",
            "unit",
            "source_revision",
        )
    }
    source_hash = sha256_hex(source_payload)
    method_hash = sha256_hex(
        {
            "method": norm["method"],
            "version": norm["method_version"],
            "specification": norm["specification"],
            "matrix": norm["matrix"],
        }
    )
    result_payload = {
        "count": norm["count"],
        "unit": norm["unit"],
        "timepoints_hours": norm["timepoints_hours"],
        "qc_control": norm["qc_control"],
        "positive_control": norm["positive_control"],
        "source_hash": source_hash,
        "method_hash": method_hash,
    }
    result_hash = sha256_hex(result_payload)
    job_id = _job_id(norm["submission_id"])
    report_id = _report_id(norm["submission_id"])
    record = {
        **source_payload,
        "rush": norm["rush"],
        "minimum_duration_hours": route["duration_hours"],
        "source_hash": source_hash,
        "method_hash": method_hash,
        "job_id": job_id,
        "report_id": report_id,
        "state": "READY_FOR_REVIEWER",
        "released": False,
        "released_by": None,
        "interface_state": "SIMULATED",
    }
    job = {
        "job_id": job_id,
        "submission_id": norm["submission_id"],
        "route": norm["route"],
        "method": norm["method"],
        "method_version": norm["method_version"],
        "timepoints_hours": norm["timepoints_hours"],
        "minimum_duration_hours": route["duration_hours"],
        "planned_duration_hours": norm["planned_duration_hours"],
        "rush": norm["rush"],
        "qc_control": norm["qc_control"],
        "positive_control": norm["positive_control"],
        "result": result_payload,
        "result_hash": result_hash,
        "state": "COMPLETE_PENDING_REVIEW",
    }
    report = {
        "report_id": report_id,
        "submission_id": norm["submission_id"],
        "job_id": job_id,
        "source_hash": source_hash,
        "method_hash": method_hash,
        "result_hash": result_hash,
        "status": "STAGED",
        "released": False,
        "released_by": None,
    }
    journal["submissions"][norm["submission_id"]] = record
    journal["submission_index"][norm["submission_id"]] = norm["row_id"]
    journal["jobs"][job_id] = job
    journal["reports"][report_id] = report
    journal["processed_rows"][norm["row_id"]] = {
        "kind": "READY",
        "submission_id": norm["submission_id"],
        "job_id": job_id,
        "report_id": report_id,
    }
    _event(
        journal,
        "REPORT_STAGED",
        {
            "submission_id": norm["submission_id"],
            "job_id": job_id,
            "report_id": report_id,
            "route": norm["route"],
        },
    )
    return {
        "kind": "READY",
        "submission_id": norm["submission_id"],
        "job_id": job_id,
        "report_id": report_id,
    }


def release_report(
    journal: dict[str, Any], report_id: str, *, actor_role: str, actor: str
) -> dict[str, Any]:
    report = journal["reports"].get(report_id)
    if report is None:
        return {"ok": False, "code": "UNKNOWN_REPORT"}
    if _text(actor_role).upper() != HUMAN_REVIEWER_ROLE or not _text(actor):
        _event(
            journal,
            "RELEASE_DENIED",
            {"report_id": report_id, "code": "AUTONOMOUS_RELEASE_DENIED"},
        )
        return {"ok": False, "code": "AUTONOMOUS_RELEASE_DENIED"}
    if report["released"]:
        return {"ok": True, "duplicate": True, "status": "RELEASED"}
    report["released"] = True
    report["released_by"] = _text(actor)
    report["status"] = "RELEASED"
    submission = journal["submissions"][report["submission_id"]]
    submission["released"] = True
    submission["released_by"] = _text(actor)
    submission["state"] = "RELEASED"
    _event(
        journal,
        "RELEASED",
        {"report_id": report_id, "released_by": _text(actor)},
    )
    return {"ok": True, "duplicate": False, "status": "RELEASED"}


def replay_into(
    journal: dict[str, Any], rows: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    before = {
        "submissions": len(journal["submissions"]),
        "jobs": len(journal["jobs"]),
        "holds": len(journal["holds"]),
        "reports": len(journal["reports"]),
    }
    effects = [ingest_row(journal, row) for row in inbound]
    return {
        "added_submissions": len(journal["submissions"]) - before["submissions"],
        "added_jobs": len(journal["jobs"]) - before["jobs"],
        "added_holds": len(journal["holds"]) - before["holds"],
        "added_reports": len(journal["reports"]) - before["reports"],
        "replay_noops": sum(item["kind"] == "REPLAY_NOOP" for item in effects),
    }


def run_gate(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inbound = deepcopy(rows if rows is not None else build_acceptance_fixture())
    journal = empty_journal()
    effects = [ingest_row(journal, row) for row in inbound]
    autonomous = [
        release_report(
            journal,
            report_id,
            actor_role="SYSTEM",
            actor="",
        )
        for report_id in sorted(journal["reports"])
    ]
    hold_counts = {code: 0 for code in HOLD_CODES}
    for hold in journal["holds"]:
        hold_counts[hold["code"]] += 1
    route_counts = {route: 0 for route in ROUTES}
    for job in journal["jobs"].values():
        route_counts[job["route"]] += 1
    staged_reports = sorted(journal["reports"].values(), key=lambda item: item["report_id"])
    manifest = {
        "demand_id": DEMAND_ID,
        "submissions": sorted(journal["submissions"]),
        "jobs": sorted(journal["jobs"]),
        "reports": [item["report_id"] for item in staged_reports],
        "holds": sorted(
            (item["row_id"], item["submission_id"], item["code"])
            for item in journal["holds"]
        ),
    }
    result = {
        "schema": SCHEMA,
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "truth_gate": TRUTH_GATE,
        "input_rows": len(inbound),
        "ready": len(journal["submissions"]),
        "holds": len(journal["holds"]),
        "jobs": len(journal["jobs"]),
        "reports_staged": len(staged_reports),
        "reports_released": sum(item["released"] for item in staged_reports),
        "hold_counts": hold_counts,
        "route_counts": route_counts,
        "manifest_sha256": sha256_hex(manifest),
        "audit_sha256": sha256_hex(
            {
                "events": journal["events"],
                "manifest": manifest,
                "truth_gate": TRUTH_GATE,
            }
        ),
        "submissions": sorted(
            journal["submissions"].values(), key=lambda item: item["submission_id"]
        ),
        "job_records": sorted(
            journal["jobs"].values(), key=lambda item: item["job_id"]
        ),
        "report_records": staged_reports,
        "hold_records": deepcopy(journal["holds"]),
        "effects": effects,
        "autonomous_release_effects": autonomous,
        "interface_live": False,
        "interfaces": "SIMULATED_READ_ONLY",
        "production_writes": 0,
        "automatic_releases": 0,
        "autonomous_release": False,
        "pre_sale_transport": "NONE",
        "cash_usd": 0,
    }
    return result


def pass_contract(result: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    expected_hold_counts = {
        "HOLD_DUPLICATE_SUBMISSION_ID": 8,
        "HOLD_MISSING_METHOD_SPEC_MATRIX": 7,
        "HOLD_ROUTE_MISMATCH": 5,
        "HOLD_INCUBATION_WINDOW": 5,
        "HOLD_QC_CONTROL_FAILURE": 5,
    }
    expected_route_counts = {"MICROBIAL_LIMITS": 30, "STERILITY": 30, "CCIT": 30}
    checks = {
        "input_rows": result.get("input_rows") == 120,
        "ready": result.get("ready") == 90,
        "holds": result.get("holds") == 30,
        "jobs": result.get("jobs") == 90,
        "reports_staged": result.get("reports_staged") == 90,
        "reports_released": result.get("reports_released") == 0,
        "hold_counts": result.get("hold_counts") == expected_hold_counts,
        "route_counts": result.get("route_counts") == expected_route_counts,
        "interfaces": result.get("interfaces") == "SIMULATED_READ_ONLY",
        "production_writes": result.get("production_writes") == 0,
        "automatic_releases": result.get("automatic_releases") == 0,
        "autonomous_release": result.get("autonomous_release") is False,
    }
    failures.extend(name for name, passed in checks.items() if not passed)
    if not all(
        item.get("code") == "AUTONOMOUS_RELEASE_DENIED"
        for item in result.get("autonomous_release_effects") or []
    ):
        failures.append("autonomous_release_not_denied")
    if any(
        item.get("jobs_created")
        or item.get("results_created")
        or item.get("reports_staged")
        or item.get("released")
        for item in result.get("hold_records") or []
    ):
        failures.append("held_record_created_output")
    for job in result.get("job_records") or []:
        route = ROUTES.get(job["route"])
        if route is None:
            failures.append("unknown_route")
            break
        if job["planned_duration_hours"] < route["duration_hours"]:
            failures.append("shortened_duration")
            break
        if job["timepoints_hours"] != route["timepoints_hours"]:
            failures.append("timepoint_drift")
            break
    for report in result.get("report_records") or []:
        if report.get("status") != "STAGED" or report.get("released"):
            failures.append("report_not_staged")
            break
        if not all(len(report.get(field) or "") == 64 for field in ("source_hash", "method_hash", "result_hash")):
            failures.append("report_hash")
            break
    return failures


def main() -> int:
    result = run_gate()
    journal = empty_journal()
    for row in build_acceptance_fixture():
        ingest_row(journal, row)
    replay = replay_into(journal)
    failures = pass_contract(result)
    if any(replay[key] != 0 for key in ("added_submissions", "added_jobs", "added_holds", "added_reports")):
        failures.append("replay_added_output")
    if replay["replay_noops"] != 120:
        failures.append("replay_noops")
    report = {
        "ok": not failures,
        "failures": failures,
        "command": "python3 pace_lebanon_microbial_volume_evidence.py",
        "demand_id": DEMAND_ID,
        "buyer": BUYER,
        "input_rows": result["input_rows"],
        "ready": result["ready"],
        "holds": result["holds"],
        "jobs": result["jobs"],
        "reports_staged": result["reports_staged"],
        "reports_released": result["reports_released"],
        "hold_counts": result["hold_counts"],
        "route_counts": result["route_counts"],
        "replay": replay,
        "manifest_sha256": result["manifest_sha256"],
        "audit_sha256": result["audit_sha256"],
        "truth_gate": TRUTH_GATE,
        "interfaces": result["interfaces"],
        "pre_sale_transport": "NONE",
        "cash_usd": 0,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
