# SPDX-License-Identifier: Apache-2.0
"""V3.1 B5 CARROT fertilize (ASTRA · GPT-5.6 SOL, PR #12499): production transform for the R04 route.

Replaces only an already-authored literal PASS with FERTILIZE when that worker is already
standing on a CARROT plant, already carrying fertilizer, and the tile is not fertilized
through the next two days. Malformed or non-canonical state fails closed to the parent
action. The functions below are the gated experiment's (candidate.py blob 4e4f9d49) byte for
byte; only the experiment scaffolding (path setup, baseline install, standalone agent) is
not carried, because r04_full_router.v3_agent() applies the transform itself.
"""
from __future__ import annotations

import copy


REPORT = {"carrot_fertilize_requests": 0}


def _int(value):
    """Engine integers only; bool/float/string coercions are not evidence."""
    return type(value) is int


def _eligible(tile, inventory, day):
    """True only for a carried-fertilizer CARROT top-up with canonical integer state."""
    if not isinstance(tile, dict) or not isinstance(inventory, dict) or not _int(day):
        return False
    fertilizer = inventory.get("FERTILIZER")
    coverage = tile.get("fertilized_until_day")
    return (
        tile.get("kind") == "PLANT"
        and tile.get("crop") == "CARROT"
        and _int(fertilizer)
        and fertilizer > 0
        and _int(coverage)
        and coverage < day + 2
    )


def apply_carrot_fertilizer(observation, action):
    """Replace eligible literal PASS rows; malformed inputs preserve parent identity."""
    if not isinstance(observation, dict) or not isinstance(action, dict):
        return action
    player = observation.get("player")
    step = observation.get("step")
    farms = observation.get("farms")
    private = observation.get("private")
    if (
        not _int(player)
        or player < 0
        or not _int(step)
        or step < 0
        or not isinstance(farms, list)
        or player >= len(farms)
        or not isinstance(private, dict)
    ):
        return action
    farm = farms[player]
    inventories = private.get("inventories")
    farm_hands = farm.get("hands") if isinstance(farm, dict) else None
    action_hands = action.get("hands")
    if (
        not isinstance(farm, dict)
        or "farmer" not in farm
        or "farmer" not in action
        or not isinstance(farm_hands, list)
        or not isinstance(action_hands, list)
        or not isinstance(inventories, list)
    ):
        return action

    positions = [farm["farmer"], *farm_hands]
    commands = [action["farmer"], *action_hands]
    if len(positions) != len(commands) or len(commands) != len(inventories):
        return action
    tiles = farm.get("tiles")
    if not isinstance(tiles, list):
        return action

    # Atomic validation pass. No replacement is recorded until every explicitly
    # represented actor row is canonical enough for this transform to reason about.
    actor_rows = []
    for command, position, inventory in zip(commands, positions, inventories):
        if not isinstance(command, list) or not command or not isinstance(command[0], str):
            return action
        # PASS is the only opcode this transform interprets. A PASS-like row with
        # extra payload is malformed evidence, not a non-PASS command to ignore.
        if command[0] == "PASS" and command != ["PASS"]:
            return action
        if (
            not isinstance(position, (list, tuple))
            or len(position) != 2
            or not _int(position[0])
            or not _int(position[1])
            or not isinstance(inventory, dict)
        ):
            return action
        if "FERTILIZER" in inventory:
            fertilizer = inventory["FERTILIZER"]
            if not _int(fertilizer) or fertilizer < 0:
                return action
        x, y = position
        if y < 0 or y >= len(tiles) or not isinstance(tiles[y], list) or x < 0 or x >= len(tiles[y]):
            return action
        tile = tiles[y][x]
        # A literal PASS on a CARROT is potentially transformable, so malformed
        # coverage cannot be downgraded to ordinary ineligibility after another
        # actor has already qualified.
        if (
            command == ["PASS"]
            and isinstance(tile, dict)
            and tile.get("kind") == "PLANT"
            and tile.get("crop") == "CARROT"
            and not _int(tile.get("fertilized_until_day"))
        ):
            return action
        actor_rows.append((command, inventory, x, y, tile))

    day = step // 24
    claimed = set()
    replacements = {}
    for actor, (command, inventory, x, y, tile) in enumerate(actor_rows):
        if command != ["PASS"] or (x, y) in claimed:
            continue
        if not _eligible(tile, inventory, day):
            continue
        replacements[actor] = ["FERTILIZE"]
        claimed.add((x, y))

    if not replacements:
        return action
    result = copy.deepcopy(action)
    result_commands = [result["farmer"], *result["hands"]]
    for actor, command in replacements.items():
        result_commands[actor] = command
    result["farmer"] = result_commands[0]
    result["hands"] = result_commands[1:]
    REPORT["carrot_fertilize_requests"] += len(replacements)
    return result
