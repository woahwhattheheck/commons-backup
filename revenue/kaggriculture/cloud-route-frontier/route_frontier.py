# SPDX-License-Identifier: Apache-2.0
"""Ordered route traces, explicit Pareto tradeoffs, and exact segment splicing.

All objectives maximize. Callers supply pure bounded transitions and complete
JSON state (including time/controller state); no policy or engine is imported.
Mapping insertion order is retained because ordered inventories affect DROP.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
import math
from typing import Any, Callable, Iterable, Sequence


def exact_key(value: Any) -> str:
    """Lossless ordered JSON snapshot, not a sorted or rounded state projection."""
    def check(x: Any) -> None:
        if x is None or type(x) in (str, bool, int):
            return
        if type(x) is float and math.isfinite(x):
            return
        if type(x) is list:
            for v in x:
                check(v)
            return
        if type(x) is dict and all(type(k) is str for k in x):
            for v in x.values():
                check(v)
            return
        raise ValueError("state/actions must be finite JSON values with string keys")
    check(value)
    return json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":"))


class Incompatible(ValueError):
    """A route segment does not start at the recorded complete state/context."""


@dataclass(frozen=True)
class Trace:
    name: str
    context: str
    snapshots: tuple[str, ...]
    actions: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "snapshots", tuple(self.snapshots))
        object.__setattr__(self, "actions", tuple(self.actions))
        if (type(self.name) is not str or not self.name or
                type(self.context) is not str or not self.context or not self.actions):
            raise ValueError("a trace needs a name, context and at least one action")
        if len(self.snapshots) != len(self.actions) + 1:
            raise ValueError("each action needs its before and after snapshots")
        for text in (*self.snapshots, *self.actions):
            if exact_key(json.loads(text)) != text:
                raise ValueError("trace contains a noncanonical ordered snapshot")

    @property
    def entry(self) -> str:
        return self.snapshots[0]

    @property
    def exit(self) -> str:
        return self.snapshots[-1]

    def state(self, index: int = -1) -> Any:
        return json.loads(self.snapshots[index])

    def action(self, index: int = 0) -> Any:
        return json.loads(self.actions[index])


def rollout(name: str, state: Any, actions: Iterable[Any],
            advance: Callable[[Any, Any], Any], *, context: str,
            max_steps: int = 720) -> Trace:
    """Execute an entire macro. Exhausted/failed macros never return partial traces.

    Each callback receives private copies. max_steps bounds callback count, not
    callback duration; callers must bound the cost of their transition itself.
    Context identifies engine/configuration plus the supplied causal scenario.
    """
    if type(max_steps) is not int or max_steps < 1:
        raise ValueError("max_steps must be a positive integer")
    snapshots = [exact_key(state)]
    encoded_actions: list[str] = []
    for index, action in enumerate(actions):
        if index >= max_steps:
            raise ValueError("macro exceeds max_steps; no completed trace")
        encoded = exact_key(action)
        following = advance(json.loads(snapshots[-1]), json.loads(encoded))
        snapshots.append(exact_key(following))
        encoded_actions.append(encoded)
    return Trace(name, context, tuple(snapshots), tuple(encoded_actions))


def splice(prefix: Trace, suffix: Trace, *, name: str | None = None) -> Trace:
    """Compose only an exact state-and-context match. No implicit WAIT or reset."""
    if prefix.context != suffix.context:
        raise Incompatible("different transition/scenario contexts")
    if prefix.exit != suffix.entry:
        raise Incompatible("prefix exit differs from suffix entry")
    return Trace(name or prefix.name + "+" + suffix.name, prefix.context,
                 prefix.snapshots + suffix.snapshots[1:], prefix.actions + suffix.actions)


@dataclass(frozen=True)
class Alternative:
    name: str
    traces: tuple[Trace, ...]
    objectives: tuple[str, ...]
    values: tuple[tuple[float, ...], ...]
    # Optional caller-asserted continuation equivalence, one key per context.
    # Default is the complete exact exit, including cash and ordered inventories.
    continuation_keys: tuple[str, ...] | None = None
    equivalence_label: str = "exact-state"

    def __post_init__(self) -> None:
        object.__setattr__(self, "traces", tuple(self.traces))
        object.__setattr__(self, "objectives", tuple(self.objectives))
        object.__setattr__(self, "values", tuple(tuple(row) for row in self.values))
        if self.continuation_keys is not None:
            object.__setattr__(self, "continuation_keys", tuple(self.continuation_keys))
        if (type(self.name) is not str or not self.name or not self.traces or
                not all(isinstance(t, Trace) for t in self.traces) or not self.objectives or
                not all(type(x) is str and x for x in self.objectives)):
            raise ValueError("provide a name, complete scenario traces and objectives")
        if type(self.equivalence_label) is not str or not self.equivalence_label:
            raise ValueError("continuation equivalence needs a nonempty label")
        if len(set(self.objectives)) != len(self.objectives):
            raise ValueError("objective names must be unique")
        contexts = tuple(t.context for t in self.traces)
        if len(set(contexts)) != len(contexts):
            raise ValueError("scenario/context labels must be unique")
        if len(self.values) != len(self.traces):
            raise ValueError("one objective vector per complete scenario is needed")
        for row in self.values:
            if len(row) != len(self.objectives) or any(
                type(v) not in (int, float) or not math.isfinite(v) for v in row
            ):
                raise ValueError("objective vectors must be finite and have matching dimensions")
        if self.continuation_keys is not None:
            if (len(self.continuation_keys) != len(self.traces) or
                    not all(type(k) is str and k for k in self.continuation_keys)):
                raise ValueError("one nonempty continuation key per scenario is needed")
            if self.equivalence_label == "exact-state" or not self.equivalence_label:
                raise ValueError("custom equivalence needs an explicit descriptive label")

    def comparison_key(self) -> tuple:
        exits = self.continuation_keys or tuple(t.exit for t in self.traces)
        # Sort contexts, not the state maps within them. Scenario order is immaterial.
        rows = tuple(sorted((t.context, t.entry, len(t.actions), key)
                            for t, key in zip(self.traces, exits)))
        return self.objectives, self.equivalence_label, rows

    def vector(self) -> tuple[float, ...]:
        return tuple(v for _, row in sorted((t.context, row)
                     for t, row in zip(self.traces, self.values)) for v in row)


def dominates(left: Alternative, right: Alternative) -> bool:
    """Exact only within the stated continuation equivalence and objective set."""
    if left.comparison_key() != right.comparison_key():
        return False
    a, b = left.vector(), right.vector()
    return all(x >= y for x, y in zip(a, b)) and any(x > y for x, y in zip(a, b))


@dataclass(frozen=True)
class Frontier:
    kept: tuple[Alternative, ...]
    dominated: tuple[tuple[str, str], ...]
    budget_dropped: tuple[str, ...]
    dominance_comparisons: int

    @property
    def approximate(self) -> bool:
        return bool(self.budget_dropped)


def pareto_frontier(alternatives: Sequence[Alternative], *, max_size: int = 64,
                    max_candidates: int = 256,
                    rank: Callable[[Alternative], Any] | None = None) -> Frontier:
    """Retain incomparable routes. Any size-cap removal is explicitly approximate.

    All vectors use the same maximize convention. No inventory monotonicity,
    unobserved probability, or automatic equivalence of different exits is assumed.
    """
    if type(max_size) is not int or max_size < 1:
        raise ValueError("max_size must be positive")
    if type(max_candidates) is not int or max_candidates < 1:
        raise ValueError("max_candidates must be positive")
    if len(alternatives) > max_candidates:
        raise ValueError("candidate bound exceeded; no truncated exact frontier")
    names = [x.name for x in alternatives]
    if len(set(names)) != len(names):
        raise ValueError("alternative names must be unique")
    kept: list[Alternative] = []
    removed: list[tuple[str, str]] = []
    checks = 0
    # Alternative freezes its inputs. Reuse its scenario alignment within this
    # invocation, without hashing snapshots or retaining cross-call state. Keep
    # the original method-dispatch path for custom Alternative subclasses.
    cacheable = len(alternatives) > 1 and all(
        type(a) is Alternative and all(type(t) is Trace for t in a.traces)
        for a in alternatives)
    keys = [a.comparison_key() for a in alternatives] if cacheable else None
    vectors: dict[int, tuple[float, ...]] = {}
    for ri, right in enumerate(alternatives):
        winner = None
        for li, left in enumerate(alternatives):
            if left is right:
                continue
            checks += 1
            if keys is None:
                better = dominates(left, right)
            elif keys[li] != keys[ri]:
                better = False
            else:
                if li not in vectors:
                    vectors[li] = left.vector()
                if ri not in vectors:
                    vectors[ri] = right.vector()
                a, b = vectors[li], vectors[ri]
                better = (all(x >= y for x, y in zip(a, b)) and
                          any(x > y for x, y in zip(a, b)))
            if better:
                winner = left
                break
        if winner is None:
            kept.append(right)
        else:
            removed.append((right.name, winner.name))
    dropped: list[str] = []
    if len(kept) > max_size:
        if rank is not None:
            kept.sort(key=rank, reverse=True)
        # Stable input order is used without a caller ranking, not a hidden score.
        dropped = [a.name for a in kept[max_size:]]
        kept = kept[:max_size]
    return Frontier(tuple(kept), tuple(removed), tuple(dropped), checks)


class BoundRoute:
    """One chosen complete trace; no controller calls or arbitrary state repair.

    Feed the same complete observable representation used when planning. Example
    full-engine evaluator snapshots are NOT suitable runtime agent observations.
    A repeated identical observation returns the same action idempotently.
    """
    def __init__(self, trace: Trace):
        self.trace = trace
        self.index = 0
        self.status = "ready"
        self._previous: str | None = None
        self._action: str | None = None

    def act(self, state: Any, fallback: Any) -> Any:
        key = exact_key(state)
        if self.status != "state_mismatch" and key == self._previous:
            return json.loads(self._action)
        if self.status == "state_mismatch":
            return deepcopy(fallback)
        if self.index >= len(self.trace.actions):
            self.status = "complete"
            return deepcopy(fallback)
        if key != self.trace.snapshots[self.index]:
            self.status = "state_mismatch"
            return deepcopy(fallback)
        encoded = self.trace.actions[self.index]
        self._previous, self._action = key, encoded
        self.index += 1
        self.status = "running"
        return json.loads(encoded)


def kernel_model(kernel: Any, traces: Sequence[Trace],
                 evaluate: Callable[[Any, Any], float]) -> Any:
    """T06 Model adapter over completed macro traces; no changes to T06 files.

    Scenarios are their exact Trace.context strings. Cached transitions are reused
    only at matching ordered entry snapshots and context. A kernel depth counts
    complete macros, not game turns; evaluate must price their actual timestamps.
    One macro name always means the same ordered actions in every scenario. The
    adapter never turns a hidden scenario label into a different chosen plan.
    """
    lookup: dict[tuple[str, str, str], Trace] = {}
    commands: dict[str, tuple[str, ...]] = {}
    by_entry: dict[str, list[str]] = {}
    for trace in traces:
        if trace.name in commands and commands[trace.name] != trace.actions:
            raise ValueError("one macro name must have identical actions across scenarios")
        commands[trace.name] = trace.actions
        key = (trace.context, trace.entry, trace.name)
        if key in lookup and lookup[key] != trace:
            raise ValueError("same macro/context/entry has different transitions")
        lookup[key] = trace
        bucket = by_entry.setdefault(trace.entry, [])
        if trace.name not in bucket:
            bucket.append(trace.name)

    def candidates(state: Any) -> Iterable[str]:
        return tuple(by_entry.get(exact_key(state), ()))

    def transition(state: Any, name: str, context: str) -> Any:
        trace = lookup.get((context, exact_key(state), name))
        if trace is None:
            raise kernel.Infeasible("no matching complete macro in this scenario")
        return trace.state()

    return kernel.Model(candidates=candidates, transition=transition,
                        evaluate=evaluate, state_key=exact_key,
                        action_key=exact_key, scenario_key=exact_key)
