"""Paired T10 trials through the existing process-isolated official evaluator.

The observer tolerates tape actions for workers not hired. It never substitutes
transition rules or passes recorded future/private rival data into a policy.
"""
from __future__ import annotations
import argparse
from collections import Counter
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import sys

HERE = Path(__file__).resolve().parent


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def unit_snapshot(farm, private, idx):
    positions = [farm['farmer'], *farm['hands']]
    if idx >= len(positions):
        return {'missing_unit': True, 'position': None, 'inventory': {}, 'tile': None}
    x, y = positions[idx]
    inventories = private.get('inventories', [])
    return {'missing_unit': False, 'position': [x, y],
            'inventory': copy.deepcopy(inventories[idx]) if idx < len(inventories) else {},
            'tile': copy.deepcopy(farm['tiles'][y][x])}


def run_game(ev, engine, sourcepack, runtime, seed, opponent, seat, variant):
    paths = {'control': runtime/'arlene-adapter.py',
             'reserve': runtime/'t10-reserve-adapter.py',
             'timed': runtime/'t10-timed-adapter.py'}
    arlene = load(sourcepack/'commons/revenue/kaggriculture/cloud-frontier-policy/next-panel/vendor/arlene.py',
                  't10_passive_parent')
    reference = arlene.Agent()
    original_unit, original_interpreter, original_hire = engine._apply_unit_action, engine.interpreter, engine._do_hire
    current_step, farm_ids = [-1], {}
    diagnostics = [dict(hire_count=0, wage_spend=0, unit_actions=Counter(), ghost_actions=0) for _ in (0,1)]
    differences, ghost_events, final = [], [], {}
    def hire(farm, private, *args, **kwargs):
        before_cash, count = farm['money'], farm['hires_today']
        result = original_hire(farm, private, *args, **kwargs)
        d = diagnostics[farm_ids[id(farm)]]
        d['hire_count'] += farm['hires_today'] - count
        d['wage_spend'] += before_cash - farm['money']
        return result
    def unit(farm, private, idx, action, *args, **kwargs):
        player = farm_ids[id(farm)]
        d = diagnostics[player]
        op = action[0] if isinstance(action, list) and action else 'EMPTY'
        d['unit_actions'][op] += 1
        if idx > len(farm['hands']):
            d['ghost_actions'] += 1
            if player == seat and len(ghost_events) < 24:
                ghost_events.append(dict(step=current_step[0], unit=idx, action=copy.deepcopy(action),
                                         **unit_snapshot(farm, private, idx)))
        return original_unit(farm, private, idx, action, *args, **kwargs)
    def interpreter(state, env):
        if state[0].observation.get('farms'):
            farm_ids.update({id(f): i for i, f in enumerate(state[0].observation.farms)})
            current_step[0] = state[0].observation.get('step', 0)
            obs = state[seat].observation
            parent_action = reference.act(copy.deepcopy(obs))
            if state[seat].action != parent_action:
                differences.append({'step':current_step[0], 'action':copy.deepcopy(state[seat].action),
                                    'parent_same_observation':parent_action,
                                    'observation':copy.deepcopy(obs)})
        result = original_interpreter(state, env)
        farm_ids.update({id(f): i for i,f in enumerate(state[0].observation.farms)})
        if all(s.status == 'DONE' for s in state):
            final.update(farms=copy.deepcopy(state[0].observation.farms),
                         private=[copy.deepcopy(s.observation.private) for s in state],
                         market=copy.deepcopy(state[0].observation.market))
        return result
    engine._apply_unit_action, engine.interpreter, engine._do_hire = unit, interpreter, hire
    candidate, rival = str(paths[variant]), str(runtime/(opponent+'-adapter.py'))
    pair = [candidate, rival] if seat == 0 else [rival, candidate]
    try:
        game = ev.play(engine, pair, sourcepack/'engine', ev.LOADER, seed, seat)
    finally:
        engine._apply_unit_action, engine.interpreter, engine._do_hire = original_unit, original_interpreter, original_hire
    game.update(variant=variant, opponent=opponent, diagnostics=diagnostics,
                differences=differences, ghost_events=ghost_events, terminal=final)
    return game


def summarize(games):
    out = {}
    controls = {(g['seed'], g['opponent'], g['candidate_seat']):g for g in games
                if g['variant']=='control' and g['status']=='complete'}
    for variant in sorted({g['variant'] for g in games}):
        for opponent in sorted({g['opponent'] for g in games}):
            rows = [g for g in games if g['variant']==variant and g['opponent']==opponent]
            complete = [g for g in rows if g['status']=='complete']
            cash_deltas, flips = [], Counter()
            margins = [g['scores'][g['candidate_seat']]-g['scores'][1-g['candidate_seat']] for g in complete]
            for g, margin in zip(complete, margins):
                control = controls.get((g['seed'],g['opponent'],g['candidate_seat']))
                if control:
                    seat = g['candidate_seat']
                    cm = control['scores'][seat]-control['scores'][1-seat]
                    label = lambda x: 'W' if x>0 else 'L' if x<0 else 'T'
                    flips[label(cm)+'->'+label(margin)] += 1
                    cash_deltas.append(g['scores'][seat]-control['scores'][seat])
            out[f'{variant}/{opponent}'] = {
                'scheduled':len(rows), 'completed':len(complete), 'failed':len(rows)-len(complete),
                'wins':sum(x>0 for x in margins), 'ties':sum(x==0 for x in margins), 'losses':sum(x<0 for x in margins),
                'mean_margin':statistics.mean(margins) if margins else None,
                'mean_paired_cash_delta':statistics.mean(cash_deltas) if cash_deltas else None,
                'paired_flips':dict(flips),
                'max_call_seconds':max((g['actors'][g['candidate_seat']]['max_call_seconds'] for g in complete), default=None)}
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sourcepack',type=Path,required=True)
    p.add_argument('--runtime',type=Path,required=True)
    p.add_argument('--seeds',required=True)
    p.add_argument('--variants',default='control,reserve,timed')
    p.add_argument('--opponents',default='arlene,apex')
    p.add_argument('--seats',default='0,1')
    p.add_argument('--output',type=Path,required=True)
    args = p.parse_args()
    sourcepack, runtime = args.sourcepack.resolve(), args.runtime.resolve()
    ev = load(sourcepack/'commons/revenue/kaggriculture/cloud-eval/evaluate.py', 't10_process_evaluator')
    engine, hashes = ev.get_engine(sourcepack/'engine')
    report = {'engine_ref':ev.ENGINE_REF, 'engine_sha256':hashes,
              'evaluator_sha256':ev.sha256(ev.__file__),
              'source_sha256':{f.name:ev.sha256(f) for f in sorted(HERE.glob('*.py'))},
              'runtime_manifest':json.loads((runtime/'T10-MANIFEST.json').read_text()),
              'baseline_manifest':json.loads((runtime/'manifest.json').read_text()),
              'method':'Unmodified official transitions, existing process-isolated ev.play; passive observations only. Zero future rival orders applies only to the policy forecast, NOT actual games.',
              'limits':{'action_rpc_seconds':1, 'game_seconds':120, 'remaining_overage_time':0},
              'games':[]}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    for seed in map(int,args.seeds.split(',')):
        for opponent in args.opponents.split(','):
            for seat in map(int,args.seats.split(',')):
                for variant in args.variants.split(','):
                    game = run_game(ev,engine,sourcepack,runtime,seed,opponent,seat,variant)
                    report['games'].append(game)
                    report['summary'] = summarize(report['games'])
                    args.output.write_text(json.dumps(report,indent=2)+'\n')
                    print(json.dumps({k:game[k] for k in ('seed','opponent','candidate_seat','variant','status','scores','failure')}),flush=True)
    print(json.dumps(report['summary'],indent=2))
    return int(any(g['status']!='complete' for g in report['games']))


if __name__ == '__main__':
    raise SystemExit(main())
