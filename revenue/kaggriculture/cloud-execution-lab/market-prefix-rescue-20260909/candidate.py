# SPDX-License-Identifier: Apache-2.0
"""Default-off TITAN candidate that applies final market-prefix rescue."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys

from market_prefix_rescue import rescue_market_prefix

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DIAGNOSTIC_KEY = "__titan_market_prefix_rescue__"
_BASE_MODULE = None


def _load_base():
    global _BASE_MODULE
    if _BASE_MODULE is not None:
        return _BASE_MODULE
    path = ROOT / "main.py"
    name = "_titan_market_prefix_rescue_canonical_base"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load canonical TITAN base at {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    _BASE_MODULE = module
    return module


def _candidate_action(observation, configuration=None):
    action = _load_base().agent(observation, configuration)
    output, report = rescue_market_prefix(action, configuration)
    if report.get("changed"):
        report = dict(report)
        report["step"] = int(observation.get("step", -1))
        report["player"] = int(observation.get("player", -1))
    return output, report


def agent(observation, configuration=None):
    """Submission-compatible candidate entrypoint; emits no diagnostic fields."""
    output, _ = _candidate_action(observation, configuration)
    return output


def instrumented_agent(observation, configuration=None):
    """Evidence-run entrypoint; the runner strips its marker before the engine."""
    output, report = _candidate_action(observation, configuration)
    if not report.get("changed"):
        return output
    marked = deepcopy(output)
    marked[DIAGNOSTIC_KEY] = report
    return marked
