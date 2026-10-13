"""Exact finite CRT lemmas for Zhi-Wei Sun's OEIS A308734 conjecture.

A308734 asks whether every n > 1 has

    n = x^2 + y^2 + (2^a 3^b)^2 + (2^c 5^d)^2.

The two restricted squares are 4^a 9^b and 4^c 25^d.  A residual can be a
sum of two squares only if every prime p == 3 (mod 4) has even valuation.  This
module proves a deliberately finite support lemma: a fixed menu of 20 tiny
restricted-square pairs always makes the residual coprime to the first eight
such primes.  It is proof-support, not a proof of A308734.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import gcd, prod
from typing import Iterable, Sequence

OBSTRUCTION_PRIMES: tuple[int, ...] = (3, 7, 11, 19, 23, 31, 43, 47)
OBSTRUCTION_MODULUS: int = prod(OBSTRUCTION_PRIMES)


@dataclass(frozen=True, slots=True, order=True)
class RestrictedPair:
    """Exponent tuple for 4^a 9^b + 4^c 25^d."""

    a: int
    b: int
    c: int
    d: int

    @property
    def left(self) -> int:
        return 4**self.a * 9**self.b

    @property
    def right(self) -> int:
        return 4**self.c * 25**self.d

    @property
    def total(self) -> int:
        return self.left + self.right

    def as_dict(self) -> dict[str, int]:
        return {
            "a": self.a,
            "b": self.b,
            "c": self.c,
            "d": self.d,
            "left": self.left,
            "right": self.right,
            "total": self.total,
        }


# Sorted by the actual restricted-square pair sum.  Every total is <= 85.
PAIR_MENU: tuple[RestrictedPair, ...] = (
    RestrictedPair(0, 0, 0, 0),   # 2  = 1 + 1
    RestrictedPair(0, 0, 1, 0),   # 5  = 1 + 4
    RestrictedPair(1, 0, 1, 0),   # 8  = 4 + 4
    RestrictedPair(0, 1, 0, 0),   # 10 = 9 + 1
    RestrictedPair(0, 1, 1, 0),   # 13 = 9 + 4
    RestrictedPair(0, 0, 2, 0),   # 17 = 1 + 16
    RestrictedPair(1, 0, 2, 0),   # 20 = 4 + 16
    RestrictedPair(0, 1, 2, 0),   # 25 = 9 + 16
    RestrictedPair(0, 0, 0, 1),   # 26 = 1 + 25
    RestrictedPair(1, 0, 0, 1),   # 29 = 4 + 25
    RestrictedPair(2, 0, 2, 0),   # 32 = 16 + 16
    RestrictedPair(0, 1, 0, 1),   # 34 = 9 + 25
    RestrictedPair(1, 1, 0, 0),   # 37 = 36 + 1
    RestrictedPair(1, 1, 1, 0),   # 40 = 36 + 4
    RestrictedPair(2, 0, 0, 1),   # 41 = 16 + 25
    RestrictedPair(1, 1, 2, 0),   # 52 = 36 + 16
    RestrictedPair(1, 1, 0, 1),   # 61 = 36 + 25
    RestrictedPair(0, 0, 3, 0),   # 65 = 1 + 64
    RestrictedPair(0, 1, 3, 0),   # 73 = 9 + 64
    RestrictedPair(0, 2, 1, 0),   # 85 = 81 + 4
)

# Earlier 12-term menu: exact through p=31, but not through p=43.
SEED_MENU: tuple[RestrictedPair, ...] = tuple(
    pair
    for pair in PAIR_MENU
    if pair.total in {2, 5, 8, 10, 17, 20, 25, 32, 34, 37, 40, 85}
)

SEED_FAILURE_PRIMES: tuple[int, ...] = (3, 7, 11, 19, 23, 31, 43)
SEED_FAILURE_MODULUS: int = prod(SEED_FAILURE_PRIMES)
SEED_FAILURE_RESIDUE: int = 99_162_274

NEXT_PRIME_FAILURE_PRIMES: tuple[int, ...] = OBSTRUCTION_PRIMES + (59,)
NEXT_PRIME_FAILURE_MODULUS: int = prod(NEXT_PRIME_FAILURE_PRIMES)
NEXT_PRIME_FAILURE_RESIDUE: int = 41_144_806_933


@dataclass(frozen=True, slots=True)
class CoverStep:
    prime: int
    reachable_masks: int
    minimum_survivors: int
    zero_mask_reachable: bool

    def as_dict(self) -> dict[str, int | bool]:
        return {
            "prime": self.prime,
            "reachable_masks": self.reachable_masks,
            "minimum_survivors": self.minimum_survivors,
            "zero_mask_reachable": self.zero_mask_reachable,
        }


def _residue_survivor_mask(
    prime: int,
    residue: int,
    menu: Sequence[RestrictedPair],
) -> int:
    """Bit i is 1 iff candidate i avoids divisibility by prime."""
    mask = 0
    for index, pair in enumerate(menu):
        if (residue - pair.total) % prime:
            mask |= 1 << index
    return mask


def cover_trace(
    menu: Sequence[RestrictedPair] = PAIR_MENU,
    primes: Sequence[int] = OBSTRUCTION_PRIMES,
) -> tuple[CoverStep, ...]:
    """Exhaust every CRT residue vector, compressed as survivor bitmasks.

    For a residue n mod p, a candidate survives p exactly when p does not divide
    n - candidate.total.  Intersecting survivor masks over primes therefore
    enumerates *all* possible CRT residue vectors without enumerating their
    product modulus.  Absence of the zero mask proves at least one candidate
    survives every prime simultaneously for every integer n.
    """
    if not menu:
        raise ValueError("menu must be nonempty")
    if not primes:
        raise ValueError("primes must be nonempty")
    full_mask = (1 << len(menu)) - 1
    reachable = {full_mask}
    trace: list[CoverStep] = []
    for prime in primes:
        if prime <= 1:
            raise ValueError("primes must exceed 1")
        local_masks = {
            _residue_survivor_mask(prime, residue, menu)
            for residue in range(prime)
        }
        reachable = {
            global_mask & local_mask
            for global_mask in reachable
            for local_mask in local_masks
        }
        trace.append(
            CoverStep(
                prime=prime,
                reachable_masks=len(reachable),
                minimum_survivors=min(mask.bit_count() for mask in reachable),
                zero_mask_reachable=0 in reachable,
            )
        )
    return tuple(trace)


def uniform_cover_holds(
    menu: Sequence[RestrictedPair] = PAIR_MENU,
    primes: Sequence[int] = OBSTRUCTION_PRIMES,
) -> bool:
    """Return True iff every CRT residue vector has a surviving candidate."""
    return not cover_trace(menu, primes)[-1].zero_mask_reachable


def choose_low_obstruction_free(n: int) -> RestrictedPair:
    """Return a menu pair whose residual is coprime to OBSTRUCTION_MODULUS."""
    for pair in PAIR_MENU:
        if gcd(n - pair.total, OBSTRUCTION_MODULUS) == 1:
            return pair
    raise RuntimeError("internal certificate contradiction: menu failed")


def verify_failure_residue(
    residue: int,
    modulus: int,
    menu: Sequence[RestrictedPair],
) -> tuple[tuple[int, int], ...]:
    """Return (candidate total, gcd) rows; every gcd > 1 certifies failure."""
    return tuple((pair.total, gcd(residue - pair.total, modulus)) for pair in menu)


def certificate_dict() -> dict[str, object]:
    """Canonical machine-readable certificate payload."""
    trace = cover_trace()
    seed_failure = verify_failure_residue(
        SEED_FAILURE_RESIDUE, SEED_FAILURE_MODULUS, SEED_MENU
    )
    next_failure = verify_failure_residue(
        NEXT_PRIME_FAILURE_RESIDUE,
        NEXT_PRIME_FAILURE_MODULUS,
        PAIR_MENU,
    )
    if trace[-1].zero_mask_reachable:
        raise RuntimeError("uniform-cover certificate unexpectedly failed")
    if not all(g > 1 for _, g in seed_failure):
        raise RuntimeError("seed-menu counterexample is not a counterexample")
    if not all(g > 1 for _, g in next_failure):
        raise RuntimeError("p=59 boundary counterexample is not a counterexample")
    return {
        "schema": "sun-a308734-low-obstruction-cover/v1",
        "proof_scope": (
            "finite CRT lemma only; not a proof or counterexample of A308734"
        ),
        "claim": {
            "statement": (
                "for every integer n there is a listed restricted-square pair "
                "s with gcd(n-s, product(primes)) = 1"
            ),
            "primes": list(OBSTRUCTION_PRIMES),
            "modulus": OBSTRUCTION_MODULUS,
            "menu_size": len(PAIR_MENU),
            "maximum_pair_sum": max(pair.total for pair in PAIR_MENU),
        },
        "menu": [pair.as_dict() for pair in PAIR_MENU],
        "dynamic_program": {
            "method": "exact survivor-bitmask enumeration over every residue per prime",
            "trace": [step.as_dict() for step in trace],
            "zero_mask_reachable_final": trace[-1].zero_mask_reachable,
        },
        "negative_evidence": {
            "seed_menu_does_not_extend_through_43": {
                "primes": list(SEED_FAILURE_PRIMES),
                "modulus": SEED_FAILURE_MODULUS,
                "residue": SEED_FAILURE_RESIDUE,
                "rows": [
                    {"pair_sum": pair_sum, "gcd": common}
                    for pair_sum, common in seed_failure
                ],
            },
            "final_menu_does_not_extend_through_59": {
                "primes": list(NEXT_PRIME_FAILURE_PRIMES),
                "modulus": NEXT_PRIME_FAILURE_MODULUS,
                "residue": NEXT_PRIME_FAILURE_RESIDUE,
                "rows": [
                    {"pair_sum": pair_sum, "gcd": common}
                    for pair_sum, common in next_failure
                ],
            },
        },
    }


def menu_totals(menu: Iterable[RestrictedPair] = PAIR_MENU) -> tuple[int, ...]:
    return tuple(pair.total for pair in menu)
