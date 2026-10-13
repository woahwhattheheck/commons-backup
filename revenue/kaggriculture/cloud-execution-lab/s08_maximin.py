"""Deterministic five-scenario maximin decision contract for TITAN S08.

This module is intentionally separate from the live seller planner while E04/E18
own overlapping core paths.  It consumes values produced by an executable
market/economic evaluator; it does not infer value from cash reserves, quote
movement, or hidden rival state.

Funding, survival, and inherited-order preservation are feasibility constraints.
Among feasible candidates, expected-value and maximin strategies rank the same
five public rival-response scenarios.  Ties preserve the canonical candidate.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping, Sequence

SCENARIOS = (
    "no_rival",
    "incumbent_forecast",
    "mirror",
    "max_rival_buy",
    "max_rival_sell",
)


@dataclass(frozen=True)
class Candidate:
    """One already-evaluated plan and its hard feasibility evidence."""

    name: str
    values: Mapping[str, float]
    funding_ok: bool = True
    survival_ok: bool = True
    inherited_orders_preserved: bool = True
    inherited_slots: int = 0
    total_slots: int = 0
    max_slots: int = 10

    @property
    def added_slots(self) -> int:
        return max(0, int(self.total_slots) - int(self.inherited_slots))


@dataclass(frozen=True)
class Decision:
    strategy: str
    candidate: str
    worst_value: float
    expected_value: float
    worst_gain_vs_canonical: float
    expected_gain_vs_canonical: float
    added_slots: int
    reason: str


def preserves_inherited_prefix(
    inherited: Sequence[Sequence[object]],
    proposed: Sequence[Sequence[object]],
    max_slots: int,
) -> bool:
    """Require byte/order-equivalent inherited orders as an exact queue prefix."""

    limit = int(max_slots)
    if limit < 0 or len(proposed) > limit or len(proposed) < len(inherited):
        return False
    return all(tuple(got) == tuple(want) for got, want in zip(proposed, inherited))


def candidate_from_queue(
    *,
    name: str,
    values: Mapping[str, float],
    inherited: Sequence[Sequence[object]],
    proposed: Sequence[Sequence[object]],
    max_slots: int,
    funding_ok: bool = True,
    survival_ok: bool = True,
) -> Candidate:
    """Construct a candidate while making queue preservation auditable."""

    return Candidate(
        name=name,
        values=values,
        funding_ok=funding_ok,
        survival_ok=survival_ok,
        inherited_orders_preserved=preserves_inherited_prefix(inherited, proposed, max_slots),
        inherited_slots=len(inherited),
        total_slots=len(proposed),
        max_slots=int(max_slots),
    )


def _vector(candidate: Candidate) -> tuple[float, ...] | None:
    if set(candidate.values) != set(SCENARIOS):
        # Every candidate must cover the same fixed public scenario panel.
        return None
    out = tuple(float(candidate.values[name]) for name in SCENARIOS)
    return out if all(math.isfinite(value) for value in out) else None


def feasible(candidate: Candidate) -> bool:
    """Apply only hard constraints; spare cash is never a ranking bonus."""

    return (
        bool(candidate.funding_ok)
        and bool(candidate.survival_ok)
        and bool(candidate.inherited_orders_preserved)
        and int(candidate.inherited_slots) >= 0
        and int(candidate.total_slots) >= int(candidate.inherited_slots)
        and int(candidate.total_slots) <= int(candidate.max_slots)
        and _vector(candidate) is not None
    )


def _weights(weights: Mapping[str, float] | None) -> tuple[float, ...]:
    if weights is None:
        return tuple(1.0 / len(SCENARIOS) for _ in SCENARIOS)
    if set(weights) != set(SCENARIOS):
        raise ValueError("weights must cover exactly the five S08 scenarios")
    raw = tuple(float(weights[name]) for name in SCENARIOS)
    if not all(math.isfinite(value) and value >= 0 for value in raw):
        raise ValueError("weights must be finite and non-negative")
    total = sum(raw)
    if total <= 0:
        raise ValueError("weights must have positive total mass")
    return tuple(value / total for value in raw)


def _stats(candidate: Candidate, normalized_weights: tuple[float, ...]) -> tuple[float, float]:
    vector = _vector(candidate)
    if vector is None:
        raise ValueError("candidate does not contain a valid five-scenario vector")
    return min(vector), sum(value * weight for value, weight in zip(vector, normalized_weights))


def _decision(
    strategy: str,
    winner: Candidate,
    canonical: Candidate,
    normalized_weights: tuple[float, ...],
    reason: str,
) -> Decision:
    worst, expected = _stats(winner, normalized_weights)
    base_worst, base_expected = _stats(canonical, normalized_weights)
    return Decision(
        strategy=strategy,
        candidate=winner.name,
        worst_value=worst,
        expected_value=expected,
        worst_gain_vs_canonical=worst - base_worst,
        expected_gain_vs_canonical=expected - base_expected,
        added_slots=winner.added_slots,
        reason=reason,
    )


def choose(
    candidates: Sequence[Candidate],
    *,
    strategy: str,
    canonical_name: str = "canonical",
    weights: Mapping[str, float] | None = None,
) -> Decision:
    """Choose expected-value or maximin winner from the exact same panel.

    Ranking never includes cash-on-hand.  Funding/survival are booleans supplied
    by the executable feasibility layer.  After economic objectives, fewer added
    slots wins.  If a challenger is economically tied with canonical, canonical
    is retained even if it uses more slots; S08 is not allowed to rewrite a live
    queue without measurable value.
    """

    if strategy not in {"expected", "maximin"}:
        raise ValueError("strategy must be 'expected' or 'maximin'")
    normalized_weights = _weights(weights)
    by_name = {candidate.name: candidate for candidate in candidates}
    if len(by_name) != len(candidates):
        raise ValueError("candidate names must be unique")
    canonical = by_name.get(canonical_name)
    if canonical is None or not feasible(canonical):
        raise ValueError("canonical candidate must exist and be feasible")

    valid = [candidate for candidate in candidates if feasible(candidate)]
    base_worst, base_expected = _stats(canonical, normalized_weights)

    def objective(candidate: Candidate) -> tuple[float, float, int]:
        worst, expected = _stats(candidate, normalized_weights)
        if strategy == "maximin":
            return (worst, expected, -candidate.added_slots)
        return (expected, worst, -candidate.added_slots)

    best = canonical
    best_objective = objective(canonical)
    for candidate in sorted(valid, key=lambda c: c.name):
        if candidate.name == canonical_name:
            continue
        worst, expected = _stats(candidate, normalized_weights)
        # Exact economic tie with canonical is an intentional no-op regardless
        # of queue-shape differences.
        if worst == base_worst and expected == base_expected:
            continue
        rank = objective(candidate)
        if rank > best_objective:
            best, best_objective = candidate, rank

    reason = "canonical retained: no feasible measurable improvement" if best is canonical else (
        "maximized worst realizable value" if strategy == "maximin" else "maximized weighted expected value"
    )
    return _decision(strategy, best, canonical, normalized_weights, reason)


def compare(
    candidates: Sequence[Candidate],
    *,
    canonical_name: str = "canonical",
    weights: Mapping[str, float] | None = None,
) -> dict[str, Decision]:
    """Return canonical, expected-value, and maximin decisions side-by-side."""

    normalized_weights = _weights(weights)
    by_name = {candidate.name: candidate for candidate in candidates}
    canonical = by_name.get(canonical_name)
    if canonical is None or not feasible(canonical):
        raise ValueError("canonical candidate must exist and be feasible")
    baseline = _decision(
        "canonical",
        canonical,
        canonical,
        normalized_weights,
        "unchanged canonical market plan",
    )
    return {
        "canonical": baseline,
        "expected": choose(candidates, strategy="expected", canonical_name=canonical_name, weights=weights),
        "maximin": choose(candidates, strategy="maximin", canonical_name=canonical_name, weights=weights),
    }
