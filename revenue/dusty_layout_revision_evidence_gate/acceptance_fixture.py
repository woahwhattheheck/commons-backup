#!/usr/bin/env python3
"""Generate the deterministic 120-job Dusty acceptance corpus."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

REASONS = (
    "DESIGN_HASH_MISMATCH",
    "DESIGN_REVISION_MISMATCH",
    "TRADE_SIGNOFF_STALE",
    "UNIT_SCALE_MISMATCH",
    "CONTROL_POINT_SURVEY_MISMATCH",
    "STATION_VERIFICATION_FAILED",
    "PORTAL_QR_MISMATCH",
    "RUNTIME_REPORT_MISMATCH",
)


def h(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def clean_job(index: int) -> dict:
    job_id = f"PRINT-{index:03d}"
    design_hash = h(f"design:{job_id}")
    design_revision = f"R{1 + (index % 9)}"
    control_hash = h(f"control:{job_id}")
    survey = f"SURVEY-{1 + (index % 11):02d}"
    qr_hash = h(f"portal:{job_id}")
    printer = f"FP2-{2 + (index % 3)}.{index % 10}"
    app = f"APP-{8 + (index % 4)}.{index % 7}"
    unit = "mm"
    scale = 1.0
    return {
        "job_id": job_id,
        "prejob": {
            "design": {"sha256": design_hash, "revision": design_revision},
            "trade_signoffs": [
                {"trade": "MEP", "approved": True, "design_sha256": design_hash, "design_revision": design_revision},
                {"trade": "STRUCTURAL", "approved": True, "design_sha256": design_hash, "design_revision": design_revision},
            ],
            "layout": {"unit": unit, "scale": scale},
            "control_points": {"survey_version": survey, "sha256": control_hash},
            "station_verification": {"passed": True, "survey_version": survey, "control_points_sha256": control_hash},
            "portal_preview": {"design_sha256": design_hash, "design_revision": design_revision, "qr_sha256": qr_hash},
            "expected_runtime": {"printer_version": printer, "app_version": app},
        },
        "postjob": {
            "final_report": {
                "design_sha256": design_hash,
                "design_revision": design_revision,
                "unit": unit,
                "scale": scale,
                "survey_version": survey,
                "control_points_sha256": control_hash,
                "station_verified": True,
                "portal_qr_sha256": qr_hash,
                "printer_version": printer,
                "app_version": app,
                "report_sha256": h(f"report:{job_id}"),
            }
        },
    }


def apply_fault(job: dict, reason: str) -> None:
    report = job["postjob"]["final_report"]
    pre = job["prejob"]
    if reason == "DESIGN_HASH_MISMATCH":
        report["design_sha256"] = h(f"wrong-design:{job['job_id']}")
    elif reason == "DESIGN_REVISION_MISMATCH":
        report["design_revision"] = "R-WRONG"
    elif reason == "TRADE_SIGNOFF_STALE":
        pre["trade_signoffs"][0]["approved"] = False
    elif reason == "UNIT_SCALE_MISMATCH":
        report["scale"] = 0.5
    elif reason == "CONTROL_POINT_SURVEY_MISMATCH":
        report["survey_version"] = "SURVEY-STALE"
    elif reason == "STATION_VERIFICATION_FAILED":
        pre["station_verification"]["passed"] = False
    elif reason == "PORTAL_QR_MISMATCH":
        report["portal_qr_sha256"] = h(f"wrong-qr:{job['job_id']}")
    elif reason == "RUNTIME_REPORT_MISMATCH":
        report["app_version"] = "APP-WRONG"
    else:
        raise ValueError(reason)


def build_fixture() -> dict:
    jobs = [clean_job(index) for index in range(1, 121)]
    bad = jobs[96:]
    for reason_index, reason in enumerate(REASONS):
        for offset in range(3):
            apply_fault(bad[reason_index * 3 + offset], reason)
    return {"schema_version": 1, "jobs": jobs}


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="acceptance_120.json")
    args = parser.parse_args()
    path = Path(args.output)
    path.write_text(json.dumps(build_fixture(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
