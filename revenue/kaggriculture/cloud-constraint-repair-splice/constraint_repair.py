# SPDX-License-Identifier: Apache-2.0
"""Bounded deterministic constraint-repair splice search.

The planner repairs a divergent worker continuation only when it can reach an
*exact material checkpoint*. Position equality by itself is never sufficient.
Callers own exact transition semantics and may supply a stricter checkpoint
projector; the bundled Kaggriculture projector includes positions, per-worker
inventory, shed/seeds, cash, funding, market/public/shared state, and explicit
producer-owned valued deltas.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import copy
import hashlib
import json
import time
from typing import Any, Callable, Iterable, Mapping, Sequence

Action = Any
State = Any
CandidateProvider = Callable[[State, int], Iterable[Action]]
Transition = Callable[[State, Action], State | None]
Projector = Callable[[State], Any]
Clock = Callable[[], int]


@dataclass(frozen=True)
class RepairConfig:
    max_nodes: int = 128
    max_depth: int = 8
    budget_ns: int = 10_000_000
    max_candidates: int = 32
    # Hard bound on raw candidate pulls so a duplicate-heavy or infinite
    # provider cannot stall past the wall deadline while unique collection runs.
    max_raw_pulls: int = 256

    def validate(self) -> "RepairConfig":
        if self.max_nodes < 1:
            raise ValueError("max_nodes must be positive")
        if self.max_depth < 0:
            raise ValueError("max_depth must be non-negative")
        if self.budget_ns < 0:
            raise ValueError("budget_ns must be non-negative")
        if self.max_candidates < 1:
            raise ValueError("max_candidates must be positive")
        if self.max_raw_pulls < 1:
            raise ValueError("max_raw_pulls must be positive")
        return self


@dataclass(frozen=True)
class RepairResult:
    actions: tuple[Action, ...]
    found: bool
    used_fallback: bool
    reason: str
    nodes_seen: int
    expanded: int
    pruned_illegal: int
    visited_duplicates: int
    depth: int | None
    target_checkpoint_sha256: str


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("non-finite float in checkpoint")
        return value
    if isinstance(value, Mapping):
        # Fail closed on non-string keys: str(k) collapses distinct keys
        # (e.g. 1 and "1") and permits false exact-checkpoint matches.
        encoded: list[tuple[str, Any]] = []
        for k, v in value.items():
            if not isinstance(k, str):
                raise ValueError(
                    f"non-string mapping key {k!r} (type {type(k).__name__}) "
                    "in checkpoint; exact equality requires string keys"
                )
            encoded.append((k, _jsonable(v)))
        encoded.sort(key=lambda kv: kv[0])
        return {k: v for k, v in encoded}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (set, frozenset)):
        encoded = [_jsonable(v) for v in value]
        return sorted(encoded, key=lambda v: json.dumps(v, sort_keys=True, separators=(",", ":")))
    if hasattr(value, "__dict__"):
        return _jsonable(vars(value))
    return repr(value)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def checkpoint_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _copy_mapping(value: Any) -> Any:
    return copy.deepcopy(value) if value is not None else {}


def kaggriculture_material_checkpoint(
    state: Mapping[str, Any],
    *,
    producer_values: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Conservative material checkpoint for Kaggriculture-like state.

    This intentionally includes more than geometry. Unknown caller-specific
    economic consequences should be supplied in ``producer_values``. The
    checkpoint is suitable for equality at the *same target step*; callers
    comparing across different timeline steps should provide their own projector.
    """
    farm = state.get("farm") or {}
    private = state.get("private") or {}
    positions = [copy.deepcopy(farm.get("farmer"))]
    hands = farm.get("hands") or []
    if isinstance(hands, Sequence) and not isinstance(hands, (str, bytes)):
        positions.extend(copy.deepcopy(list(hands)))
    return {
        "positions": positions,
        "worker_inventories": _copy_mapping(private.get("inventories")),
        "shed": _copy_mapping(private.get("shed")),
        "seeds": _copy_mapping(private.get("seeds")),
        "cash": copy.deepcopy(farm.get("money")),
        "funding": _copy_mapping(state.get("funding")),
        "shared": _copy_mapping(state.get("shared")),
        "public": _copy_mapping(state.get("public")),
        "market": _copy_mapping(state.get("market")),
        "producer_values": _copy_mapping(producer_values),
    }


def make_kaggriculture_projector(
    *, producer_values: Mapping[str, Any] | Callable[[State], Mapping[str, Any]] | None = None,
) -> Projector:
    def project(state: State) -> Any:
        values = producer_values(state) if callable(producer_values) else producer_values
        return kaggriculture_material_checkpoint(state, producer_values=values)
    return project


def _action_key(action: Action) -> bytes:
    return canonical_bytes(action)


def _bounded_actions(
    actions: Iterable[Action],
    cap: int,
    *,
    max_raw_pulls: int,
    expired: Callable[[], bool] | None = None,
) -> list[Action]:
    """Collect up to ``cap`` unique actions under a raw-pull and optional deadline bound.

    A provider that yields only duplicates (or blocks) cannot run past
    ``max_raw_pulls`` iterations or past ``expired()`` when supplied.
    """
    unique: dict[bytes, Action] = {}
    raw_pulls = 0
    for action in actions:
        if expired is not None and expired():
            break
        raw_pulls += 1
        if raw_pulls >= max_raw_pulls:
            break
        key = _action_key(action)
        if key not in unique:
            unique[key] = action
        if len(unique) >= cap:
            break
    return [unique[key] for key in sorted(unique)]


def find_shortest_splice(
    initial_state: State,
    target_checkpoint: Any,
    candidates: CandidateProvider,
    transition: Transition,
    *,
    projector: Projector,
    config: RepairConfig = RepairConfig(),
    deadline_ns: int | None = None,
    now_ns: Clock = time.perf_counter_ns,
    state_key: Projector | None = None,
) -> RepairResult:
    """Breadth-first shortest legal splice under strict node/time bounds.

    Search order is deterministic: breadth first, then canonical JSON action
    order. ``transition`` must return a fresh legal successor or ``None`` for an
    illegal action. Any callback error, node cap, or deadline returns no splice.
    The caller's initial state is never returned or mutated by this function.

    Candidate enumeration is deadline-aware and raw-pull bounded so a
    duplicate-heavy or infinite provider cannot stall past the wall budget.
    Blocking callbacks remain cooperative only; the contract is hard on the
    search loop and on raw pulls, not on a single non-yielding call.
    """
    config.validate()
    try:
        target_bytes = canonical_bytes(target_checkpoint)
    except Exception:
        # No trustworthy target means there is no safe repair.
        return RepairResult((), False, True, "invalid-target", 0, 0, 0, 0, None, "")
    target_sha = hashlib.sha256(target_bytes).hexdigest()

    start = now_ns()
    hard_deadline = start + config.budget_ns
    if deadline_ns is not None:
        hard_deadline = min(hard_deadline, deadline_ns)

    def expired() -> bool:
        return now_ns() >= hard_deadline

    def failure(reason: str, *, nodes_seen: int, expanded: int,
                pruned: int, duplicates: int) -> RepairResult:
        return RepairResult((), False, True, reason, nodes_seen, expanded,
                            pruned, duplicates, None, target_sha)

    if expired():
        return failure("deadline-before-search", nodes_seen=0, expanded=0,
                       pruned=0, duplicates=0)

    key_projector = state_key or (lambda s: s)
    try:
        start_state = copy.deepcopy(initial_state)
        start_projection = canonical_bytes(projector(start_state))
        if start_projection == target_bytes:
            return RepairResult((), True, False, "already-equal", 1, 0, 0, 0, 0, target_sha)
        start_key = canonical_bytes(key_projector(start_state))
    except Exception:
        return failure("projector-error", nodes_seen=0, expanded=0,
                       pruned=0, duplicates=0)

    queue = deque([(start_state, tuple())])
    seen = {start_key}
    nodes_seen = 1
    expanded = 0
    pruned = 0
    duplicates = 0

    while queue:
        if expired():
            return failure("deadline", nodes_seen=nodes_seen, expanded=expanded,
                           pruned=pruned, duplicates=duplicates)
        state, path = queue.popleft()
        if len(path) >= config.max_depth:
            continue
        try:
            offered = _bounded_actions(
                candidates(state, len(path)),
                config.max_candidates,
                max_raw_pulls=config.max_raw_pulls,
                expired=expired,
            )
        except Exception:
            return failure("candidate-error", nodes_seen=nodes_seen, expanded=expanded,
                           pruned=pruned, duplicates=duplicates)
        if expired():
            return failure("deadline", nodes_seen=nodes_seen, expanded=expanded,
                           pruned=pruned, duplicates=duplicates)
        for action in offered:
            if expired():
                return failure("deadline", nodes_seen=nodes_seen, expanded=expanded,
                               pruned=pruned, duplicates=duplicates)
            if nodes_seen >= config.max_nodes:
                return failure("node-cap", nodes_seen=nodes_seen, expanded=expanded,
                               pruned=pruned, duplicates=duplicates)
            expanded += 1
            try:
                successor = transition(copy.deepcopy(state), copy.deepcopy(action))
            except Exception:
                return failure("transition-error", nodes_seen=nodes_seen, expanded=expanded,
                               pruned=pruned, duplicates=duplicates)
            if successor is None:
                pruned += 1
                continue
            try:
                successor_projection = canonical_bytes(projector(successor))
                successor_key = canonical_bytes(key_projector(successor))
            except Exception:
                return failure("projector-error", nodes_seen=nodes_seen, expanded=expanded,
                               pruned=pruned, duplicates=duplicates)
            new_path = path + (copy.deepcopy(action),)
            nodes_seen += 1
            if successor_projection == target_bytes:
                return RepairResult(new_path, True, False, "matched", nodes_seen,
                                    expanded, pruned, duplicates, len(new_path), target_sha)
            if successor_key in seen:
                duplicates += 1
                continue
            seen.add(successor_key)
            queue.append((successor, new_path))

    return failure("no-match", nodes_seen=nodes_seen, expanded=expanded,
                   pruned=pruned, duplicates=duplicates)
