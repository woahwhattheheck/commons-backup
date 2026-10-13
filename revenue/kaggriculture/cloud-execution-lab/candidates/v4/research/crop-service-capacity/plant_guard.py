# SPDX-License-Identifier: Apache-2.0
"""One-sided same-EOD PLANT survival evidence for TITAN V4.

This module strengthens the source-derived CROPSCALE theorem without becoming a
scheduler. A newly created plant starts unwatered and will become a weed at the
same end-of-day refresh unless WATER reaches that tile after PLANT.

`assess_same_eod_plant_survival` consumes an already-produced current action plus
an authenticated complete authored unit suffix through end-of-day. It returns
`DOOMED_AUTHORED_SUFFIX` only when an executable current PLANT has no WATER from
any existing actor after creation and before EOD. It never returns SAFE.

Future HIRE is a hard ambiguity because a new actor could create a watering path.
Malformed/incomplete evidence likewise returns `NOT_CERTIFIED`.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
CONFIG_GIT_BLOB = "b354d06b742fe48402513792253f1a5c29366b20"
DEFAULT_TURNS_PER_DAY = 24
DEFAULT_EPISODE_STEPS = 720
DEFAULT_MAX_MARKET_ORDERS = 10
CROPS = frozenset(("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON"))
MOVES = {
    "NORTH": (0, -1),
    "SOUTH": (0, 1),
    "EAST": (1, 0),
    "WEST": (-1, 0),
}


class PlantGuardInputError(ValueError):
    """Evidence is too ambiguous for one-sided PLANT rejection."""


def _strict_int(value: Any, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise PlantGuardInputError(f"{name}_must_be_int_ge_{minimum}")
    return value


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PlantGuardInputError(f"{name}_must_be_mapping")
    return value


def _config_int(
    configuration: Mapping[str, Any] | None,
    key: str,
    default: int,
    *,
    minimum: int = 1,
) -> int:
    if configuration is None:
        return default
    cfg = _mapping(configuration, "configuration")
    return _strict_int(cfg.get(key, default), key, minimum=minimum)


def _action_rows(action: Mapping[str, Any], actor_count: int) -> list[list[Any]]:
    if not isinstance(action, Mapping):
        raise PlantGuardInputError("action_must_be_mapping")
    farmer = action.get("farmer")
    hands = action.get("hands")
    if not isinstance(farmer, list) or not farmer:
        raise PlantGuardInputError("farmer_command_must_be_nonempty_list")
    if not isinstance(hands, list) or len(hands) != actor_count - 1:
        raise PlantGuardInputError("hand_command_cardinality_mismatch")
    if any(not isinstance(row, list) or not row for row in hands):
        raise PlantGuardInputError("hand_command_must_be_nonempty_list")
    return [farmer, *hands]


def _market_has_actionable_hire(action: Mapping[str, Any], max_orders: int) -> bool:
    rows = action.get("market", [])
    if not isinstance(rows, list):
        raise PlantGuardInputError("market_must_be_list")
    for row in rows[:max_orders]:
        if not row:
            continue
        if not isinstance(row, list):
            raise PlantGuardInputError("truthy_market_row_must_be_list")
        if row[0] == "HIRE":
            return True
    return False


def _farm_and_private(
    observation: Mapping[str, Any],
) -> tuple[Mapping[str, Any], Mapping[str, Any], list[list[int]], int]:
    obs = _mapping(observation, "observation")
    player = _strict_int(obs.get("player"), "player")
    farms = obs.get("farms")
    if not isinstance(farms, list) or player >= len(farms):
        raise PlantGuardInputError("farms_missing_player")
    farm = _mapping(farms[player], "farm")
    tiles = farm.get("tiles")
    hands = farm.get("hands")
    farmer = farm.get("farmer")
    if not isinstance(tiles, list) or not tiles:
        raise PlantGuardInputError("tiles_must_be_square")
    board_size = len(tiles)
    if any(not isinstance(row, list) or len(row) != board_size for row in tiles):
        raise PlantGuardInputError("tiles_must_be_square")
    if not isinstance(hands, list):
        raise PlantGuardInputError("hands_must_be_list")
    raw_positions = [farmer, *hands]
    positions: list[list[int]] = []
    for index, pos in enumerate(raw_positions):
        if (
            not isinstance(pos, list)
            or len(pos) != 2
            or any(isinstance(v, bool) or not isinstance(v, int) for v in pos)
        ):
            raise PlantGuardInputError(f"actor_{index}_position_malformed")
        x, y = pos
        if not (0 <= x < board_size and 0 <= y < board_size):
            raise PlantGuardInputError(f"actor_{index}_position_out_of_bounds")
        positions.append([x, y])
    private = _mapping(obs.get("private"), "private")
    seeds = _mapping(private.get("seeds"), "private_seeds")
    for crop in CROPS:
        if crop in seeds:
            _strict_int(seeds[crop], f"seed_{crop}")
    return farm, private, positions, board_size


def _move(position: list[int], command: list[Any], board_size: int) -> None:
    op = command[0]
    if op not in MOVES:
        return
    dx, dy = MOVES[op]
    nx, ny = position[0] + dx, position[1] + dy
    if 0 <= nx < board_size and 0 <= ny < board_size:
        position[0], position[1] = nx, ny


def _not_certified(reason: str, *, candidates: Sequence[int] = ()) -> dict[str, Any]:
    return {
        "verdict": "NOT_CERTIFIED",
        "reason": reason,
        "candidate_actor_indices": list(candidates),
        "doomed_actor_indices": [],
        "watered_actor_indices": [],
        "removed_actor_indices": [],
        "engine_git_blob": ENGINE_GIT_BLOB,
        "configuration_git_blob": CONFIG_GIT_BLOB,
        "decision_authority": False,
    }


def assess_same_eod_plant_survival(
    observation: Mapping[str, Any],
    selected_action: Mapping[str, Any],
    authored_suffix: Sequence[Mapping[str, Any]],
    configuration: Mapping[str, Any] | None = None,
    *,
    suffix_authenticated: bool = False,
    configuration_authenticated: bool = False,
) -> dict[str, Any]:
    """Return one-sided evidence about current PLANT actions.

    `authored_suffix` must contain exactly one action dict for every remaining
    callback after the current one and before same-day EOD. It is evidence, not
    a forecast: callers may set `suffix_authenticated=True` only when those unit
    commands are the exact authored suffix whose custody they are evaluating.
    When `configuration` is supplied explicitly, callers must likewise set
    `configuration_authenticated=True` only after binding those values to the
    interpreter instance whose action custody is being evaluated. Omitting
    `configuration` uses the pinned official defaults.

    Result semantics:
    - `DOOMED_AUTHORED_SUFFIX`: at least one executable current PLANT has no
      WATER on its tile after creation and before EOD in the authenticated
      suffix, with no future-HIRE actor ambiguity.
    - `NOT_CERTIFIED`: everything else, including a discovered WATER. This
      helper intentionally never labels a plant SAFE or profitable.
    """
    try:
        if configuration is not None and configuration_authenticated is not True:
            return _not_certified("configuration_not_authenticated")
        if suffix_authenticated is not True:
            return _not_certified("suffix_not_authenticated")
        turns_per_day = _config_int(
            configuration, "turnsPerDay", DEFAULT_TURNS_PER_DAY
        )
        episode_steps = _config_int(
            configuration, "episodeSteps", DEFAULT_EPISODE_STEPS, minimum=2
        )
        max_orders = _config_int(
            configuration, "maxMarketOrdersPerTurn", DEFAULT_MAX_MARKET_ORDERS
        )
        hour = _strict_int(observation.get("hour"), "hour")
        step = _strict_int(observation.get("step"), "step")
        if hour >= turns_per_day:
            raise PlantGuardInputError("hour_out_of_day")
        if hour != step % turns_per_day:
            raise PlantGuardInputError("hour_step_mismatch")

        # The official interpreter marks the episode done at
        # step >= episodeSteps - 2. The callback at episodeSteps - 2 is the
        # final executable callback; later nominal clock rows are never
        # executed. A same-EOD doom certificate therefore requires not merely
        # an authored suffix shaped through hour 23, but proof that this day's
        # hour-23 callback actually occurs inside the executable horizon.
        final_executable_step = episode_steps - 2
        if step > final_executable_step:
            raise PlantGuardInputError("step_after_final_executable_callback")
        eod_step = step + (turns_per_day - hour - 1)
        if eod_step > final_executable_step:
            return _not_certified("eod_not_reachable_before_terminal")

        farm, private, positions, board_size = _farm_and_private(observation)
        actor_count = len(positions)
        current_commands = _action_rows(selected_action, actor_count)

        if not isinstance(authored_suffix, Sequence) or isinstance(
            authored_suffix, (str, bytes)
        ):
            raise PlantGuardInputError("authored_suffix_must_be_sequence")
        expected = turns_per_day - hour - 1
        if len(authored_suffix) != expected:
            return _not_certified("incomplete_authored_suffix")

        future_actions = list(authored_suffix)
        future_commands: list[list[list[Any]]] = []
        for offset, action in enumerate(future_actions, start=1):
            future_commands.append(_action_rows(action, actor_count))
            callback_hour = hour + offset
            # A HIRE at hour 23 cannot act before that same EOD; earlier HIREs
            # can add a watering actor and therefore destroy one-sided doom.
            if callback_hour < turns_per_day - 1 and _market_has_actionable_hire(
                action, max_orders
            ):
                return _not_certified("future_hire_actor_ambiguity")

        if hour < turns_per_day - 1 and _market_has_actionable_hire(
            selected_action, max_orders
        ):
            return _not_certified("current_hire_actor_ambiguity")

        # Official atomic PLANT preflight rejects every same-crop PLANT when
        # aggregate demand exceeds held seeds.
        demand: dict[str, int] = {}
        for command in current_commands:
            if command and command[0] == "PLANT" and len(command) >= 2:
                crop = command[1]
                if crop in CROPS:
                    demand[crop] = demand.get(crop, 0) + 1

        seeds = private["seeds"]
        seed_blocked = {
            crop for crop, count in demand.items()
            if _strict_int(seeds.get(crop, 0), f"seed_{crop}") < count
        }

        # Find PLANTs that can actually create a plant on the current unit stage.
        # Unit rows execute farmer first, then hands. A prior same-site PLANT
        # that survives the atomic seed preflight definitely occupies the tile.
        # BUILD_COOP/BUILD_PASTURE can also occupy an initially-empty tile, but
        # whether they succeed depends on mutable farm money. Rather than infer
        # that private transition here, fail closed when such a possible build
        # precedes a PLANT at the same site. Earlier clearing actions are left
        # conservative: an initially nonempty tile is never promoted to a
        # candidate merely because a preceding DIG/HARVEST might clear it.
        target_owner: dict[tuple[int, int], int] = {}
        possible_build_targets: set[tuple[int, int]] = set()
        candidate_targets: dict[int, tuple[int, int]] = {}
        tiles = farm["tiles"]
        for actor_index, command in enumerate(current_commands):
            target = tuple(positions[actor_index])
            x, y = target
            op = command[0]

            if op in {"BUILD_COOP", "BUILD_PASTURE"}:
                if tiles[y][x] is None and target not in target_owner:
                    possible_build_targets.add(target)
                continue

            if op != "PLANT" or len(command) < 2:
                continue
            crop = command[1]
            if crop not in CROPS or crop in seed_blocked:
                continue
            if tiles[y][x] is not None:
                continue
            if target in possible_build_targets:
                return _not_certified(
                    "current_stage_tile_effect_ambiguity",
                    candidates=sorted(candidate_targets),
                )
            if target in target_owner:
                continue
            target_owner[target] = actor_index
            candidate_targets[actor_index] = target

        if not candidate_targets:
            return _not_certified("no_executable_current_plant")

        unresolved = set(candidate_targets)
        watered: set[int] = set()
        removed: set[int] = set()

        # Current unit-stage actor order matters. WATER before a later PLANT is
        # too early; DIG after a PLANT removes that exact plant and therefore
        # cannot support a same-EOD weed-doom certificate. An earlier DIG on an
        # initially empty site is a no-op and must not suppress a later PLANT.
        for actor_index, command in enumerate(current_commands):
            op = command[0]
            here = tuple(positions[actor_index])
            if op == "WATER":
                for plant_actor in list(unresolved):
                    if (
                        candidate_targets[plant_actor] == here
                        and plant_actor < actor_index
                    ):
                        unresolved.remove(plant_actor)
                        watered.add(plant_actor)
            elif op == "DIG":
                for plant_actor in list(unresolved):
                    if (
                        candidate_targets[plant_actor] == here
                        and plant_actor < actor_index
                    ):
                        unresolved.remove(plant_actor)
                        removed.add(plant_actor)
            _move(positions[actor_index], command, board_size)

        # On later callbacks every unresolved candidate already exists. WATER
        # discharges its same-EOD watering obligation; DIG removes the plant, so
        # the original PLANT can no longer be certified as a weed at that EOD.
        for commands in future_commands:
            for actor_index, command in enumerate(commands):
                op = command[0]
                here = tuple(positions[actor_index])
                if op == "WATER":
                    for plant_actor in list(unresolved):
                        if candidate_targets[plant_actor] == here:
                            unresolved.remove(plant_actor)
                            watered.add(plant_actor)
                elif op == "DIG":
                    for plant_actor in list(unresolved):
                        if candidate_targets[plant_actor] == here:
                            unresolved.remove(plant_actor)
                            removed.add(plant_actor)
                _move(positions[actor_index], command, board_size)

        candidates = sorted(candidate_targets)
        if not unresolved:
            reason = (
                "plant_removed_before_eod" if removed else "water_found_before_eod"
            )
            return {
                "verdict": "NOT_CERTIFIED",
                "reason": reason,
                "candidate_actor_indices": candidates,
                "doomed_actor_indices": [],
                "watered_actor_indices": sorted(watered),
                "removed_actor_indices": sorted(removed),
                "targets": {
                    str(index): list(candidate_targets[index]) for index in candidates
                },
                "engine_git_blob": ENGINE_GIT_BLOB,
                "configuration_git_blob": CONFIG_GIT_BLOB,
                "decision_authority": False,
            }

        return {
            "verdict": "DOOMED_AUTHORED_SUFFIX",
            "reason": "no_water_after_plant_before_eod",
            "candidate_actor_indices": candidates,
            "doomed_actor_indices": sorted(unresolved),
            "watered_actor_indices": sorted(watered),
            "removed_actor_indices": sorted(removed),
            "targets": {
                str(index): list(candidate_targets[index]) for index in candidates
            },
            "engine_git_blob": ENGINE_GIT_BLOB,
            "configuration_git_blob": CONFIG_GIT_BLOB,
            "decision_authority": False,
        }
    except (PlantGuardInputError, KeyError, TypeError, IndexError) as error:
        return _not_certified(str(error) or type(error).__name__)
