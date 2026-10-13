# SPDX-License-Identifier: MIT
"""T11 runtime: frozen T08 SELL with a bounded rule-cycle transform."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from cycle import RuleCycleTransform

HERE = Path(__file__).resolve().parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = _load("t11_frozen_sell_parent", HERE.parent / "cloud-titan-composition/arms/sell.py")
_transform = None


def agent(observation, configuration=None):
    global _transform
    if _transform is None or int(observation.get("step", 0)) == 0:
        _transform = RuleCycleTransform()
    selected = base.agent(observation)
    return _transform.transform(observation, configuration or {}, selected)
