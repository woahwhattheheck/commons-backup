# SPDX-License-Identifier: Apache-2.0
"""Canonical-entrypoint carrier for the isolated KESTREL Titan V3 candidate.

The exported ``agent`` is the canonical source-tree entrypoint function itself.
Only its construction hook is replaced, and that hook asks canonical
``main.py::_new_instance`` to build its own local ``FinalPressureAgent`` over
``KestrelTitanAgent`` instead of over the predecessor ``TitanAgent``.  The
whole-call deadline, fallback, reconstruction, finalization, and final-pressure
ordering therefore remain canonical byte-for-byte.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import threading
from types import ModuleType
from typing import Any

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[1]
for _source in (_HERE, _ROOT):
    if str(_source) not in sys.path:
        sys.path.insert(0, str(_source))


def _load_exact(name: str, path: Path) -> ModuleType:
    """Load one exact source path, replacing a stale same-name module."""
    target = path.resolve()
    existing = sys.modules.get(name)
    existing_path = getattr(existing, "__file__", None)
    if existing_path is not None and Path(existing_path).resolve() == target:
        return existing

    spec = importlib.util.spec_from_file_location(name, target)
    if spec is None or spec.loader is None:
        raise ImportError(f"unable to load {target}")
    module = importlib.util.module_from_spec(spec)
    prior = sys.modules.get(name)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        if prior is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = prior
        raise
    return module


# Resolve candidate-local imports before the runtime class is loaded.  The
# public aliases are intentional: the candidate modules use these exact import
# names, and an evaluator may load this entrypoint with the candidate directory
# absent from sys.path.
_load_exact("kestrel_early_capital", _HERE / "kestrel_early_capital.py")
_load_exact("lockstep_early_capital", _HERE / "lockstep_early_capital.py")
_CANDIDATE_RUNTIME = _load_exact(
    "_kestrel_candidate_runtime",
    _HERE / "candidate_runtime.py",
)
_CANONICAL = _load_exact("_kestrel_canonical_main", _ROOT / "main.py")
_CANONICAL_NEW_INSTANCE = _CANONICAL._new_instance
_FACTORY_LOCK = threading.RLock()


def _new_instance(root: Path, feature_data: dict[str, Any]):
    """Create canonical FinalPressureAgent directly over KestrelTitanAgent.

    Canonical ``_new_instance`` imports ``TitanAgent`` inside the function and
    defines the final-pressure subclass locally.  A tightly scoped symbol
    substitution lets that unchanged factory create the required MRO.  The
    substitution is restored even when construction raises.  Source/module
    drift fails closed rather than silently constructing a mixed runtime.
    """
    import titan_runtime

    candidate_base = _CANDIDATE_RUNTIME.KestrelTitanAgent
    predecessor_base = candidate_base.__mro__[1]
    with _FACTORY_LOCK:
        if titan_runtime.TitanAgent is not predecessor_base:
            raise RuntimeError("canonical TitanAgent identity drift")
        titan_runtime.TitanAgent = candidate_base
        try:
            instance = _CANONICAL_NEW_INSTANCE(root, feature_data)
        finally:
            titan_runtime.TitanAgent = predecessor_base

    mro = type(instance).__mro__
    if len(mro) < 3 or mro[1] is not candidate_base or mro[2] is not predecessor_base:
        raise RuntimeError("canonical FinalPressureAgent carrier was not constructed")
    return instance


# Delegate the complete public entrypoint.  Its function globals remain the
# canonical module, so _INSTANCE, outer timer ownership, fallback selection,
# diagnostics, and interrupted-instance destruction are exactly canonical.
_CANONICAL._new_instance = _new_instance
agent = _CANONICAL.agent


__all__ = ["agent"]
