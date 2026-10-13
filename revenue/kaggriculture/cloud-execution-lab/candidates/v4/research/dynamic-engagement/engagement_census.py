#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Strict reducer for current-V4 dynamic engagement evidence.

The reducer intentionally separates a broken positive control from natural zero
opportunity. A component is not called "engaged" merely because its entrypoint
ran: an observed output change is required.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

EVIDENCE_SCHEMA = "titan-v4-dynamic-engagement-evidence/v1"
REPORT_SCHEMA = "titan-v4-dynamic-engagement-census/v1"
PANEL_KINDS = {"positive_control", "natural"}
COUNTER_KEYS = (
    "callbacks",
    "entry_calls",
    "eligible_calls",
    "engaged_calls",
    "output_changed_calls",
)


class DataError(ValueError):
    pass


def _object_pairs_no_dupes(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise DataError(f"duplicate JSON key: {key!r}")
        out[key] = value
    return out


def _reject_constant(value: str) -> None:
    raise DataError(f"non-finite JSON constant: {value}")


def load_document(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_object_pairs_no_dupes,
            parse_constant=_reject_constant,
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise DataError(str(exc)) from exc
    if not isinstance(value, dict):
        raise DataError("top-level evidence must be an object")
    return value


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise DataError(f"{label}: wrong fields; missing={missing}, extra={extra}")


def _nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise DataError(f"{label} must be a nonempty exact string")
    return value


def _strict_count(value: Any, label: str) -> int:
    if isinstance(value, bool) or type(value) is not int or value < 0:
        raise DataError(f"{label} must be a nonnegative literal integer")
    return value


def _hex(value: Any, length: int, label: str) -> str:
    if not isinstance(value, str) or len(value) != length:
        raise DataError(f"{label} must be lowercase {length}-hex")
    if value.lower() != value or any(c not in "0123456789abcdef" for c in value):
        raise DataError(f"{label} must be lowercase {length}-hex")
    return value


def _safe_relative_path(value: Any, label: str) -> str:
    text = _nonempty_string(value, label)
    if "\\" in text:
        raise DataError(f"{label} must use POSIX separators")
    pure = PurePosixPath(text)
    if pure.is_absolute() or any(part in ("", ".", "..") for part in pure.parts):
        raise DataError(f"{label} must be a canonical relative path")
    if str(pure) != text:
        raise DataError(f"{label} must be canonical")
    return text


def git_blob_sha1(data: bytes) -> str:
    prefix = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(prefix + data).hexdigest()


def _bind_file(root: Path, path_text: str, expected_blob: str) -> None:
    root_real = root.resolve(strict=True)
    candidate = root_real.joinpath(*PurePosixPath(path_text).parts)
    if candidate.is_symlink():
        raise DataError(f"binding {path_text!r}: symlink is not allowed")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise DataError(f"binding {path_text!r}: missing file") from exc
    try:
        resolved.relative_to(root_real)
    except ValueError as exc:
        raise DataError(f"binding {path_text!r}: escapes root") from exc
    if not resolved.is_file():
        raise DataError(f"binding {path_text!r}: must be a regular file")
    actual = git_blob_sha1(resolved.read_bytes())
    if actual != expected_blob:
        raise DataError(
            f"binding {path_text!r}: Git blob mismatch; expected {expected_blob}, got {actual}"
        )


def _normalize_binding(value: Any, index: int, root: Path) -> tuple[str, str]:
    if not isinstance(value, dict):
        raise DataError(f"record {index} binding must be object")
    _exact_keys(value, {"path", "git_blob"}, f"record {index} binding")
    path = _safe_relative_path(value["path"], f"record {index} binding.path")
    blob = _hex(value["git_blob"], 40, f"record {index} binding.git_blob")
    _bind_file(root, path, blob)
    return path, blob


def _normalize_record(value: Any, index: int, root: Path) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DataError(f"record {index} must be object")
    _exact_keys(
        value,
        {"component", "bindings", "panel", "counters", "completed", "error_count"},
        f"record {index}",
    )
    component = _nonempty_string(value["component"], f"record {index} component")

    bindings_raw = value["bindings"]
    if not isinstance(bindings_raw, list) or not bindings_raw:
        raise DataError(f"record {index} bindings must be a nonempty list")
    bindings = [_normalize_binding(item, index, root) for item in bindings_raw]
    if len({path for path, _blob in bindings}) != len(bindings):
        raise DataError(f"record {index}: duplicate binding path")
    bindings.sort()

    panel = value["panel"]
    if not isinstance(panel, dict):
        raise DataError(f"record {index} panel must be object")
    _exact_keys(panel, {"id", "kind", "sha256"}, f"record {index} panel")
    panel_id = _nonempty_string(panel["id"], f"record {index} panel.id")
    kind = panel["kind"]
    if kind not in PANEL_KINDS:
        raise DataError(f"record {index} panel.kind must be one of {sorted(PANEL_KINDS)}")
    panel_sha = _hex(panel["sha256"], 64, f"record {index} panel.sha256")

    counters = value["counters"]
    if not isinstance(counters, dict):
        raise DataError(f"record {index} counters must be object")
    _exact_keys(counters, set(COUNTER_KEYS), f"record {index} counters")
    normalized_counts = {
        key: _strict_count(counters[key], f"record {index} {key}")
        for key in COUNTER_KEYS
    }
    ordered = [normalized_counts[key] for key in COUNTER_KEYS]
    if not all(left >= right for left, right in zip(ordered, ordered[1:])):
        raise DataError(
            f"record {index}: counters must satisfy callbacks >= entry >= eligible >= engaged >= output_changed"
        )

    completed = value["completed"]
    if type(completed) is not bool:
        raise DataError(f"record {index} completed must be literal bool")
    error_count = _strict_count(value["error_count"], f"record {index} error_count")
    if completed and error_count:
        raise DataError(f"record {index}: completed evidence cannot have errors")

    return {
        "component": component,
        "bindings": bindings,
        "panel_id": panel_id,
        "panel_kind": kind,
        "panel_sha256": panel_sha,
        "counters": normalized_counts,
        "completed": completed,
        "error_count": error_count,
    }


def _control_failure(records: list[dict[str, Any]]) -> str | None:
    if not records:
        return "INSUFFICIENT_POSITIVE_CONTROL"
    if any((not row["completed"]) or row["error_count"] for row in records):
        return "CONTROL_EXECUTION_FAILED"
    # Every declared positive control is a proof obligation. Aggregating first
    # would let one live witness hide another dead/unwired witness.
    for field, state in (
        ("entry_calls", "CONTROL_UNWIRED"),
        ("eligible_calls", "CONTROL_NOT_ELIGIBLE"),
        ("engaged_calls", "CONTROL_NOT_ENGAGED"),
        ("output_changed_calls", "CONTROL_NO_OUTPUT_CHANGE"),
    ):
        if any(row["counters"][field] == 0 for row in records):
            return state
    return None


def _natural_state(records: list[dict[str, Any]]) -> str:
    if not records:
        return "NO_NATURAL_PANEL"
    if any((not row["completed"]) or row["error_count"] for row in records):
        return "NATURAL_EXECUTION_FAILED"
    sums = {key: sum(row["counters"][key] for row in records) for key in COUNTER_KEYS}
    if sums["output_changed_calls"]:
        return "NATURAL_OUTPUT_CHANGED"
    if sums["engaged_calls"]:
        return "NATURAL_ENGAGED_NO_OUTPUT_CHANGE"
    if sums["eligible_calls"]:
        return "NATURAL_ELIGIBLE_NO_ENGAGEMENT"
    if sums["entry_calls"]:
        return "NATURAL_WIRED_ZERO_ELIGIBILITY"
    return "NATURAL_ZERO_ENTRY"


def analyze(document: dict[str, Any], root: Path) -> dict[str, Any]:
    _exact_keys(document, {"schema", "records"}, "top-level evidence")
    if document["schema"] != EVIDENCE_SCHEMA:
        raise DataError(f"schema must be {EVIDENCE_SCHEMA!r}")
    records_raw = document["records"]
    if not isinstance(records_raw, list) or not records_raw:
        raise DataError("records must be a nonempty list")

    records = [
        _normalize_record(value, index, root)
        for index, value in enumerate(records_raw)
    ]
    seen_panels: set[tuple[str, str]] = set()
    by_component: dict[str, list[dict[str, Any]]] = {}
    for row in records:
        key = (row["component"], row["panel_id"])
        if key in seen_panels:
            raise DataError(f"duplicate component/panel id: {key!r}")
        seen_panels.add(key)
        by_component.setdefault(row["component"], []).append(row)

    components = []
    state_counts: Counter[str] = Counter()
    for component in sorted(by_component):
        rows = by_component[component]
        binding_sets = {tuple(row["bindings"]) for row in rows}
        if len(binding_sets) != 1:
            raise DataError(f"component {component!r}: inconsistent source bindings across panels")
        bindings = [
            dict(path=path, git_blob=blob)
            for path, blob in next(iter(binding_sets))
        ]
        controls = [row for row in rows if row["panel_kind"] == "positive_control"]
        natural = [row for row in rows if row["panel_kind"] == "natural"]
        failure = _control_failure(controls)
        natural_state = _natural_state(natural)
        if failure is not None:
            state = failure
        elif natural_state == "NATURAL_OUTPUT_CHANGED":
            state = "ENGAGED"
        elif natural_state == "NATURAL_EXECUTION_FAILED":
            state = "NATURAL_EXECUTION_FAILED"
        else:
            state = "CONTROL_PROVEN_NATURAL_ZERO"
        state_counts[state] += 1
        components.append({
            "component": component,
            "state": state,
            "natural_state": natural_state,
            "positive_controls": len(controls),
            "natural_panels": len(natural),
            "bindings": bindings,
            "counter_totals": {
                key: sum(row["counters"][key] for row in rows)
                for key in COUNTER_KEYS
            },
            "panel_digests": [
                {
                    "id": row["panel_id"],
                    "kind": row["panel_kind"],
                    "sha256": row["panel_sha256"],
                }
                for row in sorted(
                    rows,
                    key=lambda item: (item["panel_kind"], item["panel_id"]),
                )
            ],
        })

    return {
        "schema": REPORT_SCHEMA,
        "component_count": len(components),
        "state_counts": dict(sorted(state_counts.items())),
        "components": components,
        "interpretation": (
            "CONTROL_PROVEN_NATURAL_ZERO is not a kill: the positive control proves the seam can engage, "
            "while the supplied natural panels observed no output change. CONTROL_* failures are wiring/"
            "witness blockers, not economic conclusions. ENGAGED means at least one natural output changed; "
            "it does not imply positive EV or activation authority."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    parser.add_argument(
        "--root",
        required=True,
        type=Path,
        help="repository/worktree root for Git-blob binding",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = analyze(load_document(args.evidence), args.root)
    except (DataError, OSError) as exc:
        parser.error(str(exc))
    payload = json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
