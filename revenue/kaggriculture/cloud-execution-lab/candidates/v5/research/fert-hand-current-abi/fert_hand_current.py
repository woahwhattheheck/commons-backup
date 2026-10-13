# SPDX-License-Identifier: Apache-2.0
"""Current-ABI recovery of the V3.1 endgame fertilizer-hand theorem.

The submitted V3.1 policy owned one extra late-game farm hand without allowing
that hand to perturb its parent route.  The historical wrapper achieved this by
removing the owned hand from the observation before calling the parent, then
reinserting only the owned hand's command afterward.

This module preserves that theorem as a two-boundary V5 adapter.  It never
constructs or calls a producer and it does not wire itself into TITAN.  A caller
may:

1. call ``parent_observation`` before its existing producer;
2. call ``transform_selected`` on the producer's returned action.

The candidate is fail-closed, instance-local, and default-disconnected.  It is
evidence/source for a current-ABI carrier, not a promotion decision.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import math
from typing import Any, Mapping, Sequence

HISTORICAL_SOURCE_COMMIT = "a90d888f03987ef0b35cfd20ec3519c6144db08a"
HISTORICAL_SOURCE_BLOB = "79fefde712a38f802e9d77e68b3f8943fe137cd3"
HISTORICAL_SUBMISSION_SHA256 = (
    "5db3921f85efbc7596e5a1e7e198fc5f4644ceea43d8e8323c74ded7b4ba4361"
)

DAYS = (24, 25, 26, 27, 28)
HIRE_HOUR = 3
CROPS = ("CARROT",)
PRICE_KEEP = 0.8
REACH = 6
MIN_GAIN = 100
GAIN_RATIO = 1.2
BOARD_SIZE = 10
MAX_ORDERS = 10
TURNS_PER_DAY = 24
EPISODE_STEPS = 720

# first_yield_day, max_yield_day, max_yield
CROP_DATA = {
    "CARROT": (2, 3, 4),
}


@dataclass
class _DayState:
    day: int
    index: int | None = None
    pending: int | None = None
    tried: bool = False
    picked: bool = False
    want: int = 0
    last_step: int = -1
    hire_step: int | None = None
    hire_buy: int = 0
    command_step: int | None = None
    command: list[Any] | None = None


def _finite_number(value: Any) -> bool:
    return (
        type(value) in (int, float)
        and (type(value) is int or math.isfinite(value))
    )


def _plain_nonnegative_int(value: Any) -> bool:
    return type(value) is int and value >= 0


def _fib(index: int) -> int:
    a, b = 1, 1
    for _ in range(index):
        a, b = b, a + b
    return a


def _shed_tiles(board: int) -> set[tuple[int, int]]:
    half = board // 2
    return {
        (half - 1, half - 1),
        (half, half - 1),
        (half - 1, half),
        (half, half),
    }


def _identity(selected: Any, reason: str, **extra: Any):
    report = {"changed": False, "reason": reason}
    report.update(extra)
    return selected, report


def _config(configuration: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if configuration is None:
        cfg: dict[str, Any] = {}
    elif isinstance(configuration, Mapping):
        cfg = dict(configuration)
    else:
        return None
    expected = {
        "boardSize": BOARD_SIZE,
        "maxMarketOrdersPerTurn": MAX_ORDERS,
        "turnsPerDay": TURNS_PER_DAY,
        "episodeSteps": EPISODE_STEPS,
        "farmHandCostMult": 1,
    }
    for key, default in expected.items():
        value = cfg.get(key, default)
        if type(value) is not int or value != default:
            return None
    return cfg


def _clock(observation: Mapping[str, Any]) -> tuple[int, int, int] | None:
    player = observation.get("player")
    step = observation.get("step")
    if type(player) is not int or player not in (0, 1):
        return None
    if type(step) is not int or not 0 <= step < EPISODE_STEPS:
        return None
    return player, step, step // TURNS_PER_DAY


def _own_state(observation: Mapping[str, Any]):
    clock = _clock(observation)
    farms = observation.get("farms")
    private = observation.get("private")
    if clock is None or not isinstance(farms, list) or len(farms) != 2:
        return None
    if not isinstance(private, Mapping):
        return None
    player, step, day = clock
    farm = farms[player]
    if not isinstance(farm, Mapping):
        return None
    hands = farm.get("hands")
    inventories = private.get("inventories")
    shed = private.get("shed")
    tiles = farm.get("tiles")
    if (
        not isinstance(hands, list)
        or not isinstance(inventories, list)
        or not isinstance(shed, Mapping)
        or not isinstance(tiles, list)
        or len(tiles) != BOARD_SIZE
        or any(not isinstance(row, list) or len(row) != BOARD_SIZE for row in tiles)
        or len(inventories) != len(hands) + 1
    ):
        return None
    return player, step, day, farm, hands, inventories, shed, tiles


def _gain(tile: Any, day: int) -> int:
    if not isinstance(tile, Mapping) or tile.get("kind") != "PLANT":
        return 0
    crop = tile.get("crop")
    if crop not in CROPS:
        return 0
    _first, last, cap = CROP_DATA[crop]
    planted = tile.get("planted_day")
    covered = tile.get("fertilized_until_day", -1)
    have = tile.get("yield_units", 0)
    watered = tile.get("watered_today")
    if (
        type(planted) is not int
        or type(covered) is not int
        or type(have) is not int
        or have < 0
        or type(watered) is not bool
    ):
        return 0
    start = planted + (last + 1) // 2
    end = planted + last
    waters = [w for w in range(start, end + 1) if w > day or (w == day and not watered)]
    if not waters:
        return 0
    base = min(cap, have + sum(2 if w <= covered else 1 for w in waters))
    cover = max(covered, day + 2)
    fertilized = min(cap, have + sum(2 if w <= cover else 1 for w in waters))
    return max(0, fertilized - base)


def _targets(tiles: Sequence[Sequence[Any]], day: int) -> list[tuple[int, int, int]]:
    result = []
    for y, row in enumerate(tiles):
        for x, tile in enumerate(row):
            gain = _gain(tile, day)
            if gain > 0:
                result.append((x, y, gain))
    return result


def _validated_rest_of_day(
    future_actions: Any,
    *,
    step: int,
) -> list[Mapping[str, Any]] | None:
    """Require the complete parent route tail from step+1 to the day boundary."""
    if (
        not isinstance(future_actions, Sequence)
        or isinstance(future_actions, (str, bytes, bytearray))
    ):
        return None
    day_end = min(((step // TURNS_PER_DAY) + 1) * TURNS_PER_DAY, EPISODE_STEPS)
    expected = max(0, day_end - step - 1)
    if len(future_actions) != expected:
        return None
    rows = []
    for action in future_actions:
        if not isinstance(action, Mapping):
            return None
        farmer = action.get("farmer")
        hands = action.get("hands")
        market = action.get("market")
        if (
            not isinstance(farmer, list)
            or not isinstance(hands, list)
            or not isinstance(market, list)
            or any(not isinstance(command, list) for command in hands)
            or any(order and not isinstance(order, list) for order in market)
        ):
            return None
        rows.append(action)
    return rows


def _future_hire(rows: Sequence[Mapping[str, Any]]) -> bool:
    for action in rows:
        market = action.get("market", [])
        if not isinstance(market, list):
            return True
        for order in market:
            if order and isinstance(order, list) and order[0] == "HIRE":
                return True
    return False


def _future_plantings(rows: Sequence[Mapping[str, Any]]) -> int:
    count = 0
    for action in rows:
        unit_rows = [action.get("farmer"), *(action.get("hands") or [])]
        for command in unit_rows:
            if (
                isinstance(command, list)
                and len(command) > 1
                and command[0] == "PLANT"
                and command[1] in CROPS
            ):
                count += 1
    return count


def _future_fertilizer_pickups(rows: Sequence[Mapping[str, Any]]) -> int:
    count = 0
    for action in rows:
        unit_rows = [action.get("farmer"), *(action.get("hands") or [])]
        for command in unit_rows:
            if (
                isinstance(command, list)
                and len(command) > 1
                and command[0] == "PICKUP"
                and command[1] == "FERTILIZER"
            ):
                quantity = command[2] if len(command) > 2 else 1
                if type(quantity) is not int or quantity < 0:
                    return MAX_ORDERS * EPISODE_STEPS
                count += quantity
    return count


def _step_toward(
    pos: tuple[int, int],
    target: tuple[int, int],
    avoid: set[tuple[int, int]],
) -> list[str]:
    x, y = pos
    tx, ty = target
    options = []
    if tx > x:
        options.append(("EAST", (x + 1, y)))
    if tx < x:
        options.append(("WEST", (x - 1, y)))
    if ty > y:
        options.append(("SOUTH", (x, y + 1)))
    if ty < y:
        options.append(("NORTH", (x, y - 1)))
    if not options:
        return ["PASS"]
    options.sort(key=lambda row: row[1] in avoid)
    return [options[0][0]]


def _leave_shed(
    pos: tuple[int, int],
    avoid: set[tuple[int, int]],
) -> list[str]:
    x, y = pos
    for name, (dx, dy) in (
        ("NORTH", (0, -1)),
        ("WEST", (-1, 0)),
        ("SOUTH", (0, 1)),
        ("EAST", (1, 0)),
    ):
        target = (x + dx, y + dy)
        if (
            0 <= target[0] < BOARD_SIZE
            and 0 <= target[1] < BOARD_SIZE
            and target not in avoid
        ):
            return [name]
    return ["PASS"]


class FertHandCurrentABI:
    """Two-boundary current-ABI adapter for one candidate-owned farm hand."""

    def __init__(self):
        self._states: dict[int, _DayState] = {}
        self.diagnostics: dict[str, Any] = {}

    def _state(self, observation: Mapping[str, Any]) -> tuple[_DayState, tuple] | None:
        parsed = _own_state(observation)
        if parsed is None:
            return None
        player, step, day, farm, hands, inventories, shed, tiles = parsed
        state = self._states.get(player)
        if state is None or state.day != day or step < state.last_step:
            state = self._states[player] = _DayState(day=day)
        state.last_step = max(state.last_step, step)

        if state.pending is not None and state.hire_step is not None and step > state.hire_step:
            if len(hands) == state.pending + 1:
                state.index = state.pending
            state.pending = None

        if state.index is not None and not 0 <= state.index < len(hands):
            # End-of-day reset is handled above. Any other cardinality drift
            # means ownership can no longer be proven.
            state.index = None
            state.command_step = None
            state.command = None
        return state, parsed

    def parent_observation(self, observation: Any):
        """Hide only the proven candidate-owned hand from the current producer."""
        if not isinstance(observation, Mapping):
            return observation, {"changed": False, "reason": "malformed_observation"}
        resolved = self._state(observation)
        if resolved is None:
            return observation, {"changed": False, "reason": "malformed_observation"}
        state, parsed = resolved
        player, _step, _day, _farm, hands, inventories, _shed, _tiles = parsed
        if state.index is None:
            return deepcopy(observation), {"changed": False, "reason": "no_owned_hand"}
        if len(inventories) != len(hands) + 1:
            return deepcopy(observation), {"changed": False, "reason": "inventory_actor_mismatch"}

        view = deepcopy(observation)
        view_hands = view["farms"][player]["hands"]
        view_inventories = view["private"]["inventories"]
        if (
            not isinstance(view_hands, list)
            or not isinstance(view_inventories, list)
            or state.index >= len(view_hands)
            or state.index + 1 >= len(view_inventories)
        ):
            return deepcopy(observation), {"changed": False, "reason": "owned_index_unrepresentable"}
        del view_hands[state.index]
        del view_inventories[state.index + 1]
        return view, {
            "changed": True,
            "reason": "hide_owned_hand",
            "owned_index": state.index,
        }

    def _upcoming(
        self,
        observation: Mapping[str, Any],
        selected: Mapping[str, Any],
        owned_index: int,
    ) -> list[tuple[int, int, int]]:
        parsed = _own_state(observation)
        if parsed is None:
            return []
        _player, _step, _day, farm, hands, _inventories, _shed, tiles = parsed
        parent_hands = selected.get("hands")
        if not isinstance(parent_hands, list) or len(parent_hands) != len(hands) - 1:
            return []
        units = [(farm.get("farmer"), selected.get("farmer"))]
        for parent_index, command in enumerate(parent_hands):
            real_index = parent_index if parent_index < owned_index else parent_index + 1
            units.append((hands[real_index], command))
        result = []
        for pos, command in units:
            if (
                isinstance(pos, list)
                and len(pos) == 2
                and all(type(value) is int for value in pos)
                and isinstance(command, list)
                and len(command) > 1
                and command[0] == "PLANT"
                and command[1] in CROPS
            ):
                x, y = pos
                if 0 <= x < BOARD_SIZE and 0 <= y < BOARD_SIZE and tiles[y][x] is None:
                    result.append((x, y, 1))
        return result

    def _owned_command(
        self,
        observation: Mapping[str, Any],
        state: _DayState,
        selected: Mapping[str, Any],
        rest: list[Mapping[str, Any]] | None,
    ) -> list[Any]:
        parsed = _own_state(observation)
        if parsed is None or state.index is None:
            return ["PASS"]
        _player, step, day, _farm, hands, inventories, shed, tiles = parsed
        if state.command_step == step and state.command is not None:
            return deepcopy(state.command)

        pos = hands[state.index]
        if (
            not isinstance(pos, list)
            or len(pos) != 2
            or any(type(value) is not int for value in pos)
        ):
            command = ["PASS"]
        else:
            inv = inventories[state.index + 1]
            if not isinstance(inv, Mapping):
                command = ["PASS"]
            else:
                held = inv.get("FERTILIZER", 0)
                if not _plain_nonnegative_int(held):
                    held = 0
                sheds = _shed_tiles(BOARD_SIZE)
                point = (pos[0], pos[1])
                targets = _targets(tiles, day)

                if not state.picked and point in sheds:
                    # A pickup can steal stock from the parent route. Require a
                    # complete remaining-day route before reserving its future pickups.
                    if rest is None:
                        command = ["PASS"]
                    else:
                        future_reserved = _future_fertilizer_pickups(rest)
                        stock = shed.get("FERTILIZER", 0)
                        if not _plain_nonnegative_int(stock):
                            command = ["PASS"]
                        else:
                            quantity = min(state.want, max(0, stock - future_reserved))
                            state.picked = True
                            command = (
                                ["PICKUP", "FERTILIZER", quantity]
                                if quantity > 0 else ["PASS"]
                            )
                elif point in sheds:
                    command = _leave_shed(point, sheds)
                elif held <= 0:
                    command = ["PASS"]
                elif any((x, y) == point for x, y, _gain_units in targets):
                    command = ["FERTILIZE"]
                else:
                    goals = targets + [
                        row for row in self._upcoming(observation, selected, state.index)
                        if (row[0], row[1]) != point
                    ]
                    if not goals:
                        command = ["PASS"]
                    else:
                        target = min(
                            goals,
                            key=lambda row: (
                                abs(row[0] - point[0]) + abs(row[1] - point[1]),
                                -row[2],
                                row[1],
                                row[0],
                            ),
                        )
                        command = _step_toward(point, (target[0], target[1]), sheds)

        state.command_step = step
        state.command = deepcopy(command)
        return command

    def _reapply_hire(
        self,
        selected: Mapping[str, Any],
        state: _DayState,
    ):
        result = deepcopy(selected)
        market = result.get("market")
        if not isinstance(market, list):
            return _identity(selected, "malformed_market")
        if any(order and isinstance(order, list) and order[0] == "HIRE" for order in market):
            return _identity(selected, "parent_hire_collision")
        additions = [["HIRE"]]
        if state.hire_buy > 0:
            additions.append(["BUY_PRODUCT", "FERTILIZER", state.hire_buy])
        if len(market) + len(additions) > MAX_ORDERS:
            return _identity(selected, "market_capacity_changed_on_retry")
        result["market"] = deepcopy(market) + additions
        return result, {
            "changed": True,
            "reason": "reapply_hire_plan",
            "hire": True,
            "fertilizer_buy": state.hire_buy,
            "want": state.want,
        }

    def _consider_hire(
        self,
        observation: Mapping[str, Any],
        selected: Mapping[str, Any],
        state: _DayState,
        rest: list[Mapping[str, Any]],
    ):
        parsed = _own_state(observation)
        if parsed is None:
            return _identity(selected, "malformed_observation")
        _player, step, day, farm, hands, _inventories, shed, tiles = parsed

        if state.hire_step == step:
            return self._reapply_hire(selected, state)

        market = selected.get("market")
        if not isinstance(market, list):
            return _identity(selected, "malformed_market")
        if any(not isinstance(order, list) for order in market if order):
            return _identity(selected, "malformed_market")
        if len(market) > MAX_ORDERS:
            return _identity(selected, "market_queue_over_cap")
        if any(order and order[0] == "HIRE" for order in market):
            state.tried = True
            return _identity(selected, "parent_hire_present")
        if _future_hire(rest):
            state.tried = True
            return _identity(selected, "future_parent_hire")

        prices = observation.get("market")
        if not isinstance(prices, Mapping):
            return _identity(selected, "malformed_market_state")
        price_map = prices.get("prices")
        if not isinstance(price_map, Mapping):
            return _identity(selected, "malformed_market_prices")
        carrot_price = price_map.get("CARROT")
        fertilizer_price = price_map.get("FERTILIZER")
        if not _finite_number(carrot_price) or not _finite_number(fertilizer_price):
            return _identity(selected, "malformed_market_prices")
        carrot_price = float(carrot_price)
        fertilizer_price = float(fertilizer_price)
        if carrot_price < 0 or fertilizer_price < 0:
            return _identity(selected, "malformed_market_prices")

        hires_today = farm.get("hires_today")
        money = farm.get("money")
        if not _plain_nonnegative_int(hires_today) or not _finite_number(money):
            return _identity(selected, "malformed_farm_economics")
        money = float(money)

        targets = len(_targets(tiles, day)) + _future_plantings(rest)
        units = min(targets, REACH)
        cost = _fib(hires_today)
        edge = carrot_price * PRICE_KEEP - fertilizer_price
        gain = units * edge
        shed_fertilizer = shed.get("FERTILIZER", 0)
        if not _plain_nonnegative_int(shed_fertilizer):
            return _identity(selected, "malformed_fertilizer_stock")
        reserved = _future_fertilizer_pickups(rest)
        available = max(0, shed_fertilizer - reserved)
        short = max(0, units - available)

        additions = 1 + (1 if short > 0 else 0)
        profitable = (
            units > 0
            and gain - cost >= MIN_GAIN
            and gain >= GAIN_RATIO * cost
            and money >= cost + units * fertilizer_price + 100
        )
        state.tried = True
        if not profitable:
            return _identity(
                selected,
                "economic_gate",
                targets=targets,
                units=units,
                hire_cost=cost,
                expected_gain=gain,
            )
        if len(market) + additions > MAX_ORDERS:
            return _identity(selected, "market_capacity")

        result = deepcopy(selected)
        result_market = deepcopy(market)
        result_market.append(["HIRE"])
        if short > 0:
            result_market.append(["BUY_PRODUCT", "FERTILIZER", short])
        result["market"] = result_market

        state.pending = len(hands)
        state.want = units
        state.hire_step = step
        state.hire_buy = short
        return result, {
            "changed": True,
            "reason": "admit_fertilizer_hand",
            "hire": True,
            "fertilizer_buy": short,
            "want": units,
            "targets": targets,
            "hire_cost": cost,
            "expected_gain": gain,
            "parent_market_preserved_prefix": True,
        }

    def transform_selected(
        self,
        observation: Any,
        configuration: Mapping[str, Any] | None,
        selected: Any,
        *,
        future_actions: Any = None,
    ):
        """Reinsert the owned hand, or append one admitted HIRE, after selection."""
        if not isinstance(observation, Mapping) or not isinstance(selected, Mapping):
            return _identity(selected, "malformed_input")
        if _config(configuration) is None:
            return _identity(selected, "outside_standard_config")
        resolved = self._state(observation)
        if resolved is None:
            return _identity(selected, "malformed_observation")
        state, parsed = resolved
        _player, step, day, _farm, hands, _inventories, _shed, _tiles = parsed
        rest = _validated_rest_of_day(future_actions, step=step)

        farmer_action = selected.get("farmer")
        parent_hands = selected.get("hands")
        market = selected.get("market")
        if (
            not isinstance(farmer_action, list)
            or not isinstance(parent_hands, list)
            or not isinstance(market, list)
        ):
            return _identity(selected, "malformed_selected_shape")

        if state.index is not None:
            if len(parent_hands) != len(hands) - 1:
                return _identity(
                    selected,
                    "parent_hand_cardinality",
                    expected=len(hands) - 1,
                    observed=len(parent_hands),
                )
            command = self._owned_command(observation, state, selected, rest)
            result = deepcopy(selected)
            result_hands = deepcopy(parent_hands)
            result_hands.insert(state.index, deepcopy(command))
            result["hands"] = result_hands
            report = {
                "changed": True,
                "reason": "reinsert_owned_hand",
                "owned_index": state.index,
                "command": deepcopy(command),
                "parent_farmer_preserved": result["farmer"] == selected["farmer"],
                "parent_market_preserved": result["market"] == selected["market"],
                "future_route_authenticated": rest is not None,
            }
            self.diagnostics = deepcopy(report)
            return result, report

        if len(parent_hands) != len(hands):
            return _identity(
                selected,
                "parent_hand_cardinality",
                expected=len(hands),
                observed=len(parent_hands),
            )
        if (
            (state.tried and state.hire_step != step)
            or day not in DAYS
            or step % TURNS_PER_DAY < HIRE_HOUR
            or step >= EPISODE_STEPS - 3
        ):
            return _identity(selected, "hire_window_closed")
        if rest is None:
            return _identity(selected, "missing_complete_route_tail")

        result, report = self._consider_hire(observation, selected, state, rest)
        self.diagnostics = deepcopy(report)
        return result, report
