# SPDX-License-Identifier: Apache-2.0
"""V4 EOD capacity rescue: sell the exact discarded product vector before EOD.

The official interpreter runs unit work, market orders, then the EOD drop.
Under the inherited cargo-neutral/market-neutral/timing guards, reproduce
which carried products the baseline will discard. Inventories are visited in
actor-list order. Never rely on the insertion order of keys within a JSON
inventory: a capacity boundary inside a mixed-product actor fails closed.
Full actors before or after that boundary have order-independent effects.

If shed stock covers EVERY discarded product and ALL rescue SELL rows fit,
sell that whole vector before EOD. With carried vector Q, admitted vector A,
and discarded vector D = Q - A, final private shed is S - D + Q = S + A,
exactly the unmodified path. Partial vector rescue is deliberately forbidden.

The existing key ships disabled. Ambiguous or malformed state returns the
exact parent object. Cash and public/rival market effects still require the
paired economics gate; this source theorem is not a promotion decision.
"""
from __future__ import annotations

import copy
from collections import Counter
from typing import Any

import h3c_goose_eod_cap_rescue as h3c

_MISSING = object()
_CARGO_NEUTRAL = frozenset({
    "PASS", "NORTH", "SOUTH", "EAST", "WEST",
    "WATER", "DIG", "CARE", "BUILD_COOP", "BUILD_PASTURE", "PLANT",
})
_SHED_CHANGING_MARKET = frozenset({"SELL", "BUY_PRODUCT", "BUY_ANIMAL"})
# These are the only official market row heads whose execution cannot change shed
# stock. Any other raw head has an unspecified shed effect, so this helper
# returns the parent rather than assuming the row is shed-neutral.
_SHED_NEUTRAL_MARKET = frozenset({"HIRE", "BUY_LAND", "BUY_SEED"})
# Preserve the predecessor's official timing admission contract. Town consumes
# PUBLIC market inventory, not private shed stock; these conservative pins are
# retained unchanged rather than widening configuration support in this lane.
_STANDARD_TOWN_INTERVALS = {
    "townShopSellInterval": 4,
    "townCenterSellInterval": 24,
}
telemetry = Counter()


def _discarded_products(inventories: Any, room: int, products) -> dict[str, int] | None:
    """Return the whole EOD loss vector only when independent of mapping order.

    List order is actor order in the official drop routine. A fully admitted
    or fully discarded actor is insensitive to its inventory's key ordering.
    A partly admitted actor is provable only with one positive product.
    Validate every carried item, including later actors after room is zero.
    """
    if not isinstance(inventories, list) or type(room) is not int or room < 0:
        return None
    discarded = {}
    for inventory in inventories:
        if not isinstance(inventory, dict):
            return None
        positive = {}
        total = 0
        for item, quantity in inventory.items():
            if not isinstance(item, str) or type(quantity) is not int or quantity < 0:
                return None
            if quantity == 0:
                continue
            if item not in products:
                return None
            positive[item] = quantity
            total += quantity
        if total <= room:
            room -= total
            continue
        if room:
            # JSON object order is not evidence of the engine's insertion order.
            if len(positive) != 1:
                return None
            item, quantity = next(iter(positive.items()))
            positive[item] = quantity - room
            room = 0
        for item, quantity in positive.items():
            discarded[item] = discarded.get(item, 0) + quantity
    return discarded


def _standard_town_intervals(configuration: Any) -> bool:
    """Accept missing keys as official defaults; reject any nonstandard present value."""
    for name, expected in _STANDARD_TOWN_INTERVALS.items():
        actual = h3c._cfg(configuration, name)
        if actual is h3c._MISSING:
            continue
        if type(actual) is not int or actual != expected:
            return False
    return True


def apply_eod_capacity_rescue(action: Any, observation: Any, configuration: Any, *, enabled=False):
    """Append the bounded, whole loss vector or preserve exact parent identity."""
    if not enabled or not h3c._standard_configuration(configuration):
        return action
    # H3c's shared standard-config theorem intentionally covers only the
    # fields its own mechanism consumes. This lane additionally hard-codes
    # the 720-step season boundary (last usable pre-EOD step 695) and the
    # inherited official town consume intervals. This extension changes only
    # the cargo proof, not the predecessor's configuration admission surface.
    episode_steps = h3c._cfg(configuration, "episodeSteps")
    if type(episode_steps) is not int or episode_steps != 720:
        return action
    if not _standard_town_intervals(configuration):
        return action
    if not isinstance(observation, dict) or not isinstance(action, dict):
        return action

    step = observation.get("step", _MISSING)
    player = observation.get("player", _MISSING)
    farms = observation.get("farms", _MISSING)
    private = observation.get("private", _MISSING)
    market_obs = observation.get("market", _MISSING)
    if type(step) is not int or step < 0 or step > 695 or step % 24 != 23:
        return action
    if type(player) is not int or player not in (0, 1):
        return action
    if (not isinstance(farms, list) or len(farms) != 2 or not isinstance(private, dict)
            or not isinstance(market_obs, dict)):
        return action

    farm = farms[player]
    if not isinstance(farm, dict):
        return action
    farmer_pos = farm.get("farmer", _MISSING)
    hand_pos = farm.get("hands", _MISSING)
    if not isinstance(farmer_pos, list) or not isinstance(hand_pos, list):
        return action

    rows = h3c._parent_rows(action)
    inventories = private.get("inventories", _MISSING)
    shed = private.get("shed", _MISSING)
    if rows is None or not isinstance(inventories, list):
        return action
    if len(rows) != 1 + len(hand_pos) or len(inventories) != len(rows):
        return action

    # Restrict the theorem to commands that cannot change carried quantities or
    # shed stock during the unit-action phase. Require a literal string op before
    # frozenset membership so malformed list/dict heads fail closed instead of
    # raising TypeError while hashing an unhashable object.
    for command in rows:
        if (not isinstance(command, list) or not command
                or not isinstance(command[0], str)
                or command[0] not in _CARGO_NEUTRAL):
            telemetry["cargo_action_block"] += 1
            return action

    market = action.get("market", _MISSING)
    if not isinstance(market, list) or len(market) >= h3c.STANDARD_CONFIG["maxMarketOrdersPerTurn"]:
        return action
    for order in market:
        if not isinstance(order, list):
            return action
        if not order:
            continue
        if not isinstance(order[0], str):
            return action
        if order[0] in _SHED_CHANGING_MARKET:
            telemetry["market_stock_block"] += 1
            return action
        if order[0] not in _SHED_NEUTRAL_MARKET:
            telemetry["market_ambiguous_block"] += 1
            return action

    import r04_full_router as r04

    shed_total = h3c._strict_inventory_total(shed)
    if shed_total is None:
        return action
    capacity = h3c.STANDARD_CONFIG["shedCapacity"]
    if shed_total > capacity:
        return action
    discarded = _discarded_products(inventories, capacity - shed_total, r04.PRODUCTS)
    if not discarded:
        return action
    # A partial vector can change which later product the drop admits. Require
    # coverage and executable raw slots for the WHOLE vector before any edit.
    if len(market) + len(discarded) > h3c.STANDARD_CONFIG["maxMarketOrdersPerTurn"]:
        telemetry["rescue_order_budget_block"] += 1
        return action
    prices = market_obs.get("prices", _MISSING)
    if not isinstance(prices, dict):
        return action
    rescue_rows = []
    rescued_units = 0
    quoted_cash = 0
    floor_units = 0
    for product in sorted(discarded):
        quantity = discarded[product]
        shed_quantity = shed.get(product, 0)
        if type(shed_quantity) is not int or shed_quantity < quantity:
            telemetry["same_product_stock_block"] += 1
            return action
        price = prices.get(product, _MISSING)
        if type(price) is not int or price < 1:
            return action
        rescue_rows.append(["SELL", product, quantity])
        rescued_units += quantity
        quoted_cash += quantity * price
        if price == 1:
            floor_units += quantity

    result = copy.deepcopy(action)
    result["market"].extend(rescue_rows)
    telemetry["activations"] += 1
    telemetry["rescued_units"] += rescued_units
    telemetry["quoted_cash"] += quoted_cash
    if floor_units:
        telemetry["floor_price_units"] += floor_units
    if len(rescue_rows) > 1:
        telemetry["mixed_product_activations"] += 1
    return result


def install(parent, *, enabled=False):
    def agent(observation, configuration=None):
        action = parent(observation, configuration)
        return apply_eod_capacity_rescue(action, observation, configuration, enabled=enabled)

    agent.telemetry = telemetry
    return agent
