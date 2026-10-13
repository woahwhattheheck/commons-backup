"""Bind an already imported implementation's functions to a private generation.

This protects saved callables from ordinary subsequent module-name rebinding.
It is not a Python sandbox: code/closure/private-globals replacement, mutation of
captured object internals, and replacement of the installed source are excluded.
"""
from __future__ import annotations

import builtins
from types import FunctionType, ModuleType, SimpleNamespace
from typing import Any


def frozen_functions(module: ModuleType) -> dict[str, FunctionType]:
    if type(module) is not ModuleType:
        raise TypeError("an exact implementation module is required")
    original = vars(module)
    private: dict[str, Any] = dict(original)
    # A separate builtin-name table also avoids adopting later module-table edits.
    private["__builtins__"] = dict(vars(builtins))
    # Snapshot dependency attributes without publishing these snapshots. Public
    # aliases keep the original module objects; mutating an alias binding or a
    # directly referenced dependency function does not rewrite this table.
    for name, value in original.items():
        if type(value) is ModuleType:
            private[name] = SimpleNamespace(**vars(value))
    result: dict[str, FunctionType] = {}
    for name, value in original.items():
        if type(value) is FunctionType and value.__globals__ is original:
            cloned = FunctionType(value.__code__, private, value.__name__,
                                  value.__defaults__, value.__closure__)
            if value.__kwdefaults__ is not None:
                cloned.__kwdefaults__ = dict(value.__kwdefaults__)
            cloned.__annotations__ = dict(value.__annotations__)
            cloned.__doc__ = value.__doc__
            cloned.__qualname__ = value.__qualname__
            private[name] = cloned
            result[name] = cloned
    return result
