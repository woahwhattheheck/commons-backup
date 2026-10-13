# SPDX-License-Identifier: Apache-2.0
"""T08's frozen SELL as an OPPONENT, with the seat-1 clock supplied.

T08's `arms/sell.py` is imported unmodified. The only thing added here is the
absolute step, and it is not cosmetic: `scheduler.agent` rebuilds its
`SellScheduler` whenever `int(obs.get('step', 0)) == 0`, and a seat-1
observation has no `step`, so as a raw opponent it would reconstruct its whole
policy every single turn and then raise inside `act`. Every arm under test in
this lab already gets the same normalisation; an opponent needs it too or it is
not the policy it claims to be.

One instance per actor per match: the caller loads a fresh module each game.
"""

import importlib.util
import os
import sys
import time

T08 = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "cloud-titan-composition"))
_AGENT = None


def _load():
    for p in (os.path.join(T08, "vendor", "sell"), T08):
        if p not in sys.path:
            sys.path.insert(0, p)
    spec = importlib.util.spec_from_file_location(
        f"t08_frozen_sell_{time.time_ns()}", os.path.join(T08, "arms", "sell.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod.agent


def agent(observation, configuration=None):
    global _AGENT
    o = dict(observation)
    if o.get("step") is None:
        o["step"] = int(o["day"]) * int((configuration or {}).get("turnsPerDay", 24)) \
                    + int(o["hour"])
    if _AGENT is None or int(o["step"]) == 0:
        _AGENT = _load()
    return _AGENT(o, configuration)
