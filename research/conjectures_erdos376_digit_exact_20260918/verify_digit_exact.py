#!/usr/bin/env python3
"""Independent arithmetic checks for the Erdős #376 digit characterization.

This is deliberately stdlib-only.  It does not prove the Lean theorem; it tests the
mathematics behind the candidate reverse lemma in two independent ways:

1. generic base-p digit smallness <-> every doubled prefix is carry-free;
2. for n <= ARITH_BOUND, the simultaneous 3/5/7 digit predicate <->
   gcd(binomial(2*n,n), 105) = 1 using Python's exact integer binomial.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from typing import Iterable

PRIMES = (3, 5, 7)
ARITH_BOUND = 4096
GENERIC_BOUND = 200_000
WITNESS_BOUND = 1_000_000


def digit_good_base(n: int, p: int) -> bool:
    if n < 0:
        raise ValueError("n must be nonnegative")
    if p < 2:
        raise ValueError("base must be at least 2")
    while n:
        digit = n % p
        if 2 * digit >= p:
            return False
        n //= p
    return True


def digit_good_357(n: int) -> bool:
    return all(digit_good_base(n, p) for p in PRIMES)


def prefix_no_carry(n: int, p: int) -> bool:
    """Check 2*(n mod p^i) < p^i for all relevant positive i.

    Once p^i > 2*n, the residue is n and all later inequalities follow.
    """
    if n < 0:
        raise ValueError("n must be nonnegative")
    if p < 2:
        raise ValueError("base must be at least 2")
    q = p
    while q <= 2 * n:
        if 2 * (n % q) >= q:
            return False
        q *= p
    return 2 * (n % q) < q


def central_binom_coprime_105(n: int) -> bool:
    if n < 0:
        raise ValueError("n must be nonnegative")
    return math.gcd(math.comb(2 * n, n), 105) == 1


def witness_values(bound: int) -> list[int]:
    return [n for n in range(bound + 1) if digit_good_357(n)]


def _lines_digest(values: Iterable[int]) -> str:
    return hashlib.sha256("\n".join(map(str, values)).encode("ascii")).hexdigest()


def build_report() -> dict[str, object]:
    generic_cases = 0
    for p in PRIMES:
        for n in range(GENERIC_BOUND + 1):
            digit = digit_good_base(n, p)
            prefix = prefix_no_carry(n, p)
            if digit != prefix:
                raise AssertionError(
                    f"generic equivalence failed: p={p} n={n} digit={digit} prefix={prefix}"
                )
            generic_cases += 1

    arithmetic_cases = 0
    for n in range(ARITH_BOUND + 1):
        digit = digit_good_357(n)
        exact = central_binom_coprime_105(n)
        if digit != exact:
            raise AssertionError(
                f"exact arithmetic equivalence failed: n={n} digit={digit} exact={exact}"
            )
        arithmetic_cases += 1

    witnesses = witness_values(WITNESS_BOUND)
    return {
        "status": "PASS",
        "claim_checked": (
            "digitwise 3/5/7 smallness is equivalent to carry-free doubling; "
            "bounded exact central-binomial arithmetic agrees"
        ),
        "generic_bound_inclusive": GENERIC_BOUND,
        "generic_cases": generic_cases,
        "arithmetic_bound_inclusive": ARITH_BOUND,
        "arithmetic_cases": arithmetic_cases,
        "witness_bound_inclusive": WITNESS_BOUND,
        "witness_count": len(witnesses),
        "first_witnesses": witnesses[:20],
        "last_witnesses": witnesses[-20:],
        "witness_list_sha256": _lines_digest(witnesses),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()
    report = build_report()
    print(json.dumps(report, sort_keys=True, separators=(",", ":") if args.compact else None,
                     indent=None if args.compact else 2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
