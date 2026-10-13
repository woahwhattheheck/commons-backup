#!/usr/bin/env python3
"""Build a read-only rerun queue from a retained Commons battery report.

Compare failing test source blobs with one pinned Git commit. Source equality
is NOT a current test result: dependencies, fixtures and environment may differ.
Recorded commands are data only and are never executed by this tool.

  python3 host/battery_failure_queue.py report.json --root . --ref HEAD
  python3 host/battery_failure_queue.py report.json --report-only
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Any

REPORT_SCHEMA = "commons-battery-report-v1"
QUEUE_SCHEMA = "commons-battery-failure-queue-v1"
SHA = re.compile(r"[0-9a-f]{40}")
MAX_REPORT_BYTES = 16 * 1024 * 1024
SOURCE_STATES = (
    "NOT_COMPARED", "UNRESOLVED_RECORDED_SOURCE", "ABSENT_AT_COMPARISON",
    "CHANGED_TEST_BLOB", "SAME_TEST_BLOB",
)


class QueueError(ValueError):
    """A report or Git snapshot cannot be used without guessing."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise QueueError(message)


def _sha(value: Any) -> bool:
    return isinstance(value, str) and SHA.fullmatch(value) is not None


def _path(value: Any) -> bool:
    return (
        isinstance(value, str) and bool(value) and value != "."
        and "\\" not in value and "\x00" not in value
        and not PurePosixPath(value).is_absolute()
        and ".." not in PurePosixPath(value).parts
        and str(PurePosixPath(value)) == value
    )


def validate_report(report: Any) -> dict[str, Any]:
    """Check shapes, row uniqueness and summary counts before queue creation."""
    _require(isinstance(report, dict), "report must be an object")
    _require(report.get("schema") == REPORT_SCHEMA, "unsupported report schema")
    _require(isinstance(report.get("repository"), str) and bool(report["repository"]),
             "repository must be a nonempty string")
    for field in ("run_id", "run_attempt"):
        value = report.get(field)
        _require(isinstance(value, str) and value.isascii() and value.isdecimal()
                 and int(value) > 0, f"{field} must be a positive decimal string")
    _require(_sha(report.get("checkout_sha")), "checkout_sha must be a full Git SHA")
    _require(type(report.get("complete")) is bool, "complete must be a boolean")
    for field in ("conclusion", "workflow_outcome"):
        _require(isinstance(report.get(field), str) and bool(report[field]),
                 f"{field} must be a nonempty string")
    problems = report.get("problems")
    _require(isinstance(problems, list) and all(isinstance(p, str) for p in problems),
             "problems must be a list of strings")
    rows = report.get("results")
    _require(isinstance(rows, list), "results must be a list")
    seen: set[str] = set()
    passed = unresolved = 0
    for i, row in enumerate(rows):
        at = f"results[{i}]"
        _require(isinstance(row, dict), f"{at} must be an object")
        path = row.get("path")
        _require(_path(path), f"{at}.path must be a canonical relative POSIX path")
        _require(path not in seen, f"duplicate result path: {path}")
        seen.add(path)
        _require(type(row.get("exit_code")) is int, f"{at}.exit_code must be an integer")
        command = row.get("command")
        _require(isinstance(command, list) and bool(command)
                 and all(isinstance(v, str) and bool(v) for v in command),
                 f"{at}.command must be a nonempty list of nonempty strings")
        recorded = row.get("source_in_checkout_commit")
        _require(type(recorded) is bool, f"{at}.source_in_checkout_commit must be a boolean")
        blob = row.get("source_blob_sha")
        _require(blob is None or blob == "" or _sha(blob), f"{at}.source_blob_sha is invalid")
        _require(not recorded or _sha(blob), f"{at} claims a resolved source without a blob SHA")
        passed += row["exit_code"] == 0
        unresolved += not recorded
    expected = {
        "completed_files": len(rows), "passed_files": passed,
        "failed_files": len(rows) - passed, "unresolved_source_files": unresolved,
    }
    counts = report.get("counts")
    _require(isinstance(counts, dict), "counts must be an object")
    for key, value in expected.items():
        _require(type(counts.get(key)) is int and counts[key] == value,
                 f"counts.{key} does not match result rows")
    return report


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise QueueError(f"non-finite JSON constant: {value}")


def load_report(path: Path) -> tuple[dict[str, Any], str]:
    """Read a bounded UTF-8 JSON file and retain its exact-byte digest."""
    with path.open("rb") as handle:
        raw = handle.read(MAX_REPORT_BYTES + 1)
    _require(len(raw) <= MAX_REPORT_BYTES, "report exceeds 16 MiB")
    try:
        report = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                            parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise QueueError(f"invalid UTF-8 JSON report: {exc}") from exc
    return validate_report(report), hashlib.sha256(raw).hexdigest()


def _git(root: Path, *args: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise QueueError(f"could not read Git snapshot: {exc}") from exc
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise QueueError(f"could not read Git snapshot: {detail}")
    return result.stdout


def git_snapshot(root: Path, ref: str) -> tuple[str, dict[str, str]]:
    """Resolve once, then read committed blobs, never dirty working-tree bytes."""
    _require(isinstance(ref, str) and bool(ref) and not ref.startswith("-"),
             "ref must be a non-option Git revision")
    commit = _git(root, "rev-parse", "--verify", "--end-of-options", ref + "^{commit}")
    try:
        sha = commit.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise QueueError("Git returned a non-ASCII commit SHA") from exc
    _require(_sha(sha), "Git snapshot must use a full SHA-1 commit")
    raw = _git(root, "ls-tree", "-r", "-z", "--full-tree", sha)
    blobs: dict[str, str] = {}
    for entry in raw.split(b"\x00"):
        if not entry:
            continue
        try:
            metadata, name = entry.split(b"\t", 1)
            _mode, kind, oid = metadata.decode("ascii").split(" ")
            path = name.decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise QueueError("Git tree contains an unsupported entry encoding") from exc
        if kind == "blob":
            _require(_sha(oid), "Git tree contains an invalid blob SHA")
            blobs[path] = oid
    return sha, blobs


def build_queue(report: dict[str, Any], report_sha256: str,
                comparison_sha: str | None = None,
                current_blobs: dict[str, str] | None = None) -> dict[str, Any]:
    validate_report(report)
    _require(isinstance(report_sha256, str)
             and re.fullmatch(r"[0-9a-f]{64}", report_sha256) is not None,
             "report_sha256 must be a full SHA-256 digest")
    _require((comparison_sha is None) == (current_blobs is None),
             "comparison commit and tree must be supplied together")
    if comparison_sha is not None:
        _require(_sha(comparison_sha), "comparison_sha must be a full Git SHA")
        _require(isinstance(current_blobs, dict)
                 and all(_path(k) and _sha(v) for k, v in current_blobs.items()),
                 "comparison tree must map canonical paths to blob SHAs")
    failures = []
    for row in sorted(report["results"], key=lambda item: item["path"]):
        if row["exit_code"] == 0:
            continue
        current = current_blobs.get(row["path"]) if current_blobs is not None else None
        if not row["source_in_checkout_commit"]:
            state = "UNRESOLVED_RECORDED_SOURCE"
        elif current_blobs is None:
            state = "NOT_COMPARED"
        elif current is None:
            state = "ABSENT_AT_COMPARISON"
        elif current == row["source_blob_sha"]:
            state = "SAME_TEST_BLOB"
        else:
            state = "CHANGED_TEST_BLOB"
        failures.append({
            "path": row["path"], "recorded_exit_code": row["exit_code"],
            "recorded_command": list(row["command"]),
            "recorded_test_blob": row["source_blob_sha"],
            "comparison_test_blob": current, "source_state": state,
            "rerun_required": True,
        })
    counts = Counter(row["source_state"] for row in failures)
    return {
        "schema": QUEUE_SCHEMA,
        "report": {
            "sha256": report_sha256, "repository": report["repository"],
            "run_id": report["run_id"], "run_attempt": report["run_attempt"],
            "checkout_sha": report["checkout_sha"], "complete": report["complete"],
            "conclusion": report["conclusion"], "workflow_outcome": report["workflow_outcome"],
            "problems": list(report["problems"]), "counts": dict(report["counts"]),
        },
        "comparison_sha": comparison_sha,
        "retained_failed_files": len(failures),
        "source_state_counts": {state: counts[state] for state in SOURCE_STATES},
        "tests_executed": False,
        "current_test_status": "NOT_MEASURED",
        "limits": [
            "Source provenance and prior outcomes are recorded report metadata, not newly verified executions.",
            "Equal test blobs do not establish equal dependencies, fixtures or environment.",
            "Changed or absent test sources do not establish a fix; every queued result needs a new check.",
            "Recorded commands are untrusted data, not executable recommendations.",
        ],
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--report-only", action="store_true", help="do not read a Git repository")
    args = parser.parse_args(argv)
    try:
        report, digest = load_report(args.report)
        sha, blobs = (None, None) if args.report_only else git_snapshot(args.root, args.ref)
        queue = build_queue(report, digest, sha, blobs)
    except (QueueError, OSError, ValueError, RecursionError) as exc:
        print(f"BATTERY QUEUE ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(queue, ensure_ascii=True, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
