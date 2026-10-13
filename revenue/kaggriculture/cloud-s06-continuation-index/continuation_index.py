# SPDX-License-Identifier: Apache-2.0
"""Bounded continuation retrieval for the TITAN S06 experiment.

The index is deliberately advisory.  It retrieves prior canonical continuations
from public feature projections, always unions caller-supplied canonical actions,
and never selects or promotes a final action by itself.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import sys
from typing import Any, Callable, Iterable

FEATURE_FIELDS = (
    'phase', 'positions', 'resources', 'structures', 'animals', 'market',
    'commitments',
)
DEFAULT_QUANTA = {
    'phase': 1,
    'positions': 1,
    'resources': 4,
    'structures': 1,
    'animals': 1,
    'market': 4,
    'commitments': 1,
}
DEFAULT_MAX_BYTES = 128 * 1024 * 1024
DEFAULT_RETRIEVE = 32
# Admission uses recursive Python object size, then doubles it and adds an
# explicit per-record reserve.  The margin covers index-container growth and
# allocator slack instead of pretending serialized payload bytes equal resident
# index footprint.
ADMISSION_SAFETY_FACTOR = 2
ADMISSION_RECORD_RESERVE = 1024


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False)


def project_public_state(state: dict[str, Any]) -> dict[str, Any]:
    """Project only the S06 public features; ignore labels/future outcomes."""
    return {name: state.get(name) for name in FEATURE_FIELDS}


def exact_state_hash(state: dict[str, Any]) -> str:
    payload = _stable_json(project_public_state(state)).encode('utf-8')
    return hashlib.sha256(payload).hexdigest()


def _quantize(value: Any, quantum: int) -> Any:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, int):
        return math.floor(value / quantum)
    if isinstance(value, float):
        return math.floor(value / quantum)
    if isinstance(value, dict):
        return {str(k): _quantize(v, quantum) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [_quantize(v, quantum) for v in value]
    raise TypeError('Unsupported public-state value: %r' % (type(value),))


def product_quantized_key(state: dict[str, Any], quanta: dict[str, int] | None = None) -> str:
    quanta = dict(DEFAULT_QUANTA if quanta is None else quanta)
    projected = project_public_state(state)
    encoded = {}
    for name in FEATURE_FIELDS:
        quantum = max(1, int(quanta.get(name, 1)))
        encoded[name] = _quantize(projected[name], quantum)
    return hashlib.sha256(_stable_json(encoded).encode('utf-8')).hexdigest()


def action_key(action: Any) -> str:
    return hashlib.sha256(_stable_json(action).encode('utf-8')).hexdigest()


def _deep_size(value: Any, seen: set[int] | None = None) -> int:
    """Recursive owned Python-object footprint using ``sys.getsizeof``.

    Shared references are charged once within one measurement.  This is used as
    a deterministic structural admission bound, not as an RSS profiler.
    """
    if seen is None:
        seen = set()
    identity = id(value)
    if identity in seen:
        return 0
    seen.add(identity)
    size = sys.getsizeof(value)
    if isinstance(value, dict):
        size += sum(_deep_size(k, seen) + _deep_size(v, seen)
                    for k, v in value.items())
    elif isinstance(value, (list, tuple, set, frozenset)):
        size += sum(_deep_size(item, seen) for item in value)
    elif hasattr(value, '__dict__'):
        size += _deep_size(vars(value), seen)
    return size


def collision_reasons(action: Any, state: dict[str, Any]) -> tuple[str, ...]:
    """Fail historical candidates closed on explicit funding/seed/route conflicts.

    The caller's canonical actions are never filtered here.  Historical actions
    may express requirements under ``requires``.  Missing requirement fields are
    treated as no extra commitment rather than inferred from hidden state.
    """
    if not isinstance(action, dict):
        return ()
    # Missing requirements mean no extra commitment.  Any *explicit* value must
    # be a mapping; do not let falsy malformed values collapse through ``or {}``.
    if 'requires' not in action:
        requires = {}
    else:
        requires = action['requires']
        if not isinstance(requires, dict):
            return ('malformed_requirements',)
    resources = state.get('resources') or {}
    commitments = state.get('commitments') or {}
    reasons = []

    funding = max(0, int(requires.get('funding', 0) or 0))
    money = max(0, int(resources.get('money', resources.get('funding', 0)) or 0))
    funding_reserved = max(0, int(commitments.get('funding_reserved', 0) or 0))
    if funding > max(0, money - funding_reserved):
        reasons.append('funding')

    requested_seeds = requires.get('seeds') or {}
    available_seeds = resources.get('seeds') or {}
    reserved_seeds = commitments.get('seed_reserved') or {}
    if not isinstance(requested_seeds, dict) or not isinstance(available_seeds, dict) or not isinstance(reserved_seeds, dict):
        reasons.append('seed')
    else:
        for product, count in requested_seeds.items():
            need = max(0, int(count or 0))
            have = max(0, int(available_seeds.get(product, 0) or 0))
            reserved = max(0, int(reserved_seeds.get(product, 0) or 0))
            if need > max(0, have - reserved):
                reasons.append('seed')
                break

    route = requires.get('route')
    if route is not None:
        blocked = commitments.get('blocked_routes', commitments.get('routes', ())) or ()
        if isinstance(blocked, str):
            blocked = (blocked,)
        if route in set(blocked):
            reasons.append('route')

    return tuple(dict.fromkeys(reasons))


@dataclass(frozen=True)
class Candidate:
    action: Any
    source: str
    trajectory_id: str | None
    score: float | None
    exact_match: bool


@dataclass(frozen=True)
class _Record:
    exact_key: str
    product_key: str
    action: Any
    action_key: str
    trajectory_id: str
    order: int


class ContinuationIndex:
    """Deterministic, bounded in-memory S06 continuation index."""

    def __init__(self, *, max_bytes: int = DEFAULT_MAX_BYTES,
                 retrieve_limit: int = DEFAULT_RETRIEVE,
                 quanta: dict[str, int] | None = None):
        self.max_bytes = max(1, int(max_bytes))
        self.retrieve_limit = max(1, min(DEFAULT_RETRIEVE, int(retrieve_limit)))
        self.quanta = dict(DEFAULT_QUANTA if quanta is None else quanta)
        self._records: list[_Record] = []
        self._exact: dict[str, list[int]] = {}
        self._product: dict[str, list[int]] = {}
        self._seen: set[tuple[str, str, str]] = set()
        # Charge the actual empty index-owned graph up front.  Every later record
        # is charged from its decoded Python object graph with an additional
        # safety factor + reserve, so the admission counter is intentionally
        # above the retained structural footprint rather than below it.
        self._admission_bytes = _deep_size((self._records, self._exact,
                                             self._product, self._seen,
                                             self.quanta)) + sys.getsizeof(self)
        if self._admission_bytes > self.max_bytes:
            raise MemoryError('continuation index memory budget below empty index footprint')

    @staticmethod
    def _record_cost(record: _Record, identity: tuple[str, str, str]) -> int:
        structural = _deep_size((record, identity))
        return ADMISSION_RECORD_RESERVE + ADMISSION_SAFETY_FACTOR * structural

    def add(self, state: dict[str, Any], action: Any, trajectory_id: str) -> bool:
        exact_key = exact_state_hash(state)
        product_key = product_quantized_key(state, self.quanta)
        akey = action_key(action)
        trajectory_id = str(trajectory_id)
        identity = (exact_key, akey, trajectory_id)
        if identity in self._seen:
            return False
        action_blob = _stable_json(action)
        # Decode the exact retained representation before admission and charge
        # that object graph, not only its compact JSON bytes.  Nothing is linked
        # into the index until the charge passes.
        record = _Record(exact_key, product_key, json.loads(action_blob), akey,
                         trajectory_id, len(self._records))
        cost = self._record_cost(record, identity)
        if self._admission_bytes + cost > self.max_bytes:
            raise MemoryError('continuation index memory budget exceeded')
        index = len(self._records)
        self._records.append(record)
        self._exact.setdefault(exact_key, []).append(index)
        self._product.setdefault(product_key, []).append(index)
        self._seen.add(identity)
        self._admission_bytes += cost
        return True

    def _history_pool(self, state: dict[str, Any], mode: str) -> list[_Record]:
        exact_key = exact_state_hash(state)
        product_key = product_quantized_key(state, self.quanta)
        if mode == 'exact':
            indices = self._exact.get(exact_key, ())
        elif mode in ('quantized', 'rerank'):
            indices = self._product.get(product_key, ())
        else:
            raise ValueError('mode must be exact, quantized, or rerank')
        # Stable insertion order is the deterministic pre-rank.  Only the first
        # 32 historical continuations reach the optional economic scorer.
        return [self._records[i] for i in indices[:self.retrieve_limit]]

    def retrieve(self, state: dict[str, Any], canonical_actions: Iterable[Any], *,
                 mode: str = 'rerank',
                 legal: Callable[[Any, dict[str, Any]], bool] | None = None,
                 economic_score: Callable[[Any, dict[str, Any]], float] | None = None) -> list[Candidate]:
        """Return canonical union plus bounded eligible historical continuations.

        Canonical actions are authoritative and preserved byte-for-byte in input
        order.  Historical actions are deduplicated against them, rejected on
        explicit commitment collisions, optionally checked for legality, then
        optionally economic-reranked.  The method never chooses a final action.
        """
        exact_key = exact_state_hash(state)
        seen_actions: set[str] = set()
        canonical = []
        for action in canonical_actions:
            key = action_key(action)
            if key in seen_actions:
                continue
            seen_actions.add(key)
            score = float(economic_score(action, state)) if economic_score is not None and mode == 'rerank' else None
            canonical.append(Candidate(action=json.loads(_stable_json(action)), source='canonical',
                                       trajectory_id=None, score=score, exact_match=True))

        history = []
        for record in self._history_pool(state, mode):
            if record.action_key in seen_actions:
                continue
            if collision_reasons(record.action, state):
                continue
            if legal is not None and not bool(legal(record.action, state)):
                continue
            seen_actions.add(record.action_key)
            score = float(economic_score(record.action, state)) if economic_score is not None and mode == 'rerank' else None
            history.append(Candidate(action=json.loads(_stable_json(record.action)), source='history',
                                     trajectory_id=record.trajectory_id, score=score,
                                     exact_match=record.exact_key == exact_key))

        if mode == 'rerank' and economic_score is not None:
            # Rerank candidates by caller-supplied current economic evaluation;
            # ties prefer canonical, then stable action hash.  This is ordering,
            # not promotion: all canonical actions remain in the returned union.
            combined = canonical + history
            return sorted(combined,
                          key=lambda c: (-float(c.score), c.source != 'canonical',
                                         action_key(c.action)))
        return canonical + history

    def stats(self) -> dict[str, int]:
        return {
            'records': len(self._records),
            'exact_buckets': len(self._exact),
            'product_buckets': len(self._product),
            'admission_bytes': self._admission_bytes,
            'max_bytes': self.max_bytes,
            'retrieve_limit': self.retrieve_limit,
        }
