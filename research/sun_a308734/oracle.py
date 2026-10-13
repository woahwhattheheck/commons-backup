"""Exact fixed-menu witness constructor for OEIS A308734.

This intentionally reuses the already-merged exact unsigned-64-bit
sum-of-two-squares oracle from ``research.sun_a303656.oracle``.  Returning
``None`` means only that the 20-pair low-obstruction menu found no witness; it
is never a counterexample to A308734.
"""

from __future__ import annotations

from dataclasses import dataclass

from research.sun_a303656.oracle import sum_two_squares

from .residue_cover import PAIR_MENU, RestrictedPair


@dataclass(frozen=True, slots=True)
class A308734Witness:
    x: int
    y: int
    a: int
    b: int
    c: int
    d: int

    @property
    def value(self) -> int:
        return (
            self.x * self.x
            + self.y * self.y
            + (2**self.a * 3**self.b) ** 2
            + (2**self.c * 5**self.d) ** 2
        )

    def verify(self, n: int) -> None:
        if min(self.x, self.y, self.a, self.b, self.c, self.d) < 0:
            raise ValueError("witness fields must be nonnegative")
        if self.value != n:
            raise ValueError("witness does not reconstruct n exactly")


def witness_from_pair(n: int, pair: RestrictedPair) -> A308734Witness | None:
    residual = n - pair.total
    if residual < 0:
        return None
    xy = sum_two_squares(residual)
    if xy is None:
        return None
    witness = A308734Witness(xy[0], xy[1], pair.a, pair.b, pair.c, pair.d)
    witness.verify(n)
    return witness


def find_fixed_menu_witness(n: int) -> A308734Witness | None:
    """Try the exact 20-pair menu; absence is only finite negative evidence."""
    if not isinstance(n, int) or n < 0:
        raise ValueError("n must be a nonnegative integer")
    for pair in PAIR_MENU:
        witness = witness_from_pair(n, pair)
        if witness is not None:
            return witness
    return None
