#!/usr/bin/env python3
"""Turn the battery's NUL-delimited exit records into checkout-linked JSON.

This reads local git objects only. It never parses test stdout, contacts GitHub,
reruns tests, or changes their outcome. Counts describe executed files, not test
cases. A source blob identifies the file in the recorded starting checkout; it
is not an assertion that a test left the working tree unchanged.
"""
from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from collections.abc import Mapping

SCHEMA = "commons-battery-report-v1"
HEX40 = re.compile(r"[0-9a-f]{40}\Z")


def _parse_result_stream(raw: bytes | None) -> tuple[str, list[dict], bool, list[str], dict | None]:
    """Read command/path/exit triples, retaining completed records after a stop."""
    problems: list[str] = []
    records: list[dict] = []
    seen_paths: set[str] = set()
    sha = ""
    marker: int | None = None
    scope: dict | None = None
    if raw is None:
        return sha, records, False, ["result stream is missing"], scope
    fields = raw.split(b"\0")
    if fields[-1] == b"":
        fields.pop()
    else:
        problems.append("unterminated result stream")
        # A trailing field can be a truncated exit (e.g. 123 cut to 12).
        # Only NUL-terminated fields may contribute a completed record.
        fields.pop()
    if len(fields) % 3:
        problems.append("partial result record")
    for index in range(0, len(fields) - len(fields) % 3, 3):
        command, path, code = (field.decode("utf-8", "surrogateescape") for field in fields[index:index + 3])
        if marker is not None:
            problems.append("records follow completion marker")
        if command == "checkout_sha":
            if index != 0 or sha or not HEX40.fullmatch(path) or code:
                problems.append("invalid checkout record")
            else:
                sha = path
            continue
        if command == "battery_scope":
            if index != 3 or scope is not None or code:
                problems.append("invalid battery scope record")
                continue
            try:
                candidate = json.loads(path)
            except (json.JSONDecodeError, TypeError, ValueError):
                problems.append("invalid battery scope JSON")
                continue
            expected_scope = {
                "kind", "requested", "shard_index", "shard_count",
                "discovered_files", "planned_files", "fail_fast",
            }
            valid_integers = all(
                type(candidate.get(key)) is int and candidate[key] >= 0
                for key in ("shard_index", "discovered_files", "planned_files")
            ) if type(candidate) is dict else False
            valid_count = (
                type(candidate.get("shard_count")) is int and candidate["shard_count"] >= 1
            ) if type(candidate) is dict else False
            requested = candidate.get("requested") if type(candidate) is dict else None
            expected_kind = None
            if type(candidate) is dict and valid_count and valid_integers and type(requested) is list:
                expected_kind = (
                    "selected-shard" if requested and candidate["shard_count"] > 1
                    else "selected" if requested
                    else "shard" if candidate["shard_count"] > 1
                    else "full"
                )
            if (
                type(candidate) is not dict
                or set(candidate) != expected_scope
                or type(candidate.get("fail_fast")) is not bool
                or type(requested) is not list
                or not all(type(value) is str for value in requested)
                or not valid_integers
                or not valid_count
                or candidate["shard_index"] >= candidate["shard_count"]
                or candidate["planned_files"] > candidate["discovered_files"]
                or candidate.get("kind") != expected_kind
            ):
                problems.append("invalid battery scope")
                continue
            scope = candidate
            continue
        if command == "battery_complete":
            if path or code not in ("0", "1"):
                problems.append("invalid completion record")
            else:
                marker = int(code)
            continue
        if command == "timing_ms":
            normalized = PurePosixPath(path)
            if (not records or not path or normalized.is_absolute()
                    or ".." in normalized.parts or str(normalized) == "."
                    or not re.fullmatch(r"[0-9]{1,12}", code)):
                problems.append("invalid timing record")
            elif records[-1]["path"] != str(normalized) or records[-1].get("duration_ms") is not None:
                problems.append("timing record does not follow its test record")
            else:
                records[-1]["duration_ms"] = int(code)
            continue
        if command not in ("python3", "node"):
            problems.append("unknown result command")
            continue
        if not re.fullmatch(r"[0-9]{1,3}", code) or int(code) > 255:
            problems.append("invalid exit code")
            continue
        normalized = PurePosixPath(path)
        if not path or normalized.is_absolute() or ".." in normalized.parts or str(normalized) == ".":
            problems.append("invalid repository-relative test path")
            continue
        # Keep every exit as evidence, but do not certify repeated file records.
        if str(normalized) in seen_paths:
            problems.append("duplicate repository-relative test path")
        seen_paths.add(str(normalized))
        records.append({"path": str(normalized), "command": [command, path], "exit_code": int(code)})
    if not sha:
        problems.append("checkout record is missing")
    if marker is None:
        problems.append("completion marker is missing")
    elif marker != int(any(row["exit_code"] != 0 for row in records)):
        problems.append("completion marker disagrees with recorded exits")
    return sha, records, not problems, problems, scope


def parse_results(raw: bytes | None) -> tuple[str, list[dict], bool, list[str]]:
    """Read command/path/exit triples, retaining completed records after a stop.

    Historical streams may omit battery_scope. The four-tuple remains stable for
    truncation, duplicate-record, and fleet observers; build_report reads scope.
    """
    sha, records, complete, problems, _scope = _parse_result_stream(raw)
    return sha, records, complete, problems


def source_blobs(root: Path, sha: str) -> dict[str, str]:
    """Resolve paths on the recorded commit, even when a test moved HEAD."""
    commit = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--verify", sha + "^{commit}"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    if commit != sha:
        raise ValueError("recorded object is not a commit")
    tree = subprocess.run(
        ["git", "-C", str(root), "ls-tree", "-r", "-z", "--full-tree", sha],
        check=True, capture_output=True,
    ).stdout
    blobs = {}
    for entry in tree.split(b"\0"):
        if not entry:
            continue
        metadata, path = entry.split(b"\t", 1)
        _mode, kind, blob = metadata.split()
        if kind == b"blob":
            blobs[path.decode("utf-8", "surrogateescape")] = blob.decode("ascii")
    return blobs


def build_report(root: Path, raw: bytes | None, outcome: str, environ: Mapping[str, str]) -> dict:
    sha, records, complete, problems, scope = _parse_result_stream(raw)
    blobs: dict[str, str] = {}
    if sha:
        try:
            blobs = source_blobs(root, sha)
        except (OSError, subprocess.CalledProcessError, ValueError):
            problems.append("recorded checkout commit is unavailable")
            complete = False
    for row in records:
        row["source_blob_sha"] = blobs.get(row["path"])
        row["source_in_checkout_commit"] = row["source_blob_sha"] is not None
    failed = sum(row["exit_code"] != 0 for row in records)
    timed = [row for row in records if row.get("duration_ms") is not None]
    slowest = sorted(timed, key=lambda row: (-row["duration_ms"], os.fsencode(row["path"])))[:10]
    if outcome in ("cancelled", "skipped"):
        problems.append("battery step was " + outcome)
        complete = False
    elif outcome == "success" and failed:
        problems.append("step outcome disagrees with recorded exits")
        complete = False
    if not complete:
        conclusion = "INCOMPLETE"
    elif failed:
        conclusion = "FAILED"
    elif outcome == "failure":
        conclusion = "HARNESS_FAILED"
    elif not records:
        conclusion = "NO_TESTS"
    else:
        conclusion = "PASSED"
    return {
        "schema": SCHEMA,
        "repository": environ.get("GITHUB_REPOSITORY", ""),
        "run_id": environ.get("GITHUB_RUN_ID", ""),
        "run_attempt": environ.get("GITHUB_RUN_ATTEMPT", ""),
        "job_name": environ.get("GITHUB_JOB", ""),
        "workflow_name": environ.get("GITHUB_WORKFLOW", ""),
        "workflow_ref": environ.get("GITHUB_WORKFLOW_REF", ""),
        "workflow_sha": environ.get("GITHUB_WORKFLOW_SHA", ""),
        "event_name": environ.get("GITHUB_EVENT_NAME", ""),
        "event_sha": environ.get("GITHUB_SHA", ""),
        "checkout_sha": sha,
        "workflow_outcome": outcome,
        "complete": complete,
        "conclusion": conclusion,
        "scope": scope,
        "counts": {
            "completed_files": len(records),
            "passed_files": len(records) - failed,
            "failed_files": failed,
            "unresolved_source_files": sum(not row["source_in_checkout_commit"] for row in records),
        },
        "timing": {
            "clock": "monotonic",
            "unit": "ms",
            "measured_files": len(timed),
            "slowest_limit": 10,
            "slowest": [
                {"path": row["path"], "duration_ms": row["duration_ms"], "exit_code": row["exit_code"]}
                for row in slowest
            ],
        },
        "results": records,
        "problems": problems,
    }


def summary(report: dict) -> str:
    counts = report["counts"]
    lines = [
        "## Battery source-linked results",
        "",
        "**%s** — %d completed files, %d failed files. These are file counts, not test-case counts."
        % (report["conclusion"], counts["completed_files"], counts["failed_files"]),
        "",
        "Recorded starting checkout: `%s`." % (report["checkout_sha"] or "UNAVAILABLE"),
        "Source blobs refer to that commit, not to a later moving main or uncommitted working-tree bytes.",
        "",
    ]
    scope = report.get("scope")
    if scope and scope.get("fail_fast"):
        completed = counts["completed_files"]
        planned = scope["planned_files"]
        if completed < planned and counts["failed_files"]:
            lines += [
                "Fail-fast mode was enabled; execution intentionally stopped after the first failed file "
                f"({completed} of {planned} planned files completed).",
                "",
            ]
        else:
            lines += [f"Fail-fast mode was enabled; {completed} of {planned} planned files completed.", ""]
    failures = [row for row in report["results"] if row["exit_code"] != 0]
    if failures:
        lines += ["| Test file | Exit | Source blob |", "| --- | --- | --- |"]
        for row in failures:
            path = html.escape(json.dumps(row["path"], ensure_ascii=True)).replace("|", "&#124;")
            lines.append("| <code>%s</code> | %d | `%s` |" % (
                path, row["exit_code"], row["source_blob_sha"] or "NOT_IN_CHECKOUT_COMMIT"))
    if counts["unresolved_source_files"]:
        lines += ["", "%d executed file(s) were not resolved to this checkout commit; see the JSON artifact."
                  % counts["unresolved_source_files"]]
    slowest = report.get("timing", {}).get("slowest", [])
    if slowest:
        lines += ["", "### Slowest completed test files", "",
                  "| Test file | Wall time (ms) | Exit |", "| --- | ---: | ---: |"]
        for row in slowest:
            path = html.escape(json.dumps(row["path"], ensure_ascii=True)).replace("|", "&#124;")
            lines.append("| %s | %d | %d |" % (path, row["duration_ms"], row["exit_code"]))
        lines += ["", "Timing is diagnostic wall duration from a monotonic clock; it never determines pass/fail.", ""]
    if report["problems"]:
        lines += ["", "Report diagnostics: " + "; ".join(report["problems"]) + "."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--outcome", choices=("success", "failure", "cancelled", "skipped", "unknown"), default="unknown")
    args = parser.parse_args(argv)
    try:
        try:
            raw = args.results.read_bytes()
        except FileNotFoundError:
            raw = None
        report = build_report(args.root, raw, args.outcome, os.environ)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        if args.summary:
            with args.summary.open("a", encoding="utf-8") as handle:
                handle.write(summary(report))
    except OSError:
        print("battery report could not read or write its local result files", file=sys.stderr)
        return 1
    # The battery's original exit code controls CI. Reporting a red is not a
    # second test execution, nor may it turn the failed battery step green.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
