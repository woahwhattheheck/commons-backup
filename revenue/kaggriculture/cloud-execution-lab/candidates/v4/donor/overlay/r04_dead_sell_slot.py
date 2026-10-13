# SPDX-License-Identifier: Apache-2.0
"""Free only terminal market slots that are provably unable to execute.

The official market truncates the raw row list before execution.  A trailing
non-buyable SELL with no possible same-turn shed supply is therefore both a
guaranteed no-op and a capacity hazard for the policy's later sale append.

Only a trailing suffix is removable, and only when the authored raw market is
already at the standard ten-row execution cap.  Pruning an unsaturated queue
would move a later native appended sale to an earlier lockstep index without
freeing otherwise-blocked execution capacity.

Deleting an interspersed row would shift later authored rows against the
rival's lockstep order indices and can change quotes, funding, or atomic-order
timing.
"""
from __future__ import annotations

MARKET_ORDER_CAP = 10
NONBUYABLES = frozenset({
    "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL",
})


def _commands(action):
    farmer = action.get("farmer")
    hands = action.get("hands")
    if not isinstance(farmer, list) or not isinstance(hands, list):
        return None
    commands = [farmer] + list(hands)
    if any(not isinstance(command, list) for command in commands):
        return None
    return commands


def _post_unit_stock_is_zero(action, view, item):
    """Prove `item` cannot be in the shed when the market phase starts."""
    try:
        current = view.shed.get(item, 0)
        if type(current) is not int or current != 0:
            return False
        commands = _commands(action)
        positions = view.positions
        inventories = view.inventories
        if commands is None or len(commands) != len(positions) or len(inventories) < len(commands):
            return False
        for worker, command in enumerate(commands):
            inventory = inventories[worker]
            if not isinstance(inventory, dict):
                return False
            held = inventory.get(item, 0)
            if type(held) is not int or held < 0:
                return False
            if held == 0:
                continue
            position = positions[worker]
            if not view.beside_shed(position):
                continue
            op = command[0] if command else "PASS"
            if op == "DROP":
                return False
            if op == "PLACE" and len(command) >= 2 and command[1] == item:
                return False
        return True
    except Exception:
        return False


def prune_trailing_dead_sells(action, view, enabled=False):
    """Remove a maximal trailing suffix of engine-guaranteed dead SELL rows.

    Disabled, malformed, unsaturated, interspersed, buyable, or potentially
    supplied rows return the exact parent object.
    """
    if not enabled or not isinstance(action, dict):
        return action
    market = action.get("market")
    if not isinstance(market, list) or len(market) < MARKET_ORDER_CAP:
        return action

    cut = len(market)
    while cut:
        order = market[cut - 1]
        if not isinstance(order, list) or len(order) < 3 or order[0] != "SELL":
            break
        item = order[1]
        if type(item) is not str or item not in NONBUYABLES:
            break
        try:
            quantity = int(order[2])
        except (TypeError, ValueError, OverflowError):
            break
        if quantity > 0 and not _post_unit_stock_is_zero(action, view, item):
            break
        cut -= 1

    if cut == len(market):
        return action
    result = dict(action)
    result["market"] = market[:cut]
    return result
