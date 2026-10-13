# SPDX-License-Identifier: Apache-2.0
"""Additive P02 evaluation entrypoint; canonical ``main.py`` remains untouched."""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path

from land_unlock_runtime import LandUnlockOverlay
from titan_runtime import Features, TitanAgent, load

_INSTANCE = None


class P02TitanAgentMixin:
    """Candidate-only composition after the canonical completed-action boundary."""

    def _p02_initialize(self, *, mode="both"):
        self.land_unlock_overlay = LandUnlockOverlay(mode=mode)

    def _p02_finish(self, observation, configuration, returned):
        before = deepcopy(returned)
        result, report = self.land_unlock_overlay.apply(
            self, observation, configuration or {}, returned)
        self.diagnostics["land_unlock_timing"] = report
        self.diagnostics["land_unlock_events"] = deepcopy(
            self.land_unlock_overlay.events)
        trace_dir = os.environ.get("TITAN_P02_TRACE_DIR")
        step = observation.get("step")
        if step is None:
            step = (int(observation["day"]) * int((configuration or {}).get("turnsPerDay", 24))
                    + int(observation["hour"]))
        step = int(step)
        current_events = [event for event in self.land_unlock_overlay.events
                          if int(event.get("step", -1)) == step]
        if trace_dir and (report.get("changed") or current_events):
            path = Path(trace_dir)
            path.mkdir(parents=True, exist_ok=True)
            payload = {
                "step": step, "player": int(observation["player"]),
                "route": getattr(getattr(self, "controller", None), "cur", None),
                "status": self.diagnostics.get("status"),
                "reason": report.get("reason"),
                "before_market": before.get("market", []),
                "after_market": result.get("market", []),
                "pending": report.get("pending"), "events": current_events,
            }
            with (path / f"{os.getpid()}.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(payload, sort_keys=True) + "\n")
        return result


class P02TitanAgent(P02TitanAgentMixin, TitanAgent):
    def __init__(self, features=None, *, fourth_quadrant_admission=None):
        super().__init__(features, fourth_quadrant_admission=fourth_quadrant_admission)
        self._p02_initialize(mode="both")

    def _finish_production(self, observation, returned, cfg=None):
        result = super()._finish_production(observation, returned, cfg)
        return self._p02_finish(observation, cfg or {}, result)


def _new_instance(root, feature_data):
    features = Features(**feature_data)
    admission = None
    if features.fourth_quadrant:
        source = root / "funded_payback.py"
        if not source.is_file():
            source = root / "../cloud-economic-stress/funded_payback/funded_payback.py"
        module = load("_titan_p02_funded_payback", source, cache=True)
        adapter = load("_titan_p02_funded_payback_runtime",
                       root / "funded_payback_runtime.py", cache=True)
        admission = adapter.make_admission(module.FundedPaybackAdmission)(
            seconds=features.budget_seconds, max_proposals=24)
    return P02TitanAgent(features, fourth_quadrant_admission=admission)


def agent(observation, configuration=None):
    global _INSTANCE
    import json
    from pathlib import Path
    import sys
    import time

    entry_started = time.perf_counter()
    cfg = dict(configuration or {})
    path = globals().get("__file__") or cfg.get("__raw_path__")
    if not path:
        raise ValueError("Entrypoint path required")
    root = Path(path).resolve().parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    step = observation.get("step")
    if step is None:
        step = (int(observation["day"]) * int(cfg.get("turnsPerDay", 24))
                + int(observation["hour"]))
    if _INSTANCE is None or int(step) == 0:
        _INSTANCE = _new_instance(
            root, json.loads((root / "TITAN-CONFIG.json").read_text()))
    return _INSTANCE.act(observation, cfg, entry_started=entry_started)
