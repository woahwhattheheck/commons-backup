#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""B7 experiment: preserve carried product units that DROP would destroy at a full shed.

The official engine's shed-adjacent DROP deposits only the quantity that fits, then
removes every carried inventory entry even when some units did not fit. R04's
``projected_shed`` already caps the projected deposit by remaining shed room. For
an exact single-product carrier, replacing an overflowing DROP with ``PLACE item
room`` (or PASS when room is zero) therefore preserves the same current-turn shed
quantity while retaining the excess in the worker inventory instead of deleting it.

The guard runs after the parent policy. It models worker actions in engine order so
an earlier well-formed DROP or product PLACE consumes room before a later guarded
DROP. A preceding shed PICKUP increases later room and would require per-item shed
simulation, so B7 deliberately fails the whole transform closed if such a PICKUP
precedes a DROP that would otherwise be guarded. All commanded actor positions are
validated before replacements are staged. Shed-adjacent animal/unknown PLACE is
ambiguous because it may target a farm structure instead of the shed, so the entire
transform fails closed in that case. Malformed configuration/state/action also
preserves the exact parent action object.
"""
from __future__ import annotations

import copy
from collections import Counter
from typing import Any

DEFAULT_BOARD_SIZE = 10
DEFAULT_SHED_CAPACITY = 100
PRODUCTS = frozenset(
    (
        "WHEAT",
        "CARROT",
        "TOMATO",
        "STRAWBERRY",
        "MELON",
        "EGG",
        "MILK",
        "WOOL",
        "FERTILIZER",
    )
)

telemetry = Counter()


def _cfg(configuration: Any, name: str, default: Any) -> Any:
    if configuration is None:
        return default
    if isinstance(configuration, dict):
        return configuration.get(name, default)
    return getattr(configuration, name, default)


def _strict_positive_int_config(configuration: Any, name: str, default: int) -> int | None:
    value = _cfg(configuration, name, default)
    if type(value) is not int or value <= 0:
        return None
    return value


def _strict_position(position: Any, board_size: int) -> bool:
    if not isinstance(position, (list, tuple)) or len(position) != 2:
        return False
    x, y = position
    return (
        type(x) is int
        and type(y) is int
        and 0 <= x < board_size
        and 0 <= y < board_size
    )


def _shed_adjacent(position: Any, board_size: int) -> bool:
    if not _strict_position(position, board_size):
        return False
    x, y = position
    half = board_size // 2
    return (x, y) in {
        (half - 1, half - 1),
        (half, half - 1),
        (half - 1, half),
        (half, half),
    }


def _strict_nonnegative_mapping_total(mapping: Any) -> int | None:
    if not isinstance(mapping, dict):
        return None
    total = 0
    for key, value in mapping.items():
        if not isinstance(key, str) or type(value) is not int or value < 0:
            return None
        total += value
    return total


def _actor_inventory(inventories: list[Any], actor: int) -> dict[str, int] | None:
    # The engine grows a missing actor inventory to an empty dict on demand.
    if actor >= len(inventories):
        return {}
    value = inventories[actor]
    if not isinstance(value, dict):
        return None
    for key, qty in value.items():
        if not isinstance(key, str) or type(qty) is not int or qty < 0:
            return None
    return value


def _positive_items(inventory: dict[str, int]) -> list[tuple[str, int]]:
    return [(item, qty) for item, qty in inventory.items() if qty > 0]


def transform(observation: Any, action: Any, configuration: Any = None, enabled: bool = False):
    """Prevent exact single-product DROP overflow without changing shed deposits."""
    if not enabled:
        telemetry["disabled"] += 1
        return action
    if not isinstance(observation, dict) or not isinstance(action, dict):
        telemetry["malformed_input"] += 1
        return action

    board_size = _strict_positive_int_config(configuration, "boardSize", DEFAULT_BOARD_SIZE)
    shed_capacity = _strict_positive_int_config(configuration, "shedCapacity", DEFAULT_SHED_CAPACITY)
    if board_size is None or shed_capacity is None:
        telemetry["nonstandard_configuration"] += 1
        return action

    player = observation.get("player")
    farms = observation.get("farms")
    private = observation.get("private")
    if (
        type(player) is not int
        or not isinstance(farms, list)
        or player < 0
        or player >= len(farms)
        or not isinstance(farms[player], dict)
        or not isinstance(private, dict)
    ):
        telemetry["malformed_observation"] += 1
        return action

    farm = farms[player]
    farmer_position = farm.get("farmer")
    hand_positions = farm.get("hands")
    inventories = private.get("inventories")
    shed = private.get("shed")
    if not isinstance(hand_positions, list) or not isinstance(inventories, list):
        telemetry["malformed_observation"] += 1
        return action
    shed_total = _strict_nonnegative_mapping_total(shed)
    if shed_total is None:
        telemetry["malformed_observation"] += 1
        return action

    farmer_command = action.get("farmer")
    hand_commands = action.get("hands")
    if not isinstance(farmer_command, list) or not isinstance(hand_commands, list):
        telemetry["malformed_action"] += 1
        return action

    positions = [farmer_position, *hand_positions]
    commands = [farmer_command, *hand_commands]
    if len(commands) > len(positions):
        telemetry["malformed_action"] += 1
        return action
    if any(not _strict_position(positions[actor], board_size) for actor in range(len(commands))):
        telemetry["malformed_position"] += 1
        return action

    room = max(0, shed_capacity - shed_total)
    replacements: dict[int, list[Any]] = {}
    saved_units = 0
    placed_units = 0
    saw_prior_shed_pickup = False

    for actor, command in enumerate(commands):
        if not isinstance(command, list):
            telemetry["malformed_action"] += 1
            return action
        inventory = _actor_inventory(inventories, actor)
        if inventory is None:
            telemetry["malformed_inventory"] += 1
            return action

        adjacent = _shed_adjacent(positions[actor], board_size)
        if not adjacent or not command:
            continue

        op = command[0]
        if op == "PICKUP":
            # A successful shed PICKUP increases room for later actors. Rather
            # than model per-item shed stock here, remember the ambiguity and
            # fail the whole transform closed only if a later DROP would be
            # rewritten based on the now-stale conservative room estimate.
            saw_prior_shed_pickup = True
            continue

        if op == "DROP":
            positive = _positive_items(inventory)
            deposit = min(room, sum(qty for _item, qty in positive))

            # Rewriting is deliberately narrower than capacity simulation: the
            # changed actor must carry one positive product and no other key.
            if len(inventory) == 1 and len(positive) == 1:
                item, qty = positive[0]
                if item in PRODUCTS and qty > room:
                    if saw_prior_shed_pickup:
                        telemetry["pickup_before_guarded_drop"] += 1
                        return action
                    if room > 0:
                        replacements[actor] = ["PLACE", item, room]
                        placed_units += room
                    else:
                        replacements[actor] = ["PASS"]
                    saved_units += qty - room

            # Original DROP and the replacement both deposit exactly this much.
            room -= deposit
            continue

        if op == "PLACE":
            # A preceding product PLACE has exact shed-capacity semantics. An
            # animal/unknown PLACE may instead target a structure, so fail closed.
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
    telemetry["full_shed_pass_rows"] += sum(1 for row in replacements.values() if row == ["PASS"])
    return out


def install(parent, enabled: bool = False):
    """Wrap a parent agent; disabled/no-op paths preserve output object identity."""

    def agent(observation, configuration=None):
        action = parent(observation, configuration)
        return transform(observation, action, configuration, enabled=enabled)

    agent.parent = parent
    agent.telemetry = telemetry
    agent.b7_enabled = bool(enabled)
    return agent
