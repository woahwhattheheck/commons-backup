# SPDX-License-Identifier: Apache-2.0
"""Execute the causal selector on actual pinned-engine public observations."""
import argparse
from copy import deepcopy
import gzip
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from dependencies import official_engine
from recourse import choose_observed


def execute(ev, engine, case, stream, seat, adaptive, extra_private=0):
    cfg = ev.Struct({k: v.get('default') if isinstance(v, dict) else v
                     for k, v in engine.specification['configuration'].items()})
    cfg.seed = 0
    env = ev.Struct(configuration=cfg, done=False, info={})
    state = [ev.Struct(observation=ev.Struct(), action={}, status='ACTIVE', reward=0) for _ in range(2)]
    engine.interpreter(state, env)
    item = case['item']; policy = case['policy']
    market = state[0].observation.market
    market['inventory'][item] = case['inventory']; engine._refresh_prices(market)
    state[0].observation.town['unlocked_shops'] = list(case['shops'])
    state[seat].observation.private['shed'] = {item: case['quantity']}
    _, rival, alignment = stream
    state[1-seat].observation.private['shed'] = {item: sum(q for _, q in rival)+extra_private}
    for farm in state[0].observation.farms: farm['money'] = 0
    plan = dict(policy['plans'][0]['sales']); rival = dict(rival)
    rival_slot = {'before':0, 'paired':1, 'after':2}[alignment]
    rows = []; chosen = 0; branch_observation = None
    for step in range(case['now'], case['end']+1):
        for who in (0, 1):
            state[who].observation.update(step=step, day=step//24, hour=step%24)
        if step == policy['branch']:
            branch_observation = deepcopy(state[seat].observation)
            if adaptive:
                chosen = choose_observed(policy, branch_observation, item)
                assert chosen is not None
                plan = dict(policy['plans'][chosen]['sales'])
        for who, slot, orders in ((seat, 1, plan), (1-seat, rival_slot, rival)):
            queue = [[] for _ in range(slot)] + [['SELL', item, orders[step]]] if orders.get(step, 0) else []
            state[who].action = {'farmer':['PASS'], 'hands':[], 'market':queue}
        before = [f['money'] for f in state[0].observation.farms]
        actions = deepcopy([s.action for s in state])
        engine.interpreter(state, env)
        rows.append({'step':step, 'actions':actions, 'cash_before':before,
                     'cash_after':[f['money'] for f in state[0].observation.farms],
                     'inventory_after':market['inventory'][item]})
    return {'cash':[state[0].observation.farms[s]['money'] for s in (seat, 1-seat)],
            'chosen':chosen, 'branch_observation':branch_observation, 'transitions':rows}


def verify(case, ev, engine):
    seats = []
    for seat in (0, 1):
        controls = [execute(ev, engine, case, s, seat, False) for s in case['streams']]
        adaptive = [execute(ev, engine, case, s, seat, True) for s in case['streams']]
        deltas = [(a['cash'][0]-a['cash'][1])-(b['cash'][0]-b['cash'][1])
                  for a, b in zip(adaptive, controls)]
        assert deltas == case['policy']['causal_deltas']
        for row in adaptive:
            key = str(row['branch_observation']['market']['inventory'][case['item']])
            assert row['chosen'] == case['policy']['choices'][key]
        # Extra simulator-private carry cannot enter the policy observation.
        private_world = execute(ev, engine, case, case['streams'][0], seat, True, 7)
        assert private_world['branch_observation'] == adaptive[0]['branch_observation']
        assert private_world['chosen'] == adaptive[0]['chosen']
        unknown = deepcopy(adaptive[0]['branch_observation'])
        unknown['market']['inventory'][case['item']] = -123456
        assert choose_observed(case['policy'], unknown, case['item']) is None
        seats.append({'seat':seat, 'deltas':deltas, 'baseline':controls, 'adaptive':adaptive,
                      'identical_public_different_private':True, 'unknown_fallback':True})
    return {'context':case, 'seats':seats}


if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('--engine-dir', required=True)
    p.add_argument('--scan', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    a=p.parse_args(); ev, engine, hashes=official_engine(a.engine_dir)
    cases=json.loads(gzip.decompress(a.scan.read_bytes()))['findings']
    rows=[verify(c,ev,engine) for c in cases]
    result={'engine':hashes, 'cases':rows, 'transitions':sum(len(r['transitions']) for c in rows for s in c['seats'] for arm in ('baseline','adaptive') for r in s[arm])}
    a.output.write_bytes(gzip.compress(json.dumps(result,indent=2).encode(),mtime=0))
    print(json.dumps({'tables':len(rows),'transitions':result['transitions'],'both_seats':True}))
