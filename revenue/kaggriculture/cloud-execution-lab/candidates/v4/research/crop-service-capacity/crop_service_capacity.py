# SPDX-License-Identifier: Apache-2.0
"""Source-derived crop service capacity bounds for TITAN V4.

This module deliberately does not choose crops, schedule movement, predict market
fills, or mutate returned actions. It exposes conservative action-budget ceilings
that a planner may consume before expanding its crop footprint.

The official engine creates every plant with ``consecutive_unwatered == 1``.
At end of day an unwatered plant increments that counter and becomes a weed at
``>= 2``. Therefore establishing one new plant that still exists after the same
end-of-day boundary requires at least two unit actions before that boundary:
one PLANT and one WATER.

The bounds are intentionally envelopes, not feasibility proofs. In particular,
future BUY_LAND / DIG / HARVEST can increase the set of plantable cells, so
*current* empty owned tiles are telemetry only and must not cap an impossibility
bound. The observation-authoritative board cell count is a safe physical upper
bound for simultaneous surviving new plants; ignoring the extra actions/cash
needed to make those cells plantable only overestimates capacity.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
CONFIG_GIT_BLOB = "b354d06b742fe48402513792253f1a5c29366b20"
HISTORICAL_DONOR_PR = 9806
DEFAULT_TURNS_PER_DAY = 24
DEFAULT_EPISODE_STEPS = 720
DEFAULT_MAX_MARKET_ORDERS = 10


class CapacityInputError(ValueError):
    """Raised when an observation/configuration is too ambiguous to certify."""


@dataclass(frozen=True)
class CapacityEnvelope:
    player: int
    hour: int
    step: int
    turns_per_day: int
    episode_steps: int
    callbacks_remaining: int
    eod_reachable_before_terminal: bool
    unit_actions_per_surviving_new_plant: int
    current_actors: int
    empty_owned_tiles: int
    board_tiles: int
    current_labor_action_slots: int
    future_hire_action_slots_upper: int
    current_labor_ceiling: int
    absolute_action_ceiling: int

    def as_dict(self) -> dict[str, int]:
        return {
            "player": self.player,
            "hour": self.hour,
            "step": self.step,
            "turns_per_day": self.turns_per_day,
            "episode_steps": self.episode_steps,
            "callbacks_remaining": self.callbacks_remaining,
            "eod_reachable_before_terminal": self.eod_reachable_before_terminal,
            "unit_actions_per_surviving_new_plant": self.unit_actions_per_surviving_new_plant,
            "current_actors": self.current_actors,
            "empty_owned_tiles": self.empty_owned_tiles,
            "board_tiles": self.board_tiles,
            "current_labor_action_slots": self.current_labor_action_slots,
            "future_hire_action_slots_upper": self.future_hire_action_slots_upper,
            "current_labor_ceiling": self.current_labor_ceiling,
            "absolute_action_ceiling": self.absolute_action_ceiling,
        }


def _strict_int(value: Any, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise CapacityInputError(f"{name}_must_be_int_ge_{minimum}")
    return value


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CapacityInputError(f"{name}_must_be_mapping")
    return value


def _farm_from_observation(
    observation: Mapping[str, Any],
) -> tuple[int, Mapping[str, Any], int]:
    obs = _mapping(observation, "observation")
    player = _strict_int(obs.get("player"), "player")
    farms = obs.get("farms")
    if not isinstance(farms, list) or player >= len(farms):
        raise CapacityInputError("farms_missing_player")
    farm = _mapping(farms[player], "farm")
    hands = farm.get("hands")
    tiles = farm.get("tiles")
    if not isinstance(hands, list):
        raise CapacityInputError("hands_must_be_list")
    if not isinstance(tiles, list) or not tiles:
        raise CapacityInputError("tiles_must_be_nonempty_rows")
    width = None
    for row in tiles:
        if not isinstance(row, list) or not row:
            raise CapacityInputError("tiles_must_be_nonempty_rows")
        if width is None:
            width = len(row)
        elif len(row) != width:
            raise CapacityInputError("tiles_must_be_rectangular")
    assert width is not None
    return player, farm, len(tiles) * width


def _empty_owned_tiles(farm: Mapping[str, Any]) -> int:
    # None is the engine's exact representation for an empty, unlocked tile.
    # "LOCKED", weeds, plants, structures, and animals are unavailable *now*.
    return sum(tile is None for row in farm["tiles"] for tile in row)


def _config_int(configuration: Mapping[str, Any] | None, key: str, default: int) -> int:
    if configuration is None:
        return default
    cfg = _mapping(configuration, "configuration")
    value = cfg.get(key, default)
    return _strict_int(value, key, minimum=1)


def capacity_envelope(
    observation: Mapping[str, Any],
    configuration: Mapping[str, Any] | None = None,
    *,
    configuration_authenticated: bool = False,
) -> CapacityEnvelope:
    """Return two conservative upper bounds for same-day crop expansion.

    ``current_labor_ceiling``:
        Maximum new surviving plants supportable by unit-action count if no
        future HIRE credit is taken. It does *not* assume the currently owned
        empty-cell set is frozen: future BUY_LAND / DIG / HARVEST may make more
        cells plantable, so the only physical cap used here is total observed
        board cells.

    ``absolute_action_ceiling``:
        A looser hard upper bound that grants ``maxMarketOrdersPerTurn`` future
        HIREs after every remaining callback, assumes every such hand can act on
        every later callback, ignores all HIRE/LAND cost and competing work,
        and caps only by total observed board cells.

    When the same-day EOD callback is executable, each surviving new plant is
    charged two unit actions (PLANT + WATER). If the episode terminal horizon
    cuts the day off before EOD, the weed transition cannot occur, so the hard
    action-budget lower bound drops to one PLANT action per new surviving plant.
    Callback count is capped by the earlier of same-day EOD and the final
    executable callback (``episodeSteps - 2``). Passing either bound proves
    nothing about feasibility; exceeding the chosen bound is the only certified
    conclusion.

    Omitted configuration uses pinned official defaults. Any explicit
    configuration is proof-critical and is accepted only when the caller has
    bound it to the interpreter instance and sets
    ``configuration_authenticated=True`` literally.
    """
    if configuration is not None and configuration_authenticated is not True:
        raise CapacityInputError("configuration_not_authenticated")

    player, farm, board_tiles = _farm_from_observation(observation)
    turns_per_day = _config_int(configuration, "turnsPerDay", DEFAULT_TURNS_PER_DAY)
    episode_steps = _config_int(configuration, "episodeSteps", DEFAULT_EPISODE_STEPS)
    if episode_steps < 2:
        raise CapacityInputError("episodeSteps_must_be_int_ge_2")
    max_market_orders = _config_int(
        configuration, "maxMarketOrdersPerTurn", DEFAULT_MAX_MARKET_ORDERS
    )

    hour = _strict_int(observation.get("hour"), "hour")
    step = _strict_int(observation.get("step"), "step")
    if hour >= turns_per_day:
        raise CapacityInputError("hour_out_of_day")
    if hour != step % turns_per_day:
        raise CapacityInputError("hour_step_mismatch")

    final_executable_step = episode_steps - 2
    if step > final_executable_step:
        raise CapacityInputError("step_after_final_executable_callback")
    callbacks_to_eod = turns_per_day - hour
    executable_callbacks_to_terminal = final_executable_step - step + 1
    callbacks_remaining = min(callbacks_to_eod, executable_callbacks_to_terminal)
    eod_step = step + callbacks_to_eod - 1
    eod_reachable_before_terminal = eod_step <= final_executable_step
    unit_actions_per_new_plant = 2 if eod_reachable_before_terminal else 1
    current_actors = 1 + len(farm["hands"])
    empty_owned = _empty_owned_tiles(farm)

    current_slots = current_actors * callbacks_remaining

    # Market executes after unit actions. Hands hired after the current callback
    # can act on R-1 later callbacks; hands hired after the next can act on R-2,
    # etc. Granting the full market-row cap as HIRE every callback produces a
    # deliberately loose upper bound independent of cash/fills.
    future_hire_slots = (
        max_market_orders * callbacks_remaining * (callbacks_remaining - 1) // 2
    )
    absolute_slots = current_slots + future_hire_slots

    # IMPORTANT: current empty owned tiles are not a hard future cap. BUY_LAND
    # can unlock cells in market phase for later callbacks, while DIG/HARVEST can
    # reclaim occupied cells. Counting every observed board cell as potentially
    # plantable is deliberately loose but preserves one-sided impossibility.
    current_ceiling = min(board_tiles, current_slots // unit_actions_per_new_plant)
    absolute_ceiling = min(board_tiles, absolute_slots // unit_actions_per_new_plant)

    return CapacityEnvelope(
        player=player,
        hour=hour,
        step=step,
        turns_per_day=turns_per_day,
        episode_steps=episode_steps,
        callbacks_remaining=callbacks_remaining,
        eod_reachable_before_terminal=eod_reachable_before_terminal,
        unit_actions_per_surviving_new_plant=unit_actions_per_new_plant,
        current_actors=current_actors,
        empty_owned_tiles=empty_owned,
        board_tiles=board_tiles,
        current_labor_action_slots=current_slots,
        future_hire_action_slots_upper=future_hire_slots,
        current_labor_ceiling=current_ceiling,
        absolute_action_ceiling=absolute_ceiling,
    )


def assess_proposed_expansion(
    observation: Mapping[str, Any],
    proposed_new_plants: int,
    configuration: Mapping[str, Any] | None = None,
    *,
    no_future_hires: bool = False,
    configuration_authenticated: bool = False,
) -> dict[str, Any]:
    """Classify only what the action budget can prove.

    Returns ``IMPOSSIBLE_ACTION_BUDGET`` only when the proposal exceeds the
    applicable conservative upper bound. Otherwise returns ``NOT_CERTIFIED``:
    movement, seed collateral, actor/target assignment, watering route, future
    land/reclamation actions, other work, and market execution remain unproved.

    Explicit caller configuration is proof-critical. Without literal
    ``configuration_authenticated=True`` it cannot be used to certify
    impossibility and this function returns ``NOT_CERTIFIED`` without a ceiling.
    """
    proposed = _strict_int(proposed_new_plants, "proposed_new_plants")
    if not isinstance(no_future_hires, bool):
        raise CapacityInputError("no_future_hires_must_be_bool")
    if configuration is not None and configuration_authenticated is not True:
        return {
            "verdict": "NOT_CERTIFIED",
            "reason": "configuration_not_authenticated",
            "proposed_new_plants": proposed,
            "ceiling": None,
            "bound": "current_labor" if no_future_hires else "absolute_action",
            "engine_git_blob": ENGINE_GIT_BLOB,
            "configuration_git_blob": CONFIG_GIT_BLOB,
            "historical_donor_pr": HISTORICAL_DONOR_PR,
            "envelope": None,
        }

    env = capacity_envelope(
        observation,
        configuration,
        configuration_authenticated=configuration_authenticated,
    )
    ceiling = (
        env.current_labor_ceiling if no_future_hires else env.absolute_action_ceiling
    )
    verdict = "IMPOSSIBLE_ACTION_BUDGET" if proposed > ceiling else "NOT_CERTIFIED"
    return {
        "verdict": verdict,
        "proposed_new_plants": proposed,
        "ceiling": ceiling,
        "bound": "current_labor" if no_future_hires else "absolute_action",
        "engine_git_blob": ENGINE_GIT_BLOB,
        "configuration_git_blob": CONFIG_GIT_BLOB,
        "historical_donor_pr": HISTORICAL_DONOR_PR,
        "envelope": env.as_dict(),
    }
