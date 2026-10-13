"""Frozen local/reference-store identity for pressure-verifier test injection.

This module deliberately owns the snapshot outside ``core`` so reloading the core
module cannot rebuild verifier authority from caller-mutated facade globals.  It is
an internal compatibility/test seam only; production stores never qualify.
"""
from __future__ import annotations

from pathlib import Path

from .stores import FileLeaseStore


_LOCAL_REFERENCE_ACQUIRE_METHODS = (
    "get_active",
    "get_outcome",
    "create_active",
    "_read",
    "_create",
    "_org_lock",
    "_generation",
)
_LOCAL_REFERENCE_PROTECTED_CLASS_NAMES = _LOCAL_REFERENCE_ACQUIRE_METHODS + (
    "root",
    "active",
    "outcomes",
    "__dict__",
    "__getattribute__",
    "__setattr__",
    "__getattr__",
)
_LOCAL_REFERENCE_BASE_FORBIDDEN_NAMES = (
    "root",
    "active",
    "outcomes",
    "__getattribute__",
    "__setattr__",
    "__getattr__",
)


def _build_local_reference_checker():
    """Freeze the exact local-reference acquire implementation."""
    reference_store_type = FileLeaseStore
    concrete_path_type = type(Path("."))
    acquire_names = tuple(_LOCAL_REFERENCE_ACQUIRE_METHODS)
    protected_names = frozenset(_LOCAL_REFERENCE_PROTECTED_CLASS_NAMES)
    base_forbidden_names = frozenset(_LOCAL_REFERENCE_BASE_FORBIDDEN_NAMES)
    reference_dict = type.__getattribute__(reference_store_type, "__dict__")
    acquire_impls = tuple((name, reference_dict[name]) for name in acquire_names)

    def resolve_raw(mro, name):
        for layer in mro:
            layer_dict = type.__getattribute__(layer, "__dict__")
            if name in layer_dict:
                return layer_dict[name]
        return None

    def mechanically_local_reference_store(store):
        cls = type(store)
        mro = type.__getattribute__(cls, "__mro__")
        try:
            reference_index = mro.index(reference_store_type)
        except ValueError:
            return False

        current_reference_dict = type.__getattribute__(reference_store_type, "__dict__")
        if any(name in current_reference_dict for name in base_forbidden_names):
            return False
        for name, expected in acquire_impls:
            if current_reference_dict.get(name) is not expected:
                return False

        for layer in mro[:reference_index]:
            layer_dict = type.__getattribute__(layer, "__dict__")
            if any(name in layer_dict for name in protected_names):
                return False

        try:
            instance_dict = object.__getattribute__(store, "__dict__")
        except AttributeError:
            return False
        if any(name in instance_dict for name in acquire_names):
            return False

        for name, expected in acquire_impls:
            if resolve_raw(mro, name) is not expected:
                return False

        root = instance_dict.get("root")
        active = instance_dict.get("active")
        outcomes = instance_dict.get("outcomes")
        if not all(type(value) is concrete_path_type for value in (root, active, outcomes)):
            return False
        if active != root / "active" or outcomes != root / "outcomes":
            return False
        return True

    return (
        mechanically_local_reference_store,
        reference_store_type,
        concrete_path_type,
        acquire_impls,
    )


(
    _LOCAL_REFERENCE_CHECKER,
    _LOCAL_REFERENCE_STORE_TYPE,
    _LOCAL_REFERENCE_PATH_TYPE,
    _LOCAL_REFERENCE_ACQUIRE_IMPLS,
) = _build_local_reference_checker()
del _build_local_reference_checker


def mechanically_local_reference_store(store):
    """Diagnostic view of the frozen checker used by ``core.acquire_lease``."""
    return _LOCAL_REFERENCE_CHECKER(store)
