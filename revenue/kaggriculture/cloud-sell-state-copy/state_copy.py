# SPDX-License-Identifier: Apache-2.0
"""Optional faster state copying for the exact frozen SELL implementation.

The scheduler's function code, parent, optimizer, current state and evidence are
not changed. Only three functions receive private globals with this copy helper.
Original modules and the standard-library copy module are never patched.
"""
from __future__ import annotations

import copy
from functools import lru_cache, update_wrapper
from hashlib import sha256
from pathlib import Path
from types import FunctionType, ModuleType, SimpleNamespace
from typing import Any

FROZEN_SHA256 = '32c8610c9827d1686a6f831e2c4b6af4c00d32d2aa04dcf25699d976d6d97dd9'
_ATOMIC = frozenset((type(None), bool, int, float, complex, str, bytes))


class _NotPlain(Exception):
    """Internal signal: use normal deepcopy for the entire object instead."""


def _plain(value: Any, memo: dict[int, Any]) -> Any:
    kind = type(value)
    if kind in _ATOMIC:
        return value
    identity = id(value)
    if identity in memo:
        return memo[identity]
    if kind is list:
        result: list[Any] = []
        memo[identity] = result
        result.extend(_plain(item, memo) for item in value)
        return result
    if kind is dict:
        mapped: dict[Any, Any] = {}
        memo[identity] = mapped
        for key, item in value.items():
            if type(key) not in _ATOMIC:
                raise _NotPlain
            mapped[key] = _plain(item, memo)
        return mapped
    raise _NotPlain


def deepcopy_state(value: Any, memo: dict[int, Any] | None = None) -> Any:
    """Copy plain state graphs; preserve normal semantics for all other inputs.

    Plain means exact built-in dict/list containers and immutable scalar leaves.
    Container subclasses, tuples, sets, custom keys, custom copy hooks and other
    objects use stdlib deepcopy for the WHOLE original graph, not a partial
    hybrid copy. An explicitly supplied memo always uses stdlib deepcopy too.
    The fast path preserves shared container identities and dict/list cycles.
    Unsupported-type detection runs no user hooks before the single fallback.
    """
    if memo is not None:
        return copy.deepcopy(value, memo)
    try:
        return _plain(value, {})
    except _NotPlain:
        return copy.deepcopy(value)


def _bind(function: Any, namespace: dict[str, Any]) -> Any:
    rebound = FunctionType(function.__code__, namespace, function.__name__,
                           function.__defaults__, function.__closure__)
    rebound.__kwdefaults__ = function.__kwdefaults__
    update_wrapper(rebound, function)
    return rebound


@lru_cache(maxsize=8)
def scheduler_class(scheduler: ModuleType) -> type:
    """Return a private-copy subclass of the pinned original scheduler class.

    This is a version-specific adaptation seam, not an arbitrary agent wrapper.
    A different source version needs its own explicit correspondence work.
    Construction imports/executes no new source and creates no controller.
    """
    if sha256(Path(scheduler.__file__).read_bytes()).hexdigest() != FROZEN_SHA256:
        raise ValueError('Use the documented frozen SELL module')
    original = scheduler.SellScheduler
    functions = (scheduler.post_units, original.act, original.receipt_profile)
    if any(fn.__globals__ is not scheduler.__dict__ for fn in functions):
        raise ValueError('Use the original unmodified function namespace')
    # Forward the remaining copy attributes unchanged. This object is private;
    # assigning its deepcopy attribute cannot change the imported copy module.
    private_copy = SimpleNamespace(**vars(copy))
    private_copy.deepcopy = deepcopy_state
    namespace = dict(scheduler.__dict__)
    namespace['copy'] = private_copy
    namespace['post_units'] = _bind(scheduler.post_units, namespace)
    variant = type('StateCopySellScheduler', (original,), {
        '__module__': __name__,
        '__doc__': 'Frozen scheduler function bodies with private plain-state copying.',
        'act': _bind(original.act, namespace),
        'receipt_profile': _bind(original.receipt_profile, namespace),
    })
    return variant


def fork_scheduler(actor: Any, scheduler: ModuleType) -> Any:
    """Fork an exact frozen actor and retain every instance field.

    Used as evaluate_sell_tails(..., fork_scheduler=...) for optional speculative
    evaluation. It does not call the actor, initialize a new parent or mutate the
    live instance. Custom scheduler subclasses are not silently flattened.
    """
    variant = scheduler_class(scheduler)
    if type(actor) not in (scheduler.SellScheduler, variant):
        raise ValueError('Custom actors require their own full-state fork contract')
    cloned = copy.deepcopy(actor)
    cloned.__class__ = variant
    return cloned
