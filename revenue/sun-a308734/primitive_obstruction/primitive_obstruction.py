"""Exact primitive counterexample certificate for the fixed-3 A308734 shortcut.

F3(n) means n = x^2 + y^2 + 4^a + 4^b * 9^d with nonnegative integers.
This module does NOT claim to refute or prove the original two-family conjecture.
The proof is in PRIMITIVE_OBSTRUCTION.md; finite tests check the implementation.
Only Python's standard library is required. Verification survives python -O.
"""
from __future__ import annotations

import json
from fractions import Fraction
from itertools import product
from math import gcd, isqrt
from typing import Iterable

MODULUS = 72 * 49 * 121
EXPLICIT_BASE = 2095


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def integer(value: int, name: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def two_square_residues(modulus: int) -> frozenset[int]:
    integer(modulus, "modulus", 1)
    squares = {x * x % modulus for x in range(modulus)}
    return frozenset((a + b) % modulus for a in squares for b in squares)


def crt(equations: Iterable[tuple[int, int]]) -> tuple[int, int]:
    """Return the least nonnegative solution and product modulus; coprime only."""
    value, modulus = 0, 1
    for residue, next_modulus in equations:
        integer(residue, "residue")
        integer(next_modulus, "modulus", 2)
        require(gcd(modulus, next_modulus) == 1, "moduli are not pairwise coprime")
        value += modulus * (((residue - value) * pow(modulus, -1, next_modulus)) % next_modulus)
        modulus *= next_modulus
        value %= modulus
    return value, modulus


def certified_residues() -> tuple[int, ...]:
    """Sixty disjoint primitive counterexample progressions modulo MODULUS."""
    residues = []
    for j, k in product(range(1, 7), range(1, 11)):
        residue, modulus = crt(((7, 72), (2 + 7 * j, 49), (5 + 11 * k, 121)))
        require(modulus == MODULUS, "CRT modulus mismatch")
        residues.append(residue)
    require(len(set(residues)) == 60, "CRT residue collision")
    return tuple(sorted(residues))


def is_certified_counterexample(n: int) -> bool:
    """Certificate membership, not a complete F3 decision algorithm."""
    integer(n, "n")
    return (
        n % 72 == 7
        and (n - 2) % 7 == 0
        and (n - 2) % 49 != 0
        and (n - 5) % 11 == 0
        and (n - 5) % 121 != 0
    )


def two_square_witness(n: int) -> tuple[int, int] | None:
    """Finite exact oracle for testing; a negative remainder has no witness."""
    if type(n) is not int:
        raise ValueError("n must be an integer")
    if n < 0:
        return None
    for x in range(isqrt(n) + 1):
        y = isqrt(n - x * x)
        if x * x + y * y == n:
            return x, y
    return None


def specialized_witness(n: int) -> tuple[int, int, int, int, int] | None:
    """Independent finite enumeration of F3, without the residue lemma."""
    integer(n, "n")
    a, first = 0, 1
    while first + 1 <= n:
        b, two_part = 0, 1
        while first + two_part <= n:
            d, second = 0, two_part
            while first + second <= n:
                witness = two_square_witness(n - first - second)
                if witness is not None:
                    return (*witness, a, b, d)
                second *= 9
                d += 1
            two_part *= 4
            b += 1
        first *= 4
        a += 1
    return None


def verify_certificate() -> dict[str, object]:
    """Verify all finite residue implications used by the infinite proof."""
    residues8 = two_square_residues(8)
    require(residues8 == {0, 1, 2, 4, 5}, "two-square residues modulo 8")
    powers4_mod8 = (1, 4, 0)
    surviving = [
        [a, b] for a, b in product(range(3), repeat=2)
        if (7 - powers4_mod8[a] - powers4_mod8[b]) % 8 in residues8
    ]
    require(surviving == [[0, 0], [0, 1], [1, 0]], "modulo-8 exponent reduction")
    require(9 % 8 == 1, "all powers of 9 must be 1 modulo 8")
    positive_d_residuals9 = [(7 - pow(4, a, 9)) % 9 for a, _ in surviving]
    require(positive_d_residuals9 == [6, 6, 3], "positive-d residuals modulo 9")
    require(not set(positive_d_residuals9) & two_square_residues(9), "d>=1 exclusion")
    zero_d_subtractands = sorted({4**a + 4**b for a, b in surviving})
    require(zero_d_subtractands == [2, 5], "d=0 leaves only 2 or 5")
    require(35 not in two_square_residues(49), "explicit n-2 certificate")
    require(33 not in two_square_residues(121), "explicit n-5 certificate")
    require(EXPLICIT_BASE % 72 == 7, "explicit class modulo 72")
    require((EXPLICIT_BASE - 2) % 49 == 35, "explicit class modulo 49")
    require((EXPLICIT_BASE - 5) % 121 == 33, "explicit class modulo 121")
    residues = certified_residues()
    require(EXPLICIT_BASE in residues, "explicit progression absent")
    for residue in residues:
        require(is_certified_counterexample(residue), "bad CRT certificate")
        require(residue % 8 == 7, "not a primitive progression")
        require((residue - 2) % 49 not in two_square_residues(49), "7-adic obstruction")
        require((residue - 5) % 121 not in two_square_residues(121), "11-adic obstruction")
    density = Fraction(len(residues), MODULUS)
    require(density == Fraction(5, 35574), "density mismatch")
    require(25**2 + 38**2 + 1**2 + 5**2 == EXPLICIT_BASE, "original witness")
    return {
        "status": "VERIFIED_FINITE_CERTIFICATE_FOR_INFINITE_PROOF",
        "target": "F3(n)=x^2+y^2+4^a+4^b*9^d",
        "lemma_class": {"residue": 7, "modulus": 72},
        "lemma_residuals": ["n-2", "n-5"],
        "mod8_exponent_categories": {"0": "zero", "1": "one", "2": "at least two"},
        "surviving_mod8_categories": surviving,
        "positive_d_residuals_mod9": positive_d_residuals9,
        "progression": {"base": EXPLICIT_BASE, "step": MODULUS, "t_min": 0},
        "crt_counterexample_residues": list(residues),
        "crt_modulus": MODULUS,
        "certified_union_density": str(density),
        "original_conjecture_refuted": False,
        "original_conjecture_proved": False,
        "sponsor_contacted": False,
        "prize_claimed": False,
        "payment_claimed": False,
    }


if __name__ == "__main__":
    print(json.dumps(verify_certificate(), sort_keys=True, indent=2))
