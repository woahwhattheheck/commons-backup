#!/usr/bin/env python3
"""Exact checks for the 4-adic normalization of the nonnegative three-square count.

This is proof support, not a proof assistant. The mathematical identity is elementary:
if 4 divides x^2+y^2+z^2 then x,y,z are all even, so coordinatewise halving is
an exact bijection between representations of 4n and n.
"""

from __future__ import annotations

import argparse
from math import isqrt


def r3_nonnegative(n: int) -> int:
    """Count ordered triples (x,y,z) in N_0^3 with x^2+y^2+z^2=n."""
    if type(n) is not int or n < 0:
        raise ValueError("n must be a nonnegative integer")
    total = 0
    limit = isqrt(n)
    for x in range(limit + 1):
        rem_x = n - x * x
        for y in range(isqrt(rem_x) + 1):
            rem = rem_x - y * y
            z = isqrt(rem)
            if z * z == rem:
                total += 1
    return total


def four_free_core(n: int) -> tuple[int, int]:
    """Return (core,k) with n=4^k*core and 4 not dividing core, for n>0."""
    if type(n) is not int or n <= 0:
        raise ValueError("n must be a positive integer")
    k = 0
    while n % 4 == 0:
        n //= 4
        k += 1
    return n, k


def assert_halving_lemma(x: int, y: int, z: int) -> tuple[int, int, int]:
    """Check the parity lemma and return the halved triple when the sum is 0 mod 4."""
    for value in (x, y, z):
        if type(value) is not int or value < 0:
            raise ValueError("coordinates must be nonnegative integers")
    n = x * x + y * y + z * z
    if n % 4:
        raise ValueError("sum is not divisible by 4")
    if (x | y | z) & 1:
        raise AssertionError("mod-4 parity lemma violated")
    return x // 2, y // 2, z // 2


def verify_range(limit: int) -> dict[str, int]:
    if type(limit) is not int or limit < 1:
        raise ValueError("limit must be a positive integer")
    checked = 0
    for n in range(1, limit + 1):
        left = r3_nonnegative(4 * n)
        right = r3_nonnegative(n)
        if left != right:
            raise AssertionError(f"r3(4*{n})={left} != r3({n})={right}")
        checked += 1
    return {"checked_n": checked, "max_n": limit}


def verify_powers(max_k: int) -> dict[str, int]:
    if type(max_k) is not int or max_k < 0:
        raise ValueError("max_k must be a nonnegative integer")
    for k in range(max_k + 1):
        n = 4**k
        count = r3_nonnegative(n)
        if count != 3:
            raise AssertionError(f"r3(4^{k})={count}, expected 3")
        core, exponent = four_free_core(n)
        if (core, exponent) != (1, k):
            raise AssertionError("four-free decomposition mismatch")
    return {"checked_powers": max_k + 1, "max_k": max_k}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=256)
    parser.add_argument("--max-k", type=int, default=8)
    args = parser.parse_args(argv)
    range_result = verify_range(args.limit)
    power_result = verify_powers(args.max_k)
    print(
        "VERIFIED_R3_4ADIC_NORMALIZATION "
        f"checked_n={range_result['checked_n']} "
        f"max_k={power_result['max_k']} "
        "identity=r3(4n)=r3(n) powers=r3(4^k)=3"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
