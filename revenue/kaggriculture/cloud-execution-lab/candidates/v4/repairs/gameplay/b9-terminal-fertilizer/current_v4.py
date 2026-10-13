#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Current-V4 boundary adapter for recovered B9 terminal fertilizer semantics.

This module is deliberately not an agent wrapper and does not call a producer.
A caller supplies the exact action that would otherwise be returned.  The helper
is default-OFF and only runs for a successfully completed producer action.

Composition contract:
* call after current market/funding/pressure guards have finished;
* call before SpatialTempo/history/receipt state is committed;
* never call it to start optional work on a deadline fallback;
* keep the recovered source module adjacent and byte-pinned by the composer.

The general idle-fertilizer planner remains a separate authority.  This helper
owns only the historical terminal seam: literal represented-worker PASS at
steps 716/717 and same-episode fertilizer sale ordering at step 718.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_DONOR_PATH = Path(__file__).with_name("terminal_fertilizer.py")
_DONOR_BLOB = "ed8d6923541e700c3a0ae4b93695bbd56455a3b6"


def _load_donor():
    if not _DONOR_PATH.is_file():
        raise RuntimeError("missing recovered B9 donor")
    spec = importlib.util.spec_from_file_location("_titan_b9_recovered", _DONOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load recovered B9 donor")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_DONOR = _load_donor()


class CurrentV4TerminalFertilizer:
    """Stateful final-return transform with explicit completion/enable gates."""

    def __init__(self):
        self._state = {}
        self.last_report = {"changed": False, "reason": "not_run"}

    def _identity(self, action, reason, *, clear=False):
        if clear:
            self._state.clear()
        self.last_report = {"changed": False, "reason": reason}
        return action

    def apply(self, observation, action, configuration=None, *,
              enabled=False, completed=False):
        if enabled is not True:
            return self._identity(action, "disabled", clear=True)
        if not completed:
            return self._identity(action, "producer_not_completed", clear=True)

        cap = _DONOR._executable_market_cap(configuration)
        if not _DONOR._standard_terminal_timing(configuration) or cap is None:
            return self._identity(action, "unsupported_configuration", clear=True)

        try:
            step = observation["step"]
            player = observation["player"]
            farms = observation["farms"]
        except (KeyError, TypeError):
            return self._identity(action, "malformed_observation", clear=True)

        if (not _DONOR._exact_int(step)
                or not 0 <= step < _DONOR.EPISODE_STEPS
                or not _DONOR._exact_int(player)
                or not isinstance(farms, list)
                or not 0 <= player < len(farms)
                or not _DONOR._valid_selected_farm_envelope(farms[player])):
            return self._identity(action, "malformed_observation", clear=True)

        state = self._state.get(player)
        if state is None or step <= state["last_step"]:
            state = self._state[player] = {
                "last_step": -1,
                "collected": False,
                "collect_steps": [],
            }
        state["last_step"] = step

        if step in _DONOR.COLLECT_STEPS:
            result, changed = _DONOR._collect_passes(observation, action)
            if changed:
                state["collected"] = True
                state["collect_steps"].append(step)
                self.last_report = {
                    "changed": True,
                    "reason": "terminal_fertilizer_collected",
                    "step": step,
                    "player": player,
                }
                return result
            self.last_report = {
                "changed": False,
                "reason": "no_eligible_literal_pass",
                "step": step,
                "player": player,
            }
            return action

        if step == _DONOR.TERMINAL_STEP and state["collected"]:
            result = _DONOR._trail_fertilizer_sales(action, cap)
            changed = result is not action
            self.last_report = {
                "changed": changed,
                "reason": ("terminal_fertilizer_sales_trailed"
                           if changed else "terminal_sale_order_already_safe"),
                "step": step,
                "player": player,
                "collect_steps": list(state["collect_steps"]),
                "executable_market_cap": cap,
            }
            return result

        self.last_report = {
            "changed": False,
            "reason": "outside_terminal_seam",
            "step": step,
            "player": player,
        }
        return action


def apply_terminal_fertilizer(transform, observation, action, configuration=None, *,
                              enabled=False, completed=False):
    if not isinstance(transform, CurrentV4TerminalFertilizer):
        raise TypeError("transform must be CurrentV4TerminalFertilizer")
    return transform.apply(
        observation, action, configuration,
        enabled=enabled, completed=completed,
    )
