# SPDX-License-Identifier: Apache-2.0
"""Infer bounded PREVIOUS-turn rival market flow from public observations.

Source semantics: Kaggriculture engine Git blob
3c202c7ee921da239356789e266b694635103fc4. Research support, not a policy.

The caller must provide two consecutive observations from the SAME episode and
player, plus the exact final own action submitted between them. A step pair is
not an episode identity proof. No opponent private state/current action is read.
No row placement, cash receipt, opponent intent, or next-turn forecast is inferred.

Let D = next public inventory - previous public inventory + NPC consumption.
The pinned engine gives D = own effective net supply + rival effective net supply.
Effective supply counts a SELL only when its executed quote exceeds $1, and counts
a BUY_PRODUCT as -1. Own requested fills bound, but do not prove, own execution.
The result intersects those bounds with the engine's per-row iteration ceiling.

For sell-only products, a final pre-town quote above $1 proves every sale changed
public supply, making the interval a gross-sale interval. A price-floor sale can
be invisible: a zero residual is NOT evidence of zero rival selling.
"""
from __future__ import annotations

import math
from typing import Any

ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
MAX_SLOT_UNITS = 99_999
PRODUCTS = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG",
            "MILK", "WOOL", "FERTILIZER")
BUYABLE = frozenset(("WHEAT", "FERTILIZER"))
SHOPS = {
    "BAKERY": ("EGG", "WHEAT"),
    "PIZZA_SHOP": ("MILK", "TOMATO", "WHEAT"),
    "BRUNCH_SPOT": ("EGG", "WHEAT", "STRAWBERRY"),
    "YARN_STORE": ("WOOL",),
    "ICE_CREAM_SHOP": ("STRAWBERRY", "MILK", "WHEAT"),
    "PET_CAFE": ("CARROT",),
    "SMOOTHIE_SHOP": ("STRAWBERRY", "MILK"),
    "FARMERS_MARKET": ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY"),
}
# The engine defaults, retained to verify the supported price-curve domain.
_CURVES = {
    "WHEAT": (25, 400, "sqrt", .80, "log", .20),
    "CARROT": (35, 450, "hinge", 1.00, "sqrt", .70),
    "TOMATO": (60, 200, "hinge", .40, "sqrt", .60),
    "STRAWBERRY": (120, 100, "sqrt", .70, "linear", 1.60),
    "MELON": (250, 300, "log", .20, "sq", 3.60),
    "EGG": (50, 332, "hinge", .40, "log", .20),
    "MILK": (160, 122, "sqrt", .60, "linear", 1.60),
    "WOOL": (200, 105, "log", .20, "sq", 3.20),
    "FERTILIZER": (100, 200, "linear", .40, "linear", .40),
}
DEFAULT_PARAMS = {
    item: dict(base=p[0], I0=10_000, T=p[1], below_func=p[2],
               below_target=p[3], above_func=p[4], above_target=p[5])
    for item, p in _CURVES.items()
}


def _integer(value: Any, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(name)
    return value


def _shape(kind: str, value: float, scale: int) -> float:
    x = max(0.0, value)
    if kind == "linear":
        return x
    if kind == "sq":
        return x * x
    if kind == "sqrt":
        return math.sqrt(x)
    if kind == "log":
        return math.log(1.0 + x)
    if kind == "hinge":
        u = x / scale
        return u + 8.0 * max(0.0, u - 1.0) ** 2
    raise ValueError("unsupported_curve")


def default_price(item: str, inventory: int) -> int:
    """Pinned default quote; no configurable curve is silently approximated."""
    p = DEFAULT_PARAMS[item]
    below = inventory < p["I0"]
    side = "below" if below else "above"
    kind = p[side + "_func"]
    amp = p[side + "_target"] * p["base"] / _shape(kind, p["T"], p["T"])
    adjustment = amp * _shape(kind, abs(inventory - p["I0"]), p["T"])
    return max(1, int(round(p["base"] + adjustment if below else p["base"] - adjustment)))


def _market(observation: dict[str, Any]) -> dict[str, int]:
    market = observation.get("market")
    if type(market) is not dict:
        raise ValueError("market_shape")
    params = market.get("params")
    if params not in (None, {}) and params != DEFAULT_PARAMS:
        raise ValueError("unsupported_market_params")
    inventory = market.get("inventory")
    prices = market.get("prices")
    if type(inventory) is not dict or type(prices) is not dict:
        raise ValueError("market_shape")
    out = {}
    for item in PRODUCTS:
        # Negative public stock is legal. The numerical bound is this utility's
        # conservative supported domain, not an engine stock rule.
        stock = _integer(inventory.get(item), "inventory_domain", -10**9, 10**9)
        quote = _integer(prices.get(item), "quote_domain", 1, 10**18)
        if quote != default_price(item, stock):
            raise ValueError("price_snapshot_mismatch")
        out[item] = stock
    return out


def _own_bounds(action: Any, limit: int) -> tuple[dict[str, int], dict[str, int]]:
    sells, buys = dict.fromkeys(PRODUCTS, 0), dict.fromkeys(PRODUCTS, 0)
    if type(action) is not dict:
        if action is None or type(action) in (list, str, int, float, bool):
            return sells, buys  # The pinned engine treats a non-dict as empty.
        raise ValueError("action_shape")
    rows = action.get("market", [])
    if type(rows) is not list:
        if rows is None or type(rows) in (dict, str, int, float, bool):
            return sells, buys
        raise ValueError("queue_shape")
    # The raw cap is BEFORE parsing. Never compact malformed/atomic slots.
    for row in rows[:limit]:
        if isinstance(row, list) and type(row) is not list:
            raise ValueError("nonliteral_order")
        if type(row) is not list or len(row) < 3:
            continue
        op, item = row[:2]
        literal = (str, int, float, bool, list, dict, type(None))
        if type(op) not in literal or type(item) not in literal:
            raise ValueError("nonliteral_order")
        if type(op) is not str or op not in ("SELL", "BUY_PRODUCT"):
            continue
        if type(row[2]) not in literal:
            raise ValueError("nonliteral_quantity")
        try:
            requested = int(row[2])  # Includes bool/string/float, as engine does.
        except (TypeError, ValueError):
            continue
        except OverflowError:
            raise ValueError("order_quantity_overflow") from None
        if requested <= 0 or type(item) is not str:
            continue
        quantity = min(requested, MAX_SLOT_UNITS)
        if op == "SELL" and item in sells:
            sells[item] += quantity
        elif op == "BUY_PRODUCT" and item in BUYABLE:
            buys[item] += quantity
    return sells, buys


def infer_public_market_flow(before: Any, after: Any, own_submitted_action: Any,
                             configuration: Any = None) -> dict[str, Any]:
    """Return simultaneous conservative per-product rival-flow intervals.

    `status=ok` proves only the conditional observation/action accounting.
    Every interval contains the real flow for an authentic supported transition;
    intervals across products are NOT independently achievable scenario paths.
    `status=unknown` supplies no usable flow evidence. Input objects are untouched.
    """
    try:
        if type(before) is not dict or type(after) is not dict:
            raise ValueError("observation_shape")
        cfg = {} if configuration is None else configuration
        if type(cfg) is not dict:
            raise ValueError("configuration_shape")
        if cfg.get("marketParams") not in (None, {}):
            raise ValueError("unsupported_market_params")
        episode = _integer(cfg.get("episodeSteps", 720), "episode_domain", 2, 10**6)
        limit = _integer(cfg.get("maxMarketOrdersPerTurn", 10), "order_cap_domain", 1, 100)
        shop_tick = _integer(cfg.get("townShopSellInterval", 4), "shop_interval_domain", 1, 10**6)
        center_tick = _integer(cfg.get("townCenterSellInterval", 24), "center_interval_domain", 1, 10**6)
        step = _integer(before.get("step"), "step_domain", 0, episode - 2)
        next_step = _integer(after.get("step"), "next_step_domain", 1, episode - 1)
        if next_step != step + 1:
            raise ValueError("nonconsecutive_transition")
        player = _integer(before.get("player"), "player_domain", 0, 1)
        if _integer(after.get("player"), "player_domain", 0, 1) != player:
            raise ValueError("player_changed")
        start, end = _market(before), _market(after)
        town = before.get("town")
        if type(town) is not dict or type(town.get("unlocked_shops")) is not list:
            raise ValueError("town_shape")
        shops = town["unlocked_shops"]
        if len(shops) > 8 or any(type(s) is not str or s not in SHOPS for s in shops):
            raise ValueError("shop_domain")
        sold, bought = _own_bounds(own_submitted_action, limit)
        drain = dict.fromkeys(PRODUCTS, 0)
        # Use the completed step and PRE-transition shops: end-of-day shop
        # unlock occurs later than this turn's town consumption.
        if step % shop_tick == 0:
            for shop in shops:
                products = SHOPS[shop]
                multiplier = 2 if len(products) == 1 else 1
                for item in products:
                    drain[item] += multiplier
        if step % center_tick == 0:
            for item in PRODUCTS:
                if item != "FERTILIZER":
                    drain[item] += 1
        rival_ceiling = limit * MAX_SLOT_UNITS
        products_out = {}
        for item in PRODUCTS:
            residual = end[item] - start[item] + drain[item]
            lower = max(residual - sold[item], -rival_ceiling if item in BUYABLE else 0)
            upper = min(residual + bought[item], rival_ceiling)
            if item not in BUYABLE:
                upper = min(upper, residual)
            if lower > upper:
                raise ValueError("inconsistent_public_flow:" + item)
            final_market_stock = end[item] + drain[item]
            final_quote = default_price(item, final_market_stock)
            gross_identifiable = item not in BUYABLE and final_quote > 1
            sales_lower = max(0, lower)
            sales_upper = upper if gross_identifiable else rival_ceiling
            products_out[item] = {
                "public_inventory_delta": end[item] - start[item],
                "town_consumption": drain[item],
                "combined_effective_net_supply": residual,
                "own_requested_sell_upper": sold[item],
                "own_requested_buy_upper": bought[item],
                "rival_net_supply_lower": lower,
                "rival_net_supply_upper": upper,
                "rival_sales_lower": sales_lower,
                "rival_sales_upper": sales_upper,
                "rival_buys_lower": max(0, -upper) if item in BUYABLE else 0,
                "rival_buys_upper": rival_ceiling if item in BUYABLE else 0,
                "rival_exact_sales": sales_lower if sales_lower == sales_upper else None,
                "pre_town_final_quote": final_quote,
                "gross_sales_identifiable_from_net": gross_identifiable,
                "buy_sell_netting_possible": item in BUYABLE,
                "floor_censoring_possible": not gross_identifiable,
                "row_index": None,
            }
        return {"status": "ok", "engine_blob": ENGINE_BLOB,
                "completed_step": step, "available_at_step": next_step,
                "player": player, "evidence_kind": "completed_turn_only",
                "products": products_out}
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        return {"status": "unknown", "reason": str(exc), "products": {}}
