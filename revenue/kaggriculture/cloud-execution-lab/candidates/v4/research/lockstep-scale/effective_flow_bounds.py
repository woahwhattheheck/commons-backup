"""Conservative opponent *inventory-changing* flow for pinned Kaggriculture.

This stateless support module is not an observer, policy, or runtime hook. Inputs
must be adjacent observations from one episode/seat and the EXACT action returned
between them. Session identity, final-action custody, and accumulation belong to
the caller. Missing/invalid evidence returns None, never fabricated zero flow.

Let R = next inventory - previous inventory + prior-step town consumption.
If our executable SELL requests total S and BUY_PRODUCT requests total B, our
inventory-changing contribution is in [-B, S], regardless of cash, shed stock,
partial fills or $1 sales. Therefore opponent effective net flow is in [R-S,R+B].
Only WHEAT/FERTILIZER can be bought as products. Empty/invalid raw rows consume
market slots. Each row executes at most 99,999 units in engine blob 3c202c7ee9.
Positive flow means net inventory-increasing sales, NOT total opponent sales:
$1 sales are invisible, and simultaneous buys/sells can cancel. This is a
conservative envelope, not an exact fill reconstruction or a price prediction.
"""
from __future__ import annotations

from collections.abc import Mapping

ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
PRODUCTS = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
            "EGG", "MILK", "WOOL", "FERTILIZER")
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
PER_ROW_UNIT_LIMIT = 99_999


def _observed_int(value: object) -> int:
    # Engine-produced step/inventory are integers. Do not coerce missing quotes,
    # NaN, bools, fractions, or numeric-looking text into purported evidence.
    if type(value) is not int:
        raise ValueError("expected an observed integer")
    return value


def _configured_int(cfg: Mapping, key: str, default: int) -> int:
    value = cfg.get(key, default)
    if type(value) not in (int, float, str, bool):
        raise ValueError("unsupported configuration value")
    return max(1, int(value))


def _town_demand(step: int, shops: object, cfg: Mapping) -> dict[str, int]:
    if not isinstance(shops, list):
        raise ValueError("missing previous unlocked_shops")
    counts = dict.fromkeys(PRODUCTS, 0)
    si = _configured_int(cfg, "townShopSellInterval", 4)
    ci = _configured_int(cfg, "townCenterSellInterval", 24)
    # Validate even off-tick: an unknown shop is not authenticated public input.
    for shop in shops:
        if not isinstance(shop, str) or shop not in SHOPS:
            raise ValueError("unknown shop")
        if step % si == 0:
            products = SHOPS[shop]
            multiplier = 2 if len(products) == 1 else 1
            for product in products:
                counts[product] += multiplier
    if step % ci == 0:
        for product in PRODUCTS:
            if product != "FERTILIZER":
                counts[product] += 1
    # There is deliberately NO inventory clipping: the official engine allows
    # town consumption to drive market inventory below zero.
    return counts


def _own_limits(action: object, cfg: Mapping) -> tuple[dict, dict]:
    sell = dict.fromkeys(PRODUCTS, 0)
    buy = dict.fromkeys(PRODUCTS, 0)
    cap = _configured_int(cfg, "maxMarketOrdersPerTurn", 10)
    market = action.get("market", []) if isinstance(action, dict) else []
    if not isinstance(market, list):
        return sell, buy  # The engine ignores non-list market containers.
    for row in market[:cap]:  # Slice BEFORE validating/filtering raw slots.
        if not isinstance(row, list) or len(row) < 3:
            continue
        op, product = row[:2]
        if op not in ("SELL", "BUY_PRODUCT", "BUY_SEED", "BUY_ANIMAL"):
            continue
        # Match the engine's parse-before-product-validation order. An infinity
        # raises in the engine, so do not claim a completed transition for it.
        if type(row[2]) not in (int, float, str, bool, type(None)):
            raise ValueError("unsupported order quantity")
        try:
            qty = int(row[2])
        except (TypeError, ValueError):
            continue
        qty = min(max(0, qty), PER_ROW_UNIT_LIMIT)
        if op == "SELL" and product in PRODUCTS:
            sell[product] += qty
        elif op == "BUY_PRODUCT" and product in ("WHEAT", "FERTILIZER"):
            buy[product] += qty
    return sell, buy


def effective_flow_bounds(previous_obs: object, returned_action: object,
                          next_obs: object, cfg: Mapping | None = None
                          ) -> dict[str, tuple[int, int]] | None:
    """Return product -> (lower, upper) effective opponent net flow, or None.

    Read only public step/player/market inventory/town fields. No private state,
    market prices, inferred fills, or opponent action is required or consumed.
    Defaults match the pinned engine; supply the actual configuration otherwise.
    Caller MUST ensure the two snapshots belong to the same episode and were
    taken around a successfully completed transition. Consecutive steps alone
    cannot prove episode identity. This function neither mutates nor caches input.
    """
    try:
        if not isinstance(previous_obs, Mapping) or not isinstance(next_obs, Mapping):
            return None
        cfg = {} if cfg is None else cfg
        if not isinstance(cfg, Mapping):
            return None
        step = _observed_int(previous_obs["step"])
        next_step = _observed_int(next_obs["step"])
        player = _observed_int(previous_obs["player"])
        next_player = _observed_int(next_obs["player"])
        if step < 0 or next_step != step + 1 or player not in (0, 1) or next_player != player:
            return None
        previous = previous_obs["market"]["inventory"]
        current = next_obs["market"]["inventory"]
        if not isinstance(previous, Mapping) or not isinstance(current, Mapping):
            return None
        demand = _town_demand(step, previous_obs["town"]["unlocked_shops"], cfg)
        sell, buy = _own_limits(returned_action, cfg)
        bounds = {}
        for product in PRODUCTS:
            residual = (_observed_int(current[product])
                        - _observed_int(previous[product]) + demand[product])
            bounds[product] = (residual - sell[product], residual + buy[product])
        return bounds
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError):
        return None


def confirmed_net_sells(bounds: Mapping | None, threshold: int = 150) -> dict[str, int]:
    """Products whose LOWER bound certifies threshold net inventory additions.

    These are retrospective effective sales, not predictions of future dumps.
    Price/strategy/accumulation decisions remain with the caller. None or malformed
    bounds fail closed. In particular an upper bound is never a positive signal.
    """
    if type(threshold) is not int or threshold <= 0 or not isinstance(bounds, Mapping):
        return {}
    result = {}
    for product, interval in bounds.items():
        if (product not in PRODUCTS or not isinstance(interval, (tuple, list))
                or len(interval) != 2 or any(type(x) is not int for x in interval)
                or interval[0] > interval[1]):
            return {}
        if interval[0] >= threshold:
            result[product] = interval[0]
    return result
