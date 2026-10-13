# SPDX-License-Identifier: Apache-2.0
"""Bounded E11 economics/receipt evaluator for livestock feed supply.

This module is an evaluator only. It does not call TITAN's producer, mutate a
route, execute an environment, or read opponent-private state. The producer
supplies already-authored pickup/feed continuations and their completed economic
value. The helper compares the physical/economic cost of keeping owned WHEAT,
buying WHEAT into the shed before a later pickup, or receiving producer-owned
WHEAT from a separately certified route.

The engine orders unit actions before market orders. Therefore an arrival from a
BUY_PRODUCT order at step t is deliberately unavailable to a pickup at step t;
it may support a pickup only at a later step. The same conservative strict
ordering is used for producer-owned arrivals, avoiding invented same-turn
cross-actor transfers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class FeedService:
    """One actor-owned pickup/feed suffix already authored by the producer.

    ``feed_steps`` contains only feeds whose physical route is already certified.
    Feeds before ``pickup_step`` must be covered by ``carried_wheat``. A pickup
    consumes its full *actual* fill (up to ``pickup_quantity``), so surplus picked
    by an earlier actor is not silently returned to shared shed stock.

    ``completion_value`` is supplied by the existing producer/economic layer and
    must include only value that can be realized by ``value_realization_step``.
    This module never invents future animal output, sales, shop unlocks or cash.
    """
    actor: int
    pickup_step: int | None
    pickup_quantity: int
    feed_steps: tuple[int, ...]
    carried_wheat: int = 0
    completion_value: float = 0.0
    value_realization_step: int | None = None
    animal: str | None = None
    consecutive_unfed: int = 0
    escape_deadline_step: int | None = None


@dataclass(frozen=True)
class SupplyArrival:
    """WHEAT physically present in the shed *after* ``step``."""
    step: int
    units: int
    source: str


@dataclass(frozen=True)
class FeedSupplyCandidate:
    """A supply alternative compared without changing producer-owned unit work."""
    key: str
    mode: str
    initial_shed_wheat: int
    arrivals: tuple[SupplyArrival, ...] = ()
    costs: Mapping[str, float] = field(default_factory=dict)
    funded: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)


def _whole(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def _step(value: Any, name: str, *, minimum: int = 0) -> int:
    result = _whole(value, name)
    if result < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return result


def _money(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} cannot be a boolean")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{name} must be a finite nonnegative number")
    return result


def _market_params(mechanics: Any, observation: Mapping[str, Any]) -> Any:
    overrides = observation["market"].get("params")
    resolver = getattr(mechanics, "_resolve_market_params", None)
    if callable(resolver):
        return resolver(overrides)
    return overrides or mechanics.MARKET_PARAMS


def simulate_current_wheat_buy(
    mechanics: Any,
    observation: Mapping[str, Any],
    quantity: int,
    *,
    cash_available: float,
    shed_room: int,
    prior_wheat_buy_units: int = 0,
    rival_wheat_buy_stress: int = 0,
) -> dict[str, Any]:
    """Simulate our current BUY_PRODUCT WHEAT fill at one queue insertion point.

    The caller supplies cash and shed room *at the insertion point* after all
    earlier own queue obligations. ``rival_wheat_buy_stress`` is an explicit
    public/scenario stress, not inferred hidden inventory. Each successful unit
    uses the official current quote and then reduces market inventory by one,
    exactly matching BUY_PRODUCT price impact. A request can partially fill when
    cash or capacity becomes binding.
    """
    requested = _whole(quantity, "quantity")
    room = _whole(shed_room, "shed_room")
    prior = _whole(prior_wheat_buy_units, "prior_wheat_buy_units")
    rival = _whole(rival_wheat_buy_stress, "rival_wheat_buy_stress")
    cash = _money(cash_available, "cash_available")
    inventory = _whole(observation["market"]["inventory"]["WHEAT"], "market.inventory.WHEAT")
    inventory -= prior + rival
    params = _market_params(mechanics, observation)

    prices: list[int] = []
    spent = 0.0
    reason = "requested_fill_complete"
    for _ in range(requested):
        if len(prices) >= room:
            reason = "shed_capacity_partial_fill"
            break
        price = int(mechanics.market_price("WHEAT", inventory, params))
        if price < 0:
            raise ValueError("market_price returned a negative price")
        if spent + price > cash:
            reason = "cash_partial_fill"
            break
        prices.append(price)
        spent += price
        # Official BUY_PRODUCT commits one unit to the shed and removes one unit
        # from public market inventory after each successful unit.
        inventory -= 1

    return {
        "requested_units": requested,
        "filled_units": len(prices),
        "unit_prices": prices,
        "cash_spent": spent,
        "cash_remaining": cash - spent,
        "inventory_after_fill": inventory,
        "fill_reason": reason,
        "future_sale_cash_credit": 0,
        "same_turn_pickup_credit": 0,
        "rival_wheat_buy_stress": rival,
        "prior_wheat_buy_units": prior,
    }


def current_buy_candidate(
    mechanics: Any,
    observation: Mapping[str, Any],
    quantity: int,
    *,
    key: str = "buy-current",
    cash_available: float,
    shed_room: int,
    prior_wheat_buy_units: int = 0,
    rival_wheat_buy_stress: int = 0,
    other_costs: Mapping[str, float] | None = None,
) -> FeedSupplyCandidate:
    """Create a candidate whose successful units arrive after the current market."""
    report = simulate_current_wheat_buy(
        mechanics,
        observation,
        quantity,
        cash_available=cash_available,
        shed_room=shed_room,
        prior_wheat_buy_units=prior_wheat_buy_units,
        rival_wheat_buy_stress=rival_wheat_buy_stress,
    )
    costs = {"purchase_cash": report["cash_spent"]}
    for name, value in (other_costs or {}).items():
        costs[str(name)] = _money(value, f"other_costs.{name}")
    now = _step(observation["step"], "step")
    arrivals = ()
    if report["filled_units"]:
        arrivals = (SupplyArrival(now, report["filled_units"], "current_market_buy"),)
    return FeedSupplyCandidate(
        key=key,
        mode="buy",
        initial_shed_wheat=0,
        arrivals=arrivals,
        costs=costs,
        funded=report["filled_units"] > 0 or _whole(quantity, "quantity") == 0,
        metadata=report,
    )


def exact_wheat_sale_receipts(
    mechanics: Any,
    observation: Mapping[str, Any],
    quantity: int,
    *,
    prior_wheat_sell_units: int = 0,
    rival_wheat_sell_stress: int = 0,
) -> dict[str, Any]:
    """Exact own sequential receipts for a current WHEAT sale counterfactual."""
    requested = _whole(quantity, "quantity")
    prior = _whole(prior_wheat_sell_units, "prior_wheat_sell_units")
    rival = _whole(rival_wheat_sell_stress, "rival_wheat_sell_stress")
    inventory = _whole(observation["market"]["inventory"]["WHEAT"], "market.inventory.WHEAT")
    inventory += prior + rival
    params = _market_params(mechanics, observation)
    floor = int(getattr(mechanics, "PRICE_FLOOR", 1))
    prices: list[int] = []
    for _ in range(requested):
        price = int(mechanics.market_price("WHEAT", inventory, params))
        prices.append(price)
        # Official SELL at the $1 floor does not add public supply.
        if price > floor:
            inventory += 1
    return {
        "units": requested,
        "unit_prices": prices,
        "receipts": float(sum(prices)),
        "inventory_after_sale": inventory,
        "rival_wheat_sell_stress": rival,
        "prior_wheat_sell_units": prior,
    }


def retained_wheat_candidate(
    mechanics: Any,
    observation: Mapping[str, Any],
    units: int,
    *,
    key: str = "retain-owned",
    prior_wheat_sell_units: int = 0,
    rival_wheat_sell_stress: int = 0,
    other_costs: Mapping[str, float] | None = None,
) -> FeedSupplyCandidate:
    """Value retaining owned WHEAT by the exact current sale receipts forgone."""
    kept = _whole(units, "units")
    sale = exact_wheat_sale_receipts(
        mechanics,
        observation,
        kept,
        prior_wheat_sell_units=prior_wheat_sell_units,
        rival_wheat_sell_stress=rival_wheat_sell_stress,
    )
    costs = {"foregone_current_sale_receipts": sale["receipts"]}
    for name, value in (other_costs or {}).items():
        costs[str(name)] = _money(value, f"other_costs.{name}")
    return FeedSupplyCandidate(
        key=key,
        mode="retain",
        initial_shed_wheat=kept,
        costs=costs,
        metadata={"sale_counterfactual": sale},
    )


def _validated_service(service: FeedService, now: int, terminal: int) -> dict[str, Any]:
    actor = _whole(service.actor, "service.actor")
    carried = _whole(service.carried_wheat, "service.carried_wheat")
    pickup_quantity = _whole(service.pickup_quantity, "service.pickup_quantity")
    feed_steps = tuple(_step(value, "service.feed_step", minimum=now) for value in service.feed_steps)
    if tuple(sorted(feed_steps)) != feed_steps:
        raise ValueError("service.feed_steps must be sorted")
    pickup = None if service.pickup_step is None else _step(service.pickup_step, "service.pickup_step", minimum=now)
    if pickup is None and pickup_quantity:
        raise ValueError("pickup_quantity requires pickup_step")
    completion = _money(service.completion_value, "service.completion_value")
    realization = (
        terminal if service.value_realization_step is None
        else _step(service.value_realization_step, "service.value_realization_step", minimum=now)
    )
    consecutive = _whole(service.consecutive_unfed, "service.consecutive_unfed")
    escape = None if service.escape_deadline_step is None else _step(
        service.escape_deadline_step, "service.escape_deadline_step", minimum=now
    )
    return {
        "actor": actor,
        "carried": carried,
        "pickup": pickup,
        "pickup_quantity": pickup_quantity,
        "feed_steps": feed_steps,
        "completion_value": completion,
        "realization": realization,
        "consecutive_unfed": consecutive,
        "escape_deadline": escape,
        "animal": service.animal,
        "terminal": terminal,
    }


def evaluate_feed_supply(
    services: Sequence[FeedService],
    candidate: FeedSupplyCandidate,
    *,
    now: int,
    terminal_step: int,
) -> dict[str, Any]:
    """Evaluate one supply candidate against complete producer-owned feed suffixes."""
    current = _step(now, "now")
    terminal = _step(terminal_step, "terminal_step", minimum=current)
    costs = {str(name): _money(value, f"costs.{name}") for name, value in candidate.costs.items()}
    total_cost = sum(costs.values())
    if candidate.mode not in ("retain", "buy", "make", "inherited"):
        raise ValueError("candidate.mode must be retain, buy, make, or inherited")
    shared = _whole(candidate.initial_shed_wheat, "candidate.initial_shed_wheat")
    arrivals = []
    for arrival in candidate.arrivals:
        step = _step(arrival.step, "arrival.step", minimum=current)
        units = _whole(arrival.units, "arrival.units")
        arrivals.append((step, units, str(arrival.source)))
    arrivals.sort()
    validated = [_validated_service(service, current, terminal) for service in services]
    validated.sort(key=lambda row: (
        terminal + 1 if row["pickup"] is None else row["pickup"],
        row["actor"],
    ))

    base = {
        "key": candidate.key,
        "mode": candidate.mode,
        "costs": costs,
        "total_supply_cost": total_cost,
        "funded": bool(candidate.funded),
        "metadata": dict(candidate.metadata),
    }
    if not candidate.funded:
        return {
            **base,
            "physical": False,
            "admissible": False,
            "reason": "candidate_not_funded",
            "completion_value": 0.0,
            "net_completed_value": float("-inf"),
            "service_reports": [],
        }

    for row in validated:
        if row["realization"] > terminal:
            return {
                **base,
                "physical": False,
                "admissible": False,
                "reason": "service_value_realizes_after_terminal",
                "completion_value": 0.0,
                "net_completed_value": float("-inf"),
                "service_reports": [],
            }
        if any(step > terminal for step in row["feed_steps"]):
            return {
                **base,
                "physical": False,
                "admissible": False,
                "reason": "feed_after_terminal",
                "completion_value": 0.0,
                "net_completed_value": float("-inf"),
                "service_reports": [],
            }
        if row["consecutive_unfed"] >= 1:
            if row["escape_deadline"] is None:
                return {
                    **base,
                    "physical": False,
                    "admissible": False,
                    "reason": "missing_escape_deadline",
                    "completion_value": 0.0,
                    "net_completed_value": float("-inf"),
                    "service_reports": [],
                }
            if not row["feed_steps"] or row["feed_steps"][0] > row["escape_deadline"]:
                return {
                    **base,
                    "physical": False,
                    "admissible": False,
                    "reason": "feed_misses_escape_deadline",
                    "completion_value": 0.0,
                    "net_completed_value": float("-inf"),
                    "service_reports": [],
                }

    pending = list(arrivals)
    service_reports = []
    unused_carried = 0
    total_completion_value = 0.0
    for row in validated:
        pickup = row["pickup"]
        carried = row["carried"]
        feeds = row["feed_steps"]
        if pickup is None:
            pre_pickup = len(feeds)
        else:
            pre_pickup = sum(1 for step in feeds if step < pickup)
        if carried < pre_pickup:
            return {
                **base,
                "physical": False,
                "admissible": False,
                "reason": "feed_before_pickup_uncovered",
                "completion_value": 0.0,
                "net_completed_value": float("-inf"),
                "service_reports": service_reports,
            }
        carried_after_early_feeds = carried - pre_pickup
        suffix_need = len(feeds) - pre_pickup
        actual_pickup = 0
        if pickup is not None:
            # Market buys and producer deliveries at the same step happen too
            # late for this conservative pickup certificate. Only prior arrivals
            # become shared shed stock.
            matured = [arrival for arrival in pending if arrival[0] < pickup]
            if matured:
                shared += sum(units for _, units, _ in matured)
                pending = [arrival for arrival in pending if arrival[0] >= pickup]
            actual_pickup = min(row["pickup_quantity"], shared)
            shared -= actual_pickup
        actor_available = carried_after_early_feeds + actual_pickup
        if actor_available < suffix_need:
            reason = "same_turn_arrival_cannot_supply_pickup" if (
                pickup is not None and any(step == pickup and units > 0 for step, units, _ in pending)
            ) else "pickup_fill_does_not_cover_feed_suffix"
            return {
                **base,
                "physical": False,
                "admissible": False,
                "reason": reason,
                "completion_value": 0.0,
                "net_completed_value": float("-inf"),
                "service_reports": service_reports + [{
                    "actor": row["actor"],
                    "pickup_step": pickup,
                    "requested_pickup": row["pickup_quantity"],
                    "actual_pickup": actual_pickup,
                    "required_feed_units": len(feeds),
                    "carried_wheat": carried,
                    "animal": row["animal"],
                }],
            }
        unused = actor_available - suffix_need
        unused_carried += unused
        total_completion_value += row["completion_value"]
        service_reports.append({
            "actor": row["actor"],
            "animal": row["animal"],
            "pickup_step": pickup,
            "requested_pickup": row["pickup_quantity"],
            "actual_pickup": actual_pickup,
            "feed_steps": list(feeds),
            "required_feed_units": len(feeds),
            "carried_wheat": carried,
            "unused_actor_wheat_after_feeds": unused,
            "completion_value": row["completion_value"],
            "value_realization_step": row["realization"],
            "consecutive_unfed": row["consecutive_unfed"],
            "escape_deadline_step": row["escape_deadline"],
        })

    # Arrivals after every pickup are real supply but cannot be credited to any
    # completed service in this candidate.
    unused_future_arrivals = sum(units for _, units, _ in pending)
    net = total_completion_value - total_cost
    admissible = bool(validated) and net > 0
    return {
        **base,
        "physical": True,
        "admissible": admissible,
        "reason": "positive_completed_service_value" if admissible else (
            "no_feed_service" if not validated else "nonpositive_completed_service_value"
        ),
        "completion_value": total_completion_value,
        "net_completed_value": net,
        "shared_shed_wheat_after_pickups": shared,
        "unused_actor_wheat_after_feeds": unused_carried,
        "unused_future_arrivals": unused_future_arrivals,
        "service_reports": service_reports,
    }


def choose_feed_supply(
    services: Sequence[FeedService],
    candidates: Sequence[FeedSupplyCandidate],
    *,
    inherited_key: str,
    now: int,
    terminal_step: int,
) -> dict[str, Any]:
    """Choose a strictly better positive completed-service value or keep inherited."""
    reports = [
        evaluate_feed_supply(services, candidate, now=now, terminal_step=terminal_step)
        for candidate in candidates
    ]
    inherited = next((report for report in reports if report["key"] == inherited_key), None)
    if inherited is None:
        raise ValueError("inherited_key must name one supplied candidate")
    feasible = [report for report in reports if report["admissible"]]
    if not feasible:
        return {
            "changed": False,
            "reason": "no_positive_complete_supply_candidate",
            "chosen": inherited_key,
            "reports": reports,
        }
    best = max(feasible, key=lambda report: report["net_completed_value"])
    inherited_value = inherited["net_completed_value"] if inherited["admissible"] else float("-inf")
    if best["key"] == inherited_key or best["net_completed_value"] <= inherited_value:
        return {
            "changed": False,
            "reason": "inherited_complete_service_is_best",
            "chosen": inherited_key,
            "reports": reports,
        }
    return {
        "changed": True,
        "reason": "strictly_better_complete_feed_supply",
        "chosen": best["key"],
        "reports": reports,
    }
