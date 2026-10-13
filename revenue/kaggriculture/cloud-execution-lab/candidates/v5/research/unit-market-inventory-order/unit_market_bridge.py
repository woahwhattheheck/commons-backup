# SPDX-License-Identifier: Apache-2.0
"""Default-off V5 research transform for unit-before-market inventory ordering.

The pinned engine executes all farmer/hand unit actions before any market rows.
This helper changes only the final supplied unit action, and only when every
preceding supplied unit action is shed-inert, so the pre-final shed state is the
observed shed state. It never touches operating inputs (WHEAT/FERTILIZER).
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

PRODUCTS = (
    "WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
    "EGG", "MILK", "WOOL", "FERTILIZER",
)
SALE_ONLY = frozenset(item for item in PRODUCTS if item not in {"WHEAT", "FERTILIZER"})
_SHED_OPS = frozenset({"DROP", "PICKUP", "PLACE"})


def _report(reason: str, **extra: Any) -> dict[str, Any]:
    return {"classification": "NO_OP" if not extra else "ENGAGED", "reason": reason, **extra}


def _plain_positive(config: Mapping[str, Any], key: str, default: int) -> int | None:
    value = config.get(key, default)
    if type(value) is not int or value <= 0:
        return None
    return value


def _sell_demand(market: Any, cap: int) -> dict[str, int] | None:
    if not isinstance(market, list):
        return {}
    demand: dict[str, int] = {}
    for row in market[:cap]:
        if not isinstance(row, list) or not row:
            continue
        if row[0] != "SELL" or len(row) < 3:
            continue
        item = row[1]
        if item not in SALE_ONLY:
            continue
        try:
            quantity = int(row[2])
        except (TypeError, ValueError, OverflowError):
            return None
        if quantity <= 0:
            continue
        demand[item] = demand.get(item, 0) + quantity
    return demand


def _shed_inert(action: Any) -> bool:
    return not (isinstance(action, list) and action and action[0] in _SHED_OPS)


def _shed_adjacent(pos: Any, board_size: int) -> bool:
    if not isinstance(pos, (list, tuple)) or len(pos) < 2:
        return False
    x, y = pos[0], pos[1]
    if type(x) is not int or type(y) is not int:
        return False
    half = board_size // 2
    return (x, y) in {
        (half - 1, half - 1), (half, half - 1),
        (half - 1, half), (half, half),
    }


def _nonnegative_inventory(raw: Any) -> dict[str, int] | None:
    if type(raw) is not dict:
        return None
    result: dict[str, int] = {}
    for key, value in raw.items():
        if type(key) is not str or type(value) is not int or value < 0:
            return None
        result[key] = value
    return result


def transform(
    selected: Any,
    farm: Any,
    private: Any,
    configuration: Mapping[str, Any] | None = None,
) -> tuple[Any, dict[str, Any]]:
    """Return a default-off unit/market ordering experiment and deterministic report."""
    if type(selected) is not dict or type(farm) is not dict or type(private) is not dict:
        return selected, _report("malformed_parent")
    if configuration is not None and not isinstance(configuration, Mapping):
        return selected, _report("malformed_config")
    config = {} if configuration is None else dict(configuration)
    board_size = _plain_positive(config, "boardSize", 10)
    market_cap = _plain_positive(config, "maxMarketOrdersPerTurn", 10)
    shed_capacity = _plain_positive(config, "shedCapacity", 100)
    if board_size is None or market_cap is None or shed_capacity is None:
        return selected, _report("malformed_config")

    demand = _sell_demand(selected.get("market", []), market_cap)
    if demand is None:
        return selected, _report("malformed_sell_quantity")
    if not demand:
        return selected, _report("no_sale_only_sell")

    farmer_action = selected.get("farmer", ["PASS"])
    hands_actions = selected.get("hands", [])
    if not isinstance(hands_actions, list):
        return selected, _report("malformed_hands")
    unit_actions = [farmer_action, *hands_actions]
    if not unit_actions:
        return selected, _report("no_unit_action")
    if not all(_shed_inert(action) for action in unit_actions[:-1]):
        return selected, _report("earlier_shed_mutation")

    final_idx = len(unit_actions) - 1
    if final_idx == 0:
        position = farm.get("farmer")
    else:
        hands = farm.get("hands")
        if not isinstance(hands, list) or final_idx - 1 >= len(hands):
            return selected, _report("missing_final_worker")
        position = hands[final_idx - 1]
    if not _shed_adjacent(position, board_size):
        return selected, _report("final_worker_not_shed_adjacent")

    shed = _nonnegative_inventory(private.get("shed"))
    inventories = private.get("inventories")
    if shed is None or not isinstance(inventories, list) or final_idx >= len(inventories):
        return selected, _report("malformed_private_inventory")
    final_inventory = _nonnegative_inventory(inventories[final_idx])
    if final_inventory is None:
        return selected, _report("malformed_final_inventory")
    shed_total = sum(shed.values())
    if shed_total > shed_capacity:
        return selected, _report("shed_over_capacity")

    final_action = unit_actions[-1]
    replacement = None
    report: dict[str, Any] | None = None

    if isinstance(final_action, list) and final_action and final_action[0] == "PASS":
        room = shed_capacity - shed_total
        candidates = []
        if room > 0:
            for item in sorted(demand):
                shortage = max(0, demand[item] - shed.get(item, 0))
                carried = final_inventory.get(item, 0)
                quantity = min(shortage, carried, room)
                if quantity > 0:
                    candidates.append((item, quantity, shortage))
        if len(candidates) != 1:
            return selected, _report("ambiguous_or_no_pass_bridge")
        item, quantity, shortage = candidates[0]
        replacement = ["PLACE", item, quantity]
        report = {
            "classification": "ENGAGED",
            "reason": "place_sale_shortfall",
            "worker_index": final_idx,
            "item": item,
            "quantity": quantity,
            "sell_demand": demand[item],
            "pre_unit_shed": shed.get(item, 0),
            "shortfall": shortage,
        }

    elif isinstance(final_action, list) and final_action and final_action[0] == "PICKUP":
        if len(final_action) < 2 or final_action[1] not in SALE_ONLY:
            return selected, _report("pickup_not_sale_only")
        item = final_action[1]
        if demand.get(item, 0) <= 0:
            return selected, _report("pickup_item_not_sold")
        try:
            requested = int(final_action[2]) if len(final_action) >= 3 else 1
        except (TypeError, ValueError, OverflowError):
            return selected, _report("malformed_pickup_quantity")
        if requested <= 0:
            return selected, _report("engine_inert_pickup")
        stock = shed.get(item, 0)
        effective = min(requested, stock)
        reserve = min(demand[item], stock)
        max_take = max(0, stock - reserve)
        if effective <= max_take:
            return selected, _report("pickup_preserves_sale_stock")
        if max_take == 0:
            replacement = ["PASS"]
        else:
            replacement = list(final_action)
            if len(replacement) >= 3:
                replacement[2] = max_take
            else:
                replacement.append(max_take)
        report = {
            "classification": "ENGAGED",
            "reason": "reserve_sale_stock",
            "worker_index": final_idx,
            "item": item,
            "original_effective_pickup": effective,
            "replacement_pickup": max_take,
            "sell_demand": demand[item],
            "pre_unit_shed": stock,
        }
    else:
        return selected, _report("final_action_not_bridgeable")

    out = deepcopy(selected)
    if final_idx == 0:
        out["farmer"] = replacement
    else:
        out_hands = out.get("hands")
        out_hands[-1] = replacement
    return out, report
