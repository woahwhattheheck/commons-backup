# SPDX-License-Identifier: Apache-2.0
"""V3 lane R02: the shop-router tapes as the canonical route bank (key r02_route_bank).

R01 delegates the whole turn to the published router.  R02 keeps TITAN: it replaces the
contents of the canonical MAIN route with a router tape, in place, and lets the frozen
seller, the pending accounting and every other canonical stage run on top of it.  The
route is theirs; the market brain stays ours.

Tape source: yhay81, Shop Router 0909, https://www.kaggle.com/code/yhay81/shop-router-0909
(Apache License 2.0), carried in r01_tapes.py.  Plan selection reproduces the published
rule exactly: plan 0 until step 144, then the plan indexed by the first two unlocked shops,
then plan 2 from step 648.

Prefix safety (measured on the tapes themselves): plans 3..12 are identical to plan 0 for
steps 0..143 and plan 2 is identical to plan 0 for steps 0..312, so replacing only the tail
from the switch step leaves every already-played step byte-identical, which is the same
guarantee the canonical controller enforces for its own route switches.  Plan 1 diverges at
step 70; the published router also replays plan 0 up to step 144 before reading plan 1, so
the tail replacement reproduces its play exactly.
"""
from __future__ import annotations

ROUTE_STEP = 144
FINAL_PLAN_STEP = 648
FINAL_PLAN = 2
KEY = 'r02_route_bank'
NOOP = 'R02_noop:flag_off'

# The published table: first two unlocked shops, in their observed order, to tape index.
SHOP_PLANS = {
    ('BAKERY', 'YARN_STORE'): 3,
    ('BRUNCH_SPOT', 'YARN_STORE'): 4,
    ('FARMERS_MARKET', 'YARN_STORE'): 5,
    ('ICE_CREAM_SHOP', 'YARN_STORE'): 6,
    ('PET_CAFE', 'YARN_STORE'): 5,
    ('PIZZA_SHOP', 'YARN_STORE'): 7,
    ('SMOOTHIE_SHOP', 'YARN_STORE'): 8,
    ('YARN_STORE', 'BAKERY'): 9,
    ('YARN_STORE', 'BRUNCH_SPOT'): 9,
    ('YARN_STORE', 'FARMERS_MARKET'): 1,
    ('YARN_STORE', 'ICE_CREAM_SHOP'): 9,
    ('YARN_STORE', 'PET_CAFE'): 10,
    ('YARN_STORE', 'PIZZA_SHOP'): 6,
    ('YARN_STORE', 'SMOOTHIE_SHOP'): 11,
    ('YARN_STORE', 'YARN_STORE'): 12,
}


def plan_for(observation):
    """The published selection: the first two unlocked shops in their observed order."""
    shops = ((observation.get('town') or {}).get('unlocked_shops') or [])
    return SHOP_PLANS.get(tuple(shops[:2]), 0)


def _route_id(controller):
    """The route the canonical controller is currently playing."""
    return controller.cur


def _replace_tail(route, tape, at, controller):
    """Replace route[at:] with tape[at:], in place, and drop the future-sell cache.

    The list object is kept so every structure already holding this route keeps seeing it.
    The controller caches its future-SELL table per route id; the id is unchanged here, so
    the cache is invalidated explicitly rather than left stale.
    """
    if route[at:] == tape[at:]:
        return 0
    route[at:] = [dict(step) for step in tape[at:]]
    if getattr(controller, '_fs_for', None) is not None:
        controller._fs_for = None
    return len(route) - at


def install(agent, enabled, tapes=None):
    """Seat plan 0 as the MAIN route contents. Identity when the key is off."""
    state = {'plan': None, 'endgame': False, 'reasons': [], 'replaced': 0}
    if not enabled:
        state['reasons'].append(NOOP)
        agent._v3_r02 = state
        return state
    from r01_tapes import load_tapes
    tapes = tapes if tapes is not None else load_tapes()
    controller = agent.controller
    route = controller.R[_route_id(controller)]
    state['replaced'] += _replace_tail(route, tapes[0], 0, controller)
    state['plan'] = 0
    state['tapes'] = tapes
    state['reasons'].append('R02_seated:plan0')
    agent._v3_r02 = state
    return state


def step(agent, observation, enabled):
    """Apply the published switches for this step. Idempotent; identity when off."""
    state = getattr(agent, '_v3_r02', None)
    if not enabled or state is None or state.get('tapes') is None:
        return state
    obs_step = observation.get('step')
    if obs_step is None:
        obs_step = int(observation.get('day', 0)) * 24 + int(observation.get('hour', 0))
    obs_step = int(obs_step)
    controller = agent.controller
    route = controller.R[_route_id(controller)]
    tapes = state['tapes']
    if obs_step >= ROUTE_STEP and state.get('plan') in (None, 0):
        chosen = plan_for(observation)
        if chosen:
            state['replaced'] += _replace_tail(route, tapes[chosen], ROUTE_STEP, controller)
        state['plan'] = chosen
        state['reasons'].append('R02_plan:%d' % chosen)
    if obs_step >= FINAL_PLAN_STEP and not state.get('endgame'):
        state['replaced'] += _replace_tail(route, tapes[FINAL_PLAN], FINAL_PLAN_STEP, controller)
        state['endgame'] = True
        state['reasons'].append('R02_endgame:plan%d' % FINAL_PLAN)
    return state
