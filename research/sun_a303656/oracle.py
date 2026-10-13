"""Exact 64-bit arithmetic oracle for OEIS A303656.

The conjecture asks whether every n > 1 has

    n = a^2 + b^2 + 3^c + 5^d

with nonnegative integers a, b, c, d.  This module is deliberately an oracle,
not a proof: it constructs and verifies witnesses when it finds them.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from math import gcd, isqrt
from typing import Iterable

_U64_LIMIT = 1 << 64
_MR_BASES_U64 = (2, 325, 9375, 28178, 450775, 9780504, 1795265022)
_SMALL_PRIMES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)


@dataclass(frozen=True, slots=True)
class A303656Witness:
    a: int
    b: int
    c: int
    d: int

    def value(self) -> int:
        return self.a * self.a + self.b * self.b + 3**self.c + 5**self.d

    def verify(self, n: int) -> None:
        if min(self.a, self.b, self.c, self.d) < 0:
            raise ValueError("witness entries must be nonnegative")
        if self.value() != n:
            raise ValueError("witness does not reconstruct n exactly")


def _require_u64(n: int) -> None:
    if not isinstance(n, int) or not 0 <= n < _U64_LIMIT:
        raise ValueError("exact factor oracle supports 0 <= n < 2^64")


def is_prime_u64(n: int) -> bool:
    """Deterministic Miller-Rabin primality test for unsigned 64-bit integers."""
    _require_u64(n)
    if n < 2:
        return False
    for p in _SMALL_PRIMES:
        if n == p:
            return True
        if n % p == 0:
            return False

    d = n - 1
    s = 0
    while d & 1 == 0:
        s += 1
        d >>= 1
    for base in _MR_BASES_U64:
        a = base % n
        if a == 0:
            continue
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


def _pollard_brent(n: int) -> int:
    if n % 2 == 0:
        return 2
    if n % 3 == 0:
        return 3

    # Deterministic parameter stream keeps receipts reproducible.  The outer
    # loop changes both the polynomial and seed after a failed cycle.
    for attempt in range(1, 128):
        y = (2 + attempt * attempt) % n
        c = (1 + 2 * attempt) % n
        m = 128
        g = r = q = 1
        x = ys = 0
        while g == 1:
            x = y
            for _ in range(r):
                y = (y * y + c) % n
            k = 0
            while k < r and g == 1:
                ys = y
                for _ in range(min(m, r - k)):
                    y = (y * y + c) % n
                    q = q * abs(x - y) % n
                g = gcd(q, n)
                k += m
            r <<= 1
        if g == n:
            while True:
                ys = (ys * ys + c) % n
                g = gcd(abs(x - ys), n)
                if g > 1:
                    break
        if 1 < g < n:
            return g
    raise RuntimeError(f"deterministic Pollard-Brent failed for {n}")


@lru_cache(maxsize=32768)
def factor_u64(n: int) -> tuple[tuple[int, int], ...]:
    """Return the exact prime factorization of an integer 1 <= n < 2^64."""
    _require_u64(n)
    if n == 0:
        raise ValueError("zero has no prime factorization")
    if n == 1:
        return ()
    factors: list[int] = []
    stack = [n]
    while stack:
        value = stack.pop()
        if value == 1:
            continue
        if is_prime_u64(value):
            factors.append(value)
            continue
        divisor = _pollard_brent(value)
        stack.extend((divisor, value // divisor))
    factors.sort()
    result: list[tuple[int, int]] = []
    for p in factors:
        if result and result[-1][0] == p:
            result[-1] = (p, result[-1][1] + 1)
        else:
            result.append((p, 1))
    return tuple(result)


def _gaussian_mul(left: tuple[int, int], right: tuple[int, int]) -> tuple[int, int]:
    a, b = left
    c, d = right
    return abs(a * c - b * d), abs(a * d + b * c)


def _gaussian_pow(pair: tuple[int, int], exponent: int) -> tuple[int, int]:
    result = (1, 0)
    base = pair
    e = exponent
    while e:
        if e & 1:
            result = _gaussian_mul(result, base)
        base = _gaussian_mul(base, base)
        e >>= 1
    return result


def _prime_one_mod_four_representation(p: int) -> tuple[int, int]:
    if p % 4 != 1 or not is_prime_u64(p):
        raise ValueError("expected a prime congruent to 1 modulo 4")
    nonresidue = 2
    while pow(nonresidue, (p - 1) // 2, p) != p - 1:
        nonresidue += 1
    root = pow(nonresidue, (p - 1) // 4, p)
    for candidate in (root, p - root):
        r0, r1 = p, candidate
        while r1 * r1 > p:
            r0, r1 = r1, r0 % r1
        y2 = p - r1 * r1
        y = isqrt(y2)
        if y * y == y2:
            return abs(r1), y
    raise RuntimeError(f"Cornacchia failed for prime {p}")


@lru_cache(maxsize=32768)
def sum_two_squares(n: int) -> tuple[int, int] | None:
    """Construct a,b with n=a^2+b^2, or return None, exactly for n<2^64."""
    _require_u64(n)
    if n == 0:
        return 0, 0
    representation = (1, 0)
    for p, exponent in factor_u64(n):
        if p % 4 == 3:
            if exponent & 1:
                return None
            prime_power_rep = (p ** (exponent // 2), 0)
        elif p == 2:
            prime_power_rep = _gaussian_pow((1, 1), exponent)
        else:
            prime_power_rep = _gaussian_pow(
                _prime_one_mod_four_representation(p), exponent
            )
        representation = _gaussian_mul(representation, prime_power_rep)
    a, b = sorted(representation)
    if a * a + b * b != n:
        raise RuntimeError("internal sum-of-two-squares construction failure")
    return a, b


def _powers(base: int, upper: int) -> Iterable[tuple[int, int]]:
    exponent = 0
    value = 1
    while value <= upper:
        yield exponent, value
        exponent += 1
        value *= base


def find_witness(n: int) -> A303656Witness | None:
    """Return the first exact A303656 witness in exponent-lexicographic order."""
    _require_u64(n)
    if n <= 1:
        return None
    powers3 = tuple(_powers(3, n))
    powers5 = tuple(_powers(5, n))
    for c, p3 in powers3:
        for d, p5 in powers5:
            remainder = n - p3 - p5
            if remainder < 0:
                break
            pair = sum_two_squares(remainder)
            if pair is None:
                continue
            witness = A303656Witness(pair[0], pair[1], c, d)
            witness.verify(n)
            return witness
    return None


def _main(argv: list[str] | None = None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("n", type=int, help="integer to represent")
    args = parser.parse_args(argv)
    witness = find_witness(args.n)
    if witness is None:
        print(json.dumps({"n": args.n, "represented": False}, sort_keys=True))
        return 1
    print(
        json.dumps(
            {
                "n": args.n,
                "represented": True,
                "a": witness.a,
                "b": witness.b,
                "c": witness.c,
                "d": witness.d,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
