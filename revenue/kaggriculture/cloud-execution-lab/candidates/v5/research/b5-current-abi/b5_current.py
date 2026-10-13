# SPDX-License-Identifier: Apache-2.0
"""Current-ABI port of the submitted V3.1 B5 CARROT + JIT pair.

This module is evidence/research only. It never calls a producer and never
selects a route. A caller must provide the current selected action plus the
*authenticated next authored action* for the same current route. The two V3.1
transforms then run in their submitted order: CARROT first, JIT second.

Historical authority (submitted V3.1 source a90d888f):
  candidates/v3/overlay/b5_fertilize.py
    git blob 2a9d606835b0d04d832a4737dcb381ad3fbef1ae
    source sha256 f2d03ab19e1a233566cfc9076bd8b9843c7f8d611703578218bd73c1af0f626f
  candidates/v3/overlay/jit_pass_fertilize.py
    git blob 6ef7ddcd9590e3cb3f55ceb708b8026235d59410
    source sha256 5ad6340bf31dab13aaba82bfe0b51e6cde18222155013be1e0e080f0a26242b2
"""
from __future__ import annotations

import copy
from collections import Counter
from typing import Any

DONOR_COMMIT = "a90d888f03987ef0b35cfd20ec3519c6144db08a"
B5_CARROT_GIT_BLOB = "2a9d606835b0d04d832a4737dcb381ad3fbef1ae"
B5_CARROT_SOURCE_SHA256 = "f2d03ab19e1a233566cfc9076bd8b9843c7f8d611703578218bd73c1af0f626f"
B5_JIT_GIT_BLOB = "6ef7ddcd9590e3cb3f55ceb708b8026235d59410"
B5_JIT_SOURCE_SHA256 = "5ad6340bf31dab13aaba82bfe0b51e6cde18222155013be1e0e080f0a26242b2"

_TURNS_PER_DAY = 24
_ANNUAL = {
    "WHEAT": {"max_yield_day": 4, "max_yield": 6},
    "CARROT": {"max_yield_day": 3, "max_yield": 4},
    "MELON": {"max_yield_day": 12, "max_yield": 6},
}


def _plain_int(value: Any) -> bool:
    return type(value) is int


def _commands(row: Any) -> list[Any] | None:
    if not isinstance(row, dict):
        return None
    farmer = row.get("farmer")
    hands = row.get("hands", [])
    if not isinstance(hands, list):
        return None
    return [farmer, *hands]


def _literal_op(command: Any, name: str) -> bool:
    return isinstance(command, list) and command == [name]


def _position_tile(observation: dict[str, Any], worker: int):
    player = observation.get("player")
    farms = observation.get("farms")
    private = observation.get("private")
    if type(player) is not int or not isinstance(farms, list) or not (0 <= player < len(farms)):
        return None
    farm = farms[player]
    if not isinstance(farm, dict) or not isinstance(private, dict):
        return None
    farmer = farm.get("farmer")
    hands = farm.get("hands", [])
    tiles = farm.get("tiles")
    inventories = private.get("inventories")
    if not isinstance(hands, list) or not isinstance(tiles, list) or not isinstance(inventories, list):
        return None
    positions = [farmer, *hands]
    if not (0 <= worker < len(positions) and worker < len(inventories)):
        return None
    pos = positions[worker]
    inv = inventories[worker]
    if (not isinstance(pos, list) or len(pos) != 2 or type(pos[0]) is not int
            or type(pos[1]) is not int or not isinstance(inv, dict)):
        return None
    x, y = pos
    if not (0 <= y < len(tiles) and isinstance(tiles[y], list) and 0 <= x < len(tiles[y])):
        return None
    return tiles[y][x], inv, [x, y]


# ---------------------------------------------------------------------------
# Submitted B5 CARROT semantics, lifted from the R04 wrapper into a pure current
# selected-action transform. It edits only literal PASS and never market bytes.


def _carrot_eligible(tile: Any, inventory: Any, day: int) -> bool:
    if not isinstance(tile, dict) or not isinstance(inventory, dict) or not _plain_int(day):
        return False
    fertilizer = inventory.get("FERTILIZER")
    coverage = tile.get("fertilized_until_day")
    return (
        tile.get("kind") == "PLANT"
        and tile.get("crop") == "CARROT"
        and _plain_int(fertilizer)
        and fertilizer > 0
        and _plain_int(coverage)
        and coverage < day + 2
    )


def apply_carrot_fertilizer(observation: Any, action: Any):
    """Replace eligible literal PASS rows; ambiguous/malformed state is identity."""
    if not isinstance(observation, dict) or not isinstance(action, dict):
        return action, ()
    player = observation.get("player")
    step = observation.get("step")
    farms = observation.get("farms")
    private = observation.get("private")
    if (
        not _plain_int(player)
        or player < 0
        or not _plain_int(step)
        or step < 0
        or not isinstance(farms, list)
        or player >= len(farms)
        or not isinstance(private, dict)
    ):
        return action, ()
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
        return action, ()

    positions = [farm["farmer"], *farm_hands]
    commands = [action["farmer"], *action_hands]
    if len(positions) != len(commands) or len(commands) != len(inventories):
        return action, ()
    tiles = farm.get("tiles")
    if not isinstance(tiles, list):
        return action, ()

    actor_rows = []
    for command, position, inventory in zip(commands, positions, inventories):
        if not isinstance(command, list) or not command or not isinstance(command[0], str):
            return action, ()
        if command[0] == "PASS" and command != ["PASS"]:
            return action, ()
        if (
            not isinstance(position, (list, tuple))
            or len(position) != 2
            or not _plain_int(position[0])
            or not _plain_int(position[1])
            or not isinstance(inventory, dict)
        ):
            return action, ()
        if "FERTILIZER" in inventory:
            fertilizer = inventory["FERTILIZER"]
            if not _plain_int(fertilizer) or fertilizer < 0:
                return action, ()
        x, y = position
        if y < 0 or y >= len(tiles) or not isinstance(tiles[y], list) or x < 0 or x >= len(tiles[y]):
            return action, ()
        tile = tiles[y][x]
        if (
            command == ["PASS"]
            and isinstance(tile, dict)
            and tile.get("kind") == "PLANT"
            and tile.get("crop") == "CARROT"
            and not _plain_int(tile.get("fertilized_until_day"))
        ):
            return action, ()
        actor_rows.append((command, inventory, x, y, tile))

    day = step // _TURNS_PER_DAY
    claimed = set()
    replacements = {}
    for actor, (command, inventory, x, y, tile) in enumerate(actor_rows):
        if command != ["PASS"] or (x, y) in claimed:
            continue
        if not _carrot_eligible(tile, inventory, day):
            continue
        replacements[actor] = ["FERTILIZE"]
        claimed.add((x, y))

    if not replacements:
        return action, ()
    result = copy.deepcopy(action)
    result_commands = [result["farmer"], *result["hands"]]
    activations = []
    for actor, command in replacements.items():
        result_commands[actor] = command
        activations.append({"worker": actor, "reason": "b5_carrot_pass_fertilize"})
    result["farmer"] = result_commands[0]
    result["hands"] = result_commands[1:]
    return result, tuple(activations)


# ---------------------------------------------------------------------------
# Submitted B5 JIT semantics. The historical R04 wrapper read tape[step+1].
# Current V5 instead supplies that exact next authored action explicitly.


def _jit_qualifies(tile: Any, inventory: dict[str, Any], day: int) -> tuple[bool, str | None]:
    if not isinstance(tile, dict) or tile.get("kind") != "PLANT":
        return False, None
    crop = tile.get("crop")
    crop_data = _ANNUAL.get(crop)
    if crop_data is None:
        return False, crop if isinstance(crop, str) else None
    fertilizer = inventory.get("FERTILIZER", 0)
    planted_day = tile.get("planted_day")
    yield_units = tile.get("yield_units")
    fertilized_until = tile.get("fertilized_until_day")
    watered_today = tile.get("watered_today")
    if (type(fertilizer) is not int or fertilizer <= 0
            or type(planted_day) is not int
            or type(yield_units) is not int or yield_units < 0
            or type(fertilized_until) is not int
            or type(watered_today) is not bool):
        return False, crop
    if (watered_today or fertilized_until >= day
            or yield_units > crop_data["max_yield"] - 2):
        return False, crop
    age = day - planted_day
    window_start = (crop_data["max_yield_day"] + 1) // 2
    return window_start <= age <= crop_data["max_yield_day"], crop


def apply_jit_pass_fertilize(action: Any, observation: Any, next_authored: Any, *, enabled: bool):
    """Return ``(action, activations)`` using only a caller-authenticated next row."""
    if not enabled or not isinstance(action, dict) or not isinstance(observation, dict):
        return action, ()
    step = observation.get("step")
    if type(step) is not int or step < 0:
        return action, ()
    if step // _TURNS_PER_DAY != (step + 1) // _TURNS_PER_DAY:
        return action, ()
    selected = _commands(action)
    following = _commands(next_authored)
    if selected is None or following is None:
        return action, ()
    day = step // _TURNS_PER_DAY
    matches: list[tuple[int, str, list[int], int]] = []
    for worker in range(min(len(selected), len(following))):
        if not _literal_op(selected[worker], "PASS") or not _literal_op(following[worker], "WATER"):
            continue
        state = _position_tile(observation, worker)
        if state is None:
            continue
        tile, inventory, pos = state
        ok, crop = _jit_qualifies(tile, inventory, day)
        if ok and crop is not None:
            matches.append((worker, crop, pos, int(inventory["FERTILIZER"])))
    if not matches:
        return action, ()

    position_counts = Counter((pos[0], pos[1]) for _, _, pos, _ in matches)
    matches = [match for match in matches if position_counts[(match[2][0], match[2][1])] == 1]
    if not matches:
        return action, ()

    out = dict(action)
    hands = None
    activations = []
    for worker, crop, pos, fertilizer in matches:
        if worker == 0:
            out["farmer"] = ["FERTILIZE"]
        else:
            original_hands = action.get("hands")
            if not isinstance(original_hands, list) or worker - 1 >= len(original_hands):
                continue
            if hands is None:
                hands = [list(command) if isinstance(command, list) else command for command in original_hands]
                out["hands"] = hands
            hands[worker - 1] = ["FERTILIZE"]
        activations.append({
            "worker": worker,
            "crop": crop,
            "position": pos,
            "fertilizer_before": fertilizer,
            "reason": "literal_pass_before_same_worker_yield_water",
        })
    if not activations:
        return action, ()
    return out, tuple(activations)


class B5CurrentABI:
    """Stateless current selected-action adapter; no producer and no route lookup."""

    def __init__(self, *, carrot: bool = False, jit: bool = False):
        if type(carrot) is not bool or type(jit) is not bool:
            raise TypeError("carrot and jit must be exact bool")
        self.carrot = carrot
        self.jit = jit

    def transform(
        self,
        observation: Any,
        selected: Any,
        *,
        next_authored: Any = None,
        next_authored_step: Any = None,
    ):
        """Apply the submitted pair in order; authenticate the route edge for JIT.

        The historical JIT seam used the R04 tape at exactly ``step + 1``. A
        current caller therefore must bind both the authored action and its exact
        step. Missing/mismatched route authority makes JIT identity rather than
        guessing from current production output.
        """
        report = {
            "carrot_enabled": self.carrot,
            "jit_enabled": self.jit,
            "carrot_activations": (),
            "jit_activations": (),
            "jit_route_bound": False,
        }
        action = selected
        if self.carrot:
            action, activations = apply_carrot_fertilizer(observation, action)
            report["carrot_activations"] = activations
        if self.jit:
            step = observation.get("step") if isinstance(observation, dict) else None
            route_bound = (
                type(step) is int
                and type(next_authored_step) is int
                and next_authored_step == step + 1
                and isinstance(next_authored, dict)
            )
            report["jit_route_bound"] = route_bound
            if route_bound:
                action, activations = apply_jit_pass_fertilize(
                    action, observation, next_authored, enabled=True
                )
                report["jit_activations"] = activations
        report["changed"] = action != selected
        return action, report
