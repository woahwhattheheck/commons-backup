"""Bounded floor-cycle candidate gating for TITAN E10.

This module does not assign economic value to a public-market state change.  It
only exposes the exact feasibility primitive for the verified Kaggriculture
BUY_PRODUCT/SELL floor transition and a conservative selector that requires a
strictly positive downstream value in every supplied scenario before emitting a
cycle candidate.

The engine contract this helper relies on is intentionally small:

* BUY_PRODUCT is legal only for WHEAT and FERTILIZER.
* A product buy is quoted at the post-buy public inventory.
* A $1 sale pays $1 but does not add the unit back to public market inventory.
* A successful buy deposits one unit into the shed before a following sale.

Callers remain responsible for obtaining scenario values from executable engine
transitions or rollouts.  Public inventory movement alone is not a value signal.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable, Mapping, Sequence

BUYABLE_PRODUCTS = frozenset({"WHEAT", "FERTILIZER"})
DEFAULT_HARD_PAIR_CAP = 2


@dataclass(frozen=True)
class FloorCycleState:
    """Observable resources needed to decide whether a floor pair can execute."""

    item: str
    inventory: int
    cash: float
    shed_units: int
    shed_capacity: int
    market_orders_used: int
    max_market_orders: int
    hard_pair_cap: int = DEFAULT_HARD_PAIR_CAP


@dataclass(frozen=True)
class FloorCycleDecision:
    """Robust scenario comparison for a bounded floor-cycle candidate."""

    pairs: int
    worst_gain: float
    mean_gain: float
    reason: str


def state_changing_pair_limit(
    state: FloorCycleState,
    quote: Callable[[str, int], int],
) -> int:
    """Return the maximum verified zero-cost, state-changing pairs available.

    For pair ``k`` (1-indexed), the buy is quoted at ``inventory - k``.  The
    immediately following sale is quoted at that same inventory.  Only a quote
    of exactly $1 makes the pair *state changing*: the buy removes one public
    unit and the floor sale pays but does not re-admit it.  Above the floor the
    sale re-admits the unit and the round trip restores the public state, so this
    helper stops before that boundary.

    One transient shed slot and $1 cash are sufficient for any admitted sequence
    because pairs are emitted BUY then SELL and every admitted quote is $1.
    Market order capacity and a small hard cap bound the sequence.
    """

    item = str(state.item).upper()
    if item not in BUYABLE_PRODUCTS:
        return 0
    if not math.isfinite(float(state.cash)) or state.cash < 1:
        return 0
    if state.shed_capacity <= 0 or state.shed_units < 0:
        return 0
    if state.shed_units >= state.shed_capacity:
        return 0
    if state.inventory <= 0:
        return 0

    free_orders = max(0, int(state.max_market_orders) - int(state.market_orders_used))
    cap = min(
        max(0, int(state.hard_pair_cap)),
        free_orders // 2,
        int(state.inventory),
    )
    admitted = 0
    for pair_index in range(1, cap + 1):
        post_buy_inventory = int(state.inventory) - pair_index
        if int(quote(item, post_buy_inventory)) != 1:
            break
        admitted = pair_index
    return admitted


def floor_cycle_orders(item: str, pairs: int) -> list[list[object]]:
    """Emit an alternating BUY_PRODUCT/SELL sequence for a verified pair count."""

    canonical = str(item).upper()
    count = int(pairs)
    if canonical not in BUYABLE_PRODUCTS:
        raise ValueError(f"BUY_PRODUCT is not legal for {canonical!r}")
    if count < 0:
        raise ValueError("pairs must be non-negative")
    orders: list[list[object]] = []
    for _ in range(count):
        orders.append(["BUY_PRODUCT", canonical, 1])
        orders.append(["SELL", canonical, 1])
    return orders


def choose_robust_pairs(
    max_pairs: int,
    scenario_values: Mapping[int, Mapping[str, float]],
    *,
    min_worst_gain: float = 0.0,
) -> FloorCycleDecision:
    """Choose a bounded pair count only when every scenario strictly improves.

    ``scenario_values[0]`` is the no-cycle baseline.  Candidate rows must cover
    exactly the same named scenarios.  Values are caller-defined downstream
    economic outcomes (for example terminal score, rollout value, or a matchup
    utility that was actually evaluated).  A candidate is eligible only when its
    worst scenario delta is strictly greater than ``min_worst_gain``.

    Ties prefer the larger worst gain, then larger mean gain, then fewer pairs so
    an economically equivalent choice consumes fewer market order slots.
    """

    limit = max(0, int(max_pairs))
    baseline = scenario_values.get(0)
    if not baseline:
        return FloorCycleDecision(0, 0.0, 0.0, "no comparable baseline scenarios")

    scenario_names = tuple(sorted(str(name) for name in baseline))
    baseline_values: dict[str, float] = {}
    for name in scenario_names:
        value = float(baseline[name])
        if not math.isfinite(value):
            return FloorCycleDecision(0, 0.0, 0.0, "baseline contains a non-finite value")
        baseline_values[name] = value

    best: tuple[tuple[float, float, int], FloorCycleDecision] | None = None
    for pairs in range(1, limit + 1):
        row = scenario_values.get(pairs)
        if row is None or set(map(str, row)) != set(scenario_names):
            continue
        deltas: list[float] = []
        valid = True
        for name in scenario_names:
            value = float(row[name])
            if not math.isfinite(value):
                valid = False
                break
            deltas.append(value - baseline_values[name])
        if not valid or not deltas:
            continue
        worst = min(deltas)
        mean = sum(deltas) / len(deltas)
        if not worst > float(min_worst_gain):
            continue
        decision = FloorCycleDecision(pairs, worst, mean, "strictly positive in every scenario")
        rank = (worst, mean, -pairs)
        if best is None or rank > best[0]:
            best = (rank, decision)

    if best is None:
        return FloorCycleDecision(0, 0.0, 0.0, "no robust downstream economic gain")
    return best[1]


def screened_floor_cycle(
    state: FloorCycleState,
    quote: Callable[[str, int], int],
    scenario_values: Mapping[int, Mapping[str, float]],
    *,
    min_worst_gain: float = 0.0,
) -> tuple[FloorCycleDecision, list[list[object]]]:
    """Combine exact floor feasibility with the conservative value screen."""

    feasible = state_changing_pair_limit(state, quote)
    decision = choose_robust_pairs(
        feasible,
        scenario_values,
        min_worst_gain=min_worst_gain,
    )
    return decision, floor_cycle_orders(state.item, decision.pairs)
