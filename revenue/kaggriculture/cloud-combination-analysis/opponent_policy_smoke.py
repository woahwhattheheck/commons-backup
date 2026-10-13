# SPDX-License-Identifier: Apache-2.0
"""Compare the repaired resolver and integrated executor on actual Arlene calls.

Explicit synthetic observations reuse the shape from policy_smoke.py. No engine,
seed, complete game, cash-performance result or held evidence is produced.
"""
import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import types
from unittest.mock import patch

from test_opponent_invocation import load_resolver

EXPECTED = '1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4'


def observation(products, step, seat):
    farm = {'tiles': [[None for _ in range(10)] for _ in range(10)],
            'farmer': [4, 4], 'hands': [[4, 4], [4, 4]], 'money': 10000}
    return {'step': step, 'day': step // 24, 'hour': step % 24, 'player': seat,
            'farms': [deepcopy(farm), deepcopy(farm)],
            'private': {'seeds': {'CARROT': 10, 'TOMATO': 10, 'STRAWBERRY': 10, 'MELON': 10},
                        'inventories': [{}, {}, {}], 'shed': {'CARROT': 3}},
            'market': {'prices': {p: 50 for p in products},
                       'inventory': {p: 100 for p in products}},
            'town': {'unlocked_shops': []}}


def run(arlene, resolver, executor):
    digest = hashlib.sha256(Path(arlene).read_bytes()).hexdigest()
    if digest != EXPECTED: raise ValueError('Use the pinned intact Arlene source')
    spec = importlib.util.spec_from_file_location('smoke_direct_arlene', arlene)
    A = importlib.util.module_from_spec(spec); spec.loader.exec_module(A)
    resolved = load_resolver(Path(resolver))
    resolved.OPPONENTS['smoke'] = str(Path(arlene).resolve())
    spec = importlib.util.spec_from_file_location('smoke_actual_executor', executor)
    runner = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {'cards': types.ModuleType('cards')}):
        spec.loader.exec_module(runner)
    rows = []
    for seat in (0, 1):
        direct = A.Agent()
        opponent, opponent_id = resolved.make_opponent('smoke', A)
        factory, candidate_id = runner.load_callable(arlene)
        observer = runner.TimedFactory(factory); candidate = observer()
        for step in (0, 1, 22, 23, 100, 718):
            source = observation(A.PRODUCTS, step, seat)
            a, b, c = deepcopy(source), deepcopy(source), deepcopy(source)
            expected, opp, cand = direct.act(a), opponent(b, {}), candidate(c, {})
            if not (expected == opp == cand and a == b == c):
                raise AssertionError(f'Changed call at seat {seat}, step {step}')
            rows.append({'seat': seat, 'step': step, 'action': expected,
                         'opponent_equal': True, 'candidate_equal': True, 'inputs_equal': True})
        rows.append({'seat': seat, 'executor_timing': observer.timings()})
    return {'scope': 'actual_source_on_synthetic_observations',
            'cases': 12, 'opponent_comparisons': 12, 'candidate_comparisons': 12,
            'differences': 0, 'games': 0, 'seeds': [], 'arlene_sha256': digest,
            'resolver_sha256': hashlib.sha256(Path(resolver).read_bytes()).hexdigest(),
            'executor_sha256': hashlib.sha256(Path(executor).read_bytes()).hexdigest(), 'rows': rows}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--arlene', required=True); ap.add_argument('--resolver', required=True)
    ap.add_argument('--executor', required=True); ap.add_argument('--out', required=True)
    a = ap.parse_args(); result = run(a.arlene, a.resolver, a.executor)
    Path(a.out).write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}, sort_keys=True))
