#!/usr/bin/env python3
"""Summarize paired TITAN evaluator cells without trusting headline averages.

Input may be either:
  * a list (or {"cells"|"results"|"games"|"matches": [...]}) of paired records
    containing baseline and candidate scores, or
  * {"baseline": [...], "candidate": [...]} with one row per arm.

Each logical cell is keyed by opponent, seed, and candidate seat. Generic ``scores``
vectors, including flat ``baseline_scores``/``candidate_scores``, follow the pinned
public evaluator contract: ``[seat0, seat1]``. Explicit
``own``/``rival`` fields are already candidate-relative. Competitive margin is always
recomputed as (candidate_own - candidate_rival) -
(baseline_own - baseline_rival). A supplied delta_m is diagnostic only.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Any, Callable, Iterable, Mapping, Sequence


class DataError(ValueError):
    """Raised when evaluator evidence is incomplete, ambiguous, or malformed."""


_MISSING = object()
_NO_DEFAULT = object()
_EPS = 1e-9


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DataError(f"{label} must be a JSON number")
    try:
        out = float(value)
    except OverflowError as exc:
        raise DataError(f"{label} must be finite") from exc
    if not math.isfinite(out):
        raise DataError(f"{label} must be finite")
    return out


def _finite_statistic(operation: Callable, values: Sequence[float], label: str) -> float:
    """Reject nonfinite derived evidence, including intermediate sum overflow."""
    try:
        value = operation(values)
    except (OverflowError, ValueError) as exc:
        raise DataError(f"{label} must be finite") from exc
    return _number(value, label)


def _seat(value: Any, label: str = "seat") -> int:
    if isinstance(value, str) and value in {"0", "1"}:
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int) or value not in (0, 1):
        raise DataError(f"{label} must be 0 or 1")
    return value


def _opponent(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DataError(f"{label} must be a non-empty string")
    return value.strip()


def _seed(value: Any, label: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise DataError(f"{label} must be an integer or non-empty string")
    out = str(value).strip()
    if not out:
        raise DataError(f"{label} must be an integer or non-empty string")
    return out


def _consistent_alias(
    mapping: Mapping[str, Any],
    keys: Iterable[str],
    label: str,
    normalize: Callable[[Any, str], Any],
    *,
    default: Any = _NO_DEFAULT,
) -> Any:
    present = [(key, normalize(mapping[key], key)) for key in keys if key in mapping]
    if not present:
        if default is _NO_DEFAULT:
            raise DataError("missing required field; expected one of: " + ", ".join(keys))
        return default
    value = present[0][1]
    for key, other in present[1:]:
        if other != value:
            names = ", ".join(name for name, _ in present)
            raise DataError(f"conflicting {label} aliases: {names}")
    return value


def _optional_number_alias(mapping: Mapping[str, Any], keys: Iterable[str], label: str) -> Any:
    return _consistent_alias(mapping, keys, label, _number, default=_MISSING)


def _cell_key(record: Mapping[str, Any]) -> tuple[str, str, int]:
    if not isinstance(record, Mapping):
        raise DataError("every evidence cell must be an object")
    opponent = _consistent_alias(
        record, ("opponent", "opponent_name", "rival_name"), "opponent", _opponent
    )
    seed = _consistent_alias(record, ("seed", "game_seed"), "seed", _seed)
    seat = _consistent_alias(
        record, ("candidate_seat", "seat", "our_seat"), "seat", _seat
    )
    return opponent, seed, seat


def _score_vector(mapping: Mapping[str, Any], label: str, seat: int) -> Any:
    scores = mapping.get("scores", _MISSING)
    if scores is _MISSING:
        return _MISSING
    if not isinstance(scores, Sequence) or isinstance(scores, (str, bytes)) or len(scores) != 2:
        raise DataError(f"{label}.scores must contain player-ordered [seat0, seat1]")
    seat0 = _number(scores[0], f"{label}.scores[0]")
    seat1 = _number(scores[1], f"{label}.scores[1]")
    return (seat0, seat1) if seat == 0 else (seat1, seat0)


def _pair_from_mapping(mapping: Mapping[str, Any], label: str, *, seat: int) -> tuple[float, float]:
    """Return candidate-relative (own, rival).

    Generic ``scores`` is reserved for the official evaluator's player-ordered
    ``[seat0, seat1]`` vector. Explicit own/rival aliases are candidate-relative.
    If both forms are supplied they must normalize to the same pair.
    """
    vector_pair = _score_vector(mapping, label, seat)
    own = _optional_number_alias(
        mapping, ("own", "ours", "own_score", "our_score", "score"), f"{label}.own"
    )
    rival = _optional_number_alias(
        mapping, ("rival", "rival_score", "opponent_score", "their_score"), f"{label}.rival"
    )
    explicit_present = own is not _MISSING or rival is not _MISSING
    if explicit_present and (own is _MISSING or rival is _MISSING):
        raise DataError(f"{label} explicit score form requires both own and rival")
    explicit_pair = (own, rival) if explicit_present else _MISSING

    if vector_pair is _MISSING and explicit_pair is _MISSING:
        raise DataError(
            f"{label} must contain player-ordered scores or explicit own/rival scores"
        )
    if vector_pair is not _MISSING and explicit_pair is not _MISSING:
        if vector_pair != explicit_pair:
            raise DataError(f"conflicting {label} score forms")
        return explicit_pair
    return explicit_pair if explicit_pair is not _MISSING else vector_pair


def _player_ordered_pair_array(value: Any, label: str, *, seat: int) -> tuple[float, float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 2:
        raise DataError(f"{label} must contain player-ordered [seat0, seat1]")
    seat0 = _number(value[0], f"{label}[0]")
    seat1 = _number(value[1], f"{label}[1]")
    return (seat0, seat1) if seat == 0 else (seat1, seat0)


def _arm_scores(record: Mapping[str, Any], arm: str, *, seat: int) -> tuple[float, float]:
    forms: list[tuple[str, tuple[float, float]]] = []

    if arm in record:
        nested = record[arm]
        if not isinstance(nested, Mapping):
            raise DataError(f"{arm} must be an object")
        forms.append((arm, _pair_from_mapping(nested, arm, seat=seat)))

    flat_scores_key = f"{arm}_scores"
    if flat_scores_key in record:
        forms.append(
            (
                flat_scores_key,
                _player_ordered_pair_array(record[flat_scores_key], flat_scores_key, seat=seat),
            )
        )

    own = _optional_number_alias(
        record,
        (f"{arm}_own", f"{arm}_ours", f"{arm}_own_score", f"{arm}_our_score", f"{arm}_score"),
        f"{arm}_own",
    )
    rival = _optional_number_alias(
        record,
        (
            f"{arm}_rival",
            f"{arm}_rival_score",
            f"{arm}_opponent_score",
            f"{arm}_their_score",
        ),
        f"{arm}_rival",
    )
    flat_explicit = own is not _MISSING or rival is not _MISSING
    if flat_explicit and (own is _MISSING or rival is _MISSING):
        raise DataError(f"{arm} flat score form requires both own and rival")
    if flat_explicit:
        forms.append(("flat explicit", (own, rival)))

    if not forms:
        raise DataError(f"missing {arm} scores")
    pair = forms[0][1]
    for name, other in forms[1:]:
        if other != pair:
            raise DataError(
                f"conflicting {arm} score forms: {forms[0][0]} vs {name}"
            )
    return pair


def _activation_mapping(record: Mapping[str, Any]) -> Mapping[str, Any]:
    direct = record.get("activations", _MISSING)
    diagnostics = record.get("diagnostics", _MISSING)
    nested = _MISSING
    if diagnostics is not _MISSING:
        if not isinstance(diagnostics, Mapping):
            raise DataError("diagnostics must be an object")
        nested = diagnostics.get("activations", _MISSING)
        if nested is not _MISSING and not isinstance(nested, Mapping):
            raise DataError("diagnostics.activations must be an object")
    if direct is not _MISSING:
        if not isinstance(direct, Mapping):
            raise DataError("activations must be an object")
        if nested is not _MISSING and dict(direct) != dict(nested):
            raise DataError("conflicting activations and diagnostics.activations")
        return direct
    if nested is not _MISSING:
        return nested
    return {}


def _activation_state(value: Any, label: str) -> bool:
    if isinstance(value, bool):
        return value
    number = _number(value, label)
    if number < 0:
        raise DataError(f"{label} must not be negative")
    return number > 0


def _json_type_equal(left: Any, right: Any) -> bool:
    """Compare parsed JSON values without Python's bool/int equality aliasing."""
    if type(left) is not type(right):
        return False
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _json_type_equal(a, b) for a, b in zip(left, right)
        )
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _json_type_equal(left[key], right[key]) for key in left
        )
    return left == right


def _records_container(document: Any) -> list[Mapping[str, Any]]:
    if isinstance(document, list):
        rows = document
    elif isinstance(document, Mapping):
        present = [key for key in ("cells", "results", "games", "matches") if key in document]
        if not present:
            raise DataError(
                "input object must contain cells/results/games/matches or baseline+candidate arms"
            )
        rows = document[present[0]]
        for key in present[1:]:
            if not _json_type_equal(document[key], rows):
                raise DataError("conflicting evidence-container aliases: " + ", ".join(present))
    else:
        raise DataError("input must be a JSON list or object")
    if not isinstance(rows, list) or not rows:
        raise DataError("evidence cell list must be non-empty")
    if not all(isinstance(row, Mapping) for row in rows):
        raise DataError("every evidence cell must be an object")
    return list(rows)


def _supplied_delta(record: Mapping[str, Any]) -> tuple[str | None, Any]:
    present: list[tuple[str, float]] = []
    for name in ("delta_m", "deltaM", "delta_margin"):
        if name in record:
            present.append((name, _number(record[name], name)))
    if not present:
        return None, _MISSING
    value = present[0][1]
    for name, other in present[1:]:
        if not math.isclose(other, value, rel_tol=0.0, abs_tol=_EPS):
            raise DataError(
                "conflicting supplied delta aliases: " + ", ".join(name for name, _ in present)
            )
    return present[0][0], value


def _pair_separate_arms(document: Mapping[str, Any]) -> list[dict[str, Any]] | None:
    if "baseline" not in document or "candidate" not in document:
        return None
    if not isinstance(document["baseline"], list) or not isinstance(document["candidate"], list):
        return None
    indexed: dict[str, dict[tuple[str, str, int], Mapping[str, Any]]] = {}
    for arm in ("baseline", "candidate"):
        table: dict[tuple[str, str, int], Mapping[str, Any]] = {}
        for row in document[arm]:
            if not isinstance(row, Mapping):
                raise DataError(f"{arm} arm rows must be objects")
            key = _cell_key(row)
            if key in table:
                raise DataError(f"duplicate {arm} cell: {key}")
            table[key] = row
        if not table:
            raise DataError(f"{arm} arm must be non-empty")
        indexed[arm] = table
    baseline_keys = set(indexed["baseline"])
    candidate_keys = set(indexed["candidate"])
    if baseline_keys != candidate_keys:
        raise DataError(
            "arm cell sets differ; "
            f"missing_candidate={sorted(baseline_keys - candidate_keys)[:5]} "
            f"missing_baseline={sorted(candidate_keys - baseline_keys)[:5]}"
        )
    paired: list[dict[str, Any]] = []
    for key in sorted(baseline_keys):
        base = indexed["baseline"][key]
        cand = indexed["candidate"][key]
        bo, br = _pair_from_mapping(base, "baseline", seat=key[2])
        co, cr = _pair_from_mapping(cand, "candidate", seat=key[2])
        synthesized: dict[str, Any] = {
            "opponent": key[0],
            "seed": key[1],
            "candidate_seat": key[2],
            "baseline": {"own": bo, "rival": br},
            "candidate": {"own": co, "rival": cr},
        }
        activations = _activation_mapping(cand)
        if activations:
            synthesized["activations"] = dict(activations)
        delta_key, delta_value = _supplied_delta(cand)
        if delta_key is not None:
            synthesized[delta_key] = delta_value
        paired.append(synthesized)
    return paired


def load_records(document: Any) -> list[Mapping[str, Any]]:
    if isinstance(document, Mapping) and any(
        arm in document for arm in ("baseline", "candidate")
    ):
        # The supported root layouts are alternatives, not a priority order.
        # Never silently choose positive arm evidence over a conflicting cells list.
        if any(key in document for key in ("cells", "results", "games", "matches")):
            raise DataError("mixed separate-arm and paired-cell evidence containers")
        paired = _pair_separate_arms(document)
        if paired is None:
            raise DataError("separate-arm evidence requires baseline and candidate lists")
        return paired
    return _records_container(document)


def _outcome(own: float, rival: float) -> str:
    if own > rival:
        return "W"
    if own < rival:
        return "L"
    return "T"


def _basic_stats(cells: Sequence[dict[str, Any]]) -> dict[str, Any]:
    deltas = [cell["delta_m"] for cell in cells]
    return {
        "count": len(cells),
        "mean_delta_m": _finite_statistic(statistics.fmean, deltas, "mean delta_m"),
        "median_delta_m": _finite_statistic(statistics.median, deltas, "median delta_m"),
        "positive": sum(delta > _EPS for delta in deltas),
        "negative": sum(delta < -_EPS for delta in deltas),
        "zero": sum(abs(delta) <= _EPS for delta in deltas),
        "baseline_wtl": dict(sorted(Counter(c["baseline_outcome"] for c in cells).items())),
        "candidate_wtl": dict(sorted(Counter(c["candidate_outcome"] for c in cells).items())),
    }


def _public_cell(cell: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "opponent": cell["opponent"],
        "seed": cell["seed"],
        "seat": cell["seat"],
        "delta_m": cell["delta_m"],
        "baseline_margin": cell["baseline_margin"],
        "candidate_margin": cell["candidate_margin"],
        "baseline_outcome": cell["baseline_outcome"],
        "candidate_outcome": cell["candidate_outcome"],
    }


def analyze(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not records:
        raise DataError("evidence cell list must be non-empty")
    seen: set[tuple[str, str, int]] = set()
    cells: list[dict[str, Any]] = []
    supplied_mismatches: list[dict[str, Any]] = []
    feature_names: set[str] = set()
    for record in records:
        key = _cell_key(record)
        if key in seen:
            raise DataError(f"duplicate logical cell: {key}")
        seen.add(key)
        baseline_own, baseline_rival = _arm_scores(record, "baseline", seat=key[2])
        candidate_own, candidate_rival = _arm_scores(record, "candidate", seat=key[2])
        baseline_margin = _number(baseline_own - baseline_rival, "baseline margin")
        candidate_margin = _number(candidate_own - candidate_rival, "candidate margin")
        delta_m = _number(candidate_margin - baseline_margin, "delta_m")
        activations: dict[str, bool] = {}
        for name, raw in _activation_mapping(record).items():
            if not isinstance(name, str) or not name:
                raise DataError("activation names must be non-empty strings")
            activations[name] = _activation_state(raw, f"activations.{name}")
            feature_names.add(name)
        cell = {
            "opponent": key[0],
            "seed": key[1],
            "seat": key[2],
            "baseline_margin": baseline_margin,
            "candidate_margin": candidate_margin,
            "delta_m": delta_m,
            "baseline_outcome": _outcome(baseline_own, baseline_rival),
            "candidate_outcome": _outcome(candidate_own, candidate_rival),
            "activations": activations,
        }
        cells.append(cell)
        supplied_key, supplied = _supplied_delta(record)
        if supplied is not _MISSING and not math.isclose(
            supplied, delta_m, rel_tol=0.0, abs_tol=_EPS
        ):
            supplied_mismatches.append(
                {
                    "opponent": key[0],
                    "seed": key[1],
                    "seat": key[2],
                    "field": supplied_key,
                    "supplied": supplied,
                    "recomputed": delta_m,
                }
            )

    ordered = sorted(cells, key=lambda c: (c["opponent"], c["seed"], c["seat"]))
    deltas = [cell["delta_m"] for cell in ordered]
    worst = min(ordered, key=lambda cell: cell["delta_m"])
    best = max(ordered, key=lambda cell: cell["delta_m"])
    transitions = Counter(
        f'{cell["baseline_outcome"]}->{cell["candidate_outcome"]}' for cell in ordered
    )
    new_losses = [
        _public_cell(cell)
        for cell in ordered
        if cell["baseline_outcome"] != "L" and cell["candidate_outcome"] == "L"
    ]
    lost_wins = [
        _public_cell(cell)
        for cell in ordered
        if cell["baseline_outcome"] == "W" and cell["candidate_outcome"] != "W"
    ]
    by_seat = {
        str(seat): _basic_stats([cell for cell in ordered if cell["seat"] == seat])
        for seat in (0, 1)
        if any(cell["seat"] == seat for cell in ordered)
    }
    by_opponent = {
        opponent: _basic_stats([cell for cell in ordered if cell["opponent"] == opponent])
        for opponent in sorted({cell["opponent"] for cell in ordered})
    }
    activation_summary: dict[str, Any] = {}
    for feature in sorted(feature_names):
        active = [cell for cell in ordered if cell["activations"].get(feature) is True]
        inactive = [cell for cell in ordered if cell["activations"].get(feature) is False]
        unknown = [cell for cell in ordered if feature not in cell["activations"]]
        activation_summary[feature] = {
            "active": _basic_stats(active) if active else {"count": 0},
            "inactive": _basic_stats(inactive) if inactive else {"count": 0},
            "unknown_count": len(unknown),
        }
    return {
        "schema_version": 2,
        "cells": len(ordered),
        "delta_m": {
            "mean": _finite_statistic(statistics.fmean, deltas, "mean delta_m"),
            "median": _finite_statistic(statistics.median, deltas, "median delta_m"),
            "positive": sum(delta > _EPS for delta in deltas),
            "negative": sum(delta < -_EPS for delta in deltas),
            "zero": sum(abs(delta) <= _EPS for delta in deltas),
            "worst_cell": _public_cell(worst),
            "best_cell": _public_cell(best),
            "supplied_mismatch_count": len(supplied_mismatches),
            "supplied_mismatches": supplied_mismatches,
        },
        "outcomes": {
            "baseline_wtl": dict(
                sorted(Counter(c["baseline_outcome"] for c in ordered).items())
            ),
            "candidate_wtl": dict(
                sorted(Counter(c["candidate_outcome"] for c in ordered).items())
            ),
            "transitions": dict(sorted(transitions.items())),
            "new_losses": new_losses,
            "lost_wins": lost_wins,
        },
        "by_seat": by_seat,
        "by_opponent": by_opponent,
        "activations": activation_summary,
    }


def policy_failures(
    report: Mapping[str, Any],
    *,
    require_no_new_losses: bool = False,
    require_no_lost_wins: bool = False,
    min_mean_delta: float | None = None,
    strict_supplied_delta: bool = False,
) -> list[str]:
    failures: list[str] = []
    if require_no_new_losses and report["outcomes"]["new_losses"]:
        failures.append(f'new losses: {len(report["outcomes"]["new_losses"])}')
    if require_no_lost_wins and report["outcomes"]["lost_wins"]:
        failures.append(f'lost wins: {len(report["outcomes"]["lost_wins"])}')
    if min_mean_delta is not None and report["delta_m"]["mean"] < min_mean_delta:
        failures.append(
            f'mean delta_m {report["delta_m"]["mean"]:.12g} < {min_mean_delta:.12g}'
        )
    if strict_supplied_delta and report["delta_m"]["supplied_mismatch_count"]:
        failures.append(
            f'supplied delta_m mismatches: {report["delta_m"]["supplied_mismatch_count"]}'
        )
    return failures


def _read_json(path: Path) -> Any:
    # Validate raw evidence before dictionaries can erase duplicate members.
    # Distinct aliases remain the semantic analyzer's responsibility.
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise DataError(f"duplicate JSON member: {key!r}")
            result[key] = value
        return result

    def reject_constant(token: str) -> Any:
        raise DataError(f"nonfinite JSON constant: {token}")

    def finite_float(token: str) -> float:
        return _number(float(token), "JSON number")

    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
            parse_float=finite_float,
        )
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise DataError(f"cannot read JSON evidence {path}: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path, help="paired evaluator/bench JSON")
    parser.add_argument("--output", type=Path, help="also write the normalized report JSON")
    parser.add_argument("--require-no-new-losses", action="store_true")
    parser.add_argument("--require-no-lost-wins", action="store_true")
    parser.add_argument("--min-mean-delta", type=float)
    parser.add_argument(
        "--strict-supplied-delta",
        action="store_true",
        help="fail policy if a supplied delta field disagrees with recomputed scores",
    )
    args = parser.parse_args(argv)
    try:
        if args.min_mean_delta is not None and not math.isfinite(args.min_mean_delta):
            raise DataError("--min-mean-delta must be finite")
        report = analyze(load_records(_read_json(args.evidence)))
    except DataError as exc:
        print(f"DATA ERROR: {exc}", file=sys.stderr)
        return 2
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    sys.stdout.write(rendered)
    if args.output:
        try:
            args.output.write_text(rendered, encoding="utf-8")
        except OSError as exc:
            print(f"DATA ERROR: cannot write {args.output}: {exc}", file=sys.stderr)
            return 2
    failures = policy_failures(
        report,
        require_no_new_losses=args.require_no_new_losses,
        require_no_lost_wins=args.require_no_lost_wins,
        min_mean_delta=args.min_mean_delta,
        strict_supplied_delta=args.strict_supplied_delta,
    )
    if failures:
        for failure in failures:
            print("POLICY FAIL:", failure, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())