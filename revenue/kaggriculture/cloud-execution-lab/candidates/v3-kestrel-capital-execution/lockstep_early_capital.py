# SPDX-License-Identifier: Apache-2.0
"""Rival-lockstep safety wrapper for the KESTREL early-capital candidate.

The predecessor proves a proposed market permutation against the player's own
queue.  The official engine instead quotes both players from one pre-commit
market at every queue index, so own-only replay is not by itself a proof.

This successor admits only a narrow rival-independent shape: sale-only products
followed by one fixed-cost capital order, with no effectful order after it.  It
also reconstructs the post-unit state with the official aggregate same-crop
PLANT prepass when the caller has no captured snapshot.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import json
import math
from typing import Any

from kestrel_early_capital import order_early_capital as _predecessor_order

BUYABLE_PRODUCTS = frozenset(("WHEAT", "FERTILIZER"))
CAPITAL_OPS = frozenset(("BUY_LAND", "BUY_ANIMAL"))
_MAX_CERTIFIED_SHED_CAPACITY = 256


def _configuration_value(configuration: Mapping | None, key: str, default: Any) -> Any:
    if isinstance(configuration, Mapping):
        return configuration.get(key, default)
    return default


def _unit_actions(selected: Mapping) -> list[Any]:
    farmer = selected.get("farmer", ["PASS"])
    hands = selected.get("hands", [])
    if not isinstance(hands, list):
        hands = []
    return [farmer, *hands]


def _atomic_post_unit_snapshot(
    mechanics: Any,
    observation: Mapping,
    configuration: Mapping | None,
    selected: Mapping,
) -> dict:
    """Reconstruct the official completed own unit stage.

    The interpreter first totals PLANT demand by crop.  When demand exceeds the
    seed ledger, every request for that crop becomes PASS.  Farmer and hand
    actions are applied only after that atomic prepass.
    """
    if not isinstance(observation, Mapping) or not isinstance(selected, Mapping):
        raise ValueError("malformed unit replay input")
    farms_source = observation.get("farms")
    private_source = observation.get("private")
    if not isinstance(farms_source, list) or not isinstance(private_source, Mapping):
        raise ValueError("missing own unit state")
    player_raw = observation.get("player", 0)
    if isinstance(player_raw, bool):
        raise ValueError("invalid player")
    player = int(player_raw)
    if player < 0 or player >= len(farms_source):
        raise ValueError("invalid player")

    farms = deepcopy(farms_source)
    private = deepcopy(dict(private_source))
    farm = farms[player]
    if not isinstance(farm, dict):
        raise ValueError("invalid farm")
    tiles = farm.get("tiles")
    if not isinstance(tiles, list) or not tiles:
        raise ValueError("missing farm tiles")

    turns_per_day = max(
        1,
        int(_configuration_value(configuration, "turnsPerDay", 24)),
    )
    board_size = int(
        _configuration_value(configuration, "boardSize", len(tiles))
    )
    shed_capacity = int(
        _configuration_value(configuration, "shedCapacity", 100)
    )
    step_raw = observation.get("step", 0)
    if isinstance(step_raw, bool):
        raise ValueError("invalid step")
    day = int(step_raw) // turns_per_day

    apply_unit = getattr(mechanics, "_apply_unit_action", None)
    if not callable(apply_unit):
        raise ValueError("mechanics lacks unit replay")

    actions = _unit_actions(selected)
    demand: dict[Any, int] = {}
    for action in actions:
        if isinstance(action, list) and len(action) >= 2 and action[0] == "PLANT":
            crop = action[1]
            try:
                demand[crop] = demand.get(crop, 0) + 1
            except TypeError as exc:
                raise ValueError("unhashable crop") from exc

    seeds = private.get("seeds", {})
    if not isinstance(seeds, Mapping):
        raise ValueError("missing seed ledger")
    blocked = set()
    for crop, requested in demand.items():
        available = seeds.get(crop, 0)
        if isinstance(available, bool) or not isinstance(available, (int, float)):
            raise ValueError("invalid seed quantity")
        if not math.isfinite(float(available)):
            raise ValueError("invalid seed quantity")
        if requested > available:
            blocked.add(crop)

    for index, action in enumerate(actions):
        allowed = action
        if (
            isinstance(action, list)
            and len(action) >= 2
            and action[0] == "PLANT"
            and action[1] in blocked
        ):
            allowed = ["PASS"]
        apply_unit(
            farm,
            private,
            index,
            allowed,
            board_size,
            day,
            turns_per_day,
            shed_capacity,
        )

    return {
        "farms": farms,
        "private": private,
        "player": player,
        "step": int(step_raw),
    }


def _canonical_order(order: Any) -> str:
    try:
        return json.dumps(
            order,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("uncanonicalizable market order") from exc


def _same_order_multiset(left: list[Any], right: list[Any]) -> bool:
    if len(left) != len(right):
        return False
    return sorted(_canonical_order(order) for order in left) == sorted(
        _canonical_order(order) for order in right
    )


def _is_pass(order: Any) -> bool:
    return order is None or order == [] or order == ["PASS"]


def _order_op(order: Any) -> str:
    if _is_pass(order):
        return "PASS"
    if isinstance(order, list) and order and isinstance(order[0], str):
        return order[0]
    return "MALFORMED"


def _sell_parts(order: Any) -> tuple[str, int] | None:
    if not (isinstance(order, list) and order and order[0] == "SELL"):
        return None
    if len(order) < 3 or not isinstance(order[1], str) or not order[1]:
        raise ValueError("malformed SELL")
    quantity = order[2]
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
        raise ValueError("invalid SELL quantity")
    return order[1], quantity


def _sale_units_never_move_later(
    original: list[Any], candidate: list[Any], products: set[str]
) -> bool:
    """Require cumulative requested units per product to be no later.

    Counting rows is insufficient: swapping a ten-unit sale with a one-unit sale
    can move nine units later while leaving the row count unchanged.
    """
    before = {product: 0 for product in products}
    after = {product: 0 for product in products}
    for original_order, candidate_order in zip(original, candidate):
        original_sale = _sell_parts(original_order)
        candidate_sale = _sell_parts(candidate_order)
        if original_sale is not None and original_sale[0] in before:
            before[original_sale[0]] += original_sale[1]
        if candidate_sale is not None and candidate_sale[0] in after:
            after[candidate_sale[0]] += candidate_sale[1]
        if any(after[product] < before[product] for product in products):
            return False
    return before == after


def _checked_market_price(
    mechanics: Any,
    item: str,
    inventory: int,
    params: Mapping | None,
) -> float:
    price = mechanics.market_price(item, inventory, params)
    if isinstance(price, bool) or not isinstance(price, (int, float)):
        raise ValueError("non-numeric market price")
    value = float(price)
    if not math.isfinite(value) or value < 1:
        raise ValueError("invalid market price")
    return value


def _rival_lockstep_certificate(
    mechanics: Any,
    observation: Mapping,
    configuration: Mapping | None,
    original_action: Mapping,
    candidate_action: Mapping,
) -> tuple[bool, dict]:
    """Prove own-turn non-regression for every legal hidden rival queue.

    The proof deliberately does not claim the locally observed capital gain
    survives every rival queue.  It proves that an original own execution cannot
    be lost: candidate sale units occur no later, and the sole effectful order
    after them is one fixed-cost capital purchase.
    """
    report: dict[str, Any] = {
        "schema": 2,
        "kind": "single-terminal-capital-sale-only",
        "certified": False,
        "barriers": [],
        "products": [],
    }
    if not isinstance(original_action, Mapping) or not isinstance(candidate_action, Mapping):
        report["barriers"].append("malformed_action")
        return False, report
    original_market = original_action.get("market")
    candidate_market = candidate_action.get("market")
    if not isinstance(original_market, list) or not isinstance(candidate_market, list):
        report["barriers"].append("malformed_market")
        return False, report

    try:
        limit = max(
            1,
            int(_configuration_value(configuration, "maxMarketOrdersPerTurn", 10)),
        )
        capacity = int(_configuration_value(configuration, "shedCapacity", 100))
    except (TypeError, ValueError, OverflowError):
        report["barriers"].append("invalid_configuration")
        return False, report
    report["active_prefix_limit"] = limit
    report["shed_capacity"] = capacity
    if capacity < 1 or capacity > _MAX_CERTIFIED_SHED_CAPACITY:
        report["barriers"].append("unsupported_shed_capacity")
        return False, report

    original_active = original_market[:limit]
    candidate_active = candidate_market[:limit]
    if original_market[limit:] != candidate_market[limit:]:
        report["barriers"].append("inactive_tail_changed")
    try:
        if not _same_order_multiset(original_active, candidate_active):
            report["barriers"].append("active_prefix_membership_changed")
    except ValueError:
        report["barriers"].append("uncanonicalizable_order")

    original_capital: list[tuple[int, Any]] = []
    candidate_capital: list[tuple[int, Any]] = []
    products: set[str] = set()

    for side, active, capital in (
        ("original", original_active, original_capital),
        ("candidate", candidate_active, candidate_capital),
    ):
        for index, order in enumerate(active):
            try:
                sale = _sell_parts(order)
            except ValueError:
                report["barriers"].append(f"invalid_sell:{side}:{index}")
                continue
            if sale is not None:
                products.add(sale[0])
                if sale[0] in BUYABLE_PRODUCTS:
                    report["barriers"].append(f"rival_buyable_sale:{sale[0]}")
                continue
            if _is_pass(order):
                continue
            op = _order_op(order)
            if op in CAPITAL_OPS:
                capital.append((index, order))
            else:
                report["barriers"].append(f"unsupported_active_op:{op}")

    report["products"] = sorted(products)
    if len(original_capital) != 1 or len(candidate_capital) != 1:
        report["barriers"].append("requires_exactly_one_capital_order")
    elif _canonical_order(original_capital[0][1]) != _canonical_order(candidate_capital[0][1]):
        report["barriers"].append("capital_order_changed")
    else:
        original_index, capital_order = original_capital[0]
        candidate_index = candidate_capital[0][0]
        report["capital"] = {
            "op": capital_order[0],
            "item": capital_order[1] if len(capital_order) > 1 else None,
            "quantity": capital_order[2] if len(capital_order) > 2 else 1,
            "original_index": original_index,
            "candidate_index": candidate_index,
        }
        for index in range(candidate_index + 1, len(candidate_active)):
            if not _is_pass(candidate_active[index]):
                report["barriers"].append("effectful_order_after_capital")
                break

    try:
        if not _sale_units_never_move_later(
            original_active, candidate_active, products
        ):
            report["barriers"].append("sale_units_moved_later")
    except ValueError:
        report["barriers"].append("invalid_sell_quantity")

    market = observation.get("market") if isinstance(observation, Mapping) else None
    inventory = market.get("inventory") if isinstance(market, Mapping) else None
    prices = market.get("prices") if isinstance(market, Mapping) else None
    params = market.get("params") if isinstance(market, Mapping) else None
    if (
        not isinstance(market, Mapping)
        or not isinstance(inventory, Mapping)
        or not isinstance(prices, Mapping)
        or (params is not None and not isinstance(params, Mapping))
    ):
        report["barriers"].append("malformed_public_market")
        return False, report

    curve_checks: dict[str, dict[str, Any]] = {}
    horizon = 2 * capacity
    for item in sorted(products):
        if item in BUYABLE_PRODUCTS:
            continue
        start = inventory.get(item)
        visible = prices.get(item)
        if (
            isinstance(start, bool)
            or not isinstance(start, int)
            or isinstance(visible, bool)
            or not isinstance(visible, (int, float))
            or not math.isfinite(float(visible))
            or float(visible) < 1
        ):
            report["barriers"].append(f"invalid_public_quote:{item}")
            continue
        try:
            curve = [
                _checked_market_price(mechanics, item, start + offset, params)
                for offset in range(horizon + 1)
            ]
        except (ArithmeticError, KeyError, LookupError, TypeError, ValueError, OverflowError):
            report["barriers"].append(f"unavailable_price_curve:{item}")
            continue
        if curve[0] != float(visible):
            report["barriers"].append(f"stale_public_quote:{item}")
        if any(later > earlier for earlier, later in zip(curve, curve[1:])):
            report["barriers"].append(f"nonmonotone_price_curve:{item}")
        curve_checks[item] = {
            "inventory_start": start,
            "inventory_end": start + horizon,
            "visible_price": float(visible),
            "end_price": curve[-1],
            "samples": horizon + 1,
        }
    report["curve_checks"] = curve_checks
    report["barriers"] = sorted(set(report["barriers"]))
    report["certified"] = not report["barriers"]
    if report["certified"]:
        report["proof"] = (
            "The active queue contains only sale-only products, PASS rows, and "
            "one fixed-cost capital order. Every requested own sale unit occurs "
            "no later than before; rivals cannot buy those products, and their "
            "supply can only move a checked nonincreasing price curve downward. "
            "Thus cash and freed shed capacity before the sole capital order are "
            "never worse than the original under the same rival queue. No "
            "effectful own order follows capital, so extra capital execution "
            "cannot steal resources from an original own execution."
        )
        report["strength_boundary"] = (
            "The public-state capital gain is not claimed for every rival queue; "
            "paired official games remain the strength gate."
        )
    return report["certified"], report


def order_early_capital(
    mechanics: Any,
    observation: Mapping,
    configuration: Mapping | None,
    selected: Any,
    route: Any,
    decisions: Any = (),
    *,
    post_unit: Mapping | None = None,
):
    """Run KESTREL, then admit only a rival-lockstep-safe changed queue."""
    bound_post_unit = post_unit
    generated = False
    if post_unit is None and isinstance(selected, Mapping):
        try:
            bound_post_unit = _atomic_post_unit_snapshot(
                mechanics, observation, configuration, selected
            )
            generated = True
        except (
            ArithmeticError, KeyError, TypeError, ValueError, OverflowError,
            AttributeError,
        ) as error:
            report = {
                "changed": False,
                "reason": "atomic_unit_replay_unavailable",
                "revision": "v3-rival-lockstep-safe",
                "simulation_error": type(error).__name__,
                "post_unit_binding": "unavailable",
            }
            return selected, report

    result, report = _predecessor_order(
        mechanics,
        observation,
        configuration,
        selected,
        route,
        decisions,
        post_unit=bound_post_unit,
    )
    report = deepcopy(report) if isinstance(report, dict) else {"predecessor_report": report}
    report["revision"] = "v3-rival-lockstep-safe"
    report["post_unit_binding"] = (
        "official_atomic_unit_replay" if generated else "caller_snapshot"
    )

    if result == selected:
        report["lockstep_certificate"] = {
            "schema": 2,
            "certified": True,
            "kind": "identity",
            "proof": "No market bytes changed.",
        }
        return result, report

    certified, certificate = _rival_lockstep_certificate(
        mechanics,
        observation,
        configuration,
        selected,
        result,
    )
    report["lockstep_certificate"] = certificate
    if certified:
        report["reason"] = "rival_lockstep_nonregression_proved"
        return result, report

    report["pre_lockstep_reason"] = report.get("reason")
    report["reason"] = "rival_interleaving_unproven"
    report["changed"] = False
    report["moved"] = 0
    return selected, report


__all__ = [
    "BUYABLE_PRODUCTS",
    "CAPITAL_OPS",
    "_atomic_post_unit_snapshot",
    "_rival_lockstep_certificate",
    "_sale_units_never_move_later",
    "order_early_capital",
]
