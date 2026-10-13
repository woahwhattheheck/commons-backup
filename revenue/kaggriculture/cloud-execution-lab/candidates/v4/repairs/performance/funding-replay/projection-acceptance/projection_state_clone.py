# SPDX-License-Identifier: Apache-2.0
"""Exact built-in graph clone for detached physical-state projections.

Foreign graphs fall back to real deepcopy. The module-level walker avoids a
recursive closure retaining every memo and copied farm until cyclic GC runs.
This experimental helper is not installed in any production runtime.
"""
from __future__ import annotations
from copy import deepcopy
from typing import Any

_ATOMS = frozenset((str, int, float, bool, type(None)))


class _NeedsDeepcopy(Exception):
    pass


def _walk_projection(obj: Any, memo: dict[int, Any], depth: int) -> Any:
    kind = type(obj)
    if kind in _ATOMS:
        return obj
    if kind is not dict and kind is not list:
        raise _NeedsDeepcopy
    identity = id(obj)
    if identity in memo:
        return memo[identity]
    if depth >= 64:
        raise _NeedsDeepcopy
    if kind is list:
        result: Any = []
        memo[identity] = result
        for child in obj:
            result.append(_walk_projection(child, memo, depth + 1))
        return result
    result = {}
    memo[identity] = result
    for key, child in obj.items():
        if type(key) not in _ATOMS:
            raise _NeedsDeepcopy
        result[key] = _walk_projection(child, memo, depth + 1)
    return result


def _discard_partial(memo: dict[int, Any]) -> None:
    # Every value here is a newly allocated exact dict/list, never a borrowed
    # source container. Break only failed fast-path graphs, including cycles.
    for container in memo.values():
        container.clear()
    memo.clear()


def clone_projection_state(value: Any) -> Any:
    """Preserve values, types, order, aliases, cycles and cancellation behavior.

    Independent calls deliberately get independent memos, just as the original
    independent farm/private deepcopy calls do. Foreign values are never walked
    by the fast path. A fallback restarts from the original root with fresh memo.
    """
    memo: dict[int, Any] = {}
    try:
        return _walk_projection(value, memo, 0)
    except _NeedsDeepcopy:
        _discard_partial(memo)
        return deepcopy(value)
    except BaseException:
        _discard_partial(memo)
        raise
