# SPDX-License-Identifier: Apache-2.0
"""Propose a complete existing producer route, never isolated animal purchases.

The quote screen is a deterministic heuristic, NOT a cash-feasibility certificate
or a calibrated proceeds forecast. Every future planned sale is marked at the
current quote; missing future stock and changing rival activity are not modeled.
Exact action queues, nominal cash troughs and source route IDs are exposed so an
existing search/production owner can supply its own evaluator without a new
controller, simulator or route generator.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

MAIN = "7015cc00acfa4922"
SHEEP = "dc76e4003029ac51"
DECISION_STEP = 226


@dataclass(frozen=True)
class RouteQuote:
    route_id: str
    final_marked_cash: float
    minimum_marked_cash: float
    first_negative: tuple[int, int] | None
    receipts: float
    purchases: float
    labor: float
    land: float
    orders: tuple[dict[str, Any], ...]


def _number(value: Any) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Economic inputs must be finite")
    return result


def _hire_price(count: int, multiplier: float) -> float:
    # The exact engine's Fibonacci schedule: first two hires cost mult each.
    a, b = 1, 1
    for _ in range(count):
        a, b = b, a + b
    return a * multiplier


def quote_program(route_id: str, route: Sequence[Mapping[str, Any]],
                  observation: Mapping[str, Any], configuration: Mapping[str, Any],
                  mechanics: Any) -> RouteQuote:
    """Mark a dated full program, charging every ordered input/labor/land purchase.

    This deliberately does not claim that scheduled goods will physically exist.
    Costs are exact fixed prices or *current* marginal replacement quotes. Hires
    assume prior scheduled hires filled; min cash is nominal, not guaranteed.
    The terminal non-executed route element is excluded using episodeSteps - 1.
    """
    now = int(observation["step"])
    day_length = max(1, int(configuration.get("turnsPerDay", 24)))
    end = min(len(route), int(configuration.get("episodeSteps", 720)) - 1)
    max_orders = max(1, int(configuration.get("maxMarketOrdersPerTurn", 10)))
    farm = observation["farms"][int(observation["player"])]
    market = observation["market"]
    prices, inventory = market["prices"], market["inventory"]
    params = mechanics._resolve_market_params(configuration.get("marketParams", {}))
    cash = minimum = _number(farm["money"])
    hires, day = int(farm["hires_today"]), now // day_length
    multiplier = _number(configuration.get("farmHandCostMult", 1))
    extra_land = max(0, len(farm["unlocked_quadrants"]) - 1)
    receipts = purchases = labor = land = 0.0
    first_negative = None
    marked = []
    for step in range(now, end):
        if step // day_length != day:
            hires, day = 0, step // day_length
        for slot, order in enumerate((route[step].get("market") or [])[:max_orders]):
            if not order:
                continue
            op = order[0]
            item = order[1] if len(order) > 1 else None
            quantity = max(0, int(order[2])) if len(order) > 2 else 1
            delta = 0.0
            if op == "SELL":
                delta = quantity * _number(prices[item]); receipts += delta
            elif op == "BUY_ANIMAL":
                delta = -quantity * _number(mechanics.ANIMALS[item]["cost"]); purchases -= delta
            elif op == "BUY_SEED":
                delta = -quantity * _number(mechanics.CROPS[item]["seed"]); purchases -= delta
            elif op == "BUY_PRODUCT":
                # Replacement quote is at post-buy inventory, as in the engine.
                delta = -sum(_number(mechanics.market_price(item, int(inventory[item]) - n - 1, params))
                             for n in range(quantity))
                purchases -= delta
            elif op == "HIRE":
                delta = -_hire_price(hires, multiplier); hires += 1; labor -= delta
            elif op == "BUY_LAND":
                if extra_land < len(mechanics.LAND_PRICES):
                    delta = -_number(mechanics.LAND_PRICES[extra_land]); extra_land += 1; land -= delta
            elif op != "PASS":
                raise ValueError(f"Unsupported program order: {op}")
            cash += delta
            minimum = min(minimum, cash)
            if cash < 0 and first_negative is None:
                first_negative = (step, slot)
            marked.append({"step": step, "slot": slot, "order": list(order),
                           "delta": delta, "marked_cash": cash})
    return RouteQuote(route_id, cash, minimum, first_negative, receipts,
                      purchases, labor, land, tuple(marked))


def quote_screen(offers: Sequence[RouteQuote], observation: Mapping[str, Any]) -> str:
    """Use a higher marked surplus only when its nominal ordered budget stays >= 0."""
    current = offers[0]
    best = current
    for offer in offers[1:]:
        if offer.minimum_marked_cash >= 0 and offer.final_marked_cash > best.final_marked_cash:
            best = offer
    return best.route_id


def choose_before_action(controller: Any, observation: Mapping[str, Any],
                         configuration: Mapping[str, Any], mechanics: Any,
                         selector: Callable[[Sequence[RouteQuote], Mapping[str, Any]], str] = quote_screen
                         ) -> dict[str, Any]:
    """Choose on the supplied original controller BEFORE its one ordinary call.

    No parent is instantiated/called here and no action/route table is rewritten.
    Existing later public-feature decisions remain owned by that controller.
    Integration with a different producer requires its own compatible-state test.
    """
    old = controller.cur
    report: dict[str, Any] = {"changed": False, "before": old, "after": old,
                              "reason": "outside_checkpoint"}
    if int(observation.get("step", -1)) != DECISION_STEP or old != MAIN:
        return report
    if SHEEP not in controller.R or not controller._switch_ok(SHEEP, DECISION_STEP):
        report["reason"] = "no_matching_complete_tail"
        return report
    try:
        offers = tuple(quote_program(key, controller.R[key], observation, configuration, mechanics)
                       for key in (old, SHEEP))
        chosen = selector(offers, observation)
        if chosen not in (old, SHEEP):
            report["reason"] = "no_offered_choice"
            return report
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        report.update(reason="unpriced_program", detail=type(exc).__name__)
        return report
    controller.cur = chosen
    report.update(changed=chosen != old, after=chosen, reason="quote_screen",
                  forecast_kind="nominal_current_quote_not_realized_proceeds",
                  marked_delta=offers[1].final_marked_cash-offers[0].final_marked_cash,
                  offers=[{"route_id": v.route_id, "final_marked_cash": v.final_marked_cash,
                           "minimum_marked_cash": v.minimum_marked_cash,
                           "first_negative": v.first_negative, "receipts": v.receipts,
                           "purchases": v.purchases, "labor": v.labor, "land": v.land}
                          for v in offers])
    return report
