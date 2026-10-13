# SPDX-License-Identifier: Apache-2.0
"""Default-off B5 experiment: spend an existing PASS on just-in-time fertilizer.

This helper is deliberately narrower than a route scheduler.  It changes a literal
selected PASS only when the same worker's *next authored* command is a same-day WATER
on the annual plant the worker is already standing on, the plant's next WATER is
provably yield-bearing and uncovered, and the worker already carries fertilizer.
Anything ambiguous returns the exact parent action object unchanged.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

_TURNS_PER_DAY = 24
_ANNUAL = {
    "WHEAT": {"max_yield_day": 4, "max_yield": 6},
    "CARROT": {"max_yield_day": 3, "max_yield": 4},
    "MELON": {"max_yield_day": 12, "max_yield": 6},
}


def _literal_op(command: Any, name: str) -> bool:
    return isinstance(command, list) and command == [name]


def _commands(row: Any) -> list[Any] | None:
    if not isinstance(row, dict):
        return None
    farmer = row.get("farmer")
    hands = row.get("hands", [])
    if not isinstance(hands, list):
        return None
    return [farmer, *hands]


def _public_actor_positions(observation: dict[str, Any]) -> Counter[tuple[int, int]] | None:
    """Count every public own-farm actor position, independent of action eligibility."""
    player = observation.get("player")
    farms = observation.get("farms")
    if type(player) is not int or not isinstance(farms, list) or not (0 <= player < len(farms)):
        return None
    farm = farms[player]
    if not isinstance(farm, dict):
        return None
    farmer = farm.get("farmer")
    hands = farm.get("hands", [])
    tiles = farm.get("tiles")
    if not isinstance(hands, list) or not isinstance(tiles, list):
        return None

    positions: list[tuple[int, int]] = []
    for pos in [farmer, *hands]:
        if (not isinstance(pos, list) or len(pos) != 2
                or type(pos[0]) is not int or type(pos[1]) is not int):
            return None
        x, y = pos
        if not (0 <= y < len(tiles) and isinstance(tiles[y], list)
                and 0 <= x < len(tiles[y])):
            return None
        positions.append((x, y))
    return Counter(positions)


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


def _qualifies(tile: Any, inventory: dict[str, Any], day: int) -> tuple[bool, str | None]:
    if not isinstance(tile, dict) or tile.get("kind") != "PLANT":
        return False, None
    crop = tile.get("crop")
    if not isinstance(crop, str):
        return False, None
    crop_data = _ANNUAL.get(crop)
    if crop_data is None:
        return False, crop
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
    # Fertilized annual WATER adds 2 units while ordinary WATER adds 1. Spending
    # one fertilizer has positive marginal yield only when at least 2 units of
    # headroom remain; at max-1 both paths truncate to the same cap.
    if (watered_today or fertilized_until >= day
            or yield_units > crop_data["max_yield"] - 2):
        return False, crop
    age = day - planted_day
    window_start = (crop_data["max_yield_day"] + 1) // 2
    return window_start <= age <= crop_data["max_yield_day"], crop


def apply_jit_pass_fertilize(
    action: Any,
    observation: Any,
    next_authored: Any,
    *,
    enabled: bool = False,
) -> tuple[Any, tuple[dict[str, Any], ...]]:
    """Return ``(action, activations)``; no-match and disabled paths preserve identity."""
    if not enabled or not isinstance(action, dict) or not isinstance(observation, dict):
        return action, ()
    step = observation.get("step")
    if type(step) is not int or step < 0:
        return action, ()
    # This first experiment refuses a day boundary: it relies only on current visible
    # ``watered_today`` and does not predict the end-of-day plant refresh.
    if step // _TURNS_PER_DAY != (step + 1) // _TURNS_PER_DAY:
        return action, ()
    selected = _commands(action)
    following = _commands(next_authored)
    if selected is None or following is None:
        return action, ()
    position_counts = _public_actor_positions(observation)
    if position_counts is None:
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
        ok, crop = _qualifies(tile, inventory, day)
        # FERTILIZE updates tile coverage, not worker state. Any co-located public
        # actor could already own or consume this tile's coverage in the same callback.
        # Only a uniquely occupied tile is safe for this narrow substitution.
        if (ok and crop is not None
                and position_counts[(pos[0], pos[1])] == 1):
            matches.append((worker, crop, pos, int(inventory["FERTILIZER"])))
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
            "step": step,
            "worker": worker,
            "crop": crop,
            "position": pos,
            "fertilizer_before": fertilizer,
            "reason": "literal_pass_before_same_worker_yield_water",
        })
    if not activations:
        return action, ()
    return out, tuple(activations)
