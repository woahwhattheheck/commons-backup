#!/usr/bin/env python3
"""Build a deterministic census of failed Commons battery files.

The census never guesses from test filenames.  A failed record is placed in the
remint queue only when diagnostics bound to the exact report bytes contain a
strong stale pin/hash/pointer signal.  Missing diagnostics stay
``incomplete_evidence`` instead of being promoted to a semantic or remint
failure.

Diagnostics are optional JSON using schema ``commons-battery-diagnostics-v1``::

  {"schema":"commons-battery-diagnostics-v1",
   "records":[{"report_sha256":"<64 hex>","path":"test_x.py",
               "text":"AssertionError: pinned manifest sha ..."}]}

``report_sha256`` is SHA-256 of the complete report file, binding diagnostics to
one immutable report generation.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Iterable

SCHEMA = "commons-battery-failure-census-v1"
DIAGNOSTICS_SCHEMA = "commons-battery-diagnostics-v1"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
HEXISH = r"[0-9a-f]{7,64}"

_REMINT_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE | re.DOTALL) for pattern in (
    r"\bstale\s+(?:manifest|pin(?:ned)?|pointer|hash|digest|sha|blob|commit)\b",
    r"\b(?:manifest|pointer|pin(?:ned)?)\b.{0,120}\b(?:sha|hash|digest|blob|commit)\b"
    r".{0,120}\b(?:mismatch|drift|differs?|expected|actual|got|found)\b",
    rf"\b(?:expected|pinned)\b.{{0,80}}\b{HEXISH}\b.{{0,120}}"
    rf"\b(?:actual|got|found)\b.{{0,80}}\b{HEXISH}\b",
    r"\b(?:remint|re-mint)\b.{0,80}\b(?:manifest|pin|pointer|hash|digest|sha)\b",
))
_HARNESS_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
    r"\bcould not start test\b",
    r"\bcommand not found\b",
    r"\bno space left on device\b",
    r"\b(?:runner|worker)\s+(?:was\s+)?(?:lost|terminated|cancelled|canceled)\b",
    r"\btest timed out\b",
    r"\b(?:timeout|timed out)\b.{0,80}\b(?:runner|harness|process|command|test)\b",
    r"\b(?:process|command|test)\b.{0,80}\b(?:timeout|timed out)\b",
))
_SEMANTIC_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
    r"\bAssertionError\b",
    r"\bassert(?:Equal|True|False|In|NotIn|Regex|Raises)?\b",
    r"\b(?:expected|want(?:ed)?)\b.{0,120}\b(?:actual|got|found)\b",
))


class CensusError(ValueError):
    """Input cannot be safely interpreted as battery evidence."""


def _clean_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise CensusError("failure record path must be a non-empty string")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or str(path) in ("", "."):
        raise CensusError("failure record path must be repository-relative")
    return str(path)


def _exit_code(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 255:
        raise CensusError("failure record exit_code must be an integer from 0 through 255")
    return value


def _report_rows(payload: object) -> list[tuple[str, int]]:
    if not isinstance(payload, dict):
        raise CensusError("battery report must be a JSON object")
    if "results" in payload:
        rows = payload["results"]
        schema = payload.get("schema")
        if schema is not None and schema != "commons-battery-report-v1":
            raise CensusError("unsupported battery report schema")
    elif payload.get("category") == "battery" and "records" in payload:
        rows = payload["records"]
    else:
        raise CensusError("unrecognized battery report shape")
    if not isinstance(rows, list):
        raise CensusError("battery report records must be a list")
    result: list[tuple[str, int]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise CensusError("battery report record must be an object")
        path = _clean_path(row.get("path"))
        code = _exit_code(row.get("exit_code"))
        if path in seen:
            raise CensusError("duplicate test path in battery report: " + path)
        seen.add(path)
        result.append((path, code))
    return result


def load_reports(paths: Iterable[Path]) -> list[dict]:
    reports = []
    seen_hashes: set[str] = set()
    for path in paths:
        try:
            raw = path.read_bytes()
            payload = json.loads(raw)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CensusError(f"could not read battery report {path}: {exc}") from exc
        digest = hashlib.sha256(raw).hexdigest()
        if digest in seen_hashes:
            raise CensusError("duplicate report bytes: " + digest)
        seen_hashes.add(digest)
        rows = _report_rows(payload)
        reports.append({
            "report_sha256": digest,
            "source_name": path.name,
            "rows": rows,
        })
    if not reports:
        raise CensusError("at least one battery report is required")
    return reports


def load_diagnostics(path: Path | None) -> dict[tuple[str, str], str]:
    if path is None:
        return {}
    try:
        payload = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CensusError(f"could not read diagnostics {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema") != DIAGNOSTICS_SCHEMA:
        raise CensusError("unsupported diagnostics schema")
    rows = payload.get("records")
    if not isinstance(rows, list):
        raise CensusError("diagnostics records must be a list")
    result: dict[tuple[str, str], str] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise CensusError("diagnostic record must be an object")
        report_sha = row.get("report_sha256")
        if not isinstance(report_sha, str) or not HEX64.fullmatch(report_sha):
            raise CensusError("diagnostic report_sha256 must be 64 lowercase hex characters")
        path_value = _clean_path(row.get("path"))
        text = row.get("text")
        if not isinstance(text, str) or not text.strip():
            raise CensusError("diagnostic text must be a non-empty string")
        key = (report_sha, path_value)
        if key in result:
            raise CensusError("duplicate diagnostic binding")
        result[key] = text
    return result


def classify(text: str | None) -> str:
    if text is None:
        return "incomplete_evidence"
    if any(pattern.search(text) for pattern in _REMINT_PATTERNS):
        return "remint"
    if any(pattern.search(text) for pattern in _HARNESS_PATTERNS):
        return "harness_failure"
    if any(pattern.search(text) for pattern in _SEMANTIC_PATTERNS):
        return "semantic_assertion"
    return "incomplete_evidence"


def build_census(reports: list[dict], diagnostics: dict[tuple[str, str], str]) -> dict:
    known_report_hashes = {report["report_sha256"] for report in reports}
    failed_report_paths = {
        (report["report_sha256"], path)
        for report in reports
        for path, code in report["rows"]
        if code != 0
    }
    for key in diagnostics:
        if key[0] not in known_report_hashes:
            raise CensusError("diagnostic references a report not in this census")
        if key not in failed_report_paths:
            raise CensusError("diagnostic references a test path absent from failed records in its report")

    failures = []
    counts: Counter[str] = Counter()
    queue: dict[str, list[str]] = defaultdict(list)
    failed_report_count = 0
    passed_file_records = 0
    for report in sorted(reports, key=lambda item: item["report_sha256"]):
        report_failed = False
        for path, code in sorted(report["rows"]):
            if code == 0:
                passed_file_records += 1
                continue
            report_failed = True
            key = (report["report_sha256"], path)
            diagnostic = diagnostics.get(key)
            category = classify(diagnostic)
            counts[category] += 1
            failures.append({
                "report_sha256": report["report_sha256"],
                "path": path,
                "exit_code": code,
                "category": category,
                "diagnostic_bound": diagnostic is not None,
                "diagnostic_sha256": (
                    hashlib.sha256(diagnostic.encode("utf-8")).hexdigest()
                    if diagnostic is not None else None
                ),
            })
            if category == "remint":
                queue[path].append(report["report_sha256"])
        failed_report_count += int(report_failed)

    remint_queue = [
        {
            "path": path,
            "occurrences": len(report_hashes),
            "report_sha256": sorted(report_hashes),
        }
        for path, report_hashes in sorted(queue.items())
    ]
    return {
        "schema": SCHEMA,
        "reports": [
            {
                "report_sha256": report["report_sha256"],
                "source_name": report["source_name"],
                "record_count": len(report["rows"]),
            }
            for report in sorted(reports, key=lambda item: item["report_sha256"])
        ],
        "summary": {
            "reports": len(reports),
            "reports_with_failures": failed_report_count,
            "passed_file_records": passed_file_records,
            "failed_file_records": len(failures),
            "remint": counts["remint"],
            "semantic_assertion": counts["semantic_assertion"],
            "harness_failure": counts["harness_failure"],
            "incomplete_evidence": counts["incomplete_evidence"],
        },
        "failures": failures,
        "remint_queue": remint_queue,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", nargs="+", type=Path, help="battery report JSON; repeatable")
    parser.add_argument("--diagnostics", type=Path, help="optional exact-report-bound diagnostics JSON")
    parser.add_argument("--output", type=Path, required=True, help="write deterministic census JSON")
    args = parser.parse_args(argv)
    try:
        reports = load_reports(args.report)
        diagnostics = load_diagnostics(args.diagnostics)
        census = build_census(reports, diagnostics)
        args.output.write_text(
            json.dumps(census, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
    except (CensusError, OSError) as exc:
        print("battery failure census: " + str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
