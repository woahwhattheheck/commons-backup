# SPDX-License-Identifier: Apache-2.0
"""Fail-closed exact Pareto dominance for bounded TITAN search frontiers.

This module is intentionally policy-neutral: it never creates actions and it
never decides which state fields may be ignored.  Callers must provide the full
identity contract below.  A state can prune another state only when that exact
identity matches and every declared resource metric is weakly better, with at
least one strict gain.
"""
from dataclasses import dataclass
from collections.abc import Mapping, Sequence
from typing import Any, Iterable

IDENTITY_FIELDS = frozenset({
    "physical",
    "market",
    "obligations",
    "capacity",
    "care_bonus",
    "order_slots",
    "occupancy",
})
METRIC_FIELDS = frozenset({"cash", "inventory", "slack", "safety"})


class UnsafeDominanceState(ValueError):
    """Raised when a state cannot be compared without weakening the contract."""


def _freeze(value: Any) -> Any:
    """Return a deterministic, type-preserving immutable representation."""
    if value is None:
        return ("none",)
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, int):
        return ("int", value)
    if isinstance(value, str):
        return ("str", value)
    if isinstance(value, tuple):
        return ("tuple", tuple(_freeze(v) for v in value))
    if isinstance(value, list):
        return ("list", tuple(_freeze(v) for v in value))
    if isinstance(value, Mapping):
        frozen = [(_freeze(k), _freeze(v)) for k, v in value.items()]
        return ("map", tuple(sorted(frozen, key=repr)))
    raise UnsafeDominanceState(f"unsupported identity value: {type(value).__name__}")


def _nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise UnsafeDominanceState(f"{name} must be a nonnegative int")
    return value


def _metric_map(value: Any, name: str) -> tuple[tuple[str, int], ...]:
    if not isinstance(value, Mapping):
        raise UnsafeDominanceState(f"{name} must be a mapping")
    rows = []
    for key, amount in value.items():
        if not isinstance(key, str):
            raise UnsafeDominanceState(f"{name} keys must be strings")
        rows.append((key, _nonnegative_int(amount, f"{name}[{key!r}]")))
    rows.sort()
    return tuple(rows)


def _normalize_identity(identity: Mapping[str, Any]) -> tuple[tuple[str, Any], ...]:
    if not isinstance(identity, Mapping):
        raise UnsafeDominanceState("identity must be a mapping")
    fields = frozenset(identity.keys())
    if fields != IDENTITY_FIELDS:
        missing = sorted(IDENTITY_FIELDS - fields)
        extra = sorted(fields - IDENTITY_FIELDS, key=repr)
        raise UnsafeDominanceState(f"identity fields mismatch: missing={missing} extra={extra}")
    return tuple((field, _freeze(identity[field])) for field in sorted(IDENTITY_FIELDS))


@dataclass(frozen=True)
class DominanceNode:
    identity: Mapping[str, Any]
    cash: int
    inventory: Mapping[str, int]
    slack: Mapping[str, int]
    safety: Mapping[str, int]
    payload: Any = None
    protected: bool = False

    @classmethod
    def from_state(cls, state: Mapping[str, Any], *, payload: Any = None,
                   protected: bool = False) -> "DominanceNode":
        if not isinstance(state, Mapping):
            raise UnsafeDominanceState("state must be a mapping")
        fields = frozenset(state.keys())
        expected = IDENTITY_FIELDS | METRIC_FIELDS
        if fields != expected:
            missing = sorted(expected - fields)
            extra = sorted(fields - expected, key=repr)
            raise UnsafeDominanceState(f"state fields mismatch: missing={missing} extra={extra}")
        identity = {field: state[field] for field in IDENTITY_FIELDS}
        return cls(identity=identity, cash=state["cash"], inventory=state["inventory"],
                   slack=state["slack"], safety=state["safety"], payload=payload,
                   protected=protected)

    def identity_key(self) -> tuple[tuple[str, Any], ...]:
        return _normalize_identity(self.identity)

    def metric_key(self) -> tuple[int, tuple[tuple[str, int], ...],
                                  tuple[tuple[str, int], ...], tuple[tuple[str, int], ...]]:
        return (
            _nonnegative_int(self.cash, "cash"),
            _metric_map(self.inventory, "inventory"),
            _metric_map(self.slack, "slack"),
            _metric_map(self.safety, "safety"),
        )


def _map_weakly_ge(a: tuple[tuple[str, int], ...],
                   b: tuple[tuple[str, int], ...], *,
                   sparse_zero: bool) -> tuple[bool, bool]:
    left = dict(a); right = dict(b)
    if not sparse_zero and left.keys() != right.keys():
        return False, False
    keys = left.keys() | right.keys() if sparse_zero else left.keys()
    strict = False
    for key in keys:
        av = left.get(key, 0); bv = right.get(key, 0)
        if av < bv:
            return False, False
        strict = strict or av > bv
    return True, strict


def _metrics_dominate(a: tuple[Any, ...], b: tuple[Any, ...]) -> bool:
    if a[0] < b[0]:
        return False
    strict = a[0] > b[0]
    # Inventory may omit a good (treated as zero). Slack and safety require
    # identical declared dimensions; a missing key is unknown, not zero.
    specs = (
        (a[1], b[1], True),
        (a[2], b[2], False),
        (a[3], b[3], False),
    )
    for left, right, sparse_zero in specs:
        weak, gained = _map_weakly_ge(left, right, sparse_zero=sparse_zero)
        if not weak:
            return False
        strict = strict or gained
    return strict


def dominates(a: DominanceNode, b: DominanceNode) -> bool:
    """True iff ``a`` safely Pareto-dominates ``b`` under exact identity."""
    if a.identity_key() != b.identity_key():
        return False
    return _metrics_dominate(a.metric_key(), b.metric_key())


def prune_frontier(nodes: Iterable[DominanceNode], *, mode: str = "dominance") -> list[DominanceNode]:
    """Stable exact-dedup / Pareto prune with a protected fallback escape hatch.

    ``none`` preserves every node after validating it. ``hash`` removes only
    unprotected exact identity+metric duplicates. ``dominance`` additionally
    removes an unprotected node when another node with the same exact identity
    dominates it. Protected nodes are never removed. A protected duplicate
    replaces an earlier unprotected duplicate so the canonical/deadline
    fallback cannot disappear. Distinct protected payloads that share an exact
    state all survive, because payload/path identity is not proven irrelevant.
    """
    if mode not in {"none", "hash", "dominance"}:
        raise ValueError(f"unknown pruning mode: {mode}")

    records = []
    for node in nodes:
        if not isinstance(node, DominanceNode):
            raise UnsafeDominanceState("frontier entries must be DominanceNode")
        records.append([node, node.identity_key(), node.metric_key()])
    if mode == "none":
        return [row[0] for row in records]

    unique = []
    locations: dict[tuple[Any, Any], int] = {}
    for record in records:
        node, identity_key, metric_key = record
        exact = (identity_key, metric_key)
        prior = locations.get(exact)
        if prior is None:
            locations[exact] = len(unique)
            unique.append(record)
        elif node.protected:
            if not unique[prior][0].protected:
                unique[prior] = record
            else:
                unique.append(record)

    if mode == "hash":
        return [row[0] for row in unique]

    groups: dict[Any, list[int]] = {}
    for index, (_, identity_key, _) in enumerate(unique):
        groups.setdefault(identity_key, []).append(index)

    removed = set()
    for indices in groups.values():
        for target in indices:
            node, _, target_metrics = unique[target]
            if node.protected:
                continue
            for source in indices:
                if source == target:
                    continue
                if _metrics_dominate(unique[source][2], target_metrics):
                    removed.add(target)
                    break
    return [row[0] for index, row in enumerate(unique) if index not in removed]
