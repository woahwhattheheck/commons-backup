# SPDX-License-Identifier: Apache-2.0
"""Shadow/candidate gate for the canonical V4 W1 and H1 harvest lanes.

The gate never calls a producer.  It consumes the exact action already returned by
canonical V4, evaluates the landed W1 capacity-safe transform and the preserved H1
terminal theorem, and exposes the delta between them.  Only W1 is eligible for
execution by ``apply_candidate``; H1 remains shadow-only until it has an independent
capacity/monetization proof.
"""
from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _actor_rows(action):
    if not isinstance(action, dict):
        return None
    farmer = action.get("farmer")
    hands = action.get("hands")
    if not isinstance(farmer, list) or not isinstance(hands, list):
        return None
    if any(not isinstance(row, list) for row in hands):
        return None
    return [farmer] + list(hands)


def _changed_actor_indices(before, after):
    left, right = _actor_rows(before), _actor_rows(after)
    if left is None or right is None or len(left) != len(right):
        return []
    return [index for index, (a, b) in enumerate(zip(left, right)) if a != b]


class HarvestProbe:
    """Evaluate W1 and H1 against one already-returned canonical action."""

    def __init__(self, workspace: Path | None = None):
        workspace = (workspace or Path(__file__).resolve().parents[2]).resolve()
        w1_path = workspace / "repairs/gameplay/w1-capacity-subset/r04_dead_water_harvest.py"
        h1_path = workspace / "repairs/gameplay/h1-terminal-harvest/r04_h1_terminal_harvest.py"
        if not w1_path.is_file() or not h1_path.is_file():
            raise FileNotFoundError("canonical W1/H1 donor source missing")
        self.w1_path = w1_path
        self.h1_path = h1_path
        self.w1 = _load("_v4_harvest_gate_w1", w1_path)
        self.h1 = _load("_v4_harvest_gate_h1", h1_path)
        if hasattr(self.w1, "reset"):
            self.w1.reset()
        if hasattr(self.h1, "reset"):
            self.h1.reset()

    def inspect(self, observation, configuration, action):
        """Return counterfactual reachability without mutating ``action``."""
        if not isinstance(action, dict) or _actor_rows(action) is None:
            return {
                "valid_action": False,
                "w1_changed": False,
                "h1_changed": False,
                "h1_only": False,
                "w1_actor_indices": [],
                "h1_actor_indices": [],
            }
        original = deepcopy(action)
        w1_out = self.w1.apply_dead_water_harvest(
            observation, deepcopy(action), configuration, enabled=True
        )
        h1_out = self.h1.apply_h1_terminal_harvest(
            deepcopy(action), observation, configuration, enabled=True
        )
        w1_changed = w1_out != original
        h1_changed = h1_out != original
        return {
            "valid_action": True,
            "w1_changed": w1_changed,
            "h1_changed": h1_changed,
            "h1_only": h1_changed and not w1_changed,
            "w1_actor_indices": _changed_actor_indices(original, w1_out),
            "h1_actor_indices": _changed_actor_indices(original, h1_out),
            "w1_action": w1_out if w1_changed else None,
            "h1_action": h1_out if h1_changed else None,
        }

    def apply_candidate(self, observation, configuration, action):
        """Execute only the stronger W1 capacity-safe candidate."""
        return self.w1.apply_dead_water_harvest(
            observation, action, configuration, enabled=True
        )

    def reports(self):
        return {
            "w1": self.w1.get_report() if hasattr(self.w1, "get_report") else None,
            "h1": self.h1.get_report() if hasattr(self.h1, "get_report") else None,
        }
