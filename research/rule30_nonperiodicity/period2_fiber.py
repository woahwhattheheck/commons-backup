#!/usr/bin/env python3
"""Exact bounded fiber tools for Rule 30's period-two center-trace frontier.

The infinite prize problem remains open. This module proves bounded statements by
using Rule 30's left permutivity to complete only the left prefix that can affect
the requested center-trace prefix. For a support radius ``w`` and fixed initial
center phase, one candidate exists for each positive right-half word of length
``w``; no other row in [-w,w] can realize the first ``w+1`` alternating symbols.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path


def rule30(left: int, center: int, right: int) -> int:
    """Rule 30 in the left-permutive form a XOR (b OR c)."""
    return left ^ (center | right)


def _step(bits: int) -> int:
    """One Rule 30 step for a nonnegative integer bitset.

    Bit k represents one spatial coordinate. Callers reserve enough low-order
    zero padding that no live cell can reach bit -1 during the finite horizon.
    """
    return (bits << 1) ^ (bits | (bits >> 1))


def _center_after(bits: int, origin: int, steps: int) -> int:
    row = bits
    for _ in range(steps):
        row = _step(row)
    return (row >> origin) & 1


def alternating_bit(phase: int, time: int) -> int:
    if phase not in (0, 1):
        raise ValueError("phase must be 0 or 1")
    return phase ^ (time & 1)


def complete_candidate(radius: int, phase: int, right_word: int, *, horizon_limit: int) -> tuple[int, int, int]:
    """Return the unique [-radius,radius] candidate matching t=0..radius.

    ``right_word`` packs x_1..x_radius from least significant to most
    significant bit. The returned tuple is (row_bits, origin, left_word), where
    left_word packs x_-1..x_-radius in the same depth-first convention.

    Existence and uniqueness are constructive: at time n, x_-n enters the
    center for the first time and left permutivity makes toggling x_-n toggle
    that center bit. Therefore exactly one choice matches the prescribed trace.
    """
    if radius < 0:
        raise ValueError("radius must be nonnegative")
    if phase not in (0, 1):
        raise ValueError("phase must be 0 or 1")
    if right_word < 0 or right_word >= (1 << radius):
        raise ValueError("right_word does not fit radius")
    if horizon_limit < radius:
        raise ValueError("horizon_limit must be at least radius")

    # The leftmost live cell can move left by one per step. Keeping the origin
    # this far above bit zero makes integer right shifts exact through the
    # requested horizon rather than silently imposing a finite boundary.
    origin = horizon_limit + radius + 4
    row = phase << origin
    for depth in range(1, radius + 1):
        if (right_word >> (depth - 1)) & 1:
            row |= 1 << (origin + depth)

    left_word = 0
    for depth in range(1, radius + 1):
        current = _center_after(row, origin, depth)
        required = current ^ alternating_bit(phase, depth)
        if required:
            row |= 1 << (origin - depth)
            left_word |= 1 << (depth - 1)
        assert _center_after(row, origin, depth) == alternating_bit(phase, depth)
    return row, origin, left_word


def alternating_horizon(row: int, origin: int, phase: int, *, limit: int) -> int:
    """Last time index matching phase,1-phase,... before first discrepancy."""
    current = row
    for time in range(limit + 1):
        if ((current >> origin) & 1) != alternating_bit(phase, time):
            return time - 1
        current = _step(current)
    raise RuntimeError(f"candidate did not escape within limit={limit}")


@dataclass(frozen=True)
class PhaseResult:
    phase: int
    horizon: int
    count: int
    witness_right_lsb_first: str
    witness_left_lsb_first: str


@dataclass(frozen=True)
class RadiusResult:
    radius: int
    phase0: PhaseResult
    phase1: PhaseResult


def enumerate_phase(radius: int, phase: int, *, horizon_limit: int | None = None) -> PhaseResult:
    """Exhaust every radius-bounded candidate for one alternating phase."""
    if radius < 1:
        raise ValueError("radius must be at least 1")
    limit = horizon_limit if horizon_limit is not None else 8 * radius + 32
    best_horizon = -1
    count = 0
    best_right = 0
    best_left = 0
    for right_word in range(1 << radius):
        row, origin, left_word = complete_candidate(radius, phase, right_word, horizon_limit=limit)
        horizon = alternating_horizon(row, origin, phase, limit=limit)
        if horizon > best_horizon:
            best_horizon = horizon
            count = 1
            best_right = right_word
            best_left = left_word
        elif horizon == best_horizon:
            count += 1
    fmt = f"0{radius}b"
    return PhaseResult(
        phase=phase,
        horizon=best_horizon,
        count=count,
        witness_right_lsb_first=format(best_right, fmt)[::-1],
        witness_left_lsb_first=format(best_left, fmt)[::-1],
    )


def enumerate_radius(radius: int, *, horizon_limit: int | None = None) -> RadiusResult:
    return RadiusResult(
        radius=radius,
        phase0=enumerate_phase(radius, 0, horizon_limit=horizon_limit),
        phase1=enumerate_phase(radius, 1, horizon_limit=horizon_limit),
    )


def build_receipt(max_radius: int) -> dict[str, object]:
    rows = [asdict(enumerate_radius(radius)) for radius in range(1, max_radius + 1)]
    return {
        "schema": "rule30-period2-bounded-v1",
        "claim": (
            "For every listed radius w and both alternating phases, every finite "
            "configuration supported in [-w,w] leaves the alternating center trace "
            "no later than the recorded horizon. This is a bounded theorem only."
        ),
        "search_reduction": "2^(w+1) exact phase/right-half candidates via triangular uniqueness",
        "prize_theorem": False,
        "period_two_excluded_for_all_finite_support": False,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-radius", type=int, default=8)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    receipt = build_receipt(args.max_radius)
    text = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
