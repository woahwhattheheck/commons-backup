"""Small deterministic constrained benchmarks for policy testing.

These are not the Learn2Design simulator and no organizer-performance conclusion may
be drawn from them. They exist to catch optimizer-control and fail-closed bugs.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

from core import Candidate, ContractError


@dataclass
class BowlWithAnnulus:
    dimension: int = 6
    min_radius: float = 0.35
    max_radius: float = 1.25

    @property
    def bounds(self) -> list[tuple[float, float]]:
        return [(-2.0, 2.0)] * self.dimension

    def evaluate(self, point: Sequence[float], evaluation: int, source: str = "synthetic") -> Candidate:
        if len(point) != self.dimension:
            raise ContractError("wrong synthetic dimension")
        shifted = [float(x) - (0.15 if i % 2 == 0 else -0.1) for i, x in enumerate(point)]
        radius = math.sqrt(sum(x * x for x in point))
        low_violation = max(0.0, self.min_radius - radius)
        high_violation = max(0.0, radius - self.max_radius)
        violation = low_violation + high_violation
        loss = sum(x * x for x in shifted) / self.dimension
        return Candidate(tuple(float(x) for x in point), loss, violation, violation == 0, source, evaluation)


@dataclass
class InfeasibleTrap:
    """Unconstrained optimum is infeasible; correct ranking must prefer feasible points."""

    @property
    def bounds(self) -> list[tuple[float, float]]:
        return [(-1.0, 1.0), (-1.0, 1.0)]

    def evaluate(self, point: Sequence[float], evaluation: int, source: str = "synthetic") -> Candidate:
        x, y = (float(point[0]), float(point[1]))
        loss = x * x + y * y
        violation = max(0.0, 0.6 - (x + y))
        return Candidate((x, y), loss, violation, violation == 0.0, source, evaluation)
