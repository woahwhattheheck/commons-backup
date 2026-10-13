# SPDX-License-Identifier: Apache-2.0
"""Optional file-agent joining feed reallocation to the existing TITAN runtime."""
from __future__ import annotations

from feed_reallocation import wrap_titan_agent


def make_agent(features=None):
    from titan_runtime import Features, TitanAgent
    return wrap_titan_agent(TitanAgent)(features or Features())


_INSTANCE = None


def _step(observation, configuration):
    value = observation.get("step")
    if value is not None:
        return int(value)
    return (int(observation.get("day", 0))
            * int((configuration or {}).get("turnsPerDay", 24))
            + int(observation.get("hour", 0)))


def agent(observation, configuration=None):
    global _INSTANCE
    if _INSTANCE is None or _step(observation, configuration) == 0:
        _INSTANCE = make_agent()
    return _INSTANCE.act(observation, configuration)
