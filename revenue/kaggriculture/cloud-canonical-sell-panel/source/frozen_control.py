# SPDX-License-Identifier: Apache-2.0
"""Exact frozen SELL control exposed without changing its selected source."""
from titan_runtime import Features, TitanAgent

_INSTANCE = None


def agent(observation, configuration=None):
    global _INSTANCE
    step = observation.get("step")
    if step is None:
        step = int(observation["day"]) * int((configuration or {}).get("turnsPerDay", 24)) + int(observation["hour"])
    if _INSTANCE is None or int(step) == 0:
        _INSTANCE = TitanAgent(Features(consumer="frozen", seed=False))
    return _INSTANCE.act(observation, configuration)
