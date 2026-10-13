#!/usr/bin/env python3
"""Empirical paired-field screen; not an evaluator or promotion authority.

Reuse the exact #12646 seat-aware reporter, then enforce a separately supplied
opponent/seed panel with both seats. Never infer expected coverage from outcomes.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import sys
import tempfile
import types
from typing import Any

REPORTER_BLOB = "5fa647b46dd2c359bc045a435d1542b1b06ed738"
DEFAULT_REPORTER = Path(__file__).resolve().parents[2] / "repairs" / "tooling" / "delta-evidence" / "v31_delta_distribution_report.py"


class DataError(ValueError):
    """Invalid evidence, panel, configuration, or reporter custody."""


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def load_reporter(path: Path = DEFAULT_REPORTER) -> types.ModuleType:
    """Execute only the already-reviewed exact reporter bytes, never a substitute."""
    try:
        data = Path(path).read_bytes()
    except OSError as exc:
        raise DataError(f"cannot read reporter: {exc}") from exc
    actual = git_blob(data)
    if actual != REPORTER_BLOB:
        raise DataError(f"reporter custody mismatch: {actual} != {REPORTER_BLOB}")
    module = types.ModuleType("_v4_pinned_delta_reporter")
    module.__file__ = str(path)
    exec(compile(data, str(path), "exec"), module.__dict__)
    return module


def number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DataError(f"{label} must be a finite number")
    try:
        out = float(value)
    except OverflowError as exc:
        raise DataError(f"{label} must be finite") from exc
    if not math.isfinite(out):
        raise DataError(f"{label} must be finite")
    return out


def mean(values: list[float], label: str) -> float:
    try:
        return number(statistics.fmean(values), label)
    except (OverflowError, statistics.StatisticsError) as exc:
        raise DataError(f"{label} must be finite and nonempty") from exc


@dataclass(frozen=True)
class Policy:
    min_seed_pairs: int = 8
    min_opponents: int = 2
    min_balanced_delta: float = 0.0
    min_opponent_delta: float = 0.0
    min_opponent_seat_delta: float = 0.0
    max_new_losses: int = 0
    max_lost_wins: int = 0

    def validate(self) -> None:
        for name in ("min_seed_pairs", "min_opponents", "max_new_losses", "max_lost_wins"):
            value = getattr(self, name)
            minimum = 1 if name.startswith("min_") else 0
            if type(value) is not int or value < minimum:
                raise DataError(f"{name} must be an integer >= {minimum}")
        for name in ("min_balanced_delta", "min_opponent_delta", "min_opponent_seat_delta"):
            number(getattr(self, name), name)


def panel_keys(panel: Any) -> set[tuple[str, str, int]]:
    if not isinstance(panel, dict) or set(panel) != {"schema_version", "opponents"}:
        raise DataError("panel requires only schema_version and opponents")
    if type(panel["schema_version"]) is not int or panel["schema_version"] != 1:
        raise DataError("panel schema_version must be literal integer 1")
    opponents = panel["opponents"]
    if not isinstance(opponents, dict) or not opponents:
        raise DataError("panel opponents must be a nonempty name -> seed-list object")
    keys: set[tuple[str, str, int]] = set()
    names: set[str] = set()
    for raw_name, raw_seeds in opponents.items():
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise DataError("panel opponent names must be nonempty strings")
        name = raw_name.strip()
        if name in names:
            raise DataError(f"duplicate normalized panel opponent: {name}")
        names.add(name)
        if not isinstance(raw_seeds, list) or not raw_seeds:
            raise DataError(f"panel seeds for {name} must be a nonempty list")
        seeds: set[str] = set()
        for raw_seed in raw_seeds:
            if isinstance(raw_seed, bool) or not isinstance(raw_seed, (int, str)):
                raise DataError("panel seeds must be integers or nonempty strings")
            seed = str(raw_seed).strip()
            if not seed or seed in seeds:
                raise DataError(f"empty/duplicate normalized seed for {name}: {seed}")
            seeds.add(seed)
            keys.update((name, seed, seat) for seat in (0, 1))
    return keys



def unambiguous_layout(document: Any) -> None:
    """Narrow the pinned legacy API instead of guessing disputed vector semantics."""
    containers = ("cells", "results", "games", "matches")
    if isinstance(document, dict):
        if sum(key in document for key in containers) > 1:
            raise DataError("use one paired-container alias; do not collapse equality aliases")
        if "baseline" in document or "candidate" in document:
            rows = [row for arm in ("baseline", "candidate")
                    for row in (document.get(arm) if isinstance(document.get(arm), list) else [])]
        else:
            rows = next((document[key] for key in containers if key in document), [])
    else:
        rows = document
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict) and any(key in row for key in ("baseline_scores", "candidate_scores")):
                raise DataError("flat *_scores is ambiguous; use nested scores or explicit own/rival")


def evaluate(document: Any, panel: Any, policy: Policy | None = None,
             *, reporter_path: Path = DEFAULT_REPORTER) -> dict[str, Any]:
    policy = Policy() if policy is None else policy
    if not isinstance(policy, Policy):
        raise DataError("policy must be a Policy instance")
    policy.validate()
    expected = panel_keys(panel)
    unambiguous_layout(document)
    reporter = load_reporter(reporter_path)
    try:
        records = reporter.load_records(document)
        distribution = reporter.analyze(records)
        # Public reporter API only: reuse its score, alias, seat, and margin
        # normalization. A singleton report exposes the normalized public cell.
        cells = [reporter.analyze([row])["delta_m"]["worst_cell"] for row in records]
    except reporter.DataError as exc:
        raise DataError(str(exc)) from exc
    actual = {(c["opponent"], c["seed"], c["seat"]) for c in cells}
    if expected != actual:
        raise DataError(
            f"panel coverage mismatch: missing={sorted(expected - actual)[:12]}; "
            f"unexpected={sorted(actual - expected)[:12]}"
        )
    ordered = sorted(cells, key=lambda c: (c["opponent"], c["seed"], c["seat"]))
    failures: list[str] = []
    opponents: dict[str, Any] = {}
    for name in sorted({key[0] for key in expected}):
        group = [c for c in ordered if c["opponent"] == name]
        seed_pairs = []
        for seed in sorted({c["seed"] for c in group}):
            pair = [c for c in group if c["seed"] == seed]
            seed_pairs.append({"seed": seed, "mean_delta_m": mean(
                [c["delta_m"] for c in pair], "seed-pair delta")})
        seat_means = {str(seat): mean([c["delta_m"] for c in group if c["seat"] == seat],
                                      "opponent-seat delta") for seat in (0, 1)}
        opponent_mean = mean([p["mean_delta_m"] for p in seed_pairs], "opponent delta")
        opponents[name] = {
            "cells": len(group), "seed_pair_count": len(seed_pairs),
            "mean_delta_m": opponent_mean, "by_seat_mean_delta_m": seat_means,
            "seed_pairs": seed_pairs,
            "new_losses": [c for c in group if c["baseline_outcome"] != "L" and c["candidate_outcome"] == "L"],
            "lost_wins": [c for c in group if c["baseline_outcome"] == "W" and c["candidate_outcome"] != "W"],
            "worst_cell": min(group, key=lambda c: c["delta_m"]),
        }
        if len(seed_pairs) < policy.min_seed_pairs:
            failures.append(f"{name}: {len(seed_pairs)} seed pairs < {policy.min_seed_pairs}")
        if opponent_mean < policy.min_opponent_delta:
            failures.append(f"{name}: mean delta {opponent_mean:.12g} < {policy.min_opponent_delta:.12g}")
        for seat, value in seat_means.items():
            if value < policy.min_opponent_seat_delta:
                failures.append(f"{name}/seat{seat}: mean delta {value:.12g} < {policy.min_opponent_seat_delta:.12g}")
    balanced = mean([group["mean_delta_m"] for group in opponents.values()], "balanced delta")
    if len(opponents) < policy.min_opponents:
        failures.append(f"{len(opponents)} opponents < {policy.min_opponents}")
    if balanced < policy.min_balanced_delta:
        failures.append(f"balanced mean delta {balanced:.12g} < {policy.min_balanced_delta:.12g}")
    outcomes = distribution["outcomes"]
    for label, maximum in (("new_losses", policy.max_new_losses), ("lost_wins", policy.max_lost_wins)):
        if len(outcomes[label]) > maximum:
            failures.append(f"{label}: {len(outcomes[label])} > {maximum}")
    mismatches = distribution["delta_m"]["supplied_mismatch_count"]
    if mismatches:
        failures.append(f"supplied delta mismatches: {mismatches}")
    return {
        "schema_version": 1,
        "verdict": "FAIL" if failures else "PASS",
        "scope": "EMPIRICAL_SCREEN_ONLY_NOT_PROMOTION_AUTHORITY",
        "policy": asdict(policy), "failures": failures,
        "coverage": {"expected_cells": len(expected), "actual_cells": len(actual),
                     "opponents": len(opponents), "both_seats_every_seed": True},
        "pooled_mean_delta_m": distribution["delta_m"]["mean"],
        "opponent_balanced_mean_delta_m": balanced,
        "worst_opponent_mean_delta_m": min(g["mean_delta_m"] for g in opponents.values()),
        "by_opponent": opponents, "distribution": distribution,
        "provenance": {"reporter_git_blob": REPORTER_BLOB},
        "limitations": [
            "Coverage is relative to the supplied panel; the tool cannot prove it was preregistered or representative.",
            "File hashes bind submitted evidence, not execution, source artifact identity, or opponent authenticity.",
            "Empirical thresholds are not confidence bounds, causal attribution, or future-game guarantees.",
            "Zero-delta/no-activation evidence can pass non-regression defaults; this does not prove an improvement.",
        ],
    }


def strict_json(data: bytes) -> Any:
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise DataError(f"duplicate JSON object key: {key}")
            out[key] = value
        return out

    def constant(value):
        raise DataError(f"nonfinite JSON constant: {value}")

    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise DataError(f"invalid JSON: {exc}") from exc


def check_output(output: Path, inputs: list[Path]) -> None:
    for path in inputs:
        if output.resolve() == path.resolve() or (output.exists() and path.exists() and os.path.samefile(output, path)):
            raise DataError("output must not alias an input or the pinned reporter")


def write_atomic(path: Path, rendered: str) -> None:
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}.", delete=False) as stream:
            temp = Path(stream.name)
            stream.write(rendered)
        os.replace(temp, path)
    finally:
        if temp is not None and temp.exists():
            temp.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--reporter", type=Path, default=DEFAULT_REPORTER)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-seed-pairs", type=int, default=8)
    parser.add_argument("--min-opponents", type=int, default=2)
    parser.add_argument("--min-balanced-delta", type=float, default=0.0)
    parser.add_argument("--min-opponent-delta", type=float, default=0.0)
    parser.add_argument("--min-opponent-seat-delta", type=float, default=0.0)
    parser.add_argument("--max-new-losses", type=int, default=0)
    parser.add_argument("--max-lost-wins", type=int, default=0)
    args = parser.parse_args(argv)
    try:
        if args.output:
            check_output(args.output, [args.evidence, args.panel, args.reporter])
        evidence_bytes, panel_bytes = args.evidence.read_bytes(), args.panel.read_bytes()
        policy = Policy(**{name: getattr(args, name) for name in Policy.__dataclass_fields__})
        report = evaluate(strict_json(evidence_bytes), strict_json(panel_bytes), policy,
                          reporter_path=args.reporter)
        report["provenance"].update(
            evidence_sha256=hashlib.sha256(evidence_bytes).hexdigest(),
            panel_sha256=hashlib.sha256(panel_bytes).hexdigest(),
        )
        rendered = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
        if args.output:
            write_atomic(args.output, rendered)
    except (DataError, OSError) as exc:
        print(f"DATA ERROR: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write(rendered)
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
