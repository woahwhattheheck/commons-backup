#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bind evaluator reports to the generated archive-carrier entrypoints."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


class PanelBindingError(ValueError):
    """A panel report is not bound to its declared archive carrier."""


def _strict_load(path: Path, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise PanelBindingError(f"{label} has duplicate key {key!r}")
            result[key] = value
        return result

    def reject_constant(value: str) -> Any:
        raise PanelBindingError(f"{label} contains non-finite JSON constant {value}")

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=pairs,
            parse_constant=reject_constant,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PanelBindingError(f"cannot load {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise PanelBindingError(f"{label} root must be an object")
    return value


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise PanelBindingError(f"{label} must be a SHA-256 digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise PanelBindingError(f"{label} must be a SHA-256 digest") from exc
    return value.lower()


def _true_int(value: Any, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise PanelBindingError(f"{label} must be an integer >= {minimum}")
    return value


def _fingerprint(
    report: dict[str, Any], label: str, *, expected_entrypoint: str
) -> dict[str, Any]:
    progress = report.get("progress")
    if not isinstance(progress, dict) or progress.get("state") != "complete":
        raise PanelBindingError(f"{label} report is not a complete final snapshot")
    games = report.get("games")
    if not isinstance(games, list) or not games:
        raise PanelBindingError(f"{label} report has no game ledger")
    planned = _true_int(progress.get("planned_games"), f"{label} planned_games", minimum=1)
    recorded = _true_int(progress.get("recorded_games"), f"{label} recorded_games", minimum=1)
    if planned != recorded or recorded != len(games):
        raise PanelBindingError(
            f"{label} report cardinality mismatch: planned={planned}, "
            f"recorded={recorded}, games={len(games)}"
        )
    for index, game in enumerate(games):
        if not isinstance(game, dict):
            raise PanelBindingError(f"{label} game {index} is not an object")
        if game.get("status") != "complete" or game.get("failure") is not None:
            raise PanelBindingError(f"{label} game {index} is not complete")

    candidate = report.get("candidate")
    if not isinstance(candidate, dict):
        raise PanelBindingError(f"{label} report candidate fingerprint is missing")
    _digest(candidate.get("sha256"), f"{label} candidate SHA-256")
    entry_path, separator, callable_name = expected_entrypoint.partition("::")
    if not separator or not entry_path or callable_name != "agent":
        raise PanelBindingError(f"{label} carrier receipt has malformed entrypoint")
    if candidate.get("entry") != Path(entry_path).name:
        raise PanelBindingError(
            f"{label} report entry is {candidate.get('entry')!r}, "
            f"expected {Path(entry_path).name!r}"
        )
    if candidate.get("callable") != callable_name:
        raise PanelBindingError(f"{label} report callable is not {callable_name!r}")
    return candidate


def verify(
    receipt: dict[str, Any],
    control: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    if receipt.get("schema_version") != 1:
        raise PanelBindingError("unsupported carrier receipt schema")
    archive = receipt.get("archive")
    left = receipt.get("control")
    right = receipt.get("candidate")
    if not all(isinstance(value, dict) for value in (archive, left, right)):
        raise PanelBindingError("carrier receipt is missing archive/control/candidate objects")
    tree = _digest(archive.get("runtime_tree_sha256"), "archive runtime tree SHA-256")
    if _digest(left.get("runtime_tree_sha256"), "control runtime tree SHA-256") != tree:
        raise PanelBindingError("control runtime tree differs from archive runtime tree")
    if _digest(right.get("runtime_tree_sha256"), "candidate runtime tree SHA-256") != tree:
        raise PanelBindingError("candidate runtime tree differs from archive runtime tree")
    if receipt.get("canonical_runtime_equal") is not True:
        raise PanelBindingError("carrier does not certify equal canonical runtimes")
    if receipt.get("canonical_repository_modified") is not False:
        raise PanelBindingError("carrier reports canonical repository mutation")
    if left.get("overlay_installed") is not False or right.get("overlay_installed") is not True:
        raise PanelBindingError("carrier arm overlay identities are invalid")

    control_fp = _fingerprint(
        control, "control", expected_entrypoint=left.get("entrypoint")
    )
    candidate_fp = _fingerprint(
        candidate, "candidate", expected_entrypoint=right.get("entrypoint")
    )
    expected_control = _digest(left.get("entry_sha256"), "control entry SHA-256")
    expected_candidate = _digest(right.get("entry_sha256"), "candidate entry SHA-256")
    actual_control = _digest(control_fp.get("sha256"), "control report entry SHA-256")
    actual_candidate = _digest(candidate_fp.get("sha256"), "candidate report entry SHA-256")
    if actual_control != expected_control:
        raise PanelBindingError(
            f"control report is bound to {actual_control}, expected {expected_control}"
        )
    if actual_candidate != expected_candidate:
        raise PanelBindingError(
            f"candidate report is bound to {actual_candidate}, expected {expected_candidate}"
        )
    if actual_control == actual_candidate:
        raise PanelBindingError("control and candidate entrypoint digests are equal")

    return {
        "schema_version": 1,
        "operation": receipt.get("operation"),
        "archive_sha256": _digest(archive.get("sha256"), "archive SHA-256"),
        "source_manifest_sha256": _digest(
            archive.get("source_manifest_sha256"), "source manifest SHA-256"
        ),
        "runtime_tree_sha256": tree,
        "control_entry_sha256": actual_control,
        "candidate_entry_sha256": actual_candidate,
        "control_games": len(control["games"]),
        "candidate_games": len(candidate["games"]),
        "canonical_runtime_equal": True,
        "entrypoint_binding_complete": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = verify(
            _strict_load(args.receipt, "carrier receipt"),
            _strict_load(args.control, "control report"),
            _strict_load(args.candidate, "candidate report"),
        )
    except PanelBindingError as exc:
        print(f"panel binding error: {exc}", file=__import__("sys").stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
