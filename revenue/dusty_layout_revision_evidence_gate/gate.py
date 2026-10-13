#!/usr/bin/env python3
"""Deterministic, read-only layout revision-to-print evidence gate.

This module reconciles pre-job design, signoff, layout, survey, station,
portal-preview, runtime and final-report evidence. It never emits robot control
commands and never makes a field-release or layout-certification decision.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
from typing import Any

SCHEMA_VERSION = 1
GATE_ID = "dusty-layout-revision-to-print-evidence-v1"
MAX_JOBS = 10_000
MAX_SIGNOFFS = 128
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+:/-]{0,127}$")
ALLOWED_UNITS = {"mm", "cm", "m", "in", "ft"}
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


class GateInputError(ValueError):
    """Raised when the input contract is malformed or ambiguous."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise GateInputError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def load_json(path: str | os.PathLike[str]) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle, object_pairs_hook=_reject_duplicate_keys)
    except GateInputError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise GateInputError(f"cannot read valid JSON from {path}: {exc}") from exc


def _object(value: Any, where: str, required: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GateInputError(f"{where} must be an object")
    missing = required - set(value)
    extra = set(value) - required
    if missing:
        raise GateInputError(f"{where} missing keys: {sorted(missing)}")
    if extra:
        raise GateInputError(f"{where} unexpected keys: {sorted(extra)}")
    return value


def _string(value: Any, where: str, pattern: re.Pattern[str] = ID_RE) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise GateInputError(f"{where} has invalid value")
    return value


def _sha(value: Any, where: str) -> str:
    # Deliberately reject uppercase/noncanonical hashes. Never silently normalize.
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise GateInputError(f"{where} must be a canonical lowercase SHA-256 hex digest")
    return value


def _bool(value: Any, where: str) -> bool:
    if not isinstance(value, bool):
        raise GateInputError(f"{where} must be boolean")
    return value


def _scale(value: Any, where: str) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GateInputError(f"{where} must be numeric")
    if not math.isfinite(float(value)) or value <= 0 or value > 1_000_000:
        raise GateInputError(f"{where} must be > 0 and <= 1000000")
    return value


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _validate_job(raw: Any, index: int) -> dict[str, Any]:
    where = f"jobs[{index}]"
    job = _object(raw, where, {"job_id", "prejob", "postjob"})
    job_id = _string(job["job_id"], f"{where}.job_id")

    pre = _object(
        job["prejob"],
        f"{where}.prejob",
        {"design", "trade_signoffs", "layout", "control_points", "station_verification", "portal_preview", "expected_runtime"},
    )
    design = _object(pre["design"], f"{where}.prejob.design", {"sha256", "revision"})
    design_hash = _sha(design["sha256"], f"{where}.prejob.design.sha256")
    design_revision = _string(design["revision"], f"{where}.prejob.design.revision", VERSION_RE)

    signoffs_raw = pre["trade_signoffs"]
    if not isinstance(signoffs_raw, list) or not signoffs_raw or len(signoffs_raw) > MAX_SIGNOFFS:
        raise GateInputError(f"{where}.prejob.trade_signoffs must contain 1..{MAX_SIGNOFFS} entries")
    signoffs: list[dict[str, Any]] = []
    seen_trades: set[str] = set()
    for signoff_index, signoff_raw in enumerate(signoffs_raw):
        sw = f"{where}.prejob.trade_signoffs[{signoff_index}]"
        signoff = _object(signoff_raw, sw, {"trade", "approved", "design_sha256", "design_revision"})
        trade = _string(signoff["trade"], f"{sw}.trade")
        if trade in seen_trades:
            raise GateInputError(f"{where}.prejob.trade_signoffs duplicate trade: {trade}")
        seen_trades.add(trade)
        signoffs.append(
            {
                "trade": trade,
                "approved": _bool(signoff["approved"], f"{sw}.approved"),
                "design_sha256": _sha(signoff["design_sha256"], f"{sw}.design_sha256"),
                "design_revision": _string(signoff["design_revision"], f"{sw}.design_revision", VERSION_RE),
            }
        )

    layout = _object(pre["layout"], f"{where}.prejob.layout", {"unit", "scale"})
    unit = layout["unit"]
    if not isinstance(unit, str) or unit not in ALLOWED_UNITS:
        raise GateInputError(f"{where}.prejob.layout.unit must be one of {sorted(ALLOWED_UNITS)}")
    scale = _scale(layout["scale"], f"{where}.prejob.layout.scale")

    controls = _object(pre["control_points"], f"{where}.prejob.control_points", {"survey_version", "sha256"})
    survey_version = _string(controls["survey_version"], f"{where}.prejob.control_points.survey_version", VERSION_RE)
    control_hash = _sha(controls["sha256"], f"{where}.prejob.control_points.sha256")

    station = _object(
        pre["station_verification"],
        f"{where}.prejob.station_verification",
        {"passed", "survey_version", "control_points_sha256"},
    )
    station_passed = _bool(station["passed"], f"{where}.prejob.station_verification.passed")
    station_survey = _string(station["survey_version"], f"{where}.prejob.station_verification.survey_version", VERSION_RE)
    station_control_hash = _sha(station["control_points_sha256"], f"{where}.prejob.station_verification.control_points_sha256")

    portal = _object(
        pre["portal_preview"],
        f"{where}.prejob.portal_preview",
        {"design_sha256", "design_revision", "qr_sha256"},
    )
    portal_design_hash = _sha(portal["design_sha256"], f"{where}.prejob.portal_preview.design_sha256")
    portal_design_revision = _string(portal["design_revision"], f"{where}.prejob.portal_preview.design_revision", VERSION_RE)
    portal_qr = _sha(portal["qr_sha256"], f"{where}.prejob.portal_preview.qr_sha256")

    runtime = _object(pre["expected_runtime"], f"{where}.prejob.expected_runtime", {"printer_version", "app_version"})
    printer_version = _string(runtime["printer_version"], f"{where}.prejob.expected_runtime.printer_version", VERSION_RE)
    app_version = _string(runtime["app_version"], f"{where}.prejob.expected_runtime.app_version", VERSION_RE)

    post = _object(job["postjob"], f"{where}.postjob", {"final_report"})
    report = _object(
        post["final_report"],
        f"{where}.postjob.final_report",
        {
            "design_sha256", "design_revision", "unit", "scale", "survey_version", "control_points_sha256",
            "station_verified", "portal_qr_sha256", "printer_version", "app_version", "report_sha256",
        },
    )
    report_unit = report["unit"]
    if not isinstance(report_unit, str) or report_unit not in ALLOWED_UNITS:
        raise GateInputError(f"{where}.postjob.final_report.unit must be one of {sorted(ALLOWED_UNITS)}")

    return {
        "job_id": job_id,
        "design_hash": design_hash,
        "design_revision": design_revision,
        "signoffs": signoffs,
        "unit": unit,
        "scale": scale,
        "survey_version": survey_version,
        "control_hash": control_hash,
        "station_passed": station_passed,
        "station_survey": station_survey,
        "station_control_hash": station_control_hash,
        "portal_design_hash": portal_design_hash,
        "portal_design_revision": portal_design_revision,
        "portal_qr": portal_qr,
        "printer_version": printer_version,
        "app_version": app_version,
        "report": {
            "design_sha256": _sha(report["design_sha256"], f"{where}.postjob.final_report.design_sha256"),
            "design_revision": _string(report["design_revision"], f"{where}.postjob.final_report.design_revision", VERSION_RE),
            "unit": report_unit,
            "scale": _scale(report["scale"], f"{where}.postjob.final_report.scale"),
            "survey_version": _string(report["survey_version"], f"{where}.postjob.final_report.survey_version", VERSION_RE),
            "control_points_sha256": _sha(report["control_points_sha256"], f"{where}.postjob.final_report.control_points_sha256"),
            "station_verified": _bool(report["station_verified"], f"{where}.postjob.final_report.station_verified"),
            "portal_qr_sha256": _sha(report["portal_qr_sha256"], f"{where}.postjob.final_report.portal_qr_sha256"),
            "printer_version": _string(report["printer_version"], f"{where}.postjob.final_report.printer_version", VERSION_RE),
            "app_version": _string(report["app_version"], f"{where}.postjob.final_report.app_version", VERSION_RE),
            "report_sha256": _sha(report["report_sha256"], f"{where}.postjob.final_report.report_sha256"),
        },
    }


def _reasons(job: dict[str, Any]) -> list[str]:
    report = job["report"]
    reasons: list[str] = []
    if report["design_sha256"] != job["design_hash"] or job["portal_design_hash"] != job["design_hash"]:
        reasons.append("DESIGN_HASH_MISMATCH")
    if report["design_revision"] != job["design_revision"] or job["portal_design_revision"] != job["design_revision"]:
        reasons.append("DESIGN_REVISION_MISMATCH")
    if any(
        (not signoff["approved"])
        or signoff["design_sha256"] != job["design_hash"]
        or signoff["design_revision"] != job["design_revision"]
        for signoff in job["signoffs"]
    ):
        reasons.append("TRADE_SIGNOFF_STALE")
    if report["unit"] != job["unit"] or report["scale"] != job["scale"]:
        reasons.append("UNIT_SCALE_MISMATCH")
    if (
        job["station_survey"] != job["survey_version"]
        or job["station_control_hash"] != job["control_hash"]
        or report["survey_version"] != job["survey_version"]
        or report["control_points_sha256"] != job["control_hash"]
    ):
        reasons.append("CONTROL_POINT_SURVEY_MISMATCH")
    if not job["station_passed"] or not report["station_verified"]:
        reasons.append("STATION_VERIFICATION_FAILED")
    if report["portal_qr_sha256"] != job["portal_qr"]:
        reasons.append("PORTAL_QR_MISMATCH")
    if report["printer_version"] != job["printer_version"] or report["app_version"] != job["app_version"]:
        reasons.append("RUNTIME_REPORT_MISMATCH")
    return reasons


def evaluate(payload: Any) -> dict[str, Any]:
    root = _object(payload, "input", {"schema_version", "jobs"})
    if type(root["schema_version"]) is not int or root["schema_version"] != SCHEMA_VERSION:
        raise GateInputError(f"schema_version must be {SCHEMA_VERSION}")
    jobs_raw = root["jobs"]
    if not isinstance(jobs_raw, list) or not jobs_raw or len(jobs_raw) > MAX_JOBS:
        raise GateInputError(f"jobs must contain 1..{MAX_JOBS} entries")

    jobs = [_validate_job(raw, index) for index, raw in enumerate(jobs_raw)]
    ids = [job["job_id"] for job in jobs]
    if len(set(ids)) != len(ids):
        raise GateInputError("job_id values must be unique")

    clean_packets: list[dict[str, Any]] = []
    exceptions: list[dict[str, str]] = []
    reason_counts = {reason: 0 for reason in REASONS}

    for job in jobs:
        reasons = _reasons(job)
        if reasons:
            for reason in reasons:
                exceptions.append({"job_id": job["job_id"], "reason": reason})
                reason_counts[reason] += 1
            continue
        packet_base = {
            "job_id": job["job_id"],
            "design_sha256": job["design_hash"],
            "design_revision": job["design_revision"],
            "trade_signoffs": job["signoffs"],
            "unit": job["unit"],
            "scale": job["scale"],
            "survey_version": job["survey_version"],
            "control_points_sha256": job["control_hash"],
            "station_verified": True,
            "portal_qr_sha256": job["portal_qr"],
            "printer_version": job["printer_version"],
            "app_version": job["app_version"],
            "final_report_sha256": job["report"]["report_sha256"],
        }
        clean_packets.append({**packet_base, "packet_sha256": _digest(packet_base)})

    clean_packets.sort(key=lambda item: item["job_id"])
    exceptions.sort(key=lambda item: (item["job_id"], item["reason"]))
    base = {
        "schema_version": SCHEMA_VERSION,
        "gate_id": GATE_ID,
        "jobs_total": len(jobs),
        "clean_count": len(clean_packets),
        "exception_count": len(exceptions),
        "clean_packets": clean_packets,
        "exceptions": exceptions,
        "reason_counts": reason_counts,
        "control_commands": [],
        "input_sha256": _digest(payload),
    }
    return {**base, "receipt_sha256": _digest(base)}


def write_atomic(path: str | os.PathLike[str], value: Any, *, input_path: str | os.PathLike[str] | None = None) -> None:
    target = Path(path).resolve()
    if input_path is not None and target == Path(input_path).resolve():
        raise GateInputError("output path must not overwrite input")
    target.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    temp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        with open(temp, "x", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, target)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="JSON input batch")
    parser.add_argument("--output", help="optional atomic receipt path")
    args = parser.parse_args(argv)
    try:
        receipt = evaluate(load_json(args.input))
        if args.output:
            write_atomic(args.output, receipt, input_path=args.input)
        else:
            json.dump(receipt, sys.stdout, indent=2, sort_keys=True, ensure_ascii=False)
            sys.stdout.write("\n")
        return 0
    except GateInputError as exc:
        print(f"input error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
