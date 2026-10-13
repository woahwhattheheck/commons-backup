#!/usr/bin/env python3
"""Exact finite checks for the A308661 / A308734 ternary-5 research lane.

This module certifies only finite shortcut falsifiers and arithmetic support.
It does not claim to prove the infinite conjecture.
"""
from __future__ import annotations

from collections.abc import Iterable
from math import isqrt


def factorint(n: int) -> dict[int, int]:
    if n < 1:
        raise ValueError("factorint expects a positive integer")
    out: dict[int, int] = {}
    while n % 2 == 0:
        out[2] = out.get(2, 0) + 1
        n //= 2
    p = 3
    while p * p <= n:
        while n % p == 0:
            out[p] = out.get(p, 0) + 1
            n //= p
        p += 2
    if n > 1:
        out[n] = out.get(n, 0) + 1
    return out


def bad_support(n: int) -> tuple[int, ...]:
    """Odd-valuation p == 3 (mod 4) primes obstructing two-square status."""
    if n < 1:
        raise ValueError("bad_support expects a positive integer")
    return tuple(
        p
        for p, exponent in factorint(n).items()
        if p % 4 == 3 and exponent % 2 == 1
    )


def is_sum_of_two_squares(n: int) -> bool:
    if n < 0:
        return False
    if n == 0:
        return True
    return not bad_support(n)


def two_square_representation(n: int) -> tuple[int, int] | None:
    if n < 0:
        return None
    for x in range(isqrt(n) + 1):
        y2 = n - x * x
        y = isqrt(y2)
        if y * y == y2:
            return x, y
    return None


def residual(N: int, a: int, b: int) -> int:
    if a < 1 or b < 0:
        raise ValueError("requires a >= 1, b >= 0")
    return N - (4**a) * (25**b)


def _normalize_b_values(b_values: Iterable[int]) -> tuple[int, ...]:
    values = tuple(b_values)
    if not values:
        raise ValueError("b-menu must not be empty")
    if any(
        not isinstance(value, int) or isinstance(value, bool) or value < 0
        for value in values
    ):
        raise ValueError("b-menu values must be nonnegative integers")
    return tuple(sorted(set(values)))


def bounded_b_menu_falsifier(
    N: int, b_values: Iterable[int]
) -> list[tuple[int, int, int, tuple[int, ...]]]:
    """Return every legal residual for a menu, requiring each one to fail."""
    if N <= 0 or N % 12 != 5:
        raise ValueError("N must be positive and 5 mod 12")
    menu = _normalize_b_values(b_values)
    rows: list[tuple[int, int, int, tuple[int, ...]]] = []
    for b in menu:
        pow25 = 1
        for _ in range(b):
            pow25 *= 25
            if 4 * pow25 >= N:
                break
        else:
            a = 1
            pow4 = 4
            while pow4 * pow25 < N:
                m = N - pow4 * pow25
                support = bad_support(m)
                if not support:
                    raise AssertionError(
                        f"{N} is not a falsifier for b-menu {menu}: "
                        f"a={a}, b={b}, residual={m}"
                    )
                rows.append((a, b, m, support))
                a += 1
                pow4 *= 4
    return rows


def bounded_b_falsifier(
    N: int, max_b: int
) -> list[tuple[int, int, int, tuple[int, ...]]]:
    """Return every positive residual at b <= max_b, requiring all to fail."""
    if max_b < 0:
        raise ValueError("max_b must be nonnegative")
    rows = bounded_b_menu_falsifier(N, range(max_b + 1))
    if not rows:
        raise AssertionError("bounded menu produced no legal residual")
    return rows


def fixed_menu_size_at_most_two_falsifier(
    b_values: Iterable[int],
) -> tuple[int, list[tuple[int, int, int, tuple[int, ...]]], tuple[int, int, int, int]]:
    """Mechanize the complete case split for every fixed menu of size <= 2."""
    menu = _normalize_b_values(b_values)
    if len(menu) > 2:
        raise ValueError("menu must have size at most two")

    if 0 not in menu:
        N, witness = 5, (0, 1, 1, 0)
    elif menu == (0,):
        N, witness = 12_233, (18, 97, 1, 2)
    elif menu == (0, 1):
        N, witness = 1_595_477, (831, 946, 2, 2)
    elif menu == (0, 2):
        N, witness = 1_750_109, (403, 1260, 1, 1)
    else:
        N, witness = 12_233, (18, 97, 1, 2)

    rows = bounded_b_menu_falsifier(N, menu)
    x, y, a, b = witness
    if b in menu or x * x + y * y + (2**a * 5**b) ** 2 != N:
        raise AssertionError(("invalid outside-menu rescue", menu, N, witness))
    return N, rows, witness


def theorem_support_checks() -> None:
    # A shared bad prime in fixed-a residuals b distance 1 or 2 would divide
    # 25^d-1. Apart from 3, those constants have no 3 mod 4 prime.
    for d in (1, 2):
        support = tuple(p for p in factorint(25**d - 1) if p % 4 == 3)
        if support != (3,):
            raise AssertionError((d, support))

    # The analogous fixed-b / consecutive-a constants are 4^d-1.
    for d in (1, 2):
        support = tuple(p for p in factorint(4**d - 1) if p % 4 == 3)
        if support != (3,):
            raise AssertionError((d, support))

    six = (7, 11, 19, 23, 31, 43)
    product = 1
    for p in six:
        product *= p
    if product != 44_854_117:
        raise AssertionError(product)


def finite_regression_checks() -> None:
    # "b = 0 always suffices" is false.
    rows = bounded_b_falsifier(12_233, 0)
    if len(rows) != 6:
        raise AssertionError(len(rows))
    if two_square_representation(residual(12_233, 1, 2)) != (18, 97):
        raise AssertionError("expected higher-b witness missing")

    # Even allowing b in {0,1} does not suffice uniformly.
    rows = bounded_b_falsifier(1_595_477, 1)
    if len(rows) != 17:
        raise AssertionError(len(rows))
    rep = two_square_representation(residual(1_595_477, 2, 2))
    if rep != (831, 946):
        raise AssertionError(rep)

    # The missing nonconsecutive menu {0,2} is also exactly falsified.
    rows = bounded_b_menu_falsifier(1_750_109, (0, 2))
    if len(rows) != 15:
        raise AssertionError(len(rows))
    rep = two_square_representation(residual(1_750_109, 1, 1))
    if rep != (403, 1260):
        raise AssertionError(rep)

    # Exercise every branch of the quantified size-at-most-two case split,
    # including a huge exponent that must be rejected without constructing 25^b.
    expected = (
        ((1,), 5, 0),
        ((1, 2), 5, 0),
        ((0,), 12_233, 6),
        ((0, 1), 1_595_477, 17),
        ((0, 2), 1_750_109, 15),
        ((0, 3), 12_233, 6),
        ((0, 100_000), 12_233, 6),
    )
    for menu, target, row_count in expected:
        N, rows, _ = fixed_menu_size_at_most_two_falsifier(menu)
        if (N, len(rows)) != (target, row_count):
            raise AssertionError((menu, N, len(rows)))


def sampled_disjointness_checks(limit: int = 100_000) -> None:
    """Finite regression for the exact symbolic disjointness lemmas."""
    for N in range(5, limit + 1, 12):
        # fixed a, three consecutive b
        a = 1
        while 4**a < N:
            b = 0
            while True:
                ms = [residual(N, a, b + j) for j in range(3)]
                if ms[-1] <= 0:
                    break
                supports = [set(bad_support(m)) for m in ms]
                if any(
                    supports[i] & supports[j]
                    for i in range(3)
                    for j in range(i + 1, 3)
                ):
                    raise AssertionError(("b", N, a, b, supports))
                b += 1
            a += 1

        # fixed b, three consecutive a
        b = 0
        while 25**b < N:
            a = 1
            while True:
                ms = [residual(N, a + j, b) for j in range(3)]
                if ms[-1] <= 0:
                    break
                supports = [set(bad_support(m)) for m in ms]
                if any(
                    supports[i] & supports[j]
                    for i in range(3)
                    for j in range(i + 1, 3)
                ):
                    raise AssertionError(("a", N, a, b, supports))
                a += 1
            b += 1


def main() -> int:
    theorem_support_checks()
    finite_regression_checks()
    sampled_disjointness_checks()
    print("PASS: exact finite checks; no infinite proof claim")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
