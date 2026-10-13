# SPDX-License-Identifier: Apache-2.0
"""Canonical TITAN carrier with only route-reference echo normalization enabled."""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import types

HERE = Path(__file__).resolve().parent
LAB = HERE.parent.parent
if str(LAB) not in sys.path:
    sys.path.insert(0, str(LAB))

EXPECTED_MAIN_BLOB = "4a8cf7bcda1f0fea231a144692cb84a779a9e73e"
EXPECTED_FROZEN_SELECTED_BLOB = "fc7baf5c179818a55037f6a61d92984d81d1a21c"


def _git_blob_sha1(data: bytes) -> str:
    header = b"blob " + str(len(data)).encode("ascii") + b"\0"
    return hashlib.sha1(header + data).hexdigest()


def _pinned_bytes(path: Path, expected_blob: str) -> bytes:
    data = path.read_bytes()
    actual = _git_blob_sha1(data)
    if actual != expected_blob:
        raise ImportError(
            f"{path.name} blob mismatch: expected {expected_blob}, got {actual}"
        )
    return data


# Verify the exact canonical consumer module before importing it.  Existing
# imports are accepted only when they resolve to the same pinned path/bytes.
_pinned_bytes(LAB / "frozen_selected.py", EXPECTED_FROZEN_SELECTED_BLOB)
import frozen_selected as canonical_frozen_selected

if Path(canonical_frozen_selected.__file__).resolve() != (LAB / "frozen_selected.py").resolve():
    raise ImportError("frozen_selected resolved outside the pinned TITAN lab")

from route_reference_echo import RouteEchoGuardedFrozenSelected


def _load_canonical_main():
    """Execute one read of the exact canonical entrypoint in a private module."""
    name = "_titan_canonical_main_sol_accrual"
    path = LAB / "main.py"
    data = _pinned_bytes(path, EXPECTED_MAIN_BLOB)
    module = types.ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = ""
    sys.modules[name] = module
    try:
        exec(compile(data, str(path), "exec"), module.__dict__)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


_CANONICAL_MAIN = _load_canonical_main()
_CANONICAL_NEW_INSTANCE = _CANONICAL_MAIN._new_instance


def _new_instance(root, feature_data):
    """Retain canonical FinalPressure behavior and specialize lazy SELL init."""
    prototype = _CANONICAL_NEW_INSTANCE(root, feature_data)
    canonical_type = type(prototype)

    class RouteEchoFinalPressureAgent(canonical_type):
        def _initialize(self):
            super()._initialize()
            if self.features.consumer != "frozen":
                return
            consumer = self.consumer
            if not isinstance(consumer, canonical_frozen_selected.FrozenSelected):
                raise TypeError("canonical frozen consumer identity mismatch")
            # The adapter adds only a transform override and no instance fields.
            # Reclassifying the already-wired consumer preserves controller,
            # production, spatial, budget, history, and reconstruction identity.
            consumer.__class__ = RouteEchoGuardedFrozenSelected
            if self.consumer.controller is not self.controller:
                raise RuntimeError("consumer/controller identity changed during binding")

    RouteEchoFinalPressureAgent.__name__ = "RouteEchoFinalPressureAgent"
    RouteEchoFinalPressureAgent.__qualname__ = "RouteEchoFinalPressureAgent"
    return RouteEchoFinalPressureAgent(
        prototype.features,
        fourth_quadrant_admission=prototype._quadrant_admission,
    )


# This is a private copy of main.py, so replacing its construction seam cannot
# affect canonical imports or another evaluator actor in the same interpreter.
_CANONICAL_MAIN._new_instance = _new_instance


def agent(observation, configuration=None):
    """Delegate the complete call to the exact canonical deadline carrier."""
    return _CANONICAL_MAIN.agent(observation, configuration)
