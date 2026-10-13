# SPDX-License-Identifier: Apache-2.0
"""The archive's canonical DEFAULT, run from the archive root. terminal_route=true overlay.

Same archive, same source, same everything else: TITAN-CONFIG.json is loaded from
the immutable archive and then ONE field is overridden, terminal_route=True. The
overlay lives here and is recorded in the results, never written back into the
archive. The runtime already refuses terminal_route with a non-frozen consumer.
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
    cfg["terminal_route"] = True
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
