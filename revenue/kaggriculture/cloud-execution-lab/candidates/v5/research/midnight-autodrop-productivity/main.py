# SPDX-License-Identifier: Apache-2.0
"""Source-tree executable wrapper for the V5 midnight auto-drop research candidate."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_parent = _load("_titan_v5_midnight_parent", ROOT / "main.py")
_candidate = _load("_titan_v5_midnight_salvage", HERE / "midnight_salvage.py")

_STATS = {
    "schema": _candidate.SCHEMA,
    "calls": 0,
    "engagements": 0,
    "first_engagement": None,
    "last_report": None,
}


def diagnostics():
    return deepcopy(_STATS)


def reset_diagnostics():
    _STATS.update(calls=0, engagements=0, first_engagement=None, last_report=None)


def agent(observation, configuration=None):
    action = _parent.agent(observation, configuration)
    candidate_action, report = _candidate.apply(observation, action, configuration)
    _STATS["calls"] += 1
    _STATS["last_report"] = deepcopy(report)
    if report.get("changed") is True:
        _STATS["engagements"] += 1
        if _STATS["first_engagement"] is None:
            _STATS["first_engagement"] = deepcopy(report)
    return candidate_action
