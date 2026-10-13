# SPDX-License-Identifier: Apache-2.0
"""Optional sale-floor funding callback for the existing seed certificate.

This module never changes the default certificate. It may admit a demand-valid
seed reduction only after the existing certificate has validated every input and
rejected solely because the original queue needs additional cash.
"""
from __future__ import annotations
from copy import deepcopy
from typing import Any, Mapping

import seed_funding as base


def _whole(value: Any, name: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _quantity(order: Any) -> int:
    if not isinstance(order, list) or len(order) < 3:
        raise ValueError("quantity order must be a list with three fields")
    quantity = _whole(order[2], "quantity")
    if quantity > 99_998:
        raise ValueError("quantity reaches the interpreter's unit-loop boundary")
    return quantity


def _sale_funded_prefixes(mechanics: Any, observation: Mapping[str, Any],
                          orders: list[Any], maximum: int,
                          costs: list[Mapping[str, Any]], money: int) -> dict[str, Any]:
    """Lower-bound original-queue cash using already-owned sale stock only."""
    floor = _whole(mechanics.PRICE_FLOOR, "sale price floor", 1)
    shed = observation["private"]["shed"]
    remaining = {item: _whole(shed.get(item, 0), "observed sale stock")
                 for item in mechanics.PRODUCTS}
    by_slot = {row["slot"]: row["cost_upper_bound"] for row in costs}
    cash_floor, receipts, minimum = money, 0, money
    prefixes: list[dict[str, Any]] = []
    for slot, order in enumerate(orders[:maximum]):
        cost = by_slot.get(slot, 0)
        before = cash_floor
        cash_floor -= cost
        minimum = min(minimum, cash_floor)
        if cash_floor < 0:
            return {"funded": False, "reason": "original_prefix_needs_additional_cash",
                    "failed_slot": slot, "minimum_prefix_cash_floor": minimum,
                    "guaranteed_sale_receipts": receipts, "prefixes": prefixes}
        quantity = credit = 0
        if isinstance(order, list) and order and order[0] == "SELL":
            item = order[1]
            quantity = min(_quantity(order), remaining[item])
            remaining[item] -= quantity
            credit = floor * quantity
            cash_floor += credit
            receipts += credit
        prefixes.append({"slot": slot, "cash_floor_before": before,
                         "cost_upper_bound": cost, "sale_units_lower_bound": quantity,
                         "sale_credit_lower_bound": credit, "cash_floor_after": cash_floor})
    return {"funded": True, "reason": "original_prefixes_funded_with_sale_floor",
            "minimum_prefix_cash_floor": minimum, "cash_floor_after_queue": cash_floor,
            "guaranteed_sale_receipts": receipts, "prefixes": prefixes}


def select_seed_queue(mechanics: Any, post_unit_observation: Mapping[str, Any],
                      baseline_action: Mapping[str, Any], proposed_action: Mapping[str, Any],
                      configuration: Mapping[str, Any] | None = None, *,
                      fallback_action: Mapping[str, Any] | None = None,
                      public_product_bounds: bool = False,
                      guaranteed_sale_credit: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    """Delegate to the current certificate, optionally adding sale-floor credit."""
    chosen, report = base.select_seed_queue(
        mechanics, post_unit_observation, baseline_action, proposed_action, configuration,
        fallback_action=fallback_action, public_product_bounds=public_product_bounds)
    if not guaranteed_sale_credit or report.get("status") == "certified":
        return chosen, report
    if report.get("reason") != "original_queue_needs_additional_cash":
        return chosen, report
    try:
        config = dict(configuration or {})
        maximum = max(1, _whole(config.get("maxMarketOrdersPerTurn", 10), "order limit"))
        funding = _sale_funded_prefixes(
            mechanics, post_unit_observation, list(baseline_action.get("market", [])),
            maximum, list(report["prefixes"]), _whole(report["observed_cash"], "own cash"))
    except (AttributeError, IndexError, KeyError, TypeError, ValueError, OverflowError) as error:
        enriched = deepcopy(report)
        enriched["sale_floor_funding"] = {"funded": False, "reason": str(error)}
        return chosen, enriched
    enriched = deepcopy(report)
    enriched["sale_floor_funding"] = funding
    if not funding["funded"]:
        return chosen, enriched
    enriched.update(status="certified", reason="original_prefixes_funded_with_sale_floor",
                    minimum_cash_floor_without_sales=enriched["minimum_cash_floor"],
                    minimum_cash_floor=funding["minimum_prefix_cash_floor"],
                    non_seed_execution_preserved=True,
                    paired_current_market_cash_delta=enriched["seed_cash_reduction"])
    return deepcopy(dict(proposed_action)), enriched


def select_sale_funded_seed_queue(mechanics: Any, post_unit_observation: Mapping[str, Any],
                                  baseline_action: Mapping[str, Any], proposed_action: Mapping[str, Any],
                                  configuration: Mapping[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Five-argument callback for the existing ``seed_queue_selector`` seam."""
    return select_seed_queue(mechanics, post_unit_observation, baseline_action,
                             proposed_action, configuration, guaranteed_sale_credit=True)
