# SPDX-License-Identifier: Apache-2.0
"""Negative controls, paired timing, and exact-input native entrypoint smoke runs."""
from __future__ import annotations

import argparse
import copy
import gc
import io
import json
import platform
import random
import statistics
import sys
import time
import types
import unittest
from pathlib import Path

import validate_rival_supply_cache as v
from rival_supply_cache import git_blob, sha256, transform


def negative_controls():
    source = transform((v.ROOT / 'frozen_selected.py').read_bytes()).decode()
    variants = {
        'no_cache': source.replace('return lru_cache(maxsize=len(m.PRODUCTS))(lookup) if native else lookup', 'return lookup'),
        'shared_across_transforms': source.replace(
            'return lru_cache(maxsize=len(m.PRODUCTS))(lookup) if native else lookup',
            "if native:\n        if not hasattr(seller, '_bad_supply_cache'):\n            seller._bad_supply_cache = lru_cache(maxsize=len(m.PRODUCTS))(lookup)\n        return seller._bad_supply_cache\n    return lookup"),
        'cache_overrides': source.replace(
            'return lru_cache(maxsize=len(m.PRODUCTS))(lookup) if native else lookup',
            'return lru_cache(maxsize=len(m.PRODUCTS))(lookup)'),
        'eager_all_products': source.replace(
            'return lru_cache(maxsize=len(m.PRODUCTS))(lookup) if native else lookup',
            'result = lru_cache(maxsize=len(m.PRODUCTS))(lookup) if native else lookup\n    for product in m.PRODUCTS:\n        result(product)\n    return result'),
        'single_product_key': source.replace(
            'return seller.rival_supply(obs, item)', "return seller.rival_supply(obs, 'MILK')"),
    }
    original = v.NEW
    result = []
    for name, text in variants.items():
        if text == source:
            raise ValueError('mutation did not activate: ' + name)
        module = types.ModuleType('observe_cache_mutant_' + name)
        module.__file__ = str(v.ROOT / 'frozen_selected.py')
        exec(compile(text, module.__file__, 'exec'), module.__dict__)
        v.NEW = module
        stream = io.StringIO()
        run = unittest.TextTestRunner(stream=stream).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(v.CacheTests))
        result.append({'name': name, 'git_blob': git_blob(text.encode()),
                       'rejected': not run.wasSuccessful(), 'tests': run.testsRun,
                       'failures': [t.id() for t, _ in run.failures],
                       'errors': [t.id() for t, _ in run.errors], 'stdout': stream.getvalue()})
    v.NEW = original
    if not all(item['rejected'] for item in result):
        raise ValueError('at least one broken implementation escaped the gate')
    return {'kind': 'negative_controls', 'variants': result, 'all_rejected': True}


def benchmark(repetitions):
    if repetitions < 5:
        raise ValueError('at least five alternating observations per case required')
    output = []
    for name, rich, money, buy in (
        ('seed-funding25', True, 0, ['BUY_SEED', 'CARROT', 30]),
        ('animal-funding25', True, 0, ['BUY_ANIMAL', 'COW', 2]),
        ('land-funding25', True, 0, ['BUY_LAND']),
        ('funded-hire25', True, 100000, ['HIRE']),
        ('variable-buy-barrier25', True, 0, ['BUY_PRODUCT', 'WHEAT', 10]),
        ('zero-public-supply', False, 0, ['BUY_ANIMAL', 'COW', 2]),
    ):
        state, env, route, base = v.fixture(money=money, rich=rich)
        base['market'][1] = buy
        results = {'control': [], 'candidate': []}
        expected = None
        for repetition in range(repetitions + 2):
            order = ('control', 'candidate') if repetition % 2 == 0 else ('candidate', 'control')
            for arm in order:
                module = v.OLD if arm == 'control' else v.NEW
                bot = v.consumer(module, route)
                obs, cfg, action = copy.deepcopy((state[0].observation, env.configuration, base))
                gc.collect()
                started_cpu, started = time.process_time_ns(), time.perf_counter_ns()
                out = bot.transform(obs, cfg, action)
                elapsed = {'wall_ns': time.perf_counter_ns()-started,
                           'cpu_ns': time.process_time_ns()-started_cpu}
                result = (out, v.snapshot(bot))
                if expected is None:
                    expected = result
                elif expected != result:
                    raise ValueError('benchmark changed exact action/state/diagnostics: ' + name)
                if repetition >= 2:
                    results[arm].append(elapsed)
        medians = {arm: {metric: statistics.median(row[metric] for row in rows)
                         for metric in ('wall_ns', 'cpu_ns')} for arm, rows in results.items()}
        output.append({'case': name, 'repetitions_per_arm': repetitions,
                       'samples': results, 'median': medians,
                       'wall_speedup': medians['control']['wall_ns']/medians['candidate']['wall_ns'],
                       'cpu_speedup': medians['control']['cpu_ns']/medians['candidate']['cpu_ns'],
                       'exact_action_state_and_diagnostics': True})
    return {'kind': 'controlled_native_transform_microbenchmark', 'cases': output,
            'timing_gate_enforced': False, 'full_game_speedup_claimed': False,
            'method': 'Alternating arm order; two warmups; GC outside timed transform; no profiler; fixture copy outside timing'}


def episode(variant, seed, seat):
    # Inject only the byte-exact generated class module. The root source files,
    # default features, main entrypoint, engine, and opponent are unchanged.
    sys.modules['frozen_selected'] = v.OLD if variant == 'control' else v.NEW
    entry = v.load(v.ROOT / 'main.py', 'observe_cache_entrypoint')
    e, S = v.ENGINE, v.LOADER.Struct
    cfg = S({k: value.get('default') if isinstance(value, dict) else value
             for k, value in e.specification['configuration'].items()})
    cfg.seed = seed
    env = S(configuration=cfg, done=False, info={})
    state = [S(observation=S(), action={}, status='ACTIVE', reward=0) for _ in range(2)]
    e.interpreter(state, env)
    random.seed(seed)
    rows = []
    trace = []
    for step in range(cfg.episodeSteps):
        for player in (0, 1):
            state[player].observation.step = step
        start = time.perf_counter()
        own = entry.agent(copy.deepcopy(state[seat].observation), cfg)
        elapsed = time.perf_counter()-start
        rival = e.starter_agent(copy.deepcopy(state[1-seat].observation))
        state[seat].action, state[1-seat].action = own, rival
        instance = entry._INSTANCE
        diag = {} if instance is None else instance.diagnostics
        rows.append({'step': step, 'wall_seconds': elapsed,
                     'status': diag.get('status'), 'fallback_stage': diag.get('fallback_stage'),
                     'parent_calls': diag.get('parent_calls')})
        trace.append({'step': step, 'own': own, 'rival': rival})
        e.interpreter(state, env)
        if any(s.status == 'DONE' for s in state):
            break
    encoded = json.dumps(trace, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return {'kind': 'native_entrypoint_official_episode', 'variant': variant,
            'seed': seed, 'seat': seat, 'opponent': 'official_starter',
            'callbacks': len(rows), 'rows': rows, 'trace': trace, 'trace_sha256': sha256(encoded),
            'bank': [s.reward for s in state], 'status': [s.status for s in state],
            'fallbacks': sum(r['status'] != 'completed' for r in rows),
            'default_feature_config_unchanged': True, 'hosted_kaggle': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--mode', choices=('negative-controls', 'benchmark', 'episode'), required=True)
    parser.add_argument('--repetitions', type=int, default=21)
    parser.add_argument('--variant', choices=('control', 'candidate'), default='control')
    parser.add_argument('--seed', type=int, default=9922999)
    parser.add_argument('--seat', type=int, choices=(0, 1), default=0)
    args = parser.parse_args()
    v.prepare(args.runtime_root)
    if args.mode == 'negative-controls':
        result = negative_controls()
    elif args.mode == 'benchmark':
        result = benchmark(args.repetitions)
    else:
        result = episode(args.variant, args.seed, args.seat)
    result.update(optimized=not __debug__, python=sys.version, platform=platform.platform(),
                  fixture_identity={k: value for k, value in v.REPORT.items()
                                    if k not in ('native_cases', 'official_interpreter_pairs', 'scans')},
                  exercise_runner_git_blob=git_blob(Path(__file__).read_bytes()))
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({k:value for k,value in result.items() if k not in ('rows','trace','cases','variants')}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
