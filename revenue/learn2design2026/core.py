"""Deterministic, dependency-free optimization primitives for Learn2Design 2026.

This module deliberately contains no dfbench/JAX imports so the policy logic can be
hostile-tested without an accelerator runtime. The competition-facing adapter lives
in submission.py and consumes the same radius/restart rules.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import random
from typing import Iterable, Sequence

SCHEMA = "tjlabs.learn2design2026/core-v1"


class ContractError(ValueError):
    pass


@dataclass(frozen=True)
class Candidate:
    params: tuple[float, ...]
    loss: float
    violation: float
    feasible: bool
    source: str
    evaluation: int

    def __post_init__(self) -> None:
        if not self.params:
            raise ContractError("candidate params must be non-empty")
        if self.evaluation < 0:
            raise ContractError("evaluation must be non-negative")
        if self.violation < 0 or not math.isfinite(self.violation):
            raise ContractError("violation must be finite and non-negative")
        if any(not math.isfinite(x) for x in self.params):
            raise ContractError("params must be finite")
        if not isinstance(self.feasible, bool):
            raise ContractError("feasible must be bool")
        if self.feasible and self.violation != 0:
            raise ContractError("feasible candidate must have zero violation")
        if not self.source or len(self.source) > 80:
            raise ContractError("invalid candidate source")

    @property
    def finite_loss(self) -> bool:
        return math.isfinite(self.loss)


def rank_key(c: Candidate) -> tuple[float, ...]:
    """Fail-closed total order: finite -> feasible -> violation -> loss -> generation."""
    if not c.finite_loss:
        return (2.0, math.inf, math.inf, float(c.evaluation))
    if c.feasible:
        return (0.0, 0.0, c.loss, float(c.evaluation))
    return (1.0, c.violation, c.loss, float(c.evaluation))


def better(candidate: Candidate, incumbent: Candidate | None) -> bool:
    return incumbent is None or rank_key(candidate) < rank_key(incumbent)


def clip_point(point: Sequence[float], bounds: Sequence[tuple[float, float]]) -> tuple[float, ...]:
    if len(point) != len(bounds) or not point:
        raise ContractError("point/bounds dimension mismatch")
    out: list[float] = []
    for value, bound in zip(point, bounds):
        if len(bound) != 2:
            raise ContractError("every bound must be a pair")
        lo, hi = float(bound[0]), float(bound[1])
        if not (math.isfinite(lo) and math.isfinite(hi) and lo < hi):
            raise ContractError("invalid finite bound")
        v = float(value)
        if not math.isfinite(v):
            v = (lo + hi) / 2.0
        out.append(min(hi, max(lo, v)))
    return tuple(out)


def normalized_distance(a: Sequence[float], b: Sequence[float], bounds: Sequence[tuple[float, float]]) -> float:
    if len(a) != len(b) or len(a) != len(bounds) or not a:
        raise ContractError("distance dimension mismatch")
    total = 0.0
    for av, bv, (lo, hi) in zip(a, b, bounds):
        width = float(hi) - float(lo)
        if not (width > 0 and math.isfinite(width)):
            raise ContractError("invalid bound width")
        delta = (float(av) - float(bv)) / width
        total += delta * delta
    return math.sqrt(total / len(a))


def _first_primes(n: int) -> list[int]:
    if n <= 0:
        raise ContractError("dimension must be positive")
    primes: list[int] = []
    value = 2
    while len(primes) < n:
        if all(value % p for p in primes if p * p <= value):
            primes.append(value)
        value += 1
    return primes


def _radical_inverse(index: int, base: int) -> float:
    if index <= 0 or base <= 1:
        raise ContractError("invalid radical-inverse arguments")
    result = 0.0
    factor = 1.0 / base
    i = index
    while i:
        i, digit = divmod(i, base)
        result += digit * factor
        factor /= base
    return result


def halton_points(bounds: Sequence[tuple[float, float]], count: int, *, offset: int = 0) -> list[tuple[float, ...]]:
    """Deterministic low-discrepancy starts; offset permits distinct restart blocks."""
    if count < 0 or offset < 0:
        raise ContractError("count/offset must be non-negative")
    if not bounds:
        raise ContractError("bounds required")
    checked = clip_point([(lo + hi) / 2 for lo, hi in bounds], bounds)
    _ = checked
    primes = _first_primes(len(bounds))
    points: list[tuple[float, ...]] = []
    for row in range(count):
        idx = offset + row + 1
        point = []
        for (lo, hi), base in zip(bounds, primes):
            u = _radical_inverse(idx, base)
            point.append(float(lo) + u * (float(hi) - float(lo)))
        points.append(tuple(point))
    return points


def jitter_around(
    anchor: Sequence[float],
    bounds: Sequence[tuple[float, float]],
    *,
    radius: float,
    count: int,
    seed: int,
) -> list[tuple[float, ...]]:
    if not (0 < radius <= 1.0) or count < 0:
        raise ContractError("invalid jitter radius/count")
    anchor = clip_point(anchor, bounds)
    rng = random.Random(int(seed))
    out: list[tuple[float, ...]] = []
    for _ in range(count):
        proposal = []
        for value, (lo, hi) in zip(anchor, bounds):
            width = hi - lo
            proposal.append(value + rng.uniform(-radius, radius) * width)
        out.append(clip_point(proposal, bounds))
    return out


@dataclass
class RadiusController:
    radius: float = 0.25
    minimum: float = 0.002
    maximum: float = 0.75
    grow: float = 1.35
    shrink: float = 0.55
    successes_to_grow: int = 3
    failures_to_shrink: int = 5
    _successes: int = 0
    _failures: int = 0

    def __post_init__(self) -> None:
        if not (0 < self.minimum <= self.radius <= self.maximum <= 1):
            raise ContractError("invalid trust-region bounds")
        if not (self.grow > 1 and 0 < self.shrink < 1):
            raise ContractError("invalid trust-region multipliers")
        if self.successes_to_grow <= 0 or self.failures_to_shrink <= 0:
            raise ContractError("trust-region counters must be positive")

    def observe(self, improved: bool) -> float:
        if not isinstance(improved, bool):
            raise ContractError("improved must be bool")
        if improved:
            self._successes += 1
            self._failures = 0
            if self._successes >= self.successes_to_grow:
                self.radius = min(self.maximum, self.radius * self.grow)
                self._successes = 0
        else:
            self._failures += 1
            self._successes = 0
            if self._failures >= self.failures_to_shrink:
                self.radius = max(self.minimum, self.radius * self.shrink)
                self._failures = 0
        return self.radius

    def snapshot(self) -> dict[str, object]:
        return {
            "radius": self.radius,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "successes": self._successes,
            "failures": self._failures,
        }


@dataclass(frozen=True)
class BudgetPlan:
    total_evaluations: int
    exploration_evaluations: int
    local_evaluations: int
    restart_count: int
    evaluations_per_restart: int


def make_budget_plan(total_evaluations: int, *, exploration_fraction: float = 0.12, restart_count: int = 4) -> BudgetPlan:
    if type(total_evaluations) is not int or total_evaluations < 16:
        raise ContractError("total_evaluations must be an int >= 16")
    if not (0.0 < exploration_fraction < 0.5):
        raise ContractError("exploration_fraction must be in (0, 0.5)")
    if type(restart_count) is not int or restart_count <= 0 or restart_count > total_evaluations:
        raise ContractError("invalid restart_count")
    exploration = max(restart_count, int(total_evaluations * exploration_fraction))
    local = total_evaluations - exploration
    per = max(1, local // restart_count)
    return BudgetPlan(total_evaluations, exploration, local, restart_count, per)


def choose_elites(candidates: Iterable[Candidate], count: int) -> list[Candidate]:
    if count <= 0:
        raise ContractError("elite count must be positive")
    values = list(candidates)
    if not values:
        raise ContractError("candidates required")
    return sorted(values, key=lambda c: (rank_key(c), canonical_sha256(list(c.params))))[:count]


def canonical_json(value: object) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"not canonical-json data: {exc}") from exc


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def make_run_receipt(*, seed: int, plan: BudgetPlan, best: Candidate, radius: RadiusController, evidence_class: str) -> dict[str, object]:
    if evidence_class not in {"SYNTHETIC_LOCAL", "REAL_DFBENCH_PUBLIC", "OFFICIAL_HIDDEN"}:
        raise ContractError("invalid evidence class")
    body: dict[str, object] = {
        "schema": "tjlabs.learn2design2026/run-receipt-v1",
        "evidenceClass": evidence_class,
        "seed": int(seed),
        "plan": {
            "totalEvaluations": plan.total_evaluations,
            "explorationEvaluations": plan.exploration_evaluations,
            "localEvaluations": plan.local_evaluations,
            "restartCount": plan.restart_count,
            "evaluationsPerRestart": plan.evaluations_per_restart,
        },
        "best": {
            "paramsSha256": canonical_sha256(list(best.params)),
            "loss": best.loss,
            "violation": best.violation,
            "feasible": best.feasible,
            "source": best.source,
            "evaluation": best.evaluation,
        },
        "radius": radius.snapshot(),
        "authority": {
            "officialScoreClaimed": evidence_class == "OFFICIAL_HIDDEN",
            "prizeClaimed": False,
            "paymentClaimed": False,
            "submissionClaimed": False,
        },
    }
    if evidence_class != "OFFICIAL_HIDDEN":
        body["authority"]["officialScoreClaimed"] = False  # type: ignore[index]
    body["receiptSha256"] = canonical_sha256(body)
    return body
