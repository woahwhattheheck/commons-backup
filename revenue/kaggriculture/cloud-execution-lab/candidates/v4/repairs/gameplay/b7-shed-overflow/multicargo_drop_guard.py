#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail-closed B7 multi-cargo DROP overflow guard.

The official engine's shed-adjacent DROP visits one actor inventory in insertion
order, deposits only what fits, then deletes every inventory entry even when the
shed is already full. The preserved B7 donor proves an exact single-product
rewrite. This successor extends only cases where one unit command can preserve
the exact shed/farm post-state:

* room == 0: DROP -> PASS for canonical carried cargo with positive quantities.
* room > 0: if the first positive carried item is a PRODUCT and its quantity is
  at least the remaining room, DROP -> PLACE(item, room). The original DROP
  cannot deposit any later item, so the rewrite preserves the exact shed result
  while retaining all cargo that DROP would have destroyed.

If DROP would span multiple carried items, contains zero-quantity keys that DROP
would delete, a prior shed PICKUP makes remaining room uncertain, the first item
is an animal, cargo/state/configuration is malformed, or the shed is already
over capacity, the exact parent action object is returned unchanged. This module
is default-OFF, requires literal ``True`` to activate, and does not wire itself
into runtime.
"""
from __future__ import annotations

import copy
from collections import Counter
from typing import Any

DEFAULT_BOARD_SIZE = 10
DEFAULT_SHED_CAPACITY = 100
PRODUCTS = frozenset(("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL", "FERTILIZER"))
ANIMALS = frozenset(("GOOSE", "COW", "SHEEP"))
CARRYABLE = PRODUCTS | ANIMALS
telemetry = Counter()


def _cfg(configuration: Any, name: str, default: Any) -> Any:
    if configuration is None:
        return default
    if isinstance(configuration, dict):
        return configuration.get(name, default)
    return getattr(configuration, name, default)


def _strict_positive_int_config(configuration: Any, name: str, default: int) -> int | None:
    value = _cfg(configuration, name, default)
    return value if type(value) is int and value > 0 else None


def _strict_position(position: Any, board_size: int) -> bool:
    if not isinstance(position, (list, tuple)) or len(position) != 2:
        return False
    x, y = position
    return type(x) is int and type(y) is int and 0 <= x < board_size and 0 <= y < board_size


def _shed_adjacent(position: Any, board_size: int) -> bool:
    if not _strict_position(position, board_size):
        return False
    x, y = position
    half = board_size // 2
    return (x, y) in {(half - 1, half - 1), (half, half - 1), (half - 1, half), (half, half)}


def _strict_shed_total(mapping: Any) -> int | None:
    if not isinstance(mapping, dict):
        return None
    total = 0
    for key, value in mapping.items():
        if not isinstance(key, str) or key not in CARRYABLE or type(value) is not int or value < 0:
            return None
        total += value
    return total


def _actor_inventory(inventories: list[Any], actor: int) -> dict[str, int] | None:
    if actor >= len(inventories):
        return {}
    value = inventories[actor]
    if not isinstance(value, dict):
        return None
    for key, qty in value.items():
        if not isinstance(key, str) or key not in CARRYABLE or type(qty) is not int or qty < 0:
            return None
    return value


def _positive_items(inventory: dict[str, int]) -> list[tuple[str, int]]:
    return [(item, qty) for item, qty in inventory.items() if qty > 0]


def transform(observation: Any, action: Any, configuration: Any = None, enabled: bool = False):
    """Preserve cargo destroyed by exact DROP-overflow cases."""
    if enabled is not True:
        telemetry["disabled" if enabled is False else "invalid_enabled"] += 1
        return action
    if not isinstance(observation, dict) or not isinstance(action, dict):
        telemetry["malformed_input"] += 1
        return action

    board_size = _strict_positive_int_config(configuration, "boardSize", DEFAULT_BOARD_SIZE)
    shed_capacity = _strict_positive_int_config(configuration, "shedCapacity", DEFAULT_SHED_CAPACITY)
    if board_size is None or shed_capacity is None:
        telemetry["configuration"] += 1
        return action

    player = observation.get("player")
    farms = observation.get("farms")
    private = observation.get("private")
    if type(player) is not int or not isinstance(farms, list) or player < 0 or player >= len(farms) or not isinstance(farms[player], dict) or not isinstance(private, dict):
        telemetry["observation"] += 1
        return action

    farm = farms[player]
    hands = farm.get("hands")
    inventories = private.get("inventories")
    shed_total = _strict_shed_total(private.get("shed"))
    if not isinstance(hands, list) or not isinstance(inventories, list) or shed_total is None or shed_total > shed_capacity:
        telemetry["state"] += 1
        return action

    farmer_command = action.get("farmer")
    hand_commands = action.get("hands")
    if not isinstance(farmer_command, list) or not isinstance(hand_commands, list):
        telemetry["action"] += 1
        return action

    positions = [farm.get("farmer"), *hands]
    commands = [farmer_command, *hand_commands]
    if len(commands) > len(positions):
        telemetry["action"] += 1
        return action
    if any(not _strict_position(positions[actor], board_size) for actor in range(len(commands))):
        telemetry["position"] += 1
        return action

    room = shed_capacity - shed_total
    replacements: dict[int, list[Any]] = {}
    saved_units = 0
    placed_units = 0
    saw_prior_shed_pickup = False

    for actor, command in enumerate(commands):
        if not isinstance(command, list):
            telemetry["action"] += 1
            return action
        inventory = _actor_inventory(inventories, actor)
        if inventory is None:
            telemetry["inventory"] += 1
            return action

        if not _shed_adjacent(positions[actor], board_size) or not command:
            continue

        op = command[0]
        if op == "PICKUP":
            saw_prior_shed_pickup = True
            continue

        if op == "DROP":
            positive = _positive_items(inventory)
            total = sum(qty for _item, qty in positive)
            deposit = min(room, total)
            replacement: list[Any] | None = None
            retained = total - deposit
            all_entries_positive = len(positive) == len(inventory)
            if positive and all_entries_positive and retained > 0:
                if room == 0:
                    replacement = ["PASS"]
                else:
                    first_item, first_qty = positive[0]
                    if first_item in PRODUCTS and first_qty >= room:
                        replacement = ["PLACE", first_item, room]
            elif positive and not all_entries_positive:
                telemetry["zero_quantity_drop_key"] += 1
            if replacement is not None:
                if saw_prior_shed_pickup:
                    telemetry["pickup_before_guarded_drop"] += 1
                    return action
                replacements[actor] = replacement
                saved_units += retained
                if replacement[0] == "PLACE":
                    placed_units += room
            room -= deposit
            continue

        if op == "PLACE":
            if len(command) < 2 or command[1] not in PRODUCTS:
                telemetry["ambiguous_place"] += 1
                return action
            item = command[1]
            if len(command) >= 3:
                qty = command[2]
                if type(qty) is not int:
                    telemetry["malformed_place"] += 1
                    return action
            else:
                qty = 1
            if qty <= 0:
                continue
            deposit = min(qty, inventory.get(item, 0), room)
            room -= deposit

    if not replacements:
        return action

    out = copy.deepcopy(action)
    for actor, replacement in replacements.items():
        if actor == 0:
            out["farmer"] = replacement
        else:
            out["hands"][actor - 1] = replacement

    telemetry["changed_actions"] += 1
    telemetry["guarded_drop_rows"] += len(replacements)
    telemetry["saved_units"] += saved_units
    telemetry["placed_units"] += placed_units
    telemetry["full_shed_pass_rows"] += sum(1 for replacement in replacements.values() if replacement == ["PASS"])
    return out


def install(parent, enabled: bool = False):
    """Wrap a parent policy without changing default behavior."""
    def agent(observation, configuration=None):
        action = parent(observation, configuration)
        return transform(observation, action, configuration, enabled=enabled)
    agent.parent = parent
    agent.telemetry = telemetry
    agent.b7_multicargo_enabled = enabled is True
    return agent
