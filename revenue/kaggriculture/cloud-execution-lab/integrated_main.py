# SPDX-License-Identifier: Apache-2.0
"""Relocatable whole-action entrypoint; one fresh instance per actor/match."""
from pathlib import Path
import sys
_INSTANCE = None
_LAST_STEP = None

def make_agent():
    root = Path(make_agent.__code__.co_filename).resolve().parent
    if str(root) not in sys.path: sys.path.insert(0, str(root))
    from integrated_selected import make_agent as build
    return build(seed=True, committed=True, sell=True)

def _public_step(obs, cfg=None):
    step = None
    if 'step' in obs:
        step = obs['step']
        if type(step) is not int:
            raise TypeError('step must be a plain int')
        if step < 0:
            raise ValueError('step must be nonnegative')

    has_day = 'day' in obs
    has_hour = 'hour' in obs
    if has_day != has_hour:
        raise ValueError('day and hour must be supplied together')
    if has_day:
        day = obs['day']
        hour = obs['hour']
        turns = (cfg or {}).get('turnsPerDay', 24)
        if type(day) is not int or type(hour) is not int:
            raise TypeError('day and hour must be plain ints')
        if type(turns) is not int:
            raise TypeError('turnsPerDay must be a plain int')
        if day < 0:
            raise ValueError('day must be nonnegative')
        if turns <= 0:
            raise ValueError('turnsPerDay must be positive')
        if hour < 0 or hour >= turns:
            raise ValueError('hour is outside turnsPerDay')
        derived = day * turns + hour
        if step is None:
            step = derived
        elif step != derived:
            raise ValueError('step disagrees with day/hour')

    if step is None:
        raise ValueError('public step is required')
    return step

def agent(obs, cfg=None):
    global _INSTANCE, _LAST_STEP
    step = _public_step(obs, cfg)
    rebuild = _INSTANCE is None or (_LAST_STEP is not None and step < _LAST_STEP)
    instance = make_agent() if rebuild else _INSTANCE
    output = instance.act(obs, cfg)
    # Publish the instance and replay/reset boundary together only after a
    # complete return.  A failed cold start therefore leaves no partial runtime
    # reusable, while a failed rewind retains the last completed instance/step.
    _INSTANCE = instance
    _LAST_STEP = step
    return output
