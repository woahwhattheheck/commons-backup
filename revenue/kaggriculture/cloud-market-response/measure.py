# SPDX-License-Identifier: MIT
"""Evaluation-only official-engine runner. Truth never enters policy arguments."""
from __future__ import annotations
import argparse
import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import policy

def imported(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run(seed, seat, arm, rival, engine_dir, output):
    ev = imported(HERE.parent/'cloud-eval/evaluate.py', 't12_evaluator')
    engine, hashes = ev.get_engine(engine_dir)
    cfg = ev.Struct({k: v.get('default') if isinstance(v, dict) else v
                     for k, v in engine.specification['configuration'].items()})
    cfg.seed = seed
    env = ev.Struct(configuration=cfg, done=False, info={})
    state = [ev.Struct(observation=ev.Struct(), action={}, status='ACTIVE', reward=0) for _ in range(2)]
    engine.interpreter(state, env)
    assert cfg.get('seed') is None
    monitor = policy.ResponsePolicy(enabled=arm == 'response')
    if arm == 'arlene':
        base_agent = monitor.source.parent.Agent()
        candidate = lambda obs: base_agent.act(obs)
    else:
        candidate = lambda obs: monitor.act(obs, cfg)
    rival_parent, _, variant = rival.partition(':')
    variants = imported(HERE/'vendor/league_variants.py', 't12_eval_variants') if variant else None
    opponent_changed = 0
    if rival_parent == 'arlene':
        opponent_instance = monitor.source.parent.Agent()
        opponent = lambda obs: opponent_instance.act(obs)
    elif rival_parent == 'apex':
        official = imported(HERE.parent/'cloud-pack/official.py', 't12_official')
        runner = official.make_agent(HERE.parent/'cloud-frontier-policy/next-panel/vendor/apex/main.py')
        opponent = lambda obs: runner(obs, cfg)
    else:
        raise ValueError(rival)
    seen_base = []
    original_act = monitor.scheduler.controller.act
    def parent_spy(obs):
        result = original_act(obs)
        seen_base.append(copy.deepcopy(result))
        return result
    monitor.scheduler.controller.act = parent_spy
    # Evaluation-only receipt observer: preserve exact original commit semantics.
    commit = engine._commit_unit
    truth = [dict(), dict()]
    def record_commit(op, item, price, farm, private, market, shed_capacity=100):
        ok = commit(op, item, price, farm, private, market, shed_capacity)
        if ok and op == 'SELL':
            i = 0 if farm is state[0].observation.farms[0] else 1
            truth[i][item] = truth[i].get(item, 0)+1
        return ok
    engine._commit_unit = record_commit
    output.mkdir(parents=True, exist_ok=True)
    stem = f'{arm}-{rival}-{seed}-{seat}'
    trace_path = output/(stem+'.jsonl.gz')
    times = [[], []]; summary = dict(ready=0, active=0, covered=0, exact=0, censored=0,
                                  interval_failures=0, abs_error=0, zero_error=0,
                                  positive_abs_error=0, positive_zero_error=0, positive=0)
    previous_truth = None
    changed = []
    horizon_predictions = []
    all_truth = []
    digest = hashlib.sha256()
    start = time.perf_counter()
    with gzip.open(trace_path, 'wt', encoding='utf-8') as trace:
        for step in range(cfg.episodeSteps):
            obs = []
            for s in state:
                s.observation.step = step
                obs.append(copy.deepcopy(s.observation))
            before = time.perf_counter()
            if arm == 'arlene':
                monitor.observe(obs[seat], cfg)
            action = candidate(obs[seat])
            times[seat].append(time.perf_counter()-before)
            if arm == 'arlene':
                _, private = monitor.source.post_units(obs[seat], action, cfg)
                available = dict(private['shed']); sales = {}
                for o in action.get('market', [])[:cfg.maxMarketOrdersPerTurn]:
                    if o and o[0] == 'SELL' and len(o)>2 and o[1] in monitor.source.PRODUCTS:
                        p = o[1]; n = min(max(0, int(o[2])), max(0, available.get(p, 0)))
                        sales[p] = sales.get(p, 0)+n; available[p] = available.get(p, 0)-n
                monitor.previous, monitor.previous_sales = copy.deepcopy(obs[seat]), sales
            else:
                assert len(seen_base) == step+1, 'authoritative parent called more than once'
                base = seen_base[-1]
                assert action['farmer'] == base['farmer'] and action['hands'] == base['hands']
                for i, o in enumerate(base.get('market', [])):
                    if not o or o[0] != 'SELL' or o[1] not in monitor.source.PRODUCTS:
                        assert action['market'][i] == o, 'non-SELL slot changed'
            if previous_truth is not None:
                for interval in monitor.last_intervals:
                    real = previous_truth.get(interval['product'], 0)
                    assert interval['lower'] <= real <= interval['upper'], (interval, real)
                    summary['exact' if interval['exact'] else 'censored'] += 1
            horizon = min(step+8, int(cfg.episodeSteps)-2)
            if horizon >= step:
                for product in monitor.source.PRODUCTS:
                    pred = monitor.history.window_prediction(product, step, horizon)
                    if pred['ready']:
                        horizon_predictions.append((step, horizon, product, pred['lower'], pred['point'], pred['upper']))
            before = time.perf_counter()
            rival_action = opponent(obs[1-seat])
            if variant:
                changed_action = variants.transform(rival_action, obs[1-seat], variant, monitor.source.m.SHOPS, cfg)
                opponent_changed += changed_action != rival_action
                rival_action = changed_action
            times[1-seat].append(time.perf_counter()-before)
            actions = [None, None]; actions[seat] = action; actions[1-seat] = rival_action
            for i, a in enumerate(actions):
                assert isinstance(a, dict) and len(a.get('market', [])) <= cfg.maxMarketOrdersPerTurn
                state[i].action = a
            truth = [dict(), dict()]
            engine.interpreter(state, env)
            for p, pred in monitor.last_predictions.items():
                if pred['ready']:
                    real = truth[1-seat].get(p, 0)
                    assert pred['latest_training_step'] < step
                    summary['ready'] += 1
                    summary['covered'] += pred['lower'] <= real <= pred['upper']
                    summary['active'] += pred['point'] > 0
                    summary['abs_error'] += abs(real-pred['point'])
                    summary['zero_error'] += real
                    if real:
                        summary['positive'] += 1
                        summary['positive_abs_error'] += abs(real-pred['point'])
                        summary['positive_zero_error'] += real
            if monitor.last_changes:
                changed.append({'step': step, 'changes': monitor.last_changes})
            record = {'step': step, 'actions': actions,
                      'bank': [f['money'] for f in state[0].observation.farms],
                      'inventory_before': obs[seat]['market']['inventory'],
                      'shops_before': obs[seat]['town']['unlocked_shops'],
                      'predictions': monitor.last_predictions,
                      'inferred_previous': monitor.last_intervals,
                      'evaluation_only_sales': truth,
                      'changes': monitor.last_changes}
            raw = json.dumps(record, sort_keys=True, separators=(',', ':'))
            digest.update(raw.encode()); trace.write(raw+'\n')
            previous_truth = dict(truth[1-seat])
            all_truth.append(previous_truth)
            if all(s.status == 'DONE' for s in state):
                break
    assert all(s.status == 'DONE' for s in state)
    scores = [s.reward for s in state]
    window_metrics = {'ready': 0, 'covered': 0, 'absolute_error': 0, 'zero_error': 0, 'active': 0,
                      'positive_cases': 0, 'positive_absolute_error': 0, 'positive_zero_error': 0}
    for a,b,p,lo,point,hi in horizon_predictions:
        if b >= len(all_truth): continue
        real = sum(all_truth[t].get(p,0) for t in range(a,b+1))
        window_metrics['ready'] += 1
        window_metrics['covered'] += lo <= real <= hi
        window_metrics['absolute_error'] += abs(point-real)
        window_metrics['zero_error'] += real
        window_metrics['active'] += point>0
        if real:
            window_metrics['positive_cases'] += 1
            window_metrics['positive_absolute_error'] += abs(point-real)
            window_metrics['positive_zero_error'] += real
    summary['windows'] = window_metrics
    result = {'seed': seed, 'seat': seat, 'arm': arm, 'opponent': rival,
              'scores': scores, 'terminal_bank': [f['money'] for f in state[0].observation.farms],
              'opponent_changed_turns': opponent_changed, 'margin': scores[seat]-scores[1-seat], 'steps': step+1,
              'prediction': summary, 'interventions': len(changed), 'changed': changed,
              'max_seconds': max(times[seat]), 'mean_seconds': statistics.mean(times[seat]),
              'wall_seconds': time.perf_counter()-start, 'trace_sha256': digest.hexdigest(),
              'compressed_trace_sha256': hashlib.sha256(trace_path.read_bytes()).hexdigest(),
              'engine_sha256': hashes,
              'runtime_sha256': {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.glob('*.py')},
              'frozen_scheduler_sha256': policy.FROZEN_SHA256,
              'truth_boundary': 'Receipt instrumentation is evaluation-only. Policy receives own observation and seed-cleared configuration only.'}
    (output/(stem+'.json')).write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('seed', 'seat', 'arm', 'opponent', 'scores', 'margin', 'interventions', 'prediction', 'max_seconds', 'wall_seconds')}), flush=True)
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--seed', type=int, required=True)
    parser.add_argument('--seat', type=int, choices=(0, 1), default=0)
    parser.add_argument('--arm', choices=('arlene', 'sell', 'response'), required=True)
    parser.add_argument('--opponent', choices=('arlene', 'apex', 'arlene:sale_cadence', 'apex:crop_demand', 'arlene:labor_cadence'), required=True)
    parser.add_argument('--engine-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.seed, args.seat, args.arm, args.opponent, args.engine_dir, args.output)
