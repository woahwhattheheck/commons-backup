#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail-closed provenance and paired-regression gate for canonical TITAN.

The source tree, canonical archive, test receipt, artifact registry, and game
ledger are separate evidence surfaces.  This tool refuses to collapse them into
one score claim unless every binding is exact.

Examples::

    python titan_regression_gate.py audit --root . --require-games
    python titan_regression_gate.py compare --left v1-ledger.json --right v2-ledger.json

The comparator never estimates a leaderboard score.  It reports only exact
paired deltas for rows sharing engine, environment seed, opponent artifact, and
candidate seat.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import statistics
from typing import Any, Iterable, Mapping, Sequence


ARCHIVE_FIELDS = (
    "path",
    "sha256",
    "bytes",
    "runtime_files",
    "source_manifest",
    "source_manifest_sha256",
)

DEFAULT_RECEIPT = Path("runtime/integrated-selected/CURRENT-ARCHIVE.json")
DEFAULT_TESTS = Path("runtime/integrated-selected/CURRENT-TESTS.json")
DEFAULT_SOURCE = Path("runtime/integrated-selected/CURRENT-SOURCE.json")
DEFAULT_REGISTRY = Path("exports/ARTIFACTS.json")


class GateError(ValueError):
    """Raised when an evidence ledger is malformed or cannot be compared."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GateError(f"missing required file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise GateError(f"invalid JSON in {path}: {exc}") from exc


def _issue(code: str, message: str, **details: Any) -> dict[str, Any]:
    row: dict[str, Any] = {"code": code, "message": message}
    if details:
        row["details"] = details
    return row


def _archive_record(value: Any) -> Mapping[str, Any] | None:
    """Return the first archive-like record from common evidence schemas."""
    if not isinstance(value, Mapping):
        return None
    for key in ("candidate_archive", "current_archive", "archive_receipt"):
        row = value.get(key)
        if isinstance(row, Mapping):
            return row
    if "sha256" in value and ("path" in value or "file" in value):
        return value
    row = value.get("archive")
    if isinstance(row, Mapping):
        return row
    return None


def _normalize_archive(row: Mapping[str, Any] | None) -> dict[str, Any]:
    if row is None:
        return {}
    normalized = dict(row)
    if "path" not in normalized and "file" in normalized:
        normalized["path"] = normalized["file"]
    return normalized


def _walk_bindings(value: Any) -> Iterable[dict[str, Any]]:
    """Yield file/SHA bindings from arbitrary registry JSON."""
    if isinstance(value, Mapping):
        path = value.get("path", value.get("file"))
        digest = value.get("sha256")
        if isinstance(path, str) and isinstance(digest, str):
            yield {"path": path, "sha256": digest, **dict(value)}
        for child in value.values():
            yield from _walk_bindings(child)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for child in value:
            yield from _walk_bindings(child)


def _extract_game_evidence(*values: Any) -> list[dict[str, Any]]:
    """Return game counts and archive bindings found in the same JSON object.

    A SHA elsewhere in a test report is not a game binding.  Each positive
    count must live beside an explicit archive SHA (directly or in an archive
    child object) before it can support promotion.
    """
    count_keys = {
        "new_full_games",
        "full_games",
        "completed_full_games",
        "exact_archive_full_games",
        "new_games",
        "games",
    }
    evidence: list[dict[str, Any]] = []

    def explicit_archive_shas(row: Mapping[str, Any]) -> set[str]:
        found: set[str] = set()
        direct = row.get("archive_sha256")
        if isinstance(direct, str) and direct:
            found.add(direct)
        for key in ("archive", "candidate_archive", "current_archive"):
            child = row.get(key)
            if isinstance(child, Mapping):
                digest = child.get("sha256", child.get("archive_sha256"))
                if isinstance(digest, str) and digest:
                    found.add(digest)
        return found

    def walk(value: Any, path: tuple[str, ...]) -> None:
        if isinstance(value, Mapping):
            counts = [
                int(child)
                for key, child in value.items()
                if key in count_keys and isinstance(child, int) and not isinstance(child, bool)
            ]
            if counts:
                evidence.append({
                    "path": ".".join(path) or "$",
                    "full_games": max(0, max(counts)),
                    "archive_sha256": sorted(explicit_archive_shas(value)),
                })
            for key, child in value.items():
                walk(child, path + (str(key),))
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            for index, child in enumerate(value):
                walk(child, path + (str(index),))

    for index, value in enumerate(values):
        walk(value, (f"surface[{index}]",))
    return evidence


def audit_current(
    root: str | Path,
    *,
    require_games: bool = False,
    receipt_path: Path = DEFAULT_RECEIPT,
    tests_path: Path = DEFAULT_TESTS,
    source_path: Path = DEFAULT_SOURCE,
    registry_path: Path = DEFAULT_REGISTRY,
) -> dict[str, Any]:
    """Audit whether current policy claims are bound to the canonical bytes.

    Integrity checks always run.  ``require_games`` additionally blocks a
    promotion claim unless a positive full-game count is explicitly tied to the
    canonical archive SHA.
    """
    root = Path(root).resolve()
    paths = {
        "receipt": root / receipt_path,
        "tests": root / tests_path,
        "source": root / source_path,
        "registry": root / registry_path,
    }
    blockers: list[dict[str, Any]] = []
    notes: list[dict[str, Any]] = []

    loaded: dict[str, Any] = {}
    for name, path in paths.items():
        try:
            loaded[name] = _load_json(path)
        except GateError as exc:
            blockers.append(_issue("MISSING_OR_INVALID_JSON", str(exc), surface=name, path=str(path)))

    if blockers:
        return {
            "schema_version": 1,
            "verdict": "BLOCKED",
            "promotion_ready": False,
            "require_games": require_games,
            "root": str(root),
            "blockers": blockers,
            "notes": notes,
        }

    receipt = _normalize_archive(_archive_record(loaded["receipt"]))
    tests_receipt = _normalize_archive(_archive_record(loaded["tests"]))
    source = loaded["source"]
    registry = loaded["registry"]

    if not receipt:
        blockers.append(_issue("CANONICAL_RECEIPT_MISSING", "CURRENT-ARCHIVE has no archive receipt"))
    if not tests_receipt:
        blockers.append(_issue("TEST_RECEIPT_MISSING", "CURRENT-TESTS has no candidate archive receipt"))

    missing_fields = [field for field in ARCHIVE_FIELDS if field not in receipt]
    if missing_fields:
        blockers.append(_issue(
            "CANONICAL_RECEIPT_INCOMPLETE",
            "canonical receipt omits required identity fields",
            missing=missing_fields,
        ))

    field_mismatches: dict[str, dict[str, Any]] = {}
    if receipt and tests_receipt:
        for field in ARCHIVE_FIELDS:
            if receipt.get(field) != tests_receipt.get(field):
                field_mismatches[field] = {
                    "canonical": receipt.get(field),
                    "tests": tests_receipt.get(field),
                }
        if field_mismatches:
            blockers.append(_issue(
                "STALE_TEST_RECEIPT",
                "CURRENT-TESTS is not evidence for the canonical archive",
                mismatches=field_mismatches,
            ))

    archive_path: Path | None = None
    if isinstance(receipt.get("path"), str):
        archive_path = root / receipt["path"]
        try:
            archive_bytes = archive_path.read_bytes()
        except FileNotFoundError:
            blockers.append(_issue(
                "CANONICAL_ARCHIVE_MISSING",
                "canonical receipt points to a missing archive",
                path=str(archive_path),
            ))
        else:
            actual_digest = _sha256(archive_bytes)
            actual_size = len(archive_bytes)
            if actual_digest != receipt.get("sha256"):
                blockers.append(_issue(
                    "CANONICAL_ARCHIVE_HASH_MISMATCH",
                    "archive bytes do not match CURRENT-ARCHIVE",
                    expected=receipt.get("sha256"),
                    actual=actual_digest,
                ))
            if actual_size != receipt.get("bytes"):
                blockers.append(_issue(
                    "CANONICAL_ARCHIVE_SIZE_MISMATCH",
                    "archive size does not match CURRENT-ARCHIVE",
                    expected=receipt.get("bytes"),
                    actual=actual_size,
                ))

    manifest_rel = receipt.get("source_manifest")
    if isinstance(manifest_rel, str):
        manifest_path = root / manifest_rel
        try:
            manifest_bytes = manifest_path.read_bytes()
        except FileNotFoundError:
            blockers.append(_issue(
                "SOURCE_MANIFEST_MISSING",
                "canonical source manifest is missing",
                path=str(manifest_path),
            ))
        else:
            actual_manifest_digest = _sha256(manifest_bytes)
            if actual_manifest_digest != receipt.get("source_manifest_sha256"):
                blockers.append(_issue(
                    "SOURCE_MANIFEST_HASH_MISMATCH",
                    "CURRENT-SOURCE bytes do not match CURRENT-ARCHIVE",
                    expected=receipt.get("source_manifest_sha256"),
                    actual=actual_manifest_digest,
                ))

    registry_bindings = list(_walk_bindings(registry))
    registry_match = any(
        row.get("path") == receipt.get("path") and row.get("sha256") == receipt.get("sha256")
        for row in registry_bindings
    )
    if not registry_match:
        blockers.append(_issue(
            "CURRENT_ARCHIVE_UNREGISTERED",
            "artifact registry has no exact path/SHA binding for the canonical archive",
            canonical_path=receipt.get("path"),
            canonical_sha256=receipt.get("sha256"),
            registry_bindings=[
                {"path": row.get("path"), "sha256": row.get("sha256")}
                for row in registry_bindings
            ],
        ))

    game_entries = _extract_game_evidence(source, loaded["tests"])
    game_count = max((entry["full_games"] for entry in game_entries), default=0)
    canonical_sha = receipt.get("sha256")
    exact_game_count = max(
        (
            entry["full_games"]
            for entry in game_entries
            if canonical_sha and canonical_sha in entry["archive_sha256"]
        ),
        default=0,
    )
    evidence_shas = sorted({
        digest
        for entry in game_entries
        for digest in entry["archive_sha256"]
    })
    exact_game_binding = exact_game_count > 0

    if game_count == 0:
        notes.append(_issue(
            "NO_CURRENT_FULL_GAMES",
            "no positive full-game count is reported for the current evidence surfaces",
        ))
    elif not exact_game_binding:
        blockers.append(_issue(
            "UNBOUND_GAME_EVIDENCE",
            "positive game counts are not co-located with the canonical archive SHA",
            game_count=game_count,
            canonical_sha256=canonical_sha,
            evidence_entries=game_entries,
        ))

    if require_games:
        if game_count <= 0:
            blockers.append(_issue(
                "PROMOTION_REQUIRES_CURRENT_GAMES",
                "promotion mode requires positive exact-archive full-game evidence",
                game_count=game_count,
            ))
        elif not exact_game_binding:
            blockers.append(_issue(
                "PROMOTION_REQUIRES_EXACT_GAME_BINDING",
                "promotion mode requires each positive game count to name the canonical archive SHA in the same evidence object",
                canonical_sha256=canonical_sha,
            ))

    integrity_ready = not blockers
    promotion_ready = integrity_ready and exact_game_count > 0
    verdict = "PASS" if integrity_ready and (not require_games or promotion_ready) else "BLOCKED"
    return {
        "schema_version": 1,
        "verdict": verdict,
        "integrity_ready": integrity_ready,
        "promotion_ready": promotion_ready,
        "require_games": require_games,
        "root": str(root),
        "canonical_archive": receipt,
        "test_archive": tests_receipt,
        "game_evidence": {
            "reported_full_games": game_count,
            "exact_archive_full_games": exact_game_count,
            "archive_sha256": evidence_shas,
            "exact_binding": exact_game_binding,
            "entries": game_entries,
        },
        "registry_match": registry_match,
        "blockers": blockers,
        "notes": notes,
    }


@dataclass(frozen=True, order=True)
class CellKey:
    engine_sha256: str
    environment_seed: str
    opponent_sha256: str
    seat: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "engine_sha256": self.engine_sha256,
            "environment_seed": self.environment_seed,
            "opponent_sha256": self.opponent_sha256,
            "seat": self.seat,
        }


@dataclass(frozen=True)
class Cell:
    key: CellKey
    margin: float


def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GateError(f"{field} must be a nonempty string")
    return value.strip()


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GateError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise GateError(f"{field} must be finite")
    return result


def _ledger_archive_sha(ledger: Mapping[str, Any]) -> str:
    direct = ledger.get("archive_sha256")
    if isinstance(direct, str):
        return _nonempty_string(direct, "archive_sha256")
    archive = ledger.get("archive")
    if isinstance(archive, Mapping):
        return _nonempty_string(archive.get("sha256"), "archive.sha256")
    raise GateError("ledger must include archive_sha256 or archive.sha256")


def _cell_margin(row: Mapping[str, Any]) -> float:
    if "margin" in row:
        return _finite_number(row["margin"], "row.margin")
    if "candidate_score" in row and "opponent_score" in row:
        return _finite_number(row["candidate_score"], "row.candidate_score") - _finite_number(
            row["opponent_score"], "row.opponent_score"
        )
    raise GateError("each row must include margin or candidate_score + opponent_score")


def _parse_ledger(ledger: Mapping[str, Any], label: str) -> tuple[str, dict[CellKey, Cell]]:
    archive_sha = _ledger_archive_sha(ledger)
    top_engine = ledger.get("engine_sha256")
    rows = ledger.get("rows")
    if not isinstance(rows, list) or not rows:
        raise GateError(f"{label}: rows must be a nonempty list")

    parsed: dict[CellKey, Cell] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise GateError(f"{label}: row {index} must be an object")
        status = str(row.get("status", "DONE")).upper()
        if status not in {"DONE", "COMPLETE", "COMPLETED", "PASS"}:
            raise GateError(f"{label}: row {index} is not completed: {status}")
        for failure_field in ("error", "timeout", "timed_out"):
            if row.get(failure_field):
                raise GateError(f"{label}: row {index} reports {failure_field}")

        engine = row.get("engine_sha256", top_engine)
        seed = row.get("environment_seed", row.get("seed"))
        opponent = row.get("opponent_sha256", row.get("opponent_archive_sha256"))
        seat = row.get("seat", row.get("candidate_seat"))
        if isinstance(seat, bool) or not isinstance(seat, int) or seat < 0:
            raise GateError(f"{label}: row {index} seat must be a nonnegative integer")
        key = CellKey(
            _nonempty_string(engine, f"{label}.rows[{index}].engine_sha256"),
            _nonempty_string(str(seed) if seed is not None else None, f"{label}.rows[{index}].environment_seed"),
            _nonempty_string(opponent, f"{label}.rows[{index}].opponent_sha256"),
            seat,
        )
        if key in parsed:
            raise GateError(f"{label}: duplicate comparison cell {key.as_dict()}")
        parsed[key] = Cell(key=key, margin=_cell_margin(row))
    return archive_sha, parsed


def _schedule_fingerprint(keys: Iterable[CellKey]) -> str:
    rows = [key.as_dict() for key in sorted(keys)]
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha256(encoded)


def compare_ledgers(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    require_identical_panel: bool = True,
) -> dict[str, Any]:
    """Compare exact paired game cells, refusing incomparable headlines."""
    left_sha, left_cells = _parse_ledger(left, "left")
    right_sha, right_cells = _parse_ledger(right, "right")
    left_keys = set(left_cells)
    right_keys = set(right_cells)
    common = left_keys & right_keys
    only_left = left_keys - right_keys
    only_right = right_keys - left_keys

    blockers: list[dict[str, Any]] = []
    if left_sha == right_sha:
        blockers.append(_issue(
            "SAME_ARCHIVE",
            "left and right ledgers name the same archive; no version delta exists",
            archive_sha256=left_sha,
        ))
    if not common:
        blockers.append(_issue(
            "NO_COMPARABLE_CELLS",
            "ledgers share no exact engine/seed/opponent/seat cells",
            left_schedule=_schedule_fingerprint(left_keys),
            right_schedule=_schedule_fingerprint(right_keys),
        ))
    if require_identical_panel and (only_left or only_right):
        blockers.append(_issue(
            "PANEL_MISMATCH",
            "strict comparison requires identical exact-cell schedules",
            only_left=len(only_left),
            only_right=len(only_right),
        ))

    if blockers:
        return {
            "schema_version": 1,
            "verdict": "REFUSED",
            "left_archive_sha256": left_sha,
            "right_archive_sha256": right_sha,
            "left_cells": len(left_keys),
            "right_cells": len(right_keys),
            "common_cells": len(common),
            "only_left": [key.as_dict() for key in sorted(only_left)],
            "only_right": [key.as_dict() for key in sorted(only_right)],
            "blockers": blockers,
        }

    deltas = [right_cells[key].margin - left_cells[key].margin for key in sorted(common)]
    wins = sum(delta > 0 for delta in deltas)
    ties = sum(delta == 0 for delta in deltas)
    losses = sum(delta < 0 for delta in deltas)
    rows = [
        {
            **key.as_dict(),
            "left_margin": left_cells[key].margin,
            "right_margin": right_cells[key].margin,
            "delta": right_cells[key].margin - left_cells[key].margin,
        }
        for key in sorted(common)
    ]
    return {
        "schema_version": 1,
        "verdict": "COMPARABLE",
        "left_archive_sha256": left_sha,
        "right_archive_sha256": right_sha,
        "strict_identical_panel": require_identical_panel,
        "schedule_fingerprint": _schedule_fingerprint(common),
        "cells": len(common),
        "wins_ties_losses": {"right_better": wins, "tie": ties, "right_worse": losses},
        "delta": {
            "mean": statistics.fmean(deltas),
            "median": statistics.median(deltas),
            "minimum": min(deltas),
            "maximum": max(deltas),
            "sum": math.fsum(deltas),
        },
        "rows": rows,
        "blockers": [],
    }


def _write_report(report: Mapping[str, Any], target: str | None) -> None:
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if target:
        Path(target).write_text(encoded, encoding="utf-8")
    print(encoded, end="")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    audit = sub.add_parser("audit", help="audit canonical source/archive/evidence identity")
    audit.add_argument("--root", default=".")
    audit.add_argument("--require-games", action="store_true")
    audit.add_argument("--report-json")

    compare = sub.add_parser("compare", help="compare exact paired game ledgers")
    compare.add_argument("--left", required=True)
    compare.add_argument("--right", required=True)
    compare.add_argument("--allow-partial-panel", action="store_true")
    compare.add_argument("--report-json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "audit":
            report = audit_current(args.root, require_games=args.require_games)
            _write_report(report, args.report_json)
            return 0 if report["verdict"] == "PASS" else 2
        left = _load_json(Path(args.left))
        right = _load_json(Path(args.right))
        if not isinstance(left, Mapping) or not isinstance(right, Mapping):
            raise GateError("comparison ledgers must be JSON objects")
        report = compare_ledgers(
            left,
            right,
            require_identical_panel=not args.allow_partial_panel,
        )
        _write_report(report, args.report_json)
        return 0 if report["verdict"] == "COMPARABLE" else 3
    except GateError as exc:
        report = {"schema_version": 1, "verdict": "REFUSED", "error": str(exc)}
        _write_report(report, getattr(args, "report_json", None))
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
