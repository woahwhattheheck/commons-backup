# SPDX-License-Identifier: Apache-2.0
"""Bounded joint actor assignment witness for TITAN spatial-tempo routes.

This module does not own a second scheduler.  It certifies one pairwise swap of
complete pickup->service->delivery bundles while preserving the inherited event
steps and exact continuation state.  The returned plan owns both actor streams
atomically; callers must never commit only one side.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional, Sequence

MOVES = {"NORTH": (0, -1), "SOUTH": (0, 1), "EAST": (1, 0), "WEST": (-1, 0)}
SERVICE = {
    "WATER",
    "CARE",
    "FEED",
    "HARVEST",
    "COLLECT_FERTILIZER",
    "FERTILIZE",
    "PLACE",
}
EVENTS = SERVICE | {"PICKUP", "DROP"}
CHECKPOINTS = (226, 360, 433)


class JointAssignmentError(ValueError):
    """Raised for malformed inputs rather than guessing route semantics."""


@dataclass(frozen=True)
class BundleEvent:
    offset: int
    step: int
    tile: tuple[int, int]
    action: tuple

    def as_dict(self) -> dict:
        return {
            "offset": self.offset,
            "step": self.step,
            "tile": list(self.tile),
            "action": list(self.action),
        }


@dataclass(frozen=True)
class Bundle:
    worker: int
    start: tuple[int, int]
    end: tuple[int, int]
    events: tuple[BundleEvent, ...]
    original: tuple[tuple, ...]
    travel: int


@dataclass(frozen=True)
class JointSwapPlan:
    owner_key: str
    workers: tuple[int, int]
    step: int
    end_step: int
    original_travel: int
    replacement_travel: int
    replacement: tuple[tuple[tuple, ...], tuple[tuple, ...]]
    inherited_from: tuple[int, int]
    collision_trace: tuple[dict, ...]

    @property
    def travel_saved(self) -> int:
        return self.original_travel - self.replacement_travel

    def patches(self) -> tuple[dict, ...]:
        """Return both worker actions together for every step; never one-sided."""
        a, b = self.workers
        rows = []
        for offset in range(self.end_step - self.step + 1):
            rows.append(
                {
                    "step": self.step + offset,
                    "owner": self.owner_key,
                    "units": {
                        str(a): list(self.replacement[0][offset]),
                        str(b): list(self.replacement[1][offset]),
                    },
                }
            )
        return tuple(rows)

    def as_dict(self) -> dict:
        return {
            "owner_key": self.owner_key,
            "workers": list(self.workers),
            "step": self.step,
            "end_step": self.end_step,
            "inherited_from": list(self.inherited_from),
            "original_travel": self.original_travel,
            "replacement_travel": self.replacement_travel,
            "travel_saved": self.travel_saved,
            "collision_trace": [dict(item) for item in self.collision_trace],
        }


@dataclass(frozen=True)
class JointSwapResult:
    changed: bool
    reason: str
    plan: Optional[JointSwapPlan] = None

    def as_dict(self) -> dict:
        return {
            "changed": self.changed,
            "reason": self.reason,
            "plan": None if self.plan is None else self.plan.as_dict(),
        }


def _unit(row: Mapping, worker: int) -> list:
    if not isinstance(row, Mapping):
        raise JointAssignmentError("route row must be a mapping")
    if worker == 0:
        action = row.get("farmer", ["PASS"])
    else:
        hands = row.get("hands", [])
        if not isinstance(hands, Sequence):
            raise JointAssignmentError("hands must be a sequence")
        action = hands[worker - 1] if worker <= len(hands) else ["PASS"]
    if not isinstance(action, list) or not action:
        return ["PASS"]
    return list(action)


def _row(route: Sequence | Mapping, step: int) -> Mapping:
    try:
        row = route[step]
    except (IndexError, KeyError, TypeError):
        raise JointAssignmentError(f"missing route row at step {step}") from None
    if not isinstance(row, Mapping):
        raise JointAssignmentError(f"route row {step} must be a mapping")
    return row


def _move(pos: tuple[int, int], action: Sequence, board: int) -> tuple[int, int]:
    op = action[0] if action else "PASS"
    delta = MOVES.get(op)
    if delta is None:
        return pos
    nxt = (pos[0] + delta[0], pos[1] + delta[1])
    return nxt if 0 <= nxt[0] < board and 0 <= nxt[1] < board else pos


def _path(a: tuple[int, int], b: tuple[int, int]) -> list[tuple]:
    out: list[tuple] = []
    if b[0] > a[0]:
        out.extend([("EAST",)] * (b[0] - a[0]))
    elif b[0] < a[0]:
        out.extend([("WEST",)] * (a[0] - b[0]))
    if b[1] > a[1]:
        out.extend([("SOUTH",)] * (b[1] - a[1]))
    elif b[1] < a[1]:
        out.extend([("NORTH",)] * (a[1] - b[1]))
    return out


def _position(mechanics: Any, farm: Mapping, worker: int, board: int) -> tuple[int, int]:
    pos = mechanics._farmer_position(farm, worker)
    if (
        not isinstance(pos, Sequence)
        or isinstance(pos, (str, bytes))
        or len(pos) != 2
        or type(pos[0]) is not int
        or type(pos[1]) is not int
    ):
        raise JointAssignmentError(f"worker {worker} has no exact integer position")
    point = (pos[0], pos[1])
    if not (0 <= point[0] < board and 0 <= point[1] < board):
        raise JointAssignmentError(f"worker {worker} position is out of bounds")
    return point


def _pickup_request(action: Sequence) -> Optional[int]:
    if len(action) not in (2, 3):
        return None
    item = action[1]
    if not isinstance(item, str) or not item:
        return None
    requested = action[2] if len(action) == 3 else 1
    if type(requested) is not int or requested <= 0:
        return None
    return requested


def _public_observation_binding(obs: Mapping, start_step: int, turns_per_day: int) -> int:
    """Bind a certificate to the exact public seat/clock when those fields exist."""
    player = obs.get("player")
    farms = obs.get("farms")
    if type(player) is not int:
        raise JointAssignmentError("observation player must be a plain integer")
    if (
        not isinstance(farms, Sequence)
        or isinstance(farms, (str, bytes))
        or not 0 <= player < len(farms)
    ):
        raise JointAssignmentError("observation player is out of range")

    expected = {
        "step": start_step,
        "day": start_step // turns_per_day,
        "hour": start_step % turns_per_day,
    }
    for name, wanted in expected.items():
        if name not in obs:
            continue
        value = obs[name]
        if type(value) is not int:
            raise JointAssignmentError(f"observation {name} must be a plain integer")
        if value != wanted:
            raise JointAssignmentError(f"observation {name} does not match start_step")
    return player


def _positive_plain_int(value: Any, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise JointAssignmentError(f"{name} must be a plain positive integer")
    return value


def _normalize_checkpoints(checkpoints: Iterable[int]) -> frozenset[int]:
    """Materialize a checkpoint iterable exactly once and reject lossy aliases."""
    try:
        iterator = iter(checkpoints)
    except TypeError:
        raise JointAssignmentError("checkpoints must be iterable") from None
    normalized = set()
    for step in iterator:
        if type(step) is not int or step < 0:
            raise JointAssignmentError("checkpoints must contain plain nonnegative integers")
        normalized.add(step)
    return frozenset(normalized)


def _extract_bundle(
    mechanics: Any,
    farm: Mapping,
    route: Sequence | Mapping,
    worker: int,
    start_step: int,
    end_step: int,
    board: int,
) -> tuple[Optional[Bundle], str]:
    pos = _position(mechanics, farm, worker, board)
    start = pos
    actions: list[tuple] = []
    events: list[BundleEvent] = []
    travel = 0
    for offset, step in enumerate(range(start_step, end_step + 1)):
        action = tuple(_unit(_row(route, step), worker))
        op = action[0] if action else "PASS"
        actions.append(action)
        if op in MOVES:
            new_pos = _move(pos, action, board)
            if new_pos == pos:
                return None, "original_invalid_move"
            pos = new_pos
            travel += 1
        elif op == "PASS":
            continue
        elif op in EVENTS:
            if op == "PICKUP" and _pickup_request(action) is None:
                return None, "malformed_pickup"
            events.append(BundleEvent(offset, step, pos, action))
        else:
            return None, "unsupported_bundle_action"

    if len(events) < 3:
        return None, "incomplete_bundle"
    if events[0].action[0] != "PICKUP" or events[-1].action[0] != "DROP":
        return None, "bundle_must_start_pickup_end_drop"
    if any(e.action[0] in {"PICKUP", "DROP"} for e in events[1:-1]):
        return None, "multiple_pickup_or_drop"
    if not any(e.action[0] in SERVICE for e in events[1:-1]):
        return None, "bundle_has_no_service"
    return Bundle(worker, start, pos, tuple(events), tuple(actions), travel), "ok"


def _build_inherited_stream(
    start: tuple[int, int],
    own_end: tuple[int, int],
    inherited: Bundle,
    horizon: int,
) -> tuple[Optional[tuple[tuple, ...]], str]:
    stream: list[tuple] = [("PASS",)] * horizon
    pos = start
    cursor = 0
    for event in inherited.events:
        gap = event.offset - cursor
        travel = _path(pos, event.tile)
        if len(travel) > gap:
            return None, "event_deadline_unreachable"
        first_move = event.offset - len(travel)
        for i, action in enumerate(travel):
            stream[first_move + i] = action
        if stream[event.offset] != ("PASS",):
            return None, "event_slot_collision"
        stream[event.offset] = event.action
        pos = event.tile
        cursor = event.offset + 1

    remaining = horizon - cursor
    tail = _path(pos, own_end)
    if len(tail) > remaining:
        return None, "rejoin_deadline_unreachable"
    first_move = horizon - len(tail)
    for i, action in enumerate(tail):
        if stream[first_move + i] != ("PASS",):
            return None, "rejoin_slot_collision"
        stream[first_move + i] = action
    return tuple(stream), "ok"


def _state_equal(a_farm: Mapping, a_private: Mapping, b_farm: Mapping, b_private: Mapping) -> bool:
    return a_farm == b_farm and a_private == b_private


def _event_effect(
    before_farm: Mapping,
    before_private: Mapping,
    after_farm: Mapping,
    after_private: Mapping,
) -> bool:
    return not _state_equal(before_farm, before_private, after_farm, after_private)


def _pickup_full(before_private: Mapping, after_private: Mapping, worker: int, action: Sequence) -> bool:
    requested = _pickup_request(action)
    if requested is None:
        return False
    item = action[1]
    before = before_private["inventories"][worker].get(item, 0)
    after = after_private["inventories"][worker].get(item, 0)
    return after - before == requested


def _simulate(
    mechanics: Any,
    obs: Mapping,
    route: Sequence | Mapping,
    start_step: int,
    end_step: int,
    replacements: Optional[Mapping[int, Sequence[Sequence]]],
    event_workers: set[int],
    board: int,
    turns_per_day: int,
    shed_capacity: int,
) -> tuple[Mapping, Mapping, tuple[dict, ...], Optional[str]]:
    player = obs["player"]
    farm = deepcopy(obs["farms"][player])
    private = deepcopy(obs["private"])
    count = 1 + len(farm.get("hands", []))
    trace: list[dict] = []

    for offset, step in enumerate(range(start_step, end_step + 1)):
        row = _row(route, step)
        for worker in range(count):
            action = (
                list(replacements[worker][offset])
                if replacements is not None and worker in replacements
                else _unit(row, worker)
            )
            op = action[0] if action else "PASS"
            before_farm = deepcopy(farm) if worker in event_workers and op in EVENTS else None
            before_private = deepcopy(private) if worker in event_workers and op in EVENTS else None
            mechanics._apply_unit_action(
                farm,
                private,
                worker,
                action,
                board,
                step // turns_per_day,
                turns_per_day,
                shed_capacity,
            )
            if before_farm is not None:
                if not _event_effect(before_farm, before_private, farm, private):
                    return farm, private, tuple(trace), f"worker_{worker}_{op.lower()}_noop"
                if op == "PICKUP" and not _pickup_full(before_private, private, worker, action):
                    return farm, private, tuple(trace), f"worker_{worker}_partial_pickup"
                trace.append(
                    {
                        "step": step,
                        "worker": worker,
                        "action": list(action),
                        "shed_before": dict(before_private.get("shed", {})),
                        "shed_after": dict(private.get("shed", {})),
                    }
                )
        mechanics._decay_plants(farm, step)
    return farm, private, tuple(trace), None


def propose_pair_swap(
    mechanics: Any,
    obs: Mapping,
    route: Sequence | Mapping,
    worker_a: int,
    worker_b: int,
    *,
    start_step: int,
    end_step: int,
    configuration: Optional[Mapping] = None,
    checkpoints: Iterable[int] = CHECKPOINTS,
) -> JointSwapResult:
    """Certify one travel-reducing atomic pairwise bundle swap.

    The helper intentionally rejects market-bearing rows and end-of-day spans;
    those require the parent controller's market/reset reconciliation.  It also
    requires both workers to start empty because this bounded form begins with an
    owned PICKUP and must not silently transport pre-existing cargo to a new job.
    """
    if type(worker_a) is not int or type(worker_b) is not int or worker_a == worker_b:
        raise JointAssignmentError("workers must be distinct integer indices")
    if type(start_step) is not int or type(end_step) is not int or end_step < start_step:
        raise JointAssignmentError("invalid step bounds")
    if not isinstance(obs, Mapping) or "farms" not in obs or "private" not in obs:
        raise JointAssignmentError("observation must contain farms/private")

    cfg = dict(configuration or {})
    turns_per_day = _positive_plain_int(cfg.get("turnsPerDay", 24), "turnsPerDay")
    shed_capacity = _positive_plain_int(cfg.get("shedCapacity", 100), "shedCapacity")
    checkpoint_set = _normalize_checkpoints(checkpoints)
    player = _public_observation_binding(obs, start_step, turns_per_day)
    if start_step // turns_per_day != end_step // turns_per_day:
        return JointSwapResult(False, "day_boundary")
    if any(step % turns_per_day == turns_per_day - 1 for step in range(start_step, end_step + 1)):
        return JointSwapResult(False, "end_of_day_boundary")
    if any(step in checkpoint_set for step in range(start_step, end_step + 1)):
        return JointSwapResult(False, "checkpoint_boundary")

    for step in range(start_step, end_step + 1):
        market = _row(route, step).get("market", [])
        if market:
            return JointSwapResult(False, "market_boundary")

    farm = obs["farms"][player]
    private = obs["private"]
    count = 1 + len(farm.get("hands", []))
    if not (0 <= worker_a < count and 0 <= worker_b < count):
        raise JointAssignmentError("worker index out of range")
    inventories = private.get("inventories", [])
    if len(inventories) < count:
        raise JointAssignmentError("inventories do not cover all workers")
    if inventories[worker_a] or inventories[worker_b]:
        return JointSwapResult(False, "starting_cargo_not_empty")

    board = len(farm.get("tiles", []))
    if board <= 0:
        raise JointAssignmentError("farm tiles must be non-empty")
    horizon = end_step - start_step + 1

    bundle_a, reason = _extract_bundle(mechanics, farm, route, worker_a, start_step, end_step, board)
    if bundle_a is None:
        return JointSwapResult(False, f"worker_{worker_a}_{reason}")
    bundle_b, reason = _extract_bundle(mechanics, farm, route, worker_b, start_step, end_step, board)
    if bundle_b is None:
        return JointSwapResult(False, f"worker_{worker_b}_{reason}")

    stream_a, reason = _build_inherited_stream(bundle_a.start, bundle_a.end, bundle_b, horizon)
    if stream_a is None:
        return JointSwapResult(False, f"worker_{worker_a}_{reason}")
    stream_b, reason = _build_inherited_stream(bundle_b.start, bundle_b.end, bundle_a, horizon)
    if stream_b is None:
        return JointSwapResult(False, f"worker_{worker_b}_{reason}")

    replacement_travel = sum(a[0] in MOVES for a in stream_a) + sum(a[0] in MOVES for a in stream_b)
    original_travel = bundle_a.travel + bundle_b.travel
    if replacement_travel >= original_travel:
        return JointSwapResult(False, "no_travel_gain")

    original_farm, original_private, original_trace, failure = _simulate(
        mechanics,
        obs,
        route,
        start_step,
        end_step,
        None,
        {worker_a, worker_b},
        board,
        turns_per_day,
        shed_capacity,
    )
    if failure is not None:
        return JointSwapResult(False, f"original_{failure}")

    candidate_farm, candidate_private, candidate_trace, failure = _simulate(
        mechanics,
        obs,
        route,
        start_step,
        end_step,
        {worker_a: stream_a, worker_b: stream_b},
        {worker_a, worker_b},
        board,
        turns_per_day,
        shed_capacity,
    )
    if failure is not None:
        return JointSwapResult(False, f"candidate_{failure}")
    if not _state_equal(original_farm, original_private, candidate_farm, candidate_private):
        return JointSwapResult(False, "final_state_mismatch")

    # Task events remain at their inherited global steps.  Summarize only event
    # order/stock rows so a parent writer can inspect same-step contention.
    trace = tuple(
        {
            "step": item["step"],
            "worker": item["worker"],
            "action": item["action"],
            "shed_before": item["shed_before"],
            "shed_after": item["shed_after"],
        }
        for item in candidate_trace
    )
    owner = f"joint:{min(worker_a, worker_b)}-{max(worker_a, worker_b)}:{start_step}-{end_step}"
    plan = JointSwapPlan(
        owner_key=owner,
        workers=(worker_a, worker_b),
        step=start_step,
        end_step=end_step,
        original_travel=original_travel,
        replacement_travel=replacement_travel,
        replacement=(stream_a, stream_b),
        inherited_from=(worker_b, worker_a),
        collision_trace=trace,
    )
    return JointSwapResult(True, "accepted_exact_joint_swap", plan)
