"""Stable views of observed verifier runs; raw records are never rewritten.

Only paths supplied by the executor and the exact unittest timing-summary line
are normalized. Application timings, dates, quantities and failures are data.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Iterable

FORMAT = "operator-verification-semantic-v1"
UNITTEST_TIME = re.compile(r"^Ran (\d+) (tests?) in [0-9]+(?:\.[0-9]+)?s$", re.M)
SKIP = {"__pycache__", ".git", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def canonical_digest(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def tree_digest(directory: str) -> str:
    """Bind paths and bytes, excluding only the collector's existing cache skips.

    This is not a signature or proof of authorization. For execution, the caller
    hashes the completed private copy before running it, not a moving source tree.
    """
    root = Path(directory)
    records = []
    for parent, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP)
        for name in sorted(files):
            if name.endswith((".pyc", ".pyo")):
                continue
            path = Path(parent) / name
            records.append([path.relative_to(root).as_posix(),
                            hashlib.sha256(path.read_bytes()).hexdigest()])
    return canonical_digest(records)


def normalize_output(text: str, paths: Iterable[tuple[str, str]]) -> str:
    """Replace known path roots at path boundaries, longest first.

    Do not scrub arbitrary /tmp names or every number/date: those can be the
    defect. A sibling path (/tmp/kit-other) is not /tmp/kit. Root '/' is never a
    useful relocatable binding and is intentionally left literal.
    """
    bindings = {}
    for label, value in paths:
        if value:
            value = os.path.abspath(value).rstrip(os.sep)
            if value:
                bindings.setdefault(value, "{" + label + "}")
    for path, label in sorted(bindings.items(), key=lambda item: (-len(item[0]), item[0])):
        pattern = r"(?<![\w./\\-])" + re.escape(path) + r"(?=$|[/\\\s\"'():,;{}\[\]])"
        text = re.sub(pattern, lambda _match, replacement=label: replacement, text)
    return UNITTEST_TIME.sub(r"Ran \1 \2 (timing in raw run metadata)", text)


def capture_output(text: str, command: str,
                   paths: Iterable[tuple[str, str]]) -> dict[str, Any]:
    """Normalize BEFORE truncation; long root names cannot alter the tail slice."""
    paths = list(paths)
    stable = normalize_output(text, paths)
    return {
        "output_full": text,
        "output_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "semantic_command": normalize_output(command, paths),
        "semantic_output_tail": stable.strip()[-1200:],
        "semantic_output_sha256": hashlib.sha256(stable.encode("utf-8")).hexdigest(),
    }


def semantic_report(report: dict[str, Any]) -> dict[str, Any]:
    """Return an idempotent stable projection without changing the raw report.

    Collector-generated records must include their full-output normalization.
    Failing explicitly for an old record prevents falsely claiming that an
    already-truncated, path-dependent tail can be made reproducible afterwards.
    """
    result = copy.deepcopy(report)
    if result.get("artifact_format") == FORMAT:
        return result
    result["artifact_format"] = FORMAT
    result["survey_root"] = "{ROOT}"
    result.pop("generated_at_utc", None)
    result["normalization"] = (
        "Known executor paths and exact unittest summary timings only; "
        "raw command, output, timestamp and durations require --out-run-json."
    )
    for component in result["components"]:
        for run in component["runs"]:
            for field in ("semantic_command", "semantic_output_tail", "semantic_output_sha256"):
                if field not in run:
                    raise ValueError("legacy run lacks %s; rerun the collector" % field)
            command = run.pop("semantic_command")
            component["reason"] = component["reason"].replace(run["command"], command)
            run["command"] = command
            run["output_tail"] = run.pop("semantic_output_tail")
            run["output_sha256"] = run.pop("semantic_output_sha256")
            run.pop("argv", None)
            run.pop("cwd", None)
            run.pop("output_full", None)
            run.pop("duration_s", None)
    return result


def write_json(report: dict[str, Any], path: str, *, raw: bool = False) -> None:
    payload = report if raw else semantic_report(report)
    with open(path, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
