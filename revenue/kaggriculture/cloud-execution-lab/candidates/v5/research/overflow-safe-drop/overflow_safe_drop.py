# SPDX-License-Identifier: Apache-2.0
"""Default-OFF V5 candidate: preserve over-cap worker stock across shed liquidation.

Pinned Kaggriculture mechanics give DROP and PLACE materially different overflow
semantics at shed access:

* DROP deposits up to current shed room, then deletes every carried stack key.
* PLACE <item> <qty> deposits only the fitting requested amount and leaves the
  rest of that item in the worker pocket.

For one unambiguous marketable-product pocket containing exactly one inventory
key, rewriting a selected DROP to a partial PLACE (or PASS when the shed is
already full) preserves the same current shed post-unit state while retaining
stock that DROP would destroy.  This helper is research-only: it does not
activate itself in Titan and makes no full-game profitability claim.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

SALE_GOODS = frozenset({"CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL"})


def _identity(selected: Any, reason: str, **extra):
    report = {"changed": False, "reason": reason}
    report.update(extra)
    return selected, report


def _plain_nonnegative(value: Any) -> bool:
    return type(value) is int and value >= 0


def _shed_access(board_size: int) -> set[tuple[int, int]]:
    half = board_size // 2
    return {(half - 1, half - 1), (half, half - 1),
            (half - 1, half), (half, half)}


def _valid_same_item_sell(row: Any, item: str) -> bool:
    """Recognize only a definitely executable positive SELL grammar row."""
    if not isinstance(row, list) or len(row) < 3 or row[0] != "SELL" or row[1] != item:
        return False
    try:
        quantity = int(row[2])
    except (TypeError, ValueError, OverflowError):
        return False
    return quantity > 0


def transform(selected: Any, observation: Mapping[str, Any], configuration: Mapping[str, Any] | None = None):
    """Rewrite one destructive over-cap DROP while preserving current shed effects.

    Admission is intentionally narrow.  The current selected action must contain
    exactly one shed-affecting unit action and that action must be DROP.  The
    actor inventory must contain exactly one key, a positive non-operating sale
    good; this is stricter than merely having one positive stack because engine
    DROP deletes zero-valued keys too.  The shed must have less room than that
    stack, and the executable market prefix must already contain a positive SELL
    for the same item with baseline same-item shed stock available after DROP.
    Market rows and all other unit actions are byte-for-byte preserved.
    """
    cfg = {} if configuration is None else configuration
    if not isinstance(selected, dict) or not isinstance(observation, Mapping) or not isinstance(cfg, Mapping):
        return _identity(selected, "malformed_input")

    player = observation.get("player")
    step = observation.get("step")
    if type(player) is not int or player not in (0, 1) or type(step) is not int or step < 0:
        return _identity(selected, "malformed_public_identity")

    board_size = cfg.get("boardSize", 10)
    shed_capacity = cfg.get("shedCapacity", 100)
    maximum = cfg.get("maxMarketOrdersPerTurn", 10)
    if (type(board_size) is not int or board_size != 10
            or type(shed_capacity) is not int or shed_capacity != 100
            or type(maximum) is not int or maximum != 10):
        return _identity(selected, "outside_standard_config")

    farms = observation.get("farms")
    private = observation.get("private")
    if not isinstance(farms, list) or len(farms) != 2 or not isinstance(private, Mapping):
        return _identity(selected, "malformed_private_state")
    farm = farms[player]
    if not isinstance(farm, Mapping):
        return _identity(selected, "malformed_private_state")
    farmer = farm.get("farmer")
    hands = farm.get("hands")
    inventories = private.get("inventories")
    shed = private.get("shed")
    if (not isinstance(farmer, list) or len(farmer) != 2 or not isinstance(hands, list)
            or not isinstance(inventories, list) or not isinstance(shed, Mapping)):
        return _identity(selected, "malformed_private_state")

    positions = [farmer, *hands]
    if len(inventories) != len(positions):
        return _identity(selected, "inventory_actor_mismatch")
    if any(not (isinstance(pos, list) and len(pos) == 2 and all(type(v) is int for v in pos)) for pos in positions):
        return _identity(selected, "malformed_actor_position")

    farmer_action = selected.get("farmer")
    hand_actions = selected.get("hands")
    market = selected.get("market")
    if not isinstance(farmer_action, list) or not isinstance(hand_actions, list) or not isinstance(market, list):
        return _identity(selected, "malformed_selected_shape")
    actions = [farmer_action, *hand_actions]
    if len(actions) != len(positions):
        return _identity(selected, "selected_actor_mismatch")

    # Multiple shed-affecting unit actions would require reproducing actor-order
    # room accounting. Keep this candidate smaller and exact instead.
    shed_ops = []
    for actor, action in enumerate(actions):
        if not isinstance(action, list) or not action:
            return _identity(selected, "malformed_unit_action")
        if action[0] in ("DROP", "PLACE", "PICKUP"):
            shed_ops.append((actor, action))
    if len(shed_ops) != 1 or shed_ops[0][1][0] != "DROP":
        return _identity(selected, "ambiguous_shed_unit_sequence")

    actor = shed_ops[0][0]
    if tuple(positions[actor]) not in _shed_access(board_size):
        return _identity(selected, "drop_not_at_shed")

    inventory = inventories[actor]
    if not isinstance(inventory, Mapping):
        return _identity(selected, "malformed_worker_inventory")
    # Engine DROP deletes every carried key, including zero-valued keys.  PLACE
    # or PASS would preserve any unrelated zero-valued key, so exact immediate
    # private-state equivalence requires the mapping itself to contain one key.
    if len(inventory) != 1:
        return _identity(selected, "ambiguous_worker_inventory")
    positive = []
    for item, quantity in inventory.items():
        if not isinstance(item, str) or not _plain_nonnegative(quantity):
            return _identity(selected, "malformed_worker_inventory")
        if quantity:
            positive.append((item, quantity))
    if len(positive) != 1:
        return _identity(selected, "ambiguous_worker_inventory")
    item, carried = positive[0]
    if item not in SALE_GOODS:
        return _identity(selected, "operating_or_unsupported_item")

    shed_total = 0
    for shed_item, quantity in shed.items():
        if not isinstance(shed_item, str) or not _plain_nonnegative(quantity):
            return _identity(selected, "malformed_shed")
        shed_total += quantity
    if shed_total > shed_capacity:
        return _identity(selected, "shed_already_over_capacity")
    room = shed_capacity - shed_total
    if carried <= room:
        return _identity(selected, "drop_has_no_overflow")

    prefix = market[:maximum]
    if any(row and not isinstance(row, list) for row in prefix):
        return _identity(selected, "malformed_market_prefix")
    # Requiring a positive same-item grammar row is not enough: at room=0 a
    # full shed containing only other goods would still have no same-item unit to
    # sell this tick. Bind the handoff to stock the baseline DROP actually makes
    # sellable before market execution.
    baseline_same_item_stock = int(shed.get(item, 0)) + min(room, carried)
    if baseline_same_item_stock <= 0 or not any(_valid_same_item_sell(row, item) for row in prefix):
        return _identity(selected, "no_same_item_executable_sell")

    result = deepcopy(selected)
    replacement = ["PASS"] if room == 0 else ["PLACE", item, room]
    if actor == 0:
        result["farmer"] = replacement
    else:
        result["hands"][actor - 1] = replacement
    return result, {
        "changed": True,
        "reason": "preserve_drop_overflow",
        "actor": actor,
        "item": item,
        "carried_before": carried,
        "shed_room": room,
        "baseline_same_item_stock": baseline_same_item_stock,
        "preserved_in_pocket_lower_bound": carried - room,
        "replacement": replacement,
        "market_unchanged": True,
        "same_tick_shed_effect_preserved": True,
        "full_game_gain_measured": False,
    }