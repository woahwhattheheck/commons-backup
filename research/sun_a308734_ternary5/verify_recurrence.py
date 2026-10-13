#!/usr/bin/env python3
"""Finite regression for the exact bad-prime recurrence propositions.

The proofs live in RECURRENCE.md. These checks exercise their arithmetic
consequences on bounded primes/residuals and do not replace the proofs.
"""
from __future__ import annotations

from math import gcd

from verify import bad_support, factorint, residual


def multiplicative_order(base: int, p: int) -> int:
    if gcd(base, p) != 1:
        raise ValueError("base and modulus must be coprime")
    x = 1
    for order in range(1, p):
        x = (x * base) % p
        if x == 1:
            return order
    raise AssertionError("prime-modulus order not found")


def is_power_of_two(n: int) -> bool:
    return n > 0 and n & (n - 1) == 0


def prime_order_checks(limit: int = 10_000) -> None:
    # Trial primality is sufficient at this bounded regression scale.
    for p in range(7, limit + 1, 4):
        factors = factorint(p)
        if factors != {p: 1}:
            continue
        for base in (4, 25):
            order = multiplicative_order(base, p)
            if order < 3 or order % 2 != 1:
                raise AssertionError((p, base, order))


def exact_difference_constants() -> None:
    # Dyadic separations cannot expose a bad p other than 3, which residuals exclude.
    for d in (1, 2, 4, 8):
        for base in (4, 25):
            bad = tuple(
                p for p in factorint(base**d - 1)
                if p % 4 == 3 and p != 3
            )
            if bad:
                raise AssertionError((base, d, bad))

    b3 = tuple(
        p for p in factorint(25**3 - 1)
        if p % 4 == 3 and p != 3
    )
    a3 = tuple(
        p for p in factorint(4**3 - 1)
        if p % 4 == 3 and p != 3
    )
    if b3 != (7, 31):
        raise AssertionError(b3)
    if a3 != (7,):
        raise AssertionError(a3)


def sampled_recurrence_checks(limit: int = 30_000) -> None:
    for N in range(5, limit + 1, 12):
        # Fixed a: any repeated bad prime follows its odd order in 25.
        a = 1
        while 4**a < N:
            rows: list[tuple[int, set[int]]] = []
            b = 0
            while True:
                m = residual(N, a, b)
                if m <= 0:
                    break
                rows.append((b, set(bad_support(m))))
                b += 1
            for i, (b0, s0) in enumerate(rows):
                for b1, s1 in rows[i + 1:]:
                    gap = b1 - b0
                    for p in s0 & s1:
                        order = multiplicative_order(25, p)
                        if gap % order != 0 or order < 3 or order % 2 != 1:
                            raise AssertionError(("b-order", N, a, b0, b1, p, order))
                        if is_power_of_two(gap):
                            raise AssertionError(("b-dyadic", N, a, b0, b1, p))
            a += 1

        # Fixed b: same statement for order of 4.
        b = 0
        while 25**b < N:
            rows = []
            a = 1
            while True:
                m = residual(N, a, b)
                if m <= 0:
                    break
                rows.append((a, set(bad_support(m))))
                a += 1
            for i, (a0, s0) in enumerate(rows):
                for a1, s1 in rows[i + 1:]:
                    gap = a1 - a0
                    for p in s0 & s1:
                        order = multiplicative_order(4, p)
                        if gap % order != 0 or order < 3 or order % 2 != 1:
                            raise AssertionError(("a-order", N, b, a0, a1, p, order))
                        if is_power_of_two(gap):
                            raise AssertionError(("a-dyadic", N, b, a0, a1, p))
            b += 1


def main() -> int:
    prime_order_checks()
    exact_difference_constants()
    sampled_recurrence_checks()
    print("PASS: recurrence regressions; proofs remain in RECURRENCE.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
