"""Exact proof-support utilities for Sun's ternary 5 mod 12 conjecture.

Target (OEIS A308661): for every positive n == 5 (mod 12), find
x,y,a,b >= 0 with a > 0 and

    n = x^2 + y^2 + (2^a 5^b)^2.

This module is intentionally an exact oracle/reduction harness, not a proof
of the unresolved conjecture.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from research.sun_a303656.oracle import factor_u64, sum_two_squares


@dataclass(frozen=True, slots=True)
class Ternary5Witness:
    x: int
    y: int
    a: int
    b: int

    @property
    def restricted_square(self) -> int:
        return (2**self.a * 5**self.b) ** 2

    @property
    def value(self) -> int:
        return self.x * self.x + self.y * self.y + self.restricted_square

    def verify(self, n: int) -> None:
        validate_target(n)
        if min(self.x, self.y, self.b) < 0 or self.a <= 0:
            raise ValueError("witness requires x,y,b >= 0 and a > 0")
        if self.value != n:
            raise ValueError("witness does not reconstruct target exactly")


def validate_target(n: int) -> None:
    if not isinstance(n, int) or isinstance(n, bool):
        raise ValueError("target must be an integer")
    if n <= 0 or n % 12 != 5:
        raise ValueError("target must be positive and congruent to 5 modulo 12")
    if n >= 1 << 64:
        raise ValueError("exact factor oracle supports targets below 2^64")


def primitive_25_core(n: int) -> tuple[int, int]:
    """Return unique (core,k) with n = 25^k * core and 25 does not divide core."""
    validate_target(n)
    k = 0
    core = n
    while core % 25 == 0:
        core //= 25
        k += 1
    if core % 12 != 5:
        raise RuntimeError("25-adic descent changed the target congruence")
    return core, k


def lift_witness_by_25(witness: Ternary5Witness, k: int) -> Ternary5Witness:
    """Lift a core witness from m to 25^k*m."""
    if not isinstance(k, int) or isinstance(k, bool) or k < 0:
        raise ValueError("k must be a nonnegative integer")
    scale = 5**k
    return Ternary5Witness(
        x=scale * witness.x,
        y=scale * witness.y,
        a=witness.a,
        b=witness.b + k,
    )


def iter_restricted_shifts(n: int, *, max_b: int | None = None):
    """Yield legal (a,b,shift) in b-major then a-major order."""
    validate_target(n)
    if max_b is not None and (
        not isinstance(max_b, int) or isinstance(max_b, bool) or max_b < 0
    ):
        raise ValueError("max_b must be a nonnegative integer or None")

    b = 0
    pow25 = 1
    while 4 * pow25 < n and (max_b is None or b <= max_b):
        a = 1
        pow4 = 4
        while pow4 * pow25 < n:
            yield a, b, pow4 * pow25
            a += 1
            pow4 *= 4
        b += 1
        pow25 *= 25


def _normalize_b_values(b_values: Iterable[int]) -> tuple[int, ...]:
    try:
        values = tuple(b_values)
    except TypeError as exc:
        raise ValueError("b_values must be an iterable of nonnegative integers") from exc
    if not values:
        raise ValueError("b_values must not be empty")
    if any(
        not isinstance(value, int) or isinstance(value, bool) or value < 0
        for value in values
    ):
        raise ValueError("b_values must contain only nonnegative integers")
    return tuple(sorted(set(values)))


def _iter_selected_b_shifts(n: int, b_values: tuple[int, ...]):
    """Yield legal shifts for an explicit finite b-menu without huge powers."""
    for b in b_values:
        pow25 = 1
        for _ in range(b):
            pow25 *= 25
            if 4 * pow25 >= n:
                break
        else:
            a = 1
            pow4 = 4
            while pow4 * pow25 < n:
                yield a, b, pow4 * pow25
                a += 1
                pow4 *= 4


def bad_prime_obstructions(residual: int) -> tuple[tuple[int, int], ...]:
    """Return p == 3 mod 4 with odd valuation, the exact two-square obstruction."""
    if not isinstance(residual, int) or residual < 0 or residual >= 1 << 64:
        raise ValueError("residual must satisfy 0 <= residual < 2^64")
    return tuple(
        (p, exponent)
        for p, exponent in factor_u64(residual)
        if p % 4 == 3 and exponent % 2 == 1
    )


def find_witness(n: int, *, max_b: int | None = None) -> Ternary5Witness | None:
    """Return an exact witness, or None within the requested b-bound."""
    for a, b, shift in iter_restricted_shifts(n, max_b=max_b):
        pair = sum_two_squares(n - shift)
        if pair is None:
            continue
        witness = Ternary5Witness(pair[0], pair[1], a, b)
        witness.verify(n)
        return witness
    return None


def certify_b_menu_failure(
    n: int, b_values: Iterable[int]
) -> tuple[dict[str, object], ...]:
    """Certify every legal shift in an explicit finite b-menu fails.

    An empty result is meaningful: it says the menu supplies no restricted
    square smaller than ``n``. Any legal shift that succeeds raises instead.
    """
    validate_target(n)
    menu = _normalize_b_values(b_values)
    rows: list[dict[str, object]] = []
    for a, b, shift in _iter_selected_b_shifts(n, menu):
        remainder = n - shift
        bad = bad_prime_obstructions(remainder)
        if not bad:
            raise ValueError(
                f"target {n} has a valid witness in b-menu {menu}: a={a}, b={b}"
            )
        rows.append(
            {
                "a": a,
                "b": b,
                "shift": shift,
                "residual": remainder,
                "odd_bad_prime_valuations": [list(item) for item in bad],
            }
        )
    return tuple(rows)


def certify_bounded_failure(n: int, max_b: int) -> tuple[dict[str, object], ...]:
    """Certify every legal shift with b <= max_b leaves a two-square obstruction.

    Raises if any legal shift succeeds, so returned rows are an exact falsifier
    for the bounded-b shortcut, never a conjecture counterexample.
    """
    if not isinstance(max_b, int) or isinstance(max_b, bool) or max_b < 0:
        raise ValueError("max_b must be a nonnegative integer")
    rows = certify_b_menu_failure(n, range(max_b + 1))
    if not rows:
        raise ValueError("bound produced no legal restricted shifts")
    return rows


def certify_fixed_menu_size_at_most_two(
    b_values: Iterable[int],
) -> dict[str, object]:
    """Mechanize the exact case split excluding every fixed b-menu of size <= 2.

    The returned target defeats precisely the supplied menu while the returned
    witness uses a b-value outside it, proving this is a shortcut falsifier and
    not a counterexample to Sun's conjecture.
    """
    menu = _normalize_b_values(b_values)
    if len(menu) > 2:
        raise ValueError("this theorem-support certificate requires menu size <= 2")

    if 0 not in menu:
        target = 5
        witness = Ternary5Witness(0, 1, 1, 0)
    elif menu == (0,):
        target = 12_233
        witness = Ternary5Witness(18, 97, 1, 2)
    elif menu == (0, 1):
        target = 1_595_477
        witness = Ternary5Witness(831, 946, 2, 2)
    elif menu == (0, 2):
        target = 1_750_109
        witness = Ternary5Witness(403, 1260, 1, 1)
    else:
        # Here menu=(0,k) with k>=3.  At N=12233 the k-shift is already
        # at least 4*25^3=62500>N, while every b=0 residual is obstructed.
        target = 12_233
        witness = Ternary5Witness(18, 97, 1, 2)

    rows = certify_b_menu_failure(target, menu)
    witness.verify(target)
    if witness.b in menu:
        raise RuntimeError("shortcut falsifier rescue unexpectedly lies inside menu")
    return {
        "b_values": list(menu),
        "n": target,
        "positive_residual_failures": rows,
        "outside_menu_witness": {
            "x": witness.x,
            "y": witness.y,
            "a": witness.a,
            "b": witness.b,
        },
        "status": "FINITE_EXACT_SHORTCUT_FALSIFIER_NOT_CONJECTURE_COUNTEREXAMPLE",
    }
