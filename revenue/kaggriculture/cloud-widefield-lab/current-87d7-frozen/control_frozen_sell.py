#!/usr/bin/env python3
"""Exact current-package frozen SELL control without seed/funding increments."""
from __future__ import annotations

_INSTANCE = None


def agent(observation, configuration=None):
    global _INSTANCE
    from titan_runtime import TitanAgent, Features
    step = observation.get("step")
    if step is None:
        cfg = dict(configuration or {})
        step = int(observation["day"]) * int(cfg.get("turnsPerDay", 24)) + int(observation["hour"])
    if _INSTANCE is None or int(step) == 0:
        _INSTANCE = TitanAgent(Features(
            consumer="frozen",
            seed=False,
            funding=False,
            committed=False,
            terminal_route=False,
            redundant_hire=False,
            terminal_history=False,
            budget_seconds=1.0,
            reserve_seconds=0.01,
        ))
    return _INSTANCE.act(observation, configuration)
