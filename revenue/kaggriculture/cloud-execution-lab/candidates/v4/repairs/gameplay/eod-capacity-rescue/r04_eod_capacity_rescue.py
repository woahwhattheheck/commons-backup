# SPDX-License-Identifier: Apache-2.0
"""V4 EOD capacity rescue: sell same-product shed stock to save carried overflow.

At hour 23 the official interpreter runs unit actions, then the market, then
town consume, then the end-of-day inventory drop. That final drop deletes
carried overflow when the shared 100-unit shed is full. This lane is
deliberately narrow: when every carried unit is the same product, all unit
commands are cargo-neutral, no existing market order changes shed stock, and
town consumption cannot fire on this hour-23 callback, append a SELL for
exactly the amount that would otherwise be discarded. The EOD drop then
re-admits the same product, so post-EOD private shed composition matches the
unmodified path while the otherwise-lost carried units are preserved
economically through the sale.

The key ships disabled. Ambiguous or malformed state returns the exact parent
object. Promotion remains a paired economics decision because a sale above the
$1 floor changes public market supply even though the private shed theorem is
exact.
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
# Official kaggriculture.json defaults. Hour-23 (step % 24 == 23) is not a
# consume tick under these intervals, so pre-town overflow equals pre-EOD
# overflow. A custom interval that consumes on this callback can free shed
# room after the rescue SELL and break private-shed identity.
_STANDARD_TOWN_INTERVALS = {
    "townShopSellInterval": 4,
    "townCenterSellInterval": 24,
}
telemetry = Counter()


def _single_carried_product(inventories: Any, products):
    """Return (product, total) iff all positive carried cargo is one known product."""
    if not isinstance(inventories, list):
        return None
    product = None
    total = 0
    for inventory in inventories:
        if not isinstance(inventory, dict):
            return None
        for item, quantity in inventory.items():
            if not isinstance(item, str) or type(quantity) is not int or quantity < 0:
                return None
            if quantity <= 0:
                continue
            if item not in products:
                return None
            if product is None:
                product = item
            elif item != product:
                return None
            total += quantity
    if product is None or total <= 0:
        return None
    return product, total


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
    """Append one bounded same-product SELL or preserve exact parent identity."""
    if not enabled or not h3c._standard_configuration(configuration):
        return action
    # H3c's shared standard-config theorem intentionally covers only the
    # fields its own mechanism consumes. This lane additionally hard-codes
    # the 720-step season boundary (last usable pre-EOD step 695) and the
    # official town consume intervals so hour-23 overflow is computed after
    # a market that is not followed by a consume tick.
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

    carried = _single_carried_product(inventories, r04.PRODUCTS)
    if carried is None:
        return action
    product, carried_total = carried

    shed_total = h3c._strict_inventory_total(shed)
    if shed_total is None:
        return action
    capacity = h3c.STANDARD_CONFIG["shedCapacity"]
    if shed_total > capacity:
        return action
    overflow = shed_total + carried_total - capacity
    if overflow <= 0:
        return action
    # Under a valid pre-EOD state, overflow can never exceed carried cargo.
    if overflow > carried_total:
        return action

    shed_quantity = shed.get(product, 0)
    if type(shed_quantity) is not int or shed_quantity < overflow:
        telemetry["same_product_stock_block"] += 1
        return action

    prices = market_obs.get("prices", _MISSING)
    if not isinstance(prices, dict):
        return action
    price = prices.get(product, _MISSING)
    if type(price) is not int or price < 1:
        return action

    result = copy.deepcopy(action)
    result["market"].append(["SELL", product, overflow])
    telemetry["activations"] += 1
    telemetry["rescued_units"] += overflow
    telemetry["quoted_cash"] += overflow * price
    if price == 1:
        telemetry["floor_price_units"] += overflow
    return result


def install(parent, *, enabled=False):
    def agent(observation, configuration=None):
        action = parent(observation, configuration)
        return apply_eod_capacity_rescue(action, observation, configuration, enabled=enabled)

    agent.telemetry = telemetry
    return agent
