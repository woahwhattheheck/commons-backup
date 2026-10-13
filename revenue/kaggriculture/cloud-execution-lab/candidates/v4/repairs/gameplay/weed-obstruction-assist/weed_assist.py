from __future__ import annotations

import copy
from typing import Any, Mapping

CROPS = frozenset({"WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON"})
MOVES = frozenset({"NORTH", "SOUTH", "EAST", "WEST"})
TARGET_BUILDS = frozenset({"BUILD_COOP", "BUILD_PASTURE"})
_SAFE_INTERVENING = MOVES | frozenset({"PASS", "DIG"})


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _strict_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _position(value: Any) -> tuple[int, int] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    x = _strict_int(value[0])
    y = _strict_int(value[1])
    if x is None or y is None:
        return None
    return x, y


def _op(action: Any) -> str | None:
    if not isinstance(action, list) or not action:
        return None
    return action[0] if isinstance(action[0], str) else None


def _literal_pass(action: Any) -> bool:
    return action == ["PASS"]


def _valid_target(action: Any) -> bool:
    op = _op(action)
    if op == "PLANT":
        return len(action) == 2 and action[1] in CROPS
    return op in TARGET_BUILDS and len(action) == 1


def _is_weed(tile: Any) -> bool:
    return isinstance(tile, Mapping) and tile.get("kind") == "WEED"


def _tile_at(tiles: Any, pos: tuple[int, int]) -> Any:
    if not isinstance(tiles, list):
        return None
    x, y = pos
    if y < 0 or y >= len(tiles):
        return None
    row = tiles[y]
    if not isinstance(row, list) or x < 0 or x >= len(row):
        return None
    return row[x]


def _plant_demand(actions: list[Any], crop: str) -> int:
    demand = 0
    for action in actions:
        if isinstance(action, list) and len(action) >= 2 and action[0] == "PLANT" and action[1] == crop:
            demand += 1
    return demand


def _available_seeds(observation: Any, crop: str) -> int | None:
    private = _get(observation, "private")
    seeds = _get(private, "seeds")
    if not isinstance(seeds, Mapping):
        return None
    value = seeds.get(crop)
    value = _strict_int(value)
    if value is None or value < 0:
        return None
    return value


def _actor_positions(farm: Any) -> list[tuple[int, int]] | None:
    farmer = _position(_get(farm, "farmer"))
    hands = _get(farm, "hands")
    if farmer is None or not isinstance(hands, list):
        return None
    out = [farmer]
    for raw in hands:
        pos = _position(raw)
        if pos is None:
            return None
        out.append(pos)
    return out


def assist_same_turn_weed_obstructions(
    observation: Any,
    returned_action: Any,
    *,
    enabled: bool = False,
) -> tuple[Any, dict[str, Any]]:
    """Use an earlier co-located literal PASS actor to DIG for a later PLANT/BUILD.

    The official interpreter executes main farmer first, then live hands in order.
    When a later actor stands on WEED and has a valid PLANT/BUILD action, an earlier
    co-located idle actor can clear that WEED with DIG in the same turn. The intended
    action is not moved or rewritten.

    This helper is deliberately conservative:
    * no persistent retry state;
    * only live actors may be helpers/targets;
    * helpers must be literal ``["PASS"]`` rows;
    * PLANT is admitted only when the engine's raw atomic seed census can pass;
    * an intervening co-located action must be PASS, DIG, or movement;
    * raw suffix hand rows remain byte-for-byte untouched and still count in PLANT
      demand because the engine counts them before live-actor dispatch.
    """
    enabled_is_bool = type(enabled) is bool
    report: dict[str, Any] = {
        "schema": "titan-v4-weed-assist-v1",
        "enabled": enabled is True if enabled_is_bool else False,
        "changed": False,
        "rewrites": [],
        "reason": (
            "invalid_enabled"
            if not enabled_is_bool
            else ("disabled" if enabled is False else "ineligible")
        ),
    }
    if not enabled_is_bool or enabled is False:
        return returned_action, report
    if not isinstance(returned_action, dict):
        return returned_action, report

    player = _strict_int(_get(observation, "player"))
    farms = _get(observation, "farms")
    if player is None or player < 0 or not isinstance(farms, list) or player >= len(farms):
        return returned_action, report
    farm = farms[player]
    positions = _actor_positions(farm)
    tiles = _get(farm, "tiles")
    if positions is None or not isinstance(tiles, list):
        return returned_action, report

    if "farmer" not in returned_action or "hands" not in returned_action:
        return returned_action, report
    farmer_action = returned_action["farmer"]
    hands = returned_action["hands"]
    if not isinstance(hands, list):
        return returned_action, report

    live_hand_count = len(positions) - 1
    live_actions = [farmer_action, *hands[:live_hand_count]]
    raw_actions = [farmer_action, *hands]

    # We only rewrite actor rows that are represented in the action vector.
    if len(live_actions) != len(positions):
        return returned_action, report

    replacements: dict[int, list[str]] = {}
    used_helpers: set[int] = set()
    claimed_positions: set[tuple[int, int]] = set()

    for target_idx, (target_pos, target_action) in enumerate(zip(positions, live_actions)):
        if target_pos in claimed_positions or not _valid_target(target_action):
            continue
        if not _is_weed(_tile_at(tiles, target_pos)):
            continue

        target_op = _op(target_action)
        if target_op == "PLANT":
            crop = target_action[1]
            seeds = _available_seeds(observation, crop)
            if seeds is None or _plant_demand(raw_actions, crop) > seeds:
                continue

        # Latest earlier co-located literal PASS minimizes disruption.
        helper_idx = None
        for idx in range(target_idx - 1, -1, -1):
            if idx in used_helpers:
                continue
            if positions[idx] == target_pos and _literal_pass(live_actions[idx]):
                helper_idx = idx
                break
        if helper_idx is None:
            continue

        # After the helper DIG executes, no intervening co-located actor may be
        # able to occupy/mutate that now-empty tile before the target runs.
        safe = True
        for idx in range(helper_idx + 1, target_idx):
            if positions[idx] != target_pos:
                continue
            if _op(live_actions[idx]) not in _SAFE_INTERVENING:
                safe = False
                break
        if not safe:
            continue

        replacements[helper_idx] = ["DIG"]
        used_helpers.add(helper_idx)
        claimed_positions.add(target_pos)
        report["rewrites"].append(
            {
                "helper_actor_index": helper_idx,
                "target_actor_index": target_idx,
                "position": [target_pos[0], target_pos[1]],
                "target_op": target_op,
            }
        )

    if not replacements:
        return returned_action, report

    out = copy.deepcopy(returned_action)
    for actor_idx, replacement in replacements.items():
        if actor_idx == 0:
            out["farmer"] = replacement
        else:
            out["hands"][actor_idx - 1] = replacement

    report["changed"] = True
    report["reason"] = "same_turn_assist"
    return out, report