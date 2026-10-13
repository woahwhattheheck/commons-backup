#!/usr/bin/env python3
"""Contention-stability certificate for TITAN gauntlet JSONL results.

This tool is deliberately runner-independent.  It compares the same game
coordinates from a quiet run and a loaded run and fails closed on missing,
failed, fallback, duplicate, or non-finite rows.  It never edits game data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

MARGIN_PATHS = (
    "margin",
    "terminal_margin",
    "score_margin",
    "result.margin",
    "metrics.margin",
    "terminal.margin",
    "score.margin",
)
SCORE_PAIRS = (
    ("own_score", "rival_score"),
    ("candidate_score", "opponent_score"),
    ("scores.own", "scores.rival"),
    ("scores.candidate", "scores.opponent"),
    ("terminal.own", "terminal.rival"),
    ("terminal.candidate", "terminal.opponent"),
)
COORD_ALIASES = {
    "opponent": ("opponent_id", "opponent", "opponent_name", "rival_id", "rival", "rival_name"),
    "seed": ("seed", "game_seed"),
    "seat": ("seat", "candidate_seat", "player"),
    "replicate": ("replicate", "rep", "repeat", "trial"),
}
GOOD_STATUSES = {"ok", "success", "complete", "completed", "pass", "passed"}


class InputError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedRow:
    coord: tuple[Any, ...]
    margin: float
    margin_source: str
    line_no: int
    raw: dict[str, Any]


def _get_path(obj: Any, path: str) -> Any:
    cur = obj
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise KeyError(path)
        cur = cur[part]
    return cur


def _first_path(obj: dict[str, Any], paths: Iterable[str]) -> tuple[str, Any]:
    for path in paths:
        try:
            return path, _get_path(obj, path)
        except KeyError:
            continue
    raise KeyError(tuple(paths))


def _as_finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f"{label} is not numeric: {value!r}")
    out = float(value)
    if not math.isfinite(out):
        raise InputError(f"{label} is not finite: {value!r}")
    return out


def extract_margin(row: dict[str, Any], explicit: str | None) -> tuple[float, str]:
    if explicit:
        try:
            return _as_finite_number(_get_path(row, explicit), explicit), explicit
        except KeyError as exc:
            raise InputError(f"missing explicit margin field {explicit!r}") from exc

    for path in MARGIN_PATHS:
        try:
            return _as_finite_number(_get_path(row, path), path), path
        except KeyError:
            pass

    for own_path, rival_path in SCORE_PAIRS:
        try:
            own = _as_finite_number(_get_path(row, own_path), own_path)
            rival = _as_finite_number(_get_path(row, rival_path), rival_path)
            return own - rival, f"{own_path}-{rival_path}"
        except KeyError:
            pass
    raise InputError("cannot infer terminal margin; pass --margin-field")


def _coord_value(row: dict[str, Any], canonical: str, required: bool = True) -> Any:
    paths = COORD_ALIASES[canonical]
    try:
        _path, value = _first_path(row, paths)
        return value
    except KeyError:
        if canonical == "replicate":
            return 0
        if required:
            raise InputError(f"cannot infer coordinate {canonical!r}; aliases={paths}")
        return None


def extract_coord(row: dict[str, Any], explicit_fields: list[str] | None) -> tuple[Any, ...]:
    if explicit_fields:
        vals: list[Any] = []
        for field in explicit_fields:
            try:
                vals.append(_get_path(row, field))
            except KeyError as exc:
                raise InputError(f"missing explicit key field {field!r}") from exc
        return tuple(vals)
    return (
        _coord_value(row, "opponent"),
        _coord_value(row, "seed"),
        _coord_value(row, "seat"),
        _coord_value(row, "replicate"),
    )


def validate_row_health(row: dict[str, Any], label: str) -> None:
    for path in ("error", "exception", "timed_out", "timeout"):
        try:
            value = _get_path(row, path)
        except KeyError:
            continue
        if value not in (None, False, "", 0):
            raise InputError(f"{label}: unhealthy {path}={value!r}")
    for path in ("fallback", "used_fallback", "deadline_fallback"):
        try:
            value = _get_path(row, path)
        except KeyError:
            continue
        if bool(value):
            raise InputError(f"{label}: fallback row is not certifiable ({path}={value!r})")
    for path in ("status", "result.status"):
        try:
            value = _get_path(row, path)
        except KeyError:
            continue
        if value is None:
            continue
        text = str(value).strip().lower()
        if text and text not in GOOD_STATUSES:
            raise InputError(f"{label}: non-success status {value!r}")


def load_jsonl(path: Path, margin_field: str | None, key_fields: list[str] | None) -> dict[tuple[Any, ...], ParsedRow]:
    rows: dict[tuple[Any, ...], ParsedRow] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise InputError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
            if not isinstance(raw, dict):
                raise InputError(f"{path}:{line_no}: row must be an object")
            validate_row_health(raw, f"{path}:{line_no}")
            coord = extract_coord(raw, key_fields)
            try:
                hash(coord)
            except TypeError as exc:
                raise InputError(f"{path}:{line_no}: coordinate is not hashable: {coord!r}") from exc
            margin, source = extract_margin(raw, margin_field)
            if coord in rows:
                prev = rows[coord]
                raise InputError(f"{path}:{line_no}: duplicate coordinate {coord!r}; first at line {prev.line_no}")
            rows[coord] = ParsedRow(coord, margin, source, line_no, raw)
    if not rows:
        raise InputError(f"{path}: no JSONL rows")
    return rows


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _json_coord(coord: tuple[Any, ...]) -> list[Any]:
    return list(coord)


def evaluate(
    quiet: dict[tuple[Any, ...], ParsedRow],
    loaded: dict[tuple[Any, ...], ParsedRow],
    *,
    exact_coverage: bool,
    max_abs_drift: float,
    max_mean_abs_drift: float,
    max_mean_bias: float,
    claimed_edge: float | None,
    max_noise_fraction: float,
    min_pairs: int,
    require_both_seats: bool,
    seat_index: int,
) -> dict[str, Any]:
    quiet_keys = set(quiet)
    loaded_keys = set(loaded)
    missing_loaded = sorted(quiet_keys - loaded_keys, key=repr)
    extra_loaded = sorted(loaded_keys - quiet_keys, key=repr)
    common = sorted(quiet_keys & loaded_keys, key=repr)

    failures: list[str] = []
    if missing_loaded:
        failures.append(f"loaded run misses {len(missing_loaded)} quiet coordinates")
    if exact_coverage and extra_loaded:
        failures.append(f"loaded run has {len(extra_loaded)} extra coordinates under --exact-coverage")
    if len(common) < min_pairs:
        failures.append(f"only {len(common)} aligned pairs; require >= {min_pairs}")

    seats = {coord[seat_index] for coord in common if len(coord) > seat_index}
    if require_both_seats and len(seats) < 2:
        failures.append(f"aligned rows cover only {len(seats)} seat value(s): {sorted(seats, key=repr)!r}")

    deltas = [loaded[k].margin - quiet[k].margin for k in common]
    abs_deltas = [abs(v) for v in deltas]
    if deltas:
        max_abs = max(abs_deltas)
        mean_abs = statistics.fmean(abs_deltas)
        mean_bias = statistics.fmean(deltas)
    else:
        max_abs = mean_abs = mean_bias = math.inf

    dynamic_limit = None
    if claimed_edge is not None:
        dynamic_limit = abs(claimed_edge) * max_noise_fraction
        if max_abs > dynamic_limit:
            failures.append(
                f"max contention drift {max_abs:.6g} exceeds {max_noise_fraction:.3g}x claimed edge "
                f"budget {dynamic_limit:.6g}"
            )
    if max_abs > max_abs_drift:
        failures.append(f"max contention drift {max_abs:.6g} exceeds {max_abs_drift:.6g}")
    if mean_abs > max_mean_abs_drift:
        failures.append(f"mean absolute contention drift {mean_abs:.6g} exceeds {max_mean_abs_drift:.6g}")
    if abs(mean_bias) > max_mean_bias:
        failures.append(f"absolute signed contention bias {abs(mean_bias):.6g} exceeds {max_mean_bias:.6g}")

    worst = sorted(
        (
            {
                "coordinate": _json_coord(k),
                "quiet_margin": quiet[k].margin,
                "loaded_margin": loaded[k].margin,
                "drift": loaded[k].margin - quiet[k].margin,
            }
            for k in common
        ),
        key=lambda item: abs(item["drift"]),
        reverse=True,
    )[:12]

    return {
        "certified": not failures,
        "aligned_pairs": len(common),
        "quiet_rows": len(quiet),
        "loaded_rows": len(loaded),
        "missing_loaded_count": len(missing_loaded),
        "extra_loaded_count": len(extra_loaded),
        "seat_values": sorted(seats, key=repr),
        "max_abs_drift": max_abs,
        "mean_abs_drift": mean_abs,
        "mean_signed_bias": mean_bias,
        "dynamic_claimed_edge_limit": dynamic_limit,
        "failures": failures,
        "worst_pairs": worst,
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--quiet", required=True, type=Path, help="quiet/reference JSONL (typically workers=1)")
    p.add_argument("--loaded", required=True, type=Path, help="loaded JSONL (for example workers=8)")
    p.add_argument("--out", type=Path, help="write machine-readable certificate JSON")
    p.add_argument("--margin-field", help="explicit dotted margin field; otherwise infer common schemas")
    p.add_argument("--key-fields", help="comma-separated dotted fields used as exact coordinate key")
    p.add_argument("--exact-coverage", action="store_true", help="require loaded and quiet files to have identical coordinates")
    p.add_argument("--max-abs-drift", type=float, default=100.0)
    p.add_argument("--max-mean-abs-drift", type=float, default=50.0)
    p.add_argument("--max-mean-bias", type=float, default=50.0)
    p.add_argument("--claimed-edge", type=float, help="expected lane edge; enables relative noise budget")
    p.add_argument("--max-noise-fraction", type=float, default=0.25)
    p.add_argument("--min-pairs", type=int, default=2)
    p.add_argument("--allow-one-seat", action="store_true")
    p.add_argument("--seat-key-index", type=int, default=2, help="seat tuple index (default matches inferred key)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.max_abs_drift < 0 or args.max_mean_abs_drift < 0 or args.max_mean_bias < 0:
        print("thresholds must be non-negative", file=sys.stderr)
        return 3
    if not (0 <= args.max_noise_fraction <= 1):
        print("--max-noise-fraction must be in [0,1]", file=sys.stderr)
        return 3
    if args.min_pairs < 1:
        print("--min-pairs must be >= 1", file=sys.stderr)
        return 3
    key_fields = [s.strip() for s in args.key_fields.split(",") if s.strip()] if args.key_fields else None
    try:
        quiet = load_jsonl(args.quiet, args.margin_field, key_fields)
        loaded = load_jsonl(args.loaded, args.margin_field, key_fields)
        report = evaluate(
            quiet,
            loaded,
            exact_coverage=args.exact_coverage,
            max_abs_drift=args.max_abs_drift,
            max_mean_abs_drift=args.max_mean_abs_drift,
            max_mean_bias=args.max_mean_bias,
            claimed_edge=args.claimed_edge,
            max_noise_fraction=args.max_noise_fraction,
            min_pairs=args.min_pairs,
            require_both_seats=not args.allow_one_seat,
            seat_index=args.seat_key_index,
        )
    except (OSError, InputError) as exc:
        print(f"QUIETBOX INPUT ERROR: {exc}", file=sys.stderr)
        return 3

    report.update(
        {
            "quiet_file": str(args.quiet),
            "loaded_file": str(args.loaded),
            "quiet_sha256": sha256_file(args.quiet),
            "loaded_sha256": sha256_file(args.loaded),
            "margin_field": args.margin_field or "auto",
            "key_fields": key_fields or ["opponent", "seed", "seat", "replicate"],
            "thresholds": {
                "max_abs_drift": args.max_abs_drift,
                "max_mean_abs_drift": args.max_mean_abs_drift,
                "max_mean_bias": args.max_mean_bias,
                "claimed_edge": args.claimed_edge,
                "max_noise_fraction": args.max_noise_fraction,
                "min_pairs": args.min_pairs,
                "require_both_seats": not args.allow_one_seat,
                "exact_coverage": args.exact_coverage,
            },
            "margin_sources_quiet": dict(Counter(row.margin_source for row in quiet.values())),
            "margin_sources_loaded": dict(Counter(row.margin_source for row in loaded.values())),
        }
    )
    text = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if report["certified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
