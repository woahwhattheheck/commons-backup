# SPDX-License-Identifier: Apache-2.0
"""TITAN V4: terminal animal-capital guard.

Source-bound, default-off component. It may blank only BUY_ANIMAL rows when
official callback ordering proves the purchase cannot complete the minimum
PICKUP -> PLACE route before the last executable action, and only when doing so
cannot fund a later protected market order in the same queue.

Species-product maturity is deliberately NOT an eligibility proof: the official
engine makes fertilizer available on every surviving placed animal at EOD,
independent of EGG/MILK/WOOL maturity. It never rewrites unit actions, SELL rows,
or market row indices.
"""
from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

TURNS_PER_DAY = 24
EPISODE_STEPS = 720
FINAL_PLAN_STEP = 648
LAST_ACTION_STEP = EPISODE_STEPS - 2
DEFAULT_MAX_MARKET_ORDERS = 10
STANDARD_ANIMALS = frozenset({"GOOSE", "SHEEP", "COW"})
UNIT_ACTIONS_TO_PLACE_PURCHASED_ANIMAL = 2
_MISSING = object()


def _value(obj: Any, key: str) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key)
    return getattr(obj, key, None)


def _standard_timing(configuration: Any) -> bool:
    if configuration is None:
        return False
    turns = _value(configuration, "turnsPerDay")
    steps = _value(configuration, "episodeSteps")
    return (
        type(turns) is int
        and turns == TURNS_PER_DAY
        and type(steps) is int
        and steps == EPISODE_STEPS
    )


def _max_market_orders(configuration: Any) -> int | None:
    """Return the official executable market prefix length, or fail closed.

    The official specification defaults maxMarketOrdersPerTurn to 10. For an
    explicitly supplied plain int, the interpreter executes
    market[:max(1, value)], so zero and negative ints still expose row 0.
    Missing therefore means the exact engine default; non-int values remain
    outside this component's source-safe contract and fail closed.
    """
    if isinstance(configuration, Mapping):
        value = (
            configuration["maxMarketOrdersPerTurn"]
            if "maxMarketOrdersPerTurn" in configuration
            else _MISSING
        )
    else:
        value = getattr(configuration, "maxMarketOrdersPerTurn", _MISSING)
    if value is _MISSING:
        return DEFAULT_MAX_MARKET_ORDERS
    if type(value) is not int:
        return None
    return max(1, value)


def _step(observation: Any) -> int | None:
    value = _value(observation, "step")
    return value if type(value) is int else None


def _future_unit_callbacks(step: int) -> int:
    """Number of later callbacks that can still carry a unit action.

    BUY_ANIMAL executes after this callback's unit phase, so the purchased animal
    cannot be PICKUP'd until a later callback. The official unit interpreter
    requires a PICKUP into one actor's inventory and then a separate PLACE action
    on a matching structure. Fewer than two later callbacks therefore proves the
    purchased animal cannot become a placed animal before terminal.
    """
    return max(0, LAST_ACTION_STEP - step)


def plan_terminal_animal_capital(
    action: Any,
    observation: Any,
    configuration: Any,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "eligible": False,
        "reason": "NO_OP",
        "drop_indices": [],
        "dropped_units": {},
    }
    if not isinstance(action, Mapping):
        report["reason"] = "BAD_ACTION"
        return report
    if not _standard_timing(configuration):
        report["reason"] = "NONSTANDARD_OR_MISSING_TIMING"
        return report

    max_orders = _max_market_orders(configuration)
    if max_orders is None:
        report["reason"] = "BAD_MAX_MARKET_ORDERS"
        return report

    step = _step(observation)
    if step is None or step < 0:
        report["reason"] = "BAD_STEP"
        return report
    if step < FINAL_PLAN_STEP:
        report["reason"] = "BEFORE_FINAL_PLAN"
        return report
    if step > LAST_ACTION_STEP:
        report["reason"] = "AFTER_LAST_ACTION"
        return report

    market = action.get("market")
    if not isinstance(market, list):
        report["reason"] = "BAD_MARKET_QUEUE"
        return report

    # Source-bind the same executable prefix as the official interpreter.
    # Raw suffix rows are intentionally opaque/preserved because the engine
    # silently drops them before parsing or committing any market operation.
    executable_market = market[:max_orders]
    future_callbacks = _future_unit_callbacks(step)

    parsed_ops: list[str | None] = []
    dead: dict[int, tuple[str, int, int]] = {}
    for index, row in enumerate(executable_market):
        if row == []:
            parsed_ops.append(None)
            continue
        if not isinstance(row, list) or not row or type(row[0]) is not str:
            report["reason"] = "BAD_MARKET_ROW"
            return report
        op = row[0]
        parsed_ops.append(op)
        if op != "BUY_ANIMAL":
            continue
        if len(row) != 3 or type(row[1]) is not str or type(row[2]) is not int:
            report["reason"] = "BAD_BUY_ANIMAL_ROW"
            return report
        animal, quantity = row[1], row[2]
        if quantity <= 0:
            report["reason"] = "BAD_BUY_ANIMAL_ROW"
            return report
        if animal not in STANDARD_ANIMALS:
            continue

        # Historical H5's "first species yield is after terminal" theorem was
        # false because every placed animal can create fertilizer at EOD before
        # its EGG/MILK/WOOL maturity. Suppress only when callback count itself
        # proves the purchased unit cannot even complete PICKUP -> PLACE.
        if future_callbacks < UNIT_ACTIONS_TO_PLACE_PURCHASED_ANIMAL:
            dead[index] = (animal, quantity, future_callbacks)

    if not dead:
        report["reason"] = "NO_PROVABLY_DEAD_ANIMAL_CAPITAL"
        return report

    # Blank only a dead executable suffix. Saving cash before any later
    # executable non-SELL/non-placeholder row could make that later order newly
    # executable. Raw rows at index >= max_orders never enter this calculation.
    last_protected = -1
    for index, op in enumerate(parsed_ops):
        if op is None or op == "SELL" or index in dead:
            continue
        last_protected = index

    drop = [index for index in sorted(dead) if index > last_protected]
    if not drop:
        report["reason"] = "DOWNSTREAM_AFFORDABILITY_AMBIGUITY"
        return report

    units: dict[str, int] = {}
    witnesses: list[dict[str, int | str]] = []
    for index in drop:
        animal, quantity, remaining_callbacks = dead[index]
        units[animal] = units.get(animal, 0) + quantity
        witnesses.append(
            {
                "index": index,
                "animal": animal,
                "quantity": quantity,
                "future_unit_callbacks": remaining_callbacks,
                "required_unit_actions_to_place": UNIT_ACTIONS_TO_PLACE_PURCHASED_ANIMAL,
            }
        )
    report.update(
        eligible=True,
        reason="DROP_PROVABLY_DEAD_ANIMAL_CAPITAL_SUFFIX",
        proof="INSUFFICIENT_FUTURE_UNIT_CALLBACKS_TO_PLACE",
        step=step,
        max_market_orders=max_orders,
        drop_indices=drop,
        dropped_units=units,
        protected_prefix_through=last_protected,
        witnesses=witnesses,
    )
    return report


def apply_terminal_animal_capital(
    action: Any,
    observation: Any,
    configuration: Any,
    *,
    enabled: bool = False,
) -> Any:
    """Apply the guard. Every OFF/nonmatch path preserves object identity."""
    if enabled is not True:
        return action
    plan = plan_terminal_animal_capital(action, observation, configuration)
    if plan.get("eligible") is not True:
        return action

    out = copy.deepcopy(action)
    market = out.get("market")
    original = action.get("market")
    if not isinstance(market, list) or not isinstance(original, list) or len(market) != len(original):
        return action
    for index in plan["drop_indices"]:
        market[index] = []
    return out
