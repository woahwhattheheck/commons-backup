# SPDX-License-Identifier: Apache-2.0
"""Deterministic, deadline-safe beam selection for one joint worker action.

The search is deliberately a proposer/scorer, not a controller. Callers own the
canonical action, legal transition function, market actions, and release state.
The canonical joint worker action is retained at every depth and is returned
unchanged on a deadline, exception, or incomplete search.
"""
from __future__ import annotations

from dataclasses import dataclass
import copy
import json
import time
from typing import Any, Callable, Iterable, Iterator, Sequence

DEFAULT_WIDTH = 24
DEFAULT_DEPTH = 4
DEFAULT_BUDGET_NS = 35_000_000
DEFAULT_MAX_CANDIDATES = 32

Action = Any
State = Any
CandidateProvider = Callable[[State, int, Action], Iterable[Action]]
Transition = Callable[[State, int, Action], State | None]
Scorer = Callable[[State, tuple[Action, ...]], int]
Clock = Callable[[], int]


@dataclass(frozen=True)
class BeamConfig:
    width: int = DEFAULT_WIDTH
    depth: int = DEFAULT_DEPTH
    budget_ns: int = DEFAULT_BUDGET_NS
    max_candidates: int = DEFAULT_MAX_CANDIDATES

    def validate(self) -> "BeamConfig":
        if self.width < 1:
            raise ValueError("beam width must be positive")
        if self.depth < 1:
            raise ValueError("beam depth must be positive")
        if self.budget_ns < 0:
            raise ValueError("beam budget must be non-negative")
        if self.max_candidates < 1:
            raise ValueError("max_candidates must be positive")
        return self


@dataclass(frozen=True)
class BeamResult:
    actions: tuple[Action, ...]
    score: int | None
    complete: bool
    used_fallback: bool
    expanded: int
    pruned_illegal: int
    frontier_peak: int
    searched_depth: int
    reason: str


@dataclass(frozen=True)
class _Node:
    state: State
    actions: tuple[Action, ...]
    score: int
    canonical_prefix: bool


def _encoded(value: Any) -> str:
    """Stable tie-break encoding. Kaggriculture actions are JSON values."""
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        return repr(value)


def _dedupe(
    canonical: Action,
    candidates: Iterable[Action],
    max_candidates: int,
) -> Iterator[Action]:
    """Yield a bounded unique set with canonical first, without materializing input."""
    seen: set[str] = set()
    emitted = 0
    for action in (canonical,):
        key = _encoded(action)
        seen.add(key)
        emitted += 1
        yield action
    if emitted >= max_candidates:
        return
    for action in candidates:
        key = _encoded(action)
        if key in seen:
            continue
        seen.add(key)
        emitted += 1
        yield action
        if emitted >= max_candidates:
            return


def _rank(node: _Node) -> tuple[int, int, str]:
    # Higher score first; canonical wins exact score ties; lexical JSON is the
    # final deterministic tie break independent of hash/random iteration order.
    return (-node.score, -int(node.canonical_prefix), _encoded(node.actions))


def _trim(nodes: list[_Node], width: int) -> list[_Node]:
    nodes.sort(key=_rank)
    if len(nodes) <= width:
        return nodes
    kept = nodes[:width]
    if any(node.canonical_prefix for node in kept):
        return kept
    canonical = next((node for node in nodes if node.canonical_prefix), None)
    if canonical is not None:
        kept[-1] = canonical
        kept.sort(key=_rank)
    return kept


def search_joint_actions(
    initial_state: State,
    canonical_actions: Sequence[Action],
    candidates: CandidateProvider,
    transition: Transition,
    score: Scorer,
    *,
    config: BeamConfig = BeamConfig(),
    deadline_ns: int | None = None,
    now_ns: Clock = time.perf_counter_ns,
) -> BeamResult:
    """Search a bounded prefix of a joint worker action.

    ``transition`` returns a fresh successor state for a legal/effective action
    and ``None`` for an illegal or resource-conflicting action. The true
    canonical prefix is retained even when that unit's transition is a no-op,
    because the surrounding controller owns baseline semantics. After a
    noncanonical prefix, ``successor is None`` prunes even if the attempted
    action text equals that unit's canonical action.

    The search assigns at most ``depth`` workers. Remaining workers keep their
    canonical actions and are simulated before final ranking, so changing an
    earlier worker cannot hide a later resource conflict. Any deadline or
    callback failure returns the original canonical tuple exactly.
    """
    config.validate()
    canonical = tuple(copy.deepcopy(tuple(canonical_actions)))
    if not canonical:
        return BeamResult((), None, True, False, 0, 0, 1, 0, "empty")

    start = now_ns()
    hard_deadline = start + config.budget_ns
    if deadline_ns is not None:
        hard_deadline = min(hard_deadline, deadline_ns)

    expanded = 0
    pruned = 0
    peak = 1
    planned_depth = min(config.depth, len(canonical))
    completed_depth = 0

    def expired() -> bool:
        return now_ns() >= hard_deadline

    def fallback(reason: str) -> BeamResult:
        return BeamResult(canonical, None, False, True, expanded, pruned, peak,
                          completed_depth, reason)

    if expired():
        return fallback("deadline-before-search")

    try:
        initial_score = int(score(initial_state, ()))
    except Exception:
        return fallback("scorer-error")

    frontier = [_Node(initial_state, (), initial_score, True)]
    for unit_index in range(planned_depth):
        if expired():
            return fallback("deadline-during-search")
        next_frontier: list[_Node] = []
        canonical_action = canonical[unit_index]
        for node in frontier:
            if expired():
                return fallback("deadline-during-search")
            try:
                provided = candidates(node.state, unit_index, canonical_action)
                offered = _dedupe(canonical_action, provided, config.max_candidates)
                for action in offered:
                    if expired():
                        return fallback("deadline-during-search")
                    expanded += 1
                    is_canonical = _encoded(action) == _encoded(canonical_action)
                    successor = transition(node.state, unit_index, action)
                    if expired():
                        return fallback("deadline-during-search")
                    if successor is None:
                        if not (node.canonical_prefix and is_canonical):
                            pruned += 1
                            continue
                        successor = node.state
                    actions = node.actions + (copy.deepcopy(action),)
                    canonical_prefix = node.canonical_prefix and is_canonical
                    value = int(score(successor, actions))
                    if expired():
                        return fallback("deadline-during-search")
                    next_frontier.append(_Node(successor, actions, value, canonical_prefix))
            except Exception:
                return fallback("callback-error")
        if not next_frontier:
            return fallback("no-legal-frontier")
        frontier = _trim(next_frontier, config.width)
        peak = max(peak, len(frontier))
        completed_depth = unit_index + 1

    # Preserve canonical suffix exactly, but simulate it from every changed
    # prefix so final ranking sees downstream no-ops/resource interactions.
    finalists: list[_Node] = []
    for node in frontier:
        state = node.state
        actions = list(node.actions)
        for unit_index in range(planned_depth, len(canonical)):
            if expired():
                return fallback("deadline-during-finalization")
            action = canonical[unit_index]
            try:
                successor = transition(state, unit_index, action)
            except Exception:
                return fallback("callback-error")
            if expired():
                return fallback("deadline-during-finalization")
            state = state if successor is None else successor
            actions.append(copy.deepcopy(action))
        try:
            value = int(score(state, tuple(actions)))
        except Exception:
            return fallback("callback-error")
        if expired():
            return fallback("deadline-during-finalization")
        finalists.append(_Node(state, tuple(actions), value, node.canonical_prefix))

    finalists.sort(key=_rank)
    if expired():
        return fallback("deadline-during-finalization")
    best = finalists[0]
    return BeamResult(best.actions, best.score, True, False, expanded, pruned,
                      peak, planned_depth, "complete")


def worker_actions(action: dict[str, Any], hand_count: int | None = None) -> tuple[Action, ...]:
    """Extract worker actions while leaving all controller/market fields alone."""
    if not isinstance(action, dict):
        raise TypeError("canonical action must be an object")
    farmer = copy.deepcopy(action.get("farmer", ["PASS"]))
    hands = action.get("hands", [])
    if not isinstance(hands, list):
        raise TypeError("hands must be a list")
    if hand_count is None:
        hand_count = len(hands)
    if hand_count < 0:
        raise ValueError("hand_count must be non-negative")
    normalized = [copy.deepcopy(hands[i]) if i < len(hands) else ["PASS"]
                  for i in range(hand_count)]
    return (farmer, *normalized)


def replace_worker_actions(action: dict[str, Any], units: Sequence[Action]) -> dict[str, Any]:
    """Return a copy with only farmer/hands replaced; preserve market ordering."""
    if not units:
        raise ValueError("at least the main farmer action is required")
    result = copy.deepcopy(action)
    result["farmer"] = copy.deepcopy(units[0])
    result["hands"] = copy.deepcopy(list(units[1:]))
    return result


def propose_worker_action(
    canonical_action: dict[str, Any],
    initial_state: State,
    candidates: CandidateProvider,
    transition: Transition,
    score: Scorer,
    *,
    hand_count: int | None = None,
    config: BeamConfig = BeamConfig(),
    deadline_ns: int | None = None,
    now_ns: Clock = time.perf_counter_ns,
) -> tuple[dict[str, Any], BeamResult]:
    """Return a full action object while allowing only worker fields to change."""
    canonical_workers = worker_actions(canonical_action, hand_count=hand_count)
    result = search_joint_actions(
        initial_state,
        canonical_workers,
        candidates,
        transition,
        score,
        config=config,
        deadline_ns=deadline_ns,
        now_ns=now_ns,
    )
    if result.used_fallback or result.actions == canonical_workers:
        # Preserve the exact selected object when the normalized worker tuple did
        # not change. In particular, do not expand omitted trailing hands into
        # explicit PASS actions merely because hand_count came from observed state.
        return copy.deepcopy(canonical_action), result
    return replace_worker_actions(canonical_action, result.actions), result
