# SPDX-License-Identifier: Apache-2.0
"""Exact-current TITAN with the existing certified final-step settlement.

The carrier installs the existing T01 certificate at the source's intended
returned-action seam: immediately after current ``FinalPressureAgent`` finishes
``_early_capital_selected`` and before ``TitanAgent._finish_production`` commits
its receipt. The seam therefore runs inside canonical ``main.agent`` and its
one-second outer deadline; no post-entrypoint work is added.
"""
from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
from types import MethodType
from typing import Any, Mapping

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
SOURCE = LAB / "candidates" / "v3-terminal-settlement" / "terminal_settlement.py"
BASE_COMMIT = "b986558e41938d34fcb4ab28b08c517be51203dc"

if str(LAB) not in sys.path:
    sys.path.insert(0, str(LAB))


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


_CANONICAL = _load("_sol_settle_current_main", LAB / "main.py")
_ORIGINAL_NEW_INSTANCE = _CANONICAL._new_instance
_SETTLEMENT = None
_LAST_REPORT: dict[str, Any] | None = None


def _settlement_module():
    """Load at first terminal use so the panel charges cold-load wall time."""
    global _SETTLEMENT
    if _SETTLEMENT is None:
        _SETTLEMENT = _load("_sol_settle_terminal_certificate", SOURCE)
    return _SETTLEMENT


def _observed_step(observation: Mapping[str, Any], configuration: Mapping[str, Any]) -> int | None:
    raw = observation.get("step")
    if raw is None:
        try:
            raw = int(observation["day"]) * int(configuration.get("turnsPerDay", 24)) + int(
                observation["hour"]
            )
        except (KeyError, TypeError, ValueError, OverflowError):
            return None
    if isinstance(raw, bool):
        return None
    try:
        step = int(raw)
    except (TypeError, ValueError, OverflowError):
        return None
    return step if step == raw and step >= 0 else None


def _final_executable_step(configuration: Mapping[str, Any]) -> int | None:
    raw = configuration.get("episodeSteps", 720)
    if isinstance(raw, bool):
        return None
    try:
        episode_steps = int(raw)
    except (TypeError, ValueError, OverflowError):
        return None
    if episode_steps != raw or episode_steps < 2:
        return None
    return episode_steps - 2


def last_report() -> dict[str, Any] | None:
    """Return a detached local diagnostic; never participates in game compute."""
    return deepcopy(_LAST_REPORT)


def _install(instance):
    """Install once on one freshly constructed exact-current controller."""
    if getattr(instance, "_sol_settle_installed", False):
        return instance
    original = instance._early_capital_selected

    def early_capital_then_settlement(self, observation, configuration, selected):
        global _LAST_REPORT
        returned = original(observation, configuration, selected)

        # Canonical deadline fallback owns its reserved finalizer window. The
        # current FinalPressureAgent deliberately declines optional transforms
        # on that path, so T01 must preserve the same returned object and stay
        # cold rather than introducing fallback-only activations.
        if (getattr(self, "diagnostics", {}) or {}).get("status") != "completed":
            _LAST_REPORT = None
            return returned

        cfg = dict(configuration or {})
        step = _observed_step(observation, cfg)
        last = _final_executable_step(cfg)
        if step is None or last is None or step != last:
            _LAST_REPORT = None
            return returned

        # Both the cold source load and projection are intentionally inside the
        # canonical action timer. DeadlineExceeded is not caught here: current
        # main.agent retains sole fallback/reset authority.
        from scheduler import post_units

        result, report = _settlement_module().compose_terminal_settlement(
            observation,
            cfg,
            returned,
            project_units=post_units,
        )
        _LAST_REPORT = dict(report)
        diagnostics = dict(getattr(self, "diagnostics", {}) or {})
        diagnostics["terminal_settlement"] = dict(report)
        self.diagnostics = diagnostics
        return result

    instance._early_capital_selected = MethodType(early_capital_then_settlement, instance)
    instance._sol_settle_installed = True
    return instance


def _new_instance(root, feature_data):
    return _install(_ORIGINAL_NEW_INSTANCE(root, feature_data))


# Canonical main.agent resolves this global for every normal construction and
# every post-deadline reconstruction. Only object construction is intercepted;
# the exact current entrypoint, outer timer, and fallback remain authoritative.
_CANONICAL._new_instance = _new_instance


def agent(observation, configuration=None):
    """Run exact-current canonical entrypoint with one in-budget installed seam."""
    global _LAST_REPORT
    _LAST_REPORT = None
    return _CANONICAL.agent(observation, configuration)