#!/usr/bin/env python3
"""Inspect a retained battery JSON/ZIP without rerunning tests or trusting totals.

Exit 0 means a complete recorded pass, 1 means recorded file failures, and 2
means HOLD or invalid evidence. None of these certify the current checkout.
No archive extraction, network requests, subprocesses, or repository writes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any
import zipfile

SCHEMA = "commons-battery-report-v1"
MAX_BYTES = 16 * 1024 * 1024
MEMBER = "commons-battery-report.json"
HEX40 = re.compile(r"[0-9a-f]{40}\Z")


class InvalidReport(ValueError):
    """The retained input cannot support a reliable triage summary."""


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InvalidReport(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise InvalidReport(f"non-finite JSON constant: {value}")


def load_report(path: Path) -> dict[str, Any]:
    """Read one bounded JSON document; never extract ZIP members to disk."""
    try:
        if path.stat().st_size > MAX_BYTES + 65536:
            raise InvalidReport("input file exceeds byte limit")
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                members = [item for item in archive.infolist() if item.filename == MEMBER]
                if len(members) != 1:
                    raise InvalidReport(f"ZIP must contain exactly one root {MEMBER}")
                if members[0].file_size > MAX_BYTES:
                    raise InvalidReport("report exceeds byte limit")
                with archive.open(members[0]) as handle:
                    raw = handle.read(MAX_BYTES + 1)
        else:
            with path.open("rb") as handle:
                raw = handle.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise InvalidReport("report exceeds byte limit")
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
    except InvalidReport:
        raise
    except (OSError, UnicodeError, ValueError, zipfile.BadZipFile,
            RuntimeError, NotImplementedError, RecursionError) as exc:
        raise InvalidReport(f"cannot read report: {type(exc).__name__}") from exc
    if not isinstance(data, dict):
        raise InvalidReport("report must be a JSON object")
    return data


def _path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\0" in value:
        raise InvalidReport("invalid repository-relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or str(path) == ".":
        raise InvalidReport("invalid repository-relative path")
    return str(path)


def triage_report(report: dict[str, Any], expected_checkout: str | None = None) -> dict[str, Any]:
    if not isinstance(report, dict) or report.get("schema") != SCHEMA:
        raise InvalidReport("unsupported battery report schema")
    checkout = report.get("checkout_sha")
    if not isinstance(checkout, str) or not HEX40.fullmatch(checkout):
        raise InvalidReport("missing or malformed recorded checkout SHA")
    if expected_checkout is not None:
        if not isinstance(expected_checkout, str) or not HEX40.fullmatch(expected_checkout):
            raise InvalidReport("expected checkout must be a full lowercase commit SHA")
        if checkout != expected_checkout:
            raise InvalidReport("recorded checkout does not match expected checkout")
    rows = report.get("results")
    if not isinstance(rows, list):
        raise InvalidReport("results must be a list")
    failures = []
    unresolved = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise InvalidReport(f"result {index} must be an object")
        path = _path(row.get("path"))
        if path in seen:
            raise InvalidReport(f"duplicate result path: {path}")
        seen.add(path)
        code = row.get("exit_code")
        if type(code) is not int or not 0 <= code <= 255:
            raise InvalidReport(f"invalid exit code at result {index}")
        command = row.get("command")
        if (not isinstance(command, list) or len(command) != 2
                or command[0] not in ("python3", "node") or _path(command[1]) != path):
            raise InvalidReport(f"command/path mismatch at result {index}")
        blob = row.get("source_blob_sha")
        linked = row.get("source_in_checkout_commit")
        if type(linked) is not bool:
            raise InvalidReport(f"source linkage is not boolean at result {index}")
        if linked:
            if not isinstance(blob, str) or not HEX40.fullmatch(blob):
                raise InvalidReport(f"malformed source blob at result {index}")
        elif blob is not None:
            raise InvalidReport(f"unresolved source has a blob at result {index}")
        else:
            unresolved.append(path)
        if code:
            failures.append({"path": path, "exit_code": code, "source_blob_sha": blob})
    counts = {
        "completed_files": len(rows),
        "passed_files": len(rows) - len(failures),
        "failed_files": len(failures),
        "unresolved_source_files": len(unresolved),
    }
    declared = report.get("counts")
    if not isinstance(declared, dict) or any(
        type(declared.get(key)) is not int or declared[key] != value
        for key, value in counts.items()
    ):
        raise InvalidReport("declared counts disagree with recorded rows")
    complete = report.get("complete")
    problems = report.get("problems")
    outcome = report.get("workflow_outcome")
    if type(complete) is not bool:
        raise InvalidReport("complete must be boolean")
    if not isinstance(problems, list) or not all(isinstance(item, str) for item in problems):
        raise InvalidReport("problems must be a list of strings")
    if outcome not in ("success", "failure", "cancelled", "skipped", "unknown"):
        raise InvalidReport("unknown workflow outcome")
    if complete and (outcome in ("cancelled", "skipped") or (outcome == "success" and failures)):
        raise InvalidReport("completion/outcome contradicts recorded exits")
    expected_conclusion = (
        "INCOMPLETE" if not complete else "FAILED" if failures else
        "HARNESS_FAILED" if outcome == "failure" else "NO_TESTS" if not rows else "PASSED"
    )
    if report.get("conclusion") != expected_conclusion:
        raise InvalidReport("conclusion disagrees with recorded rows/outcome")
    holds = list(problems)
    if not complete:
        holds.append("recorded battery is incomplete")
    if outcome == "unknown":
        holds.append("recorded workflow outcome is unknown")
    if unresolved:
        holds.append("some executed sources are unresolved in the recorded checkout")
    if expected_conclusion in ("NO_TESTS", "HARNESS_FAILED"):
        holds.append(expected_conclusion)
    status = "HOLD" if holds else "RECORDED_FAILURES" if failures else "RECORDED_PASS"
    provenance = {key: report.get(key) for key in (
        "repository", "run_id", "run_attempt", "workflow_ref", "workflow_sha",
        "event_name", "event_sha", "checkout_sha",
    )}
    return {
        "schema": "commons-retained-battery-triage-v1", "status": status,
        "provenance": provenance, "counts": counts,
        "recorded_conclusion": expected_conclusion, "holds": holds,
        "candidate_failures": failures, "unresolved_paths": unresolved,
        "tests_rerun": False, "current_checkout_verified": False,
        "scope": "Recorded starting checkout only; not a current-main or clean-working-tree certificate.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="retained JSON or workflow artifact ZIP")
    parser.add_argument("--expect-checkout", help="reject a report for a different full commit SHA")
    args = parser.parse_args(argv)
    try:
        result = triage_report(load_report(args.report), args.expect_checkout)
    except InvalidReport as exc:
        result = {"schema": "commons-retained-battery-triage-v1", "status": "INVALID",
                  "error": str(exc), "tests_rerun": False, "current_checkout_verified": False}
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return {"RECORDED_PASS": 0, "RECORDED_FAILURES": 1}.get(result["status"], 2)


if __name__ == "__main__":
    raise SystemExit(main())
