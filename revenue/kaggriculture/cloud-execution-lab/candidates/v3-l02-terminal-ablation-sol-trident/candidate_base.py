# SPDX-License-Identifier: Apache-2.0
"""Build exact-current TITAN agents with one isolated L02 ablation arm."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import time
from typing import Any, Callable

from ablation import ARMS, configure_overlay

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
L02 = HERE.parent / "v3-l02-ledger-tranche"


def _load(name: str, path: Path):
    if not path.is_file():
        raise FileNotFoundError(path)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_CANONICAL = _load("_sol_trident_ablation_canonical", LAB / "main.py")
_OVERLAYS: dict[str, Any] = {}
_INSTANCES: dict[str, Any] = {}


def _overlay(arm: str):
    module = _OVERLAYS.get(arm)
    if module is None:
        module = _load(f"_sol_trident_l02_{arm}", L02 / "ledger_tranche.py")
        configure_overlay(module, arm)
        _OVERLAYS[arm] = module
    return module


def make_agent(arm: str) -> Callable[[dict[str, Any], dict[str, Any] | None], Any]:
    if arm not in ARMS:
        raise ValueError(f"unknown arm: {arm}")

    def agent(observation, configuration=None):
        entry_started = time.perf_counter()
        cfg = dict(configuration or {})
        step = observation.get("step")
        if step is None:
            step = int(observation["day"]) * int(cfg.get("turnsPerDay", 24)) + int(observation["hour"])
        instance = _INSTANCES.get(arm)
        if instance is None or int(step) == 0:
            feature_data = json.loads((LAB / "TITAN-CONFIG.json").read_text(encoding="utf-8"))
            instance = _CANONICAL._new_instance(LAB, feature_data)
            _overlay(arm).install(instance)
            _INSTANCES[arm] = instance
        return instance.act(observation, cfg, entry_started=entry_started)

    agent.__name__ = f"agent_{arm}"
    return agent
