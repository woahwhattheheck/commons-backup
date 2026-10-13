# SPDX-License-Identifier: Apache-2.0
"""Within-process alternating snapshot microbenchmark; no policy/economic score."""
from copy import deepcopy
import argparse
import gc
import json
from statistics import median
import time
from test_selected_snapshot import PACKAGE, authenticate_package, fingerprint, import_module, predecessor
from selected_unit_snapshot import selected_unit_snapshot


def cases():
    authenticate_package(PACKAGE)
    ev = import_module('quarry_bench_evaluator', PACKAGE / 'checks/reference/evaluator/evaluate.py')
    engine, _ = ev.get_engine(PACKAGE / 'checks/reference/engine',
                              PACKAGE / 'checks/reference/evaluator/loader.py')
    S = ev.Struct
    cfg = S({k: v.get('default') if isinstance(v,dict) else v
             for k,v in engine.specification['configuration'].items()})
    cfg.seed = 9922999
    env = S(configuration=cfg, done=False, info={})
    state = [S(observation=S(), action={}, status='ACTIVE', reward=0) for _ in range(2)]
    engine.interpreter(state, env)
    initial = dict(state[0].observation)
    initial['step'] = 0
    dense = deepcopy(initial)
    for y, row in enumerate(dense['farms'][0]['tiles']):
        for x in range(len(row)):
            row[x] = {'kind': 'ANIMAL', 'animal': 'COW', 'yield': 1,
                      'fed_today': True, 'cared_today': True, 'tag': [y, x]}
    for _ in range(20):
        dense['private']['inventories'].append({'WHEAT': 3, 'FERTILIZER': 2})
    both = deepcopy(dense)
    both['farms'][1]['tiles'] = deepcopy(both['farms'][0]['tiles'])
    aliased = deepcopy(both)
    aliased['old_own_alias'] = aliased['farms'][0]
    aliased['old_private_alias'] = aliased['private']
    for name, obs in [('official_initial', initial), ('constructed_dense_own', dense),
                      ('constructed_dense_both', both), ('retained_old_subgraphs', aliased)]:
        pair = (deepcopy(obs['farms'][0]), deepcopy(obs['private']))
        yield name, obs, pair


def measure(fn, obs, pair, loops):
    started = time.perf_counter_ns()
    for _ in range(loops):
        fn(obs, 0, pair)
    return (time.perf_counter_ns() - started) / loops / 1000


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--loops', type=int, default=1000)
    parser.add_argument('--repeats', type=int, default=9)
    args = parser.parse_args()
    if args.loops < 1 or args.repeats < 3:
        parser.error('positive loops and at least three repeats required')
    result = {}
    for name, obs, pair in cases():
        old = predecessor(obs, 0, pair)
        new = selected_unit_snapshot(obs, 0, pair)
        if fingerprint(old,obs,pair) != fingerprint(new,obs,pair):
            raise ValueError('graph parity failed before benchmark')
        samples = [[], []]
        measure(predecessor, obs, pair, 20)
        measure(selected_unit_snapshot, obs, pair, 20)
        for rep in range(args.repeats):
            gc.collect()
            order = (0,1) if rep % 2 == 0 else (1,0)
            for index in order:
                samples[index].append(measure((predecessor,selected_unit_snapshot)[index],
                                              obs, pair, args.loops))
        old_med, new_med = map(median, samples)
        result[name] = {'predecessor_microseconds': old_med, 'candidate_microseconds': new_med,
            'speedup': old_med/new_med, 'reduction_percent': 100*(1-new_med/old_med),
            'predecessor_samples_us': samples[0], 'candidate_samples_us': samples[1]}
    print(json.dumps({'scope': 'snapshot-only; constructed worlds labelled; not full-game speed/EV',
        'loops': args.loops, 'repeats': args.repeats, 'alternating_order': True,
        'gc_disabled': False, 'results': result}, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
