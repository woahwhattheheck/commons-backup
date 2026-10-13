"""Exact finite reductions for Sun's A308734 four-square conjecture.

This module proves only elementary residue/lifting statements used by the research
note.  It deliberately does not brute-force an interval of A308734 and does not
claim the conjecture.
"""
from __future__ import annotations

from dataclasses import dataclass


PRIMITIVE_MOD24 = frozenset(r for r in range(24) if r % 4 != 0)

# Exact infinite semigroup-square residue sets.
# (2^c 5^d)^2 = 4^c * 25^d == 4^c (mod 24), because 25 == 1 (mod 24).
# Thus c=0 -> 1, c=1 -> 4, and c>=2 -> 16 (mod 24).
S5_SQUARES_MOD24 = frozenset({1, 4, 16})

# (2^a 3^b)^2 = 4^a * 9^b (mod 12).
# b=0 gives 1 or 4; b>0 gives 9 when a=0 and 0 when a>0.
S3_SQUARES_MOD12 = frozenset({0, 1, 4, 9})

# For either semigroup, the odd square is 1 mod 8 and 4^a is 1,4,0.
RESTRICTED_SQUARES_MOD8 = frozenset({0, 1, 4})
ORDINARY_SQUARES_MOD8 = frozenset({0, 1, 4})
TWO_SQUARE_SUMS_MOD8 = frozenset((a + b) % 8 for a in ORDINARY_SQUARES_MOD8 for b in ORDINARY_SQUARES_MOD8)
RESTRICTED_PAIR_SUMS_MOD8 = frozenset((a + b) % 8 for a in RESTRICTED_SQUARES_MOD8 for b in RESTRICTED_SQUARES_MOD8)

# Conditional bridges through Sun's two ternary conjectures.
TERNARY_3_TARGET_MOD24 = 10
TERNARY_5_TARGET_MOD12 = 5
TERNARY_3_BRIDGE_MOD24 = frozenset((TERNARY_3_TARGET_MOD24 + s) % 24 for s in S5_SQUARES_MOD24)
TERNARY_5_BRIDGE_MOD12 = frozenset((TERNARY_5_TARGET_MOD12 + s) % 12 for s in S3_SQUARES_MOD12)
TERNARY_5_BRIDGE_MOD24 = frozenset(r for r in range(24) if r % 12 in TERNARY_5_BRIDGE_MOD12)
CONDITIONAL_BRIDGE_MOD24 = TERNARY_3_BRIDGE_MOD24 | TERNARY_5_BRIDGE_MOD24


@dataclass(frozen=True)
class Representation:
    """A308734 representation parameters (x,y,a,b,c,d)."""

    x: int
    y: int
    a: int
    b: int
    c: int
    d: int

    def __post_init__(self) -> None:
        if any(type(v) is not int or v < 0 for v in (self.x, self.y, self.a, self.b, self.c, self.d)):
            raise ValueError("representation parameters must be nonnegative integers")

    @property
    def value(self) -> int:
        s3 = (2**self.a) * (3**self.b)
        s5 = (2**self.c) * (5**self.d)
        return self.x * self.x + self.y * self.y + s3 * s3 + s5 * s5

    def lift_by_four(self) -> "Representation":
        """Return the exact representation of four times ``value``."""
        return Representation(2 * self.x, 2 * self.y, self.a + 1, self.b, self.c + 1, self.d)


# Fixed direct witnesses for positivity exceptions in the conditional bridge.
DIRECT_SMALL_WITNESSES = {
    2: Representation(0, 0, 0, 0, 0, 0),
    5: Representation(0, 0, 0, 0, 1, 0),
    17: Representation(0, 0, 0, 0, 2, 0),
    29: Representation(0, 4, 0, 1, 1, 0),
}


def ternary3_subtrahend(n: int) -> int | None:
    """Small fixed (2^c 5^d)^2 leaving 10 mod 24, or None."""
    residue = n % 24
    # Exact values representing the three square residues 1,4,16.
    return {11: 1, 14: 4, 2: 16}.get(residue)


def ternary5_subtrahend(n: int) -> int | None:
    """Small fixed (2^a 3^b)^2 leaving 5 mod 12, or None."""
    residue = n % 12
    # 36,1,4,9 realize square residues 0,1,4,9 respectively.
    return {5: 36, 6: 1, 9: 4, 2: 9}.get(residue)


def conditional_bridge(n: int) -> tuple[str, int, int] | None:
    """Return a positive ternary remainder certificate for covered primitive n.

    The result is ``(ternary_conjecture, restricted_square, remainder)``.  It is
    conditional proof plumbing only: the named ternary conjecture is not proved
    here.  Direct small witnesses are intentionally kept separate.
    """
    if type(n) is not int or n <= 1 or n % 4 == 0:
        return None

    s = ternary3_subtrahend(n)
    if s is not None and n - s > 0:
        remainder = n - s
        if remainder % 24 != TERNARY_3_TARGET_MOD24:
            raise AssertionError("ternary-3 bridge invariant broken")
        return ("SUN_TERNARY_3", s, remainder)

    s = ternary5_subtrahend(n)
    if s is not None and n - s > 0:
        remainder = n - s
        if remainder % 12 != TERNARY_5_TARGET_MOD12:
            raise AssertionError("ternary-5 bridge invariant broken")
        return ("SUN_TERNARY_5", s, remainder)

    return None


def mod8_local_table() -> dict[int, tuple[int, ...]]:
    """Restricted-pair residues that leave a two-square-admissible mod-8 remainder."""
    table: dict[int, tuple[int, ...]] = {}
    for n_mod8 in range(8):
        choices = sorted(
            pair
            for pair in RESTRICTED_PAIR_SUMS_MOD8
            if (n_mod8 - pair) % 8 in TWO_SQUARE_SUMS_MOD8
        )
        table[n_mod8] = tuple(choices)
    return table
