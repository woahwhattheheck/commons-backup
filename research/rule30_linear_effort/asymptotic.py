"""Exact asymptotic contracts used by the Rule 30 Problem 3 carrier.

This module deliberately avoids classifying arbitrary sampled runtimes. It only
classifies symbolic n**alpha * (log n)**beta families where the relation to n
is a theorem.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from math import isqrt


class RelationToLinear(str, Enum):
    SUBLINEAR = "SUBLINEAR"          # T(n) = o(n)
    LINEAR_SCALE = "LINEAR_SCALE"    # T(n) = Theta(n)
    SUPERLINEAR = "SUPERLINEAR"      # T(n) / n -> infinity


@dataclass(frozen=True)
class PowerLogRuntime:
    """T(n) = n**alpha * (log n)**beta, up to positive constant factors.

    `alpha` is exact (Fraction) and `beta` is an integer. The classification
    is asymptotic and therefore does not depend on a finite timing census.
    """

    alpha: Fraction
    beta: int = 0

    def relation_to_linear(self) -> RelationToLinear:
        if self.alpha < 1:
            return RelationToLinear.SUBLINEAR
        if self.alpha > 1:
            return RelationToLinear.SUPERLINEAR
        if self.beta < 0:
            return RelationToLinear.SUBLINEAR
        if self.beta == 0:
            return RelationToLinear.LINEAR_SCALE
        return RelationToLinear.SUPERLINEAR

    def is_prose_shortcut(self) -> bool:
        """Intended/prose counterexample: a genuinely sublinear algorithm."""
        return self.relation_to_linear() is RelationToLinear.SUBLINEAR

    def is_displayed_predicate_counterexample(self) -> bool:
        """Counterexample to the displayed NotExists finite-limsup predicate.

        A sublinear OR linear-scale exact machine has finite limsup T(n)/n.
        """
        return self.relation_to_linear() in {
            RelationToLinear.SUBLINEAR,
            RelationToLinear.LINEAR_SCALE,
        }


def target_mismatch_witness() -> PowerLogRuntime:
    """Return the simplest witness separating the two published targets."""
    return PowerLogRuntime(Fraction(1, 1), 0)


def is_power_of_two(n: int) -> bool:
    if n <= 0:
        return False
    return (n & (n - 1)) == 0


def spiky_linear_runtime(n: int) -> int:
    """A non-smooth O(n), non-o(n) witness.

    At powers of two it costs n; elsewhere it costs floor(sqrt(n)).
    Thus limsup T(n)/n = 1 while liminf T(n)/n = 0.
    """
    if n <= 0:
        raise ValueError("n must be positive")
    if is_power_of_two(n):
        return n
    return isqrt(n)
