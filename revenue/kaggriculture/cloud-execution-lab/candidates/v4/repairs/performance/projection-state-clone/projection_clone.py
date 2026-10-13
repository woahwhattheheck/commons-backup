# SPDX-License-Identifier: Apache-2.0
"""Detached mutable projection graphs; exact builtin containers only.

Unlike JSON normalization, this retains aliases, cycles, dictionary keys and
custom copy hooks. Each top-level call owns a fresh memo unless one is supplied.
Subclasses and foreign leaves go through Python's real deepcopy with that memo.
"""
from copy import deepcopy, _keep_alive

_ATOMIC = frozenset((type(None), bool, int, float, complex, str, bytes))
_MISSING = object()


def clone_projection(value, memo=None):
    """Copy an exact dict/list graph using deepcopy-compatible memo semantics."""
    if memo is None:
        memo = {}
    return _clone(value, memo)


def _clone(value, memo):
    ident = id(value)
    cached = memo.get(ident, _MISSING)
    if cached is not _MISSING:
        return cached
    kind = type(value)
    if kind in _ATOMIC:
        return value
    if kind is list:
        result = []
        memo[ident] = result
        append = result.append
        for item in value:
            append(_clone(item, memo))
    elif kind is dict:
        result = {}
        memo[ident] = result
        for key, item in value.items():
            # RHS is copied before the key, just as in copy._deepcopy_dict.
            result[_clone(key, memo)] = _clone(item, memo)
    else:
        return deepcopy(value, memo)
    _keep_alive(value, memo)
    return result
