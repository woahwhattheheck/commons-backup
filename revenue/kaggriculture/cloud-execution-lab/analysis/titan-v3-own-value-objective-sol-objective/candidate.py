# SPDX-License-Identifier: Apache-2.0
"""TITAN V3 candidate: canonical runtime with one SELL-objective overlay."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
LAB = HERE.parent.parent
if str(LAB) not in sys.path:
    sys.path.insert(0, str(LAB))

_patch_spec = importlib.util.spec_from_file_location(
    "_titan_v3_own_value_objective_patch", HERE / "own_value_objective.py"
)
if _patch_spec is None or _patch_spec.loader is None:
    raise ImportError("cannot load own-value objective overlay")
_patch = importlib.util.module_from_spec(_patch_spec)
_patch_spec.loader.exec_module(_patch)
INSTALL_RECEIPT = _patch.install(expected_root=LAB)

import main as _canonical_main


def agent(observation, configuration=None):
    """Delegate unchanged action construction to the canonical TITAN entrypoint."""
    return _canonical_main.agent(observation, configuration)
