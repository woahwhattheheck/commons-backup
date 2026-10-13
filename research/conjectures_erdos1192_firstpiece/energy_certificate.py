#!/usr/bin/env python3
"""Exact finite certificates for a structural necessary condition in Erdős 1192.

For B = A ∩ [0,m] and ordered r-term representation counts c_B(n),

    (r*m + 1) * sum_n c_B(n)^2 >= |B|^(2*r).

The identity sum_n c_B(n) = |B|^r plus Cauchy-Schwarz proves this.
Since c_B(n) <= f_r(A,n), the same lower bound applies to the target's
truncated energy through r*m.  No floating point or third-party packages.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, Sequence


@dataclass(frozen=True)
class CaseRecord:
    m: int
    r: int
    mask: int
    size: int
    total_representations: int
    energy: int
    lhs_scaled: int
    rhs_power: int
    max_sum: int


def normalize_set(values: Iterable[int]) -> tuple[int, ...]:
    out = tuple(sorted(set(values)))
    if any((not isinstance(x, int)) or isinstance(x, bool) or x < 0 for x in out):
        raise ValueError("A must contain nonnegative integers")
    return out


def representation_counts(values: Iterable[int], r: int) -> tuple[int, ...]:
    """Ordered r-term representation counts, indexed by the represented sum."""
    if not isinstance(r, int) or isinstance(r, bool) or r < 1:
        raise ValueError("r must be a positive integer")
    A = normalize_set(values)
    if not A:
        return (0,)
    counts = [0] * (r * A[-1] + 1)
    for tup in itertools.product(A, repeat=r):
        counts[sum(tup)] += 1
    return tuple(counts)


def finite_energy(values: Iterable[int], r: int) -> int:
    counts = representation_counts(values, r)
    return sum(c * c for c in counts)


def check_finite_energy_lemma(values: Iterable[int], r: int, m: int) -> CaseRecord:
    """Check the exact finite Cauchy lower bound for B=A∩[0,m]."""
    if not isinstance(m, int) or isinstance(m, bool) or m < 0:
        raise ValueError("m must be a nonnegative integer")
    A = normalize_set(values)
    B = tuple(a for a in A if a <= m)
    counts = representation_counts(B, r)
    total = sum(counts)
    expected_total = len(B) ** r
    if total != expected_total:
        raise AssertionError((total, expected_total))
    max_sum = max((i for i, c in enumerate(counts) if c), default=0)
    if B and max_sum > r * m:
        raise AssertionError((max_sum, r * m))
    energy = sum(c * c for c in counts)
    lhs = (r * m + 1) * energy
    rhs = len(B) ** (2 * r)
    if lhs < rhs:
        raise AssertionError((A, r, m, lhs, rhs))
    mask = sum(1 << a for a in B)
    return CaseRecord(
        m=m,
        r=r,
        mask=mask,
        size=len(B),
        total_representations=total,
        energy=energy,
        lhs_scaled=lhs,
        rhs_power=rhs,
        max_sum=max_sum,
    )


def check_coverage_lower_bound(values: Iterable[int], r: int, start: int, stop: int) -> bool:
    """Finite basis analogue: covering [start,stop] forces |A∩[0,stop]|^r >= interval size."""
    if start < 0 or stop < start:
        raise ValueError("require 0 <= start <= stop")
    A = normalize_set(values)
    B = tuple(a for a in A if a <= stop)
    counts = representation_counts(B, r)
    covered = all(n < len(counts) and counts[n] > 0 for n in range(start, stop + 1))
    if not covered:
        return False
    return len(B) ** r >= stop - start + 1


def exhaustive_receipt(max_m: int = 8, min_r: int = 2, max_r: int = 5) -> dict:
    if max_m < 0 or min_r < 1 or max_r < min_r:
        raise ValueError("invalid bounds")
    hasher = hashlib.sha256()
    case_count = 0
    equality_count = 0
    minimum_slack = None
    maximum_slack = 0
    for m in range(max_m + 1):
        universe = tuple(range(m + 1))
        for mask in range(1 << (m + 1)):
            A = tuple(a for a in universe if mask & (1 << a))
            for r in range(min_r, max_r + 1):
                rec = check_finite_energy_lemma(A, r, m)
                raw = json.dumps(asdict(rec), sort_keys=True, separators=(",", ":")).encode()
                hasher.update(raw + b"\n")
                slack = rec.lhs_scaled - rec.rhs_power
                if slack == 0:
                    equality_count += 1
                minimum_slack = slack if minimum_slack is None else min(minimum_slack, slack)
                maximum_slack = max(maximum_slack, slack)
                case_count += 1
    return {
        "schema": "erdos1192-finite-energy-v1",
        "bounds": {"max_m": max_m, "min_r": min_r, "max_r": max_r},
        "case_count": case_count,
        "equality_count": equality_count,
        "minimum_slack": minimum_slack,
        "maximum_slack": maximum_slack,
        "ordered_case_stream_sha256": hasher.hexdigest(),
        "claim": "finite exact regression evidence for the Cauchy energy lower-bound lemma only",
        "evidence_ceiling": "does not prove the asymptotic Erdős 1192 conjecture or constitute sponsor acceptance",
    }


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--max-m", type=int, default=8)
    p.add_argument("--min-r", type=int, default=2)
    p.add_argument("--max-r", type=int, default=5)
    p.add_argument("--write-receipt", type=Path)
    args = p.parse_args(argv)
    receipt = exhaustive_receipt(args.max_m, args.min_r, args.max_r)
    encoded = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.write_receipt:
        args.write_receipt.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
