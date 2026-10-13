# SPDX-License-Identifier: Apache-2.0
"""Submission-compatible current-TITAN carrier plus final prefix rescue."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys

from market_prefix_rescue import rescue_market_prefix
from source_guard import verify_canonical_carrier

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
DIAGNOSTIC_KEY = "__titan_market_prefix_realized__"
_BASE_MODULE = None


def _load_base():
    global _BASE_MODULE
    if _BASE_MODULE is not None:
        return _BASE_MODULE
    verify_canonical_carrier()
    path = LAB / "main.py"
    name = "_sol_realizer_canonical_titan_base"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load canonical TITAN base at {path}")
    module = importlib.util.module_from_spec(spec)
    old_path = list(sys.path)
    try:
        sys.path.insert(0, str(LAB))
        sys.modules[name] = module
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    finally:
        sys.path[:] = old_path
    _BASE_MODULE = module
    return module


def _candidate_action(observation, configuration=None):
    action = _load_base().agent(observation, configuration)
    output, report = rescue_market_prefix(action, configuration)
    if report.get("syntactic_changed") is True:
        report = dict(report)
        report["step"] = int(observation.get("step", -1))
        report["player"] = int(observation.get("player", -1))
    return output, report


def agent(observation, configuration=None):
    """Production entrypoint.  Diagnostic metadata never reaches the engine."""

    output, _ = _candidate_action(observation, configuration)
    return output


def instrumented_agent(observation, configuration=None):
    """Evidence entrypoint; the runner strips this marker pre-interpreter."""

    output, report = _candidate_action(observation, configuration)
    if report.get("syntactic_changed") is not True:
        return output
    marked = deepcopy(output)
    marked[DIAGNOSTIC_KEY] = report
    return marked
