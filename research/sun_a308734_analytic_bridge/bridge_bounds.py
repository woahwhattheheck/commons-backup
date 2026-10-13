"""Exact arithmetic for the A308734 analytic-bridge route audit.

This module verifies constants and narrow falsifiers used by README.md.  It does
not search for A308734 counterexamples and finite output from it is not evidence
for the conjecture.
"""

from __future__ import annotations

from fractions import Fraction
from math import isqrt


ETA2 = Fraction(1, 34)
Z2_MULTIPLIER = Fraction(10, 51)
Y2_MULTIPLIER = Fraction(54, 55)
PAPER_THETA2 = Fraction(4477, 5000)  # 0.89540 exactly
COORDINATE_EXPONENT = Fraction(1, 2)


def _epsilon(value: Fraction | int = Fraction(0)) -> Fraction:
    value = Fraction(value)
    if not 0 <= value < ETA2:
        raise ValueError("epsilon must satisfy 0 <= epsilon < 1/34")
    return value


def z2_exponent(epsilon: Fraction | int = Fraction(0)) -> Fraction:
    """Exponent alpha in z_2 = m^alpha."""
    eps = _epsilon(epsilon)
    return (ETA2 - eps) * Z2_MULTIPLIER


def y2_exponent(epsilon: Fraction | int = Fraction(0)) -> Fraction:
    """Exponent beta in y_2 = m^beta."""
    eps = _epsilon(epsilon)
    return (ETA2 - eps) * Y2_MULTIPLIER


def complete_sieve_gap_ratio() -> Fraction:
    """Naive full-sifting exponent 1/2 divided by available 1/34."""
    return COORDINATE_EXPONENT / ETA2


def cofactor_band_ratio(epsilon: Fraction | int = Fraction(0)) -> Fraction:
    """Size exponent 1/2 divided by the paper's y_2 exponent."""
    return COORDINATE_EXPONENT / y2_exponent(epsilon)


def diagnostic_richert_scale(
    theta: Fraction = PAPER_THETA2,
    epsilon: Fraction | int = Fraction(0),
) -> Fraction:
    """The simplified 1/theta + (1/2)/beta scale used in the audit.

    This is a diagnostic reconstruction of why the published constants live at
    the P_18 scale; it is not a replacement statement for the paper's weighted
    sieve inequality.
    """
    theta = Fraction(theta)
    if not 0 < theta <= 1:
        raise ValueError("theta must satisfy 0 < theta <= 1")
    return Fraction(1, 1) / theta + cofactor_band_ratio(epsilon)


def sieve_threshold_excludes_three(
    m: int, epsilon: Fraction | int = Fraction(0)
) -> bool:
    """Return whether m^alpha > 3 using exact integer arithmetic.

    If alpha = p/q > 0, then m^alpha > 3 iff m^p > 3^q.  Once this
    predicate is true, the paper's condition (z, P(z_2))=1 excludes 3 from
    the odd survivor z.
    """
    if not isinstance(m, int) or m <= 0:
        raise ValueError("m must be a positive integer")
    alpha = z2_exponent(epsilon)
    return pow(m, alpha.numerator) > pow(3, alpha.denominator)


def pure_three_power_survivor_exponent(
    m: int, epsilon: Fraction | int = Fraction(0)
) -> int | None:
    """Return the only possible d for a survivor z=3^d, once 3 is sifted.

    ``0`` means only z=1 can survive. ``None`` means the z_2>3 threshold
    has not been certified from m alone, so this audit makes no conclusion.
    """
    return 0 if sieve_threshold_excludes_three(m, epsilon) else None


def is_sum_of_two_squares_by_criterion(n: int) -> bool:
    """Fermat two-square criterion, implemented by exact trial division."""
    if n < 0:
        return False
    if n == 0:
        return True

    value = n
    p = 2
    while p * p <= value:
        exponent = 0
        while value % p == 0:
            value //= p
            exponent += 1
        if p % 4 == 3 and exponent % 2:
            return False
        p = 3 if p == 2 else p + 2

    return not (value > 1 and value % 4 == 3)


def fixed_scale_absorption_counterexample() -> tuple[int, int, bool]:
    """Return the narrow q=5 obstruction documented in README.md.

    25 = 5^2.  Dividing that fixed third-coordinate scale by 5 leaves 1,
    so the two-square part would have to become 25-1=24, which fails the
    two-square criterion.
    """
    original = 25
    reduced_remainder = 24
    return original, reduced_remainder, is_sum_of_two_squares_by_criterion(
        reduced_remainder
    )


def smooth_coordinate_pair_count(limit: int) -> int:
    """Count (a,b)>=0 with 2^a 3^b <= limit exactly.

    This is a finite verifier for the target family's lacunarity only; it is
    deliberately not a conjecture search.
    """
    if not isinstance(limit, int) or limit < 1:
        return 0
    count = 0
    power2 = 1
    while power2 <= limit:
        power3 = 1
        while power2 * power3 <= limit:
            count += 1
            power3 *= 3
        power2 *= 2
    return count


if __name__ == "__main__":
    print("z2 exponent:", z2_exponent())
    print("y2 exponent:", y2_exponent())
    print("complete-sieve gap:", complete_sieve_gap_ratio())
    print("cofactor/y2 ratio:", cofactor_band_ratio())
    print("paper diagnostic scale:", diagnostic_richert_scale())
