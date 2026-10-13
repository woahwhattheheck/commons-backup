# SPDX-License-Identifier: Apache-2.0
"""The archive's canonical DEFAULT, run from the archive root. No overlay.

This is TITAN-CONFIG.json exactly as shipped (terminal_route=false), loaded from
the immutable archive at /home/user/work/titan-current. Nothing in the archive is
copied, edited, repacked or substituted; this file only holds the import root and
a fresh instance per match.
"""
import json
import os
import sys

ARCHIVE = "/home/user/work/titan-current"
_A = None


def make_agent():
    if ARCHIVE not in sys.path:
        sys.path.insert(0, ARCHIVE)
    from titan_runtime import TitanAgent, Features
    cfg = json.load(open(os.path.join(ARCHIVE, "TITAN-CONFIG.json")))
    return TitanAgent(Features(**cfg)).act


def agent(observation, configuration=None):
    global _A
    step = observation.get("step")
    if step is None:
        step = int(observation["day"]) * int((configuration or {}).get("turnsPerDay", 24)) \
               + int(observation["hour"])
    if _A is None or int(step) == 0:
        _A = make_agent()
    return _A(observation, configuration)
