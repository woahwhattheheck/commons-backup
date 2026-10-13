#!/usr/bin/env python3
"""Exact bounded checker for finite Erdős 688 covering instances.

For fixed n>1, decide each suffix of eligible primes. Search uses only exact
integer bit masks. This is bounded evidence, not an asymptotic proof.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from functools import lru_cache
from itertools import product


def primes_upto(n: int) -> tuple[int, ...]:
    out = []
    for x in range(2, n + 1):
        d = 2
        while d * d <= x and x % d:
            d += 1
        if d * d > x:
            out.append(x)
    return tuple(out)


def residue_masks(n: int, p: int) -> tuple[tuple[int, int], ...]:
    return tuple(
        (r, sum(1 << (x - 1) for x in range(1, n + 1) if x % p == r))
        for r in range(p)
        if any(x % p == r for x in range(1, n + 1))
    )


def capacity_upper_bound(n: int, primes: tuple[int, ...]) -> int:
    return sum((n + p - 1) // p for p in primes)


def can_cover(n: int, primes: tuple[int, ...]) -> tuple[bool, int]:
    primes = tuple(sorted(primes))
    if capacity_upper_bound(n, primes) < n:
        return False, 0
    full = (1 << n) - 1
    masks = {p: residue_masks(n, p) for p in primes}
    nodes = 0

    @lru_cache(maxsize=None)
    def dfs(covered: int, remaining: tuple[int, ...]) -> bool:
        nonlocal nodes
        nodes += 1
        if covered == full:
            return True
        uncovered = full ^ covered
        need = uncovered.bit_count()
        gains = [
            (max((mask & uncovered).bit_count() for _, mask in masks[p]), p)
            for p in remaining
        ]
        optimistic = sum(g for g, _ in gains)
        if optimistic < need:
            return False
        mandatory = [(g, p) for g, p in gains if optimistic - g < need]
        if mandatory:
            _, p = max(mandatory)
            rest = tuple(q for q in remaining if q != p)
            options = sorted(
                (
                    ((mask & uncovered).bit_count(), mask)
                    for _, mask in masks[p]
                    if mask & uncovered
                ),
                reverse=True,
            )
            return any(dfs(covered | mask, rest) for _, mask in options)
        bit = uncovered & -uncovered
        x = bit.bit_length()
        branches = []
        for p in remaining:
            r = x % p
            mask = next(mask for rr, mask in masks[p] if rr == r)
            branches.append(((mask & uncovered).bit_count(), p, mask))
        branches.sort(reverse=True)
        for _, p, mask in branches:
            rest = tuple(q for q in remaining if q != p)
            if dfs(covered | mask, rest):
                return True
        return False

    return dfs(0, primes), nodes


def critical_prime(n: int) -> tuple[int | None, int]:
    if n <= 1:
        raise ValueError("require n > 1")
    ps = primes_upto(n)
    total_nodes = 0
    for i in range(len(ps) - 1, -1, -1):
        ok, nodes = can_cover(n, ps[i:])
        total_nodes += nodes
        if ok:
            return ps[i], total_nodes
    return None, total_nodes


def brute_force_can_cover(n: int, primes: tuple[int, ...]) -> bool:
    primes = tuple(sorted(primes))
    for residues in product(*(range(p) for p in primes)):
        if all(
            any(x % p == r for p, r in zip(primes, residues))
            for x in range(1, n + 1)
        ):
            return True
    return False


def self_test() -> None:
    for n in range(2, 13):
        ps = primes_upto(n)
        for i in range(len(ps)):
            got = can_cover(n, ps[i:])[0]
            want = brute_force_can_cover(n, ps[i:])
            if got != want:
                raise AssertionError((n, ps[i:], got, want))
    if critical_prime(66)[0] != 2:
        raise AssertionError("n=66 regression")
    if critical_prime(67)[0] != 3:
        raise AssertionError("n=67 regression")


def build_receipt(lo: int, hi: int) -> dict:
    rows = []
    for n in range(lo, hi + 1):
        q, nodes = critical_prime(n)
        rows.append({"n": n, "critical_prime": q, "search_nodes": nodes})
    math_rows = [{"n": r["n"], "critical_prime": r["critical_prime"]} for r in rows]
    digest = hashlib.sha256(
        json.dumps(math_rows, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "algorithm_version": 1,
        "scope": {
            "lo": lo,
            "hi": hi,
            "claim": "bounded exact finite evidence only; not an asymptotic proof",
        },
        "mathematical_rows_sha256": digest,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lo", type=int, default=2)
    parser.add_argument("--hi", type=int, default=70)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("SELF_TEST_PASS")
        return 0
    if args.lo < 2 or args.hi < args.lo:
        raise SystemExit("require 2 <= lo <= hi")
    print(json.dumps(build_receipt(args.lo, args.hi), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
