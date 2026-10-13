# SPDX-License-Identifier: Apache-2.0
"""Read-only boundary observer for the canonical current TITAN entrypoint.

This is an offline evaluator adapter, NOT a competition submission or controller.
The existing agent receives the original observation/configuration objects, runs
once with its own unchanged clocks, and returns the identical output object.
Observation adds time; compare full official-engine traces to uninstrumented
controls before treating a census as source/trajectory-equivalent.
"""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import MethodType

STAGES = ("A", "B", "C", "D")
DIAGNOSTICS = ("status", "fallback_stage", "entrypoint_guard", "operating_stock",
               "feed_stock", "early_capital", "market_pressure", "crop_release",
               "crop_release_action", "elapsed_seconds", "parent_calls")


def capture(action, diagnostics, configuration):
    """Detach observations; do not normalize, filter, or rearrange raw orders."""
    raw = action.get("market", []) if isinstance(action, dict) else []
    limit = max(1, int(configuration.get("maxMarketOrdersPerTurn", 10)))
    return {"action": deepcopy(action),
            "executable_prefix": deepcopy(raw[:limit] if isinstance(raw, list) else []),
            "market_limit": limit,
            "diagnostics": deepcopy({key: diagnostics[key] for key in DIAGNOSTICS
                                     if key in diagnostics})}


class Collector:
    def __init__(self):
        self.row = None
        self.instance = None

    def begin(self, observation, configuration):
        tpd = int(configuration.get("turnsPerDay", 24))
        step = observation.get("step")
        if step is None:
            step = int(observation["day"]) * tpd + int(observation["hour"])
        self.instance = None
        self.row = {"step": int(step), "seat": int(observation["player"]),
                    "day": int(observation.get("day", int(step) // tpd)),
                    "hour": int(observation.get("hour", int(step) % tpd)),
                    "stages": {}, "capture_errors": []}

    def observe(self, stage, instance, configuration, action):
        self.instance = instance
        try:
            if self.row is None:
                raise ValueError("boundary before callback")
            if stage in self.row["stages"]:
                raise ValueError("duplicate boundary: " + stage)
            self.row["stages"][stage] = capture(action, instance.diagnostics, configuration)
        except Exception as error:
            # Never catch the runtime's BaseException deadline cancellation.
            if self.row is not None:
                self.row["capture_errors"].append(type(error).__name__ + ": " + str(error))

    def finish(self, action, configuration):
        diagnostics = {} if self.instance is None else self.instance.diagnostics
        try:
            self.row["returned"] = capture(action, diagnostics, configuration)
            self.row["all_stages"] = all(stage in self.row["stages"] for stage in STAGES)
            self.row["D_matches_returned"] = (
                "D" in self.row["stages"] and self.row["stages"]["D"]["action"] == action)
        except Exception as error:
            self.row["capture_errors"].append(type(error).__name__ + ": " + str(error))
        return self.row


def attach(instance, collector):
    """Observe methods on this one instance; never call a method twice."""
    operating = instance._operating_stock_selected
    feed = instance._feed_stock_selected
    capital_and_pressure = instance._early_capital_selected

    def observed_operating(self, obs, cfg, selected):
        collector.observe("A", self, cfg, selected)
        return operating(obs, cfg, selected)

    def observed_feed(self, obs, cfg, selected):
        # _finish_production has already applied crop/returned-action guards.
        collector.observe("B", self, cfg, selected)
        output = feed(obs, cfg, selected)
        collector.observe("C", self, cfg, output)
        return output

    def observed_capital(self, obs, cfg, selected):
        # This saved bound method is FinalPressureAgent's override, not merely
        # TitanAgent's earlier capital method. D is AFTER final pressure.
        output = capital_and_pressure(obs, cfg, selected)
        collector.observe("D", self, cfg, output)
        return output

    instance._operating_stock_selected = MethodType(observed_operating, instance)
    instance._feed_stock_selected = MethodType(observed_feed, instance)
    instance._early_capital_selected = MethodType(observed_capital, instance)
    collector.instance = instance
    return instance


_COLLECTOR = Collector()
_ENTRY = None
_OUTPUT = None


def setup(root, output):
    global _ENTRY, _OUTPUT
    root = Path(root).resolve(strict=True)
    output = Path(output).resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    spec = importlib.util.spec_from_file_location("_e3_exact_canonical_entrypoint", root / "main.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    original = module._new_instance

    def observed_new_instance(*args, **kwargs):
        return attach(original(*args, **kwargs), _COLLECTOR)

    module._new_instance = observed_new_instance
    _ENTRY = module
    _OUTPUT = output.open("x", encoding="utf-8")


def agent(observation, configuration=None):
    cfg = {} if configuration is None else configuration
    _COLLECTOR.begin(observation, cfg)
    # Root import occurs at evaluator worker startup, like the baseline; no
    # TitanAgent/controller construction is moved outside the canonical clock.
    result = _ENTRY.agent(observation, configuration)
    if _ENTRY._INSTANCE is not None:
        _COLLECTOR.instance = _ENTRY._INSTANCE
    row = _COLLECTOR.finish(result, cfg)
    _OUTPUT.write(json.dumps(row, allow_nan=False, separators=(",", ":")) + "\n")
    _OUTPUT.flush()
    return result

