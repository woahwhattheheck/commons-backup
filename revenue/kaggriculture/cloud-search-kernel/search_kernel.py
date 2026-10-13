# SPDX-License-Identifier: Apache-2.0
"""Bounded, non-anticipative economic bundle search. No chess code is imported.

Callbacks are pure and deterministic. State keys must include time, money,
flags, inventory, market and controller state; scenario keys include hypotheses.
A single action sequence is evaluated across every scenario. This is open-loop
robust planning, not alternating minimax or a contingent-information game tree.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from time import perf_counter
from typing import Any, Callable, Hashable, Iterable, Sequence
import json


def canonical_key(value: Any) -> str:
    """Exact JSON key; callers must not omit relevant state or round prices."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


class Infeasible(ValueError):
    """The proposed bundle cannot be executed in this scenario state."""


class _Exhausted(Exception):
    pass


@dataclass(frozen=True)
class Model:
    candidates: Callable[[Any], Iterable[Any]]
    transition: Callable[[Any, Any, Any], Any]
    evaluate: Callable[[Any, Any], float]
    state_key: Callable[[Any], Hashable] = canonical_key
    action_key: Callable[[Any], Hashable] = canonical_key
    scenario_key: Callable[[Any], Hashable] = canonical_key
    # Stable descending heuristic. WAIT is never intrinsically pruned.
    order: Callable[[Any, Any], float] = lambda state, action: 0.0
    extend: Callable[[Sequence[Any]], bool] = lambda states: False


@dataclass(frozen=True)
class Limits:
    seconds: float = 0.05
    max_transitions: int = 2000
    max_depth: int = 3
    extensions: int = 0
    cache_entries: int = 20000
    candidate_limit: int = 256

    def __post_init__(self) -> None:
        if not isfinite(self.seconds) or self.seconds < 0:
            raise ValueError("seconds must be finite and nonnegative")
        for name in ("max_transitions", "max_depth", "extensions", "cache_entries", "candidate_limit"):
            v = getattr(self, name)
            if isinstance(v, bool) or not isinstance(v, int) or v < 0:
                raise ValueError(name + " must be a nonnegative integer")
        if self.max_depth + self.extensions > 64 or self.candidate_limit == 0:
            raise ValueError("depth + extensions must be <=64; candidate_limit must be positive")


@dataclass(frozen=True)
class Result:
    action: Any
    principal_variation: tuple[Any, ...]
    values: tuple[float, ...]
    completed_depth: int
    selective_depth: int
    status: str
    transitions: int
    evaluations: int
    cache_hits: int
    elapsed_seconds: float


def robust_rank(values: Sequence[float]) -> tuple[float, float]:
    """Worst case first; unweighted mean only breaks ties, not an expectation."""
    return min(values), sum(values) / len(values)


def search(model: Model, states: Sequence[Any], scenarios: Sequence[Any],
           fallback: Any, *, limits: Limits = Limits(),
           warm_start: Sequence[Any] = (), cache: bool = True,
           ordering: bool = True, iterative: bool = True,
           rank: Callable[[Sequence[float]], Any] = robust_rank,
           clock: Callable[[], float] = perf_counter) -> Result:
    """Return last completely searched depth, or an explicitly unscored fallback.

    Hard work cap counts uncached transitions. Deadline is cooperative: a callback
    cannot be preempted, so its own worst-case cost bounds a single-call overrun.
    Caches are bounded and local to this invocation; no stale cross-turn reuse.
    Iterative=False is a fixed-depth ablation; it retains the initial fully
    evaluated fallback when the requested depth cannot finish. All callbacks
    and scenario-independent plan choices use only inputs provided by caller.
    """
    if not states or len(states) != len(scenarios):
        raise ValueError("provide one initial state per nonempty scenario set")
    states, scenarios = tuple(states), tuple(scenarios)
    start = clock()
    deadline = start + limits.seconds
    transitions = evaluations = hits = 0
    tt: dict[Any, Any] = {}
    et: dict[Any, float] = {}
    scenario_keys = tuple(model.scenario_key(s) for s in scenarios)
    if len(set(scenario_keys)) != len(scenario_keys):
        raise ValueError("scenario keys must be unique")
    best_plan, best_values = (fallback,), ()
    completed = selected = 0
    stopped = False
    preferred = tuple(warm_start)

    def check() -> None:
        if clock() >= deadline:
            raise _Exhausted

    def put(table: dict, key: Any, value: Any) -> None:
        if cache and len(tt) + len(et) < limits.cache_entries:
            table[key] = value

    def advance(current: tuple, action: Any) -> tuple:
        nonlocal transitions, hits
        following = []
        for state, scenario, sk in zip(current, scenarios, scenario_keys):
            check()
            key = (sk, model.state_key(state), model.action_key(action))
            if cache and key in tt:
                hits += 1
                following.append(tt[key])
                continue
            if transitions >= limits.max_transitions:
                raise _Exhausted
            transitions += 1
            nxt = model.transition(state, action, scenario)
            check()
            put(tt, key, nxt)
            following.append(nxt)
        return tuple(following)

    def assess(current: tuple) -> tuple[float, ...]:
        nonlocal evaluations, hits
        values = []
        for state, scenario, sk in zip(current, scenarios, scenario_keys):
            check()
            key = (sk, model.state_key(state))
            if cache and key in et:
                hits += 1
                value = et[key]
            else:
                evaluations += 1
                value = float(model.evaluate(state, scenario))
                check()
                if not isfinite(value):
                    raise ValueError("evaluate must return finite values")
                put(et, key, value)
            values.append(value)
        return tuple(values)

    def actions(current: tuple, level: int) -> list:
        # Intersection prevents selecting a bundle feasible only in one scenario.
        maps = []
        for state in current:
            m = {}
            for count, action in enumerate(model.candidates(state)):
                check()
                if count >= limits.candidate_limit:
                    raise ValueError("candidate_limit exceeded; bound candidates explicitly")
                m.setdefault(model.action_key(action), action)
            maps.append(m)
        common = set(maps[0]).intersection(*(set(m) for m in maps[1:]))
        out = [a for k, a in maps[0].items() if k in common]
        if ordering:
            out.sort(key=lambda a: model.order(current[0], a), reverse=True)
            if level < len(preferred):
                pk = model.action_key(preferred[level])
                out.sort(key=lambda a: model.action_key(a) != pk)
        check()
        return out

    def visit(current: tuple, remaining: int, extra: int,
              plan: tuple) -> tuple[tuple, tuple[float, ...]] | None:
        check()
        if remaining == 0:
            if extra and model.extend(current):
                remaining, extra = 1, extra - 1
            else:
                return plan, assess(current)
        winner = None
        choices = actions(current, len(plan))
        if not choices:
            return plan, assess(current)
        for action in choices:
            try:
                nxt = advance(current, action)
            except Infeasible:
                continue
            result = visit(nxt, remaining - 1, extra, plan + (action,))
            if result is not None and (winner is None or rank(result[1]) > rank(winner[1])):
                winner = result
        return winner

    try:
        # This checkpoint is useful even when depth one cannot finish.
        best_values = assess(advance(states, fallback))
        check()
        selected = 1
        if not preferred:
            preferred = best_plan
        depths = range(1, limits.max_depth + 1) if iterative else ([limits.max_depth] if limits.max_depth else [])
        for depth in depths:
            outcome = visit(states, depth, limits.extensions, ())
            check()
            if outcome is not None and outcome[0]:
                best_plan, best_values = outcome
                completed, selected = depth, len(best_plan)
                if ordering:
                    preferred = best_plan
    except _Exhausted:
        stopped = True
    status = "unscored_fallback" if not best_values else ("budget_exhausted" if stopped else "complete")
    return Result(best_plan[0], best_plan, best_values, completed, selected, status,
                  transitions, evaluations, hits, max(0.0, clock() - start))
