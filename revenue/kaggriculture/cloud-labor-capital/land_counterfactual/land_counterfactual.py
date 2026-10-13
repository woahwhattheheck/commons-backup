# SPDX-License-Identifier: Apache-2.0
"""T10 consumer for one explicit BUY_LAND counterfactual.

The current producer has already selected one action. This module compares that
incumbent action with a caller-supplied action that differs only by one added
BUY_LAND slot. Each branch receives an independent continuation fork through
T10 ``project_shift``. The result is an input to an economic policy, not a
selector: it reports conditional current-shift cash and requested worker-turn
use without assigning value to unknown future shops, weeds, rivals, or crops.

``suppress_next_land=True`` distinguishes moving an incumbent purchase earlier
from buying an additional quadrant. The candidate continuation then replaces
only the first later BUY_LAND with a slot-preserving zero-quantity SELL. No
other future action is changed by this module.
"""
from __future__ import annotations

import copy
from dataclasses import asdict, dataclass
from typing import Any, Callable, Mapping, Sequence

NO_ORDER = ["SELL", "WHEAT", 0]
MOVES = {"NORTH": (0, -1), "SOUTH": (0, 1), "WEST": (-1, 0), "EAST": (1, 0)}
# Requested unit work. A request can still fail under official mechanics; the
# report deliberately calls these requested worker turns rather than receipts.
PRODUCTIVE = {
    "PICKUP", "PLANT", "WATER", "HARVEST", "FERTILIZE", "BUILD_COOP",
    "BUILD_PASTURE", "DIG", "PLACE", "FEED", "COLLECT_FERTILIZER", "CARE",
    "DROP",
}


@dataclass(frozen=True)
class WorkerTurns:
    available: int = 0
    requested: int = 0
    pass_or_missing: int = 0
    movement: int = 0
    productive_requested: int = 0
    positioned_on_new_land: int = 0
    entry_moves_to_new_land: int = 0
    productive_requested_on_new_land: int = 0
    first_new_land_entry_step: int | None = None
    first_new_land_productive_step: int | None = None


class _Recorder:
    def __init__(self, factory: Callable[[], Callable[[Mapping[str, Any]], Mapping[str, Any]]],
                 transform: Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]] | None = None):
        if not callable(factory):
            raise TypeError("fork_parent must be callable")
        self.factory = factory
        self.transform = transform
        self.rows: list[dict[str, Any]] = []

    def wrapped_factory(self):
        continuation = self.factory()
        if not callable(continuation):
            raise TypeError("fork_parent must return an observation callable")

        def call(observation):
            raw = continuation(copy.deepcopy(observation))
            if not isinstance(raw, Mapping):
                raise TypeError("continuation action must be a mapping")
            action = (self.transform(observation, raw) if self.transform else raw)
            if not isinstance(action, Mapping):
                raise TypeError("transformed continuation action must be a mapping")
            self.rows.append({
                "step": _step(observation),
                "observation": copy.deepcopy(dict(observation)),
                "raw_action": copy.deepcopy(dict(raw)),
                "action": copy.deepcopy(dict(action)),
            })
            return action

        return call


class _SuppressNextLand:
    def __init__(self):
        self.step: int | None = None
        self.slot: int | None = None

    def __call__(self, observation, action):
        out = copy.deepcopy(dict(action))
        if self.step is not None:
            return out
        queue = out.get("market", [])
        if not isinstance(queue, list):
            return out
        for slot, order in enumerate(queue):
            if isinstance(order, list) and order and order[0] == "BUY_LAND":
                queue[slot] = list(NO_ORDER)
                self.step, self.slot = _step(observation), slot
                break
        return out


def _step(observation: Mapping[str, Any]) -> int:
    if "step" in observation:
        value = observation["step"]
    else:
        value = int(observation.get("day", 0)) * 24 + int(observation.get("hour", 0))
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("observation step must be a nonnegative integer")
    return value


def _inert(order: Any) -> bool:
    if order in (None, []):
        return True
    return (isinstance(order, list) and len(order) == 3
            and order[0] == "SELL" and order[2] == 0)


def _validate_land_delta(incumbent: Mapping[str, Any], candidate: Mapping[str, Any],
                         max_orders: int) -> int:
    if incumbent.get("farmer", ["PASS"]) != candidate.get("farmer", ["PASS"]):
        raise ValueError("land counterfactual cannot change the farmer action")
    if incumbent.get("hands", []) != candidate.get("hands", []):
        raise ValueError("land counterfactual cannot change hand actions")
    old = incumbent.get("market", [])
    new = candidate.get("market", [])
    if not isinstance(old, list) or not isinstance(new, list):
        raise ValueError("market queues must be lists")
    if len(new) > max_orders:
        raise ValueError("candidate exceeds the market slot limit")
    changes = []
    for slot in range(max(len(old), len(new))):
        before = old[slot] if slot < len(old) else None
        after = new[slot] if slot < len(new) else None
        if before == after:
            continue
        if after == ["BUY_LAND"] and _inert(before):
            changes.append(slot)
            continue
        raise ValueError("candidate must differ by exactly one BUY_LAND replacing an inert slot")
    if len(changes) != 1:
        raise ValueError("candidate must add exactly one BUY_LAND")
    return changes[0]


def make_land_candidate(selected_action: Mapping[str, Any], *, slot: int,
                        max_orders: int = 10) -> dict[str, Any]:
    """Place BUY_LAND in one inert slot without shifting any other market order."""
    if isinstance(slot, bool) or not isinstance(slot, int) or not 0 <= slot < max_orders:
        raise ValueError("slot must be inside the market limit")
    out = copy.deepcopy(dict(selected_action))
    queue = out.setdefault("market", [])
    if not isinstance(queue, list):
        raise ValueError("selected market queue must be a list")
    while len(queue) <= slot:
        queue.append(list(NO_ORDER))
    if not _inert(queue[slot]):
        raise ValueError("land slot must be empty or a zero-quantity SELL")
    queue[slot] = ["BUY_LAND"]
    return out


def _quadrant(engine: Any, x: int, y: int, board_size: int) -> str | None:
    fn = getattr(engine, "_quadrant_of", None)
    if callable(fn):
        return fn(x, y, board_size)
    half = board_size // 2
    return ("NW" if y < half and x < half else
            "NE" if y < half else
            "SW" if x < half else "SE")


def _worker_turns(engine: Any, rows: Sequence[Mapping[str, Any]],
                  new_quadrants: Sequence[str], *, start_step: int | None = None,
                  end_step: int | None = None) -> WorkerTurns:
    new = set(new_quadrants)
    values = dict(asdict(WorkerTurns()))
    first_entry = first_productive = None
    for row in rows:
        obs, action, step = row["observation"], row["action"], int(row["step"])
        if start_step is not None and step < start_step:
            continue
        if end_step is not None and step > end_step:
            continue
        me = int(obs.get("player", 0))
        farm = obs["farms"][me]
        positions = [farm["farmer"], *farm.get("hands", [])]
        supplied = [action.get("farmer", ["PASS"]), *action.get("hands", [])]
        values["available"] += len(positions)
        values["requested"] += min(len(supplied), len(positions))
        board = len(farm["tiles"])
        for index, position in enumerate(positions):
            request = supplied[index] if index < len(supplied) else ["PASS"]
            op = request[0] if isinstance(request, list) and request else "PASS"
            x, y = int(position[0]), int(position[1])
            here_new = _quadrant(engine, x, y, board) in new
            if here_new:
                values["positioned_on_new_land"] += 1
                if first_entry is None:
                    first_entry = step
            if op in MOVES:
                values["movement"] += 1
                dx, dy = MOVES[op]
                nx, ny = x + dx, y + dy
                if 0 <= nx < board and 0 <= ny < board and _quadrant(engine, nx, ny, board) in new:
                    values["entry_moves_to_new_land"] += 1
                    if first_entry is None:
                        first_entry = step
            elif op in PRODUCTIVE:
                values["productive_requested"] += 1
                if here_new:
                    values["productive_requested_on_new_land"] += 1
                    if first_productive is None:
                        first_productive = step
            else:
                values["pass_or_missing"] += 1
    values["first_new_land_entry_step"] = first_entry
    values["first_new_land_productive_step"] = first_productive
    return WorkerTurns(**values)


def _unlock_step(rows: Sequence[Mapping[str, Any]], initial: Sequence[str],
                 quadrant: str, final_projection: Any) -> int | None:
    prior = set(initial)
    for row in rows:
        obs = row["observation"]
        me = int(obs.get("player", 0))
        current = set(obs["farms"][me].get("unlocked_quadrants", []))
        if quadrant in current and quadrant not in prior:
            return int(row["step"]) - 1
        prior = current
    final = set(final_projection.productive_state["farm"].get("unlocked_quadrants", []))
    if quadrant in final and quadrant not in prior:
        return int(final_projection.horizon_step)
    return None


def compare_land_shift(
    labor_module: Any,
    engine: Any,
    observation: Mapping[str, Any],
    parent_after_call: Any,
    incumbent_action: Mapping[str, Any],
    candidate_action: Mapping[str, Any],
    configuration: Mapping[str, Any] | None,
    *,
    fork_parent: Callable[[], Callable[[Mapping[str, Any]], Mapping[str, Any]]],
    suppress_next_land: bool = False,
) -> dict[str, Any]:
    """Return a conditional cash/worker-turn record; never choose an action.

    ``fork_parent`` must snapshot the already-advanced current owner. Separate
    snapshots are requested for incumbent and candidate. T10's original horizon
    and current-visible-shop/zero-rival assumptions remain authoritative.
    """
    if not hasattr(labor_module, "project_shift"):
        raise TypeError("labor_module must expose project_shift")
    cfg = labor_module._configuration(configuration)
    land_slot = _validate_land_delta(incumbent_action, candidate_action,
                                     int(cfg.maxMarketOrdersPerTurn))
    me = int(observation.get("player", 0))
    initial_unlocked = list(observation["farms"][me].get("unlocked_quadrants", []))
    if not initial_unlocked:
        raise ValueError("starting quadrant is missing")

    baseline_recorder = _Recorder(fork_parent)
    suppressor = _SuppressNextLand() if suppress_next_land else None
    candidate_recorder = _Recorder(fork_parent, suppressor)
    first_step = _step(observation)
    baseline_recorder.rows.append({"step": first_step,
                                   "observation": copy.deepcopy(dict(observation)),
                                   "raw_action": copy.deepcopy(dict(incumbent_action)),
                                   "action": copy.deepcopy(dict(incumbent_action))})
    candidate_recorder.rows.append({"step": first_step,
                                    "observation": copy.deepcopy(dict(observation)),
                                    "raw_action": copy.deepcopy(dict(candidate_action)),
                                    "action": copy.deepcopy(dict(candidate_action))})

    baseline = labor_module.project_shift(
        engine, observation, parent_after_call, incumbent_action, cfg,
        fork_parent=baseline_recorder.wrapped_factory,
    )
    candidate = labor_module.project_shift(
        engine, observation, parent_after_call, candidate_action, cfg,
        fork_parent=candidate_recorder.wrapped_factory,
    )

    baseline_land = list(baseline.productive_state["farm"].get("unlocked_quadrants", []))
    candidate_land = list(candidate.productive_state["farm"].get("unlocked_quadrants", []))
    additions = [q for q in candidate_land if q not in initial_unlocked]
    land_success = bool(additions)
    focus = additions[0] if additions else None
    baseline_unlock = (_unlock_step(baseline_recorder.rows, initial_unlocked, focus, baseline)
                       if focus else None)
    candidate_unlock = (_unlock_step(candidate_recorder.rows, initial_unlocked, focus, candidate)
                        if focus else None)
    base_turns = _worker_turns(engine, baseline_recorder.rows, [focus] if focus else [])
    candidate_turns = _worker_turns(engine, candidate_recorder.rows, [focus] if focus else [])
    window_start = candidate_unlock + 1 if candidate_unlock is not None else None
    window_end = (baseline_unlock if baseline_unlock is not None else baseline.horizon_step)
    early_window_turns = (_worker_turns(engine, candidate_recorder.rows, [focus],
                                        start_step=window_start, end_step=window_end)
                          if focus and window_start is not None and window_start <= window_end
                          else WorkerTurns())
    baseline_actions = {int(r["step"]): r["action"] for r in baseline_recorder.rows}
    candidate_actions = {int(r["step"]): r["action"] for r in candidate_recorder.rows}
    divergence = [s for s in sorted(set(baseline_actions) | set(candidate_actions))
                  if baseline_actions.get(s) != candidate_actions.get(s)]

    return {
        "complete": True,
        "kind": "conditional_current_shift_land_counterfactual",
        "scope": "T10 current visible shops, zero rival orders, stop before unknown next-day draws",
        "land_slot": land_slot,
        "attempted_land_cost": (getattr(engine, "LAND_PRICES", [None])[len(initial_unlocked)-1]
                                if len(getattr(engine, "LAND_PRICES", [])) >= len(initial_unlocked)
                                else None),
        "land_purchase_successful": land_success,
        "new_quadrants": additions,
        "candidate_unlock_step": candidate_unlock,
        "baseline_unlock_step": baseline_unlock,
        "suppressed_next_land": ({"step": suppressor.step, "slot": suppressor.slot}
                                 if suppressor and suppressor.step is not None else None),
        "horizon_step": baseline.horizon_step,
        "cash": {
            "incumbent": baseline.estimated_cash,
            "candidate": candidate.estimated_cash,
            "delta": candidate.estimated_cash - baseline.estimated_cash,
            "incumbent_minimum": baseline.minimum_cash,
            "candidate_minimum": candidate.minimum_cash,
            "minimum_delta": candidate.minimum_cash - baseline.minimum_cash,
            "incumbent_hiring_outflow": baseline.hiring_outflow,
            "candidate_hiring_outflow": candidate.hiring_outflow,
            "incumbent_nonhire_outflow": baseline.net_nonhire_outflow,
            "candidate_nonhire_outflow": candidate.net_nonhire_outflow,
            "incumbent_nonhire_inflow": baseline.net_nonhire_inflow,
            "candidate_nonhire_inflow": candidate.net_nonhire_inflow,
        },
        "worker_turns": {
            "incumbent": asdict(base_turns),
            "candidate": asdict(candidate_turns),
            "available_delta": candidate_turns.available - base_turns.available,
            "productive_requested_delta": (candidate_turns.productive_requested
                                           - base_turns.productive_requested),
            "new_land_productive_requested": candidate_turns.productive_requested_on_new_land,
            "early_access_window": {
                "start_step": window_start,
                "end_step": window_end,
                **asdict(early_window_turns),
            },
        },
        "state": {
            "initial_unlocked": initial_unlocked,
            "incumbent_final_unlocked": baseline_land,
            "candidate_final_unlocked": candidate_land,
            "same_productive_state": candidate.productive_state == baseline.productive_state,
            "same_market_inventory": candidate.market_inventory == baseline.market_inventory,
            "future_action_divergence_steps": divergence,
        },
        "limits": {
            "requested_worker_turns_are_not_successful-action_receipts": True,
            "future_cash_or_win_value_not_established": True,
            "candidate_selection_not_performed": True,
        },
    }
