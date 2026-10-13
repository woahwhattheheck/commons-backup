# SPDX-License-Identifier: Apache-2.0
"""Shadow native funding calls on an instrumented current-package trajectory.

Returns the ORIGINAL funding result, never the experimental basket.  Additional
instrumentation uses real wall-clock budget, so this is engagement evidence,
not an uninstrumented-parent performance or head-to-head economics claim.
"""
import argparse
import collections
import copy
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import test_funding_basket as fixture
import funding_basket as basket


def run(package, seed, seat, steps):
    fixture.load_package(package)
    root = Path(package).resolve()
    fs, engine, loader = fixture.FS, fixture.ENGINE, fixture.LOADER
    prior = fs.fund_same_turn_acquisition
    probe = basket.bind(fs, enabled=True)
    counts = collections.Counter()
    witnesses = []
    probe_seconds = []

    def shadow(*args):
        original = prior(*args)
        counts['funding_calls'] += 1
        info = original[1] or {}
        counts['parent:' + str(info.get('reason', 'applied' if info.get('applied') else 'no-target'))] += 1
        if info.get('reason') == 'no-safe-prefix-sale':
            started = time.perf_counter()
            proposed, proof = probe(*args)
            probe_seconds.append(time.perf_counter() - started)
            counts['probe:' + str(proof.get('reason', 'applied' if proof.get('applied') else 'no-target'))] += 1
            if proof.get('mechanism') == 'same-turn-funding-basket' and proof.get('applied'):
                witnesses.append({'step': args[6], 'original_market': copy.deepcopy(args[0]),
                                  'candidate_market': proposed, 'proof': proof,
                                  'farm': copy.deepcopy(args[1]), 'private': copy.deepcopy(args[2]),
                                  'market': copy.deepcopy(args[3]), 'shops': copy.deepcopy(args[4])})
        return original

    spec = importlib.util.spec_from_file_location('basket_census_entry', root/'main.py')
    entry = importlib.util.module_from_spec(spec); spec.loader.exec_module(entry)
    cfg = loader.Struct({k: v.get('default') if isinstance(v, dict) else v
                         for k, v in engine.specification['configuration'].items()})
    cfg.seed = seed
    env = loader.Struct(configuration=cfg, done=False, info={})
    state = [loader.Struct(observation=loader.Struct(), action={}, status='ACTIVE', reward=0)
             for _ in range(2)]
    engine.interpreter(state, env)
    calls = 0
    fs.fund_same_turn_acquisition = shadow
    try:
        for step in range(steps):
            for i, s in enumerate(state):
                s.observation.step = step
                obs = copy.deepcopy(s.observation)
                action = entry.agent(obs, cfg) if i == seat else engine.starter_agent(obs)
                if not isinstance(action, dict):
                    raise ValueError('non-dictionary agent output')
                s.action = action
            instance = entry._INSTANCE
            counts['runtime:' + str(getattr(instance, 'diagnostics', {}).get('status'))] += 1
            engine.interpreter(state, env)
            calls += 1
            if any(s.status == 'DONE' for s in state):
                break
    finally:
        fs.fund_same_turn_acquisition = prior
    return {'mode': 'shadow; original funding output returned', 'seed': seed, 'seat': seat,
            'callbacks': calls, 'status': [s.status for s in state],
            'completed': all(s.status == 'DONE' for s in state), 'counts': dict(counts),
            'witnesses': witnesses, 'probe_max_seconds': max(probe_seconds, default=0),
            'source_sha256': fixture.SOURCE_SHA256,
            'helper_sha256': hashlib.sha256(Path(basket.__file__).read_bytes()).hexdigest(),
            'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'limits': ['One seed and starter opponent only.',
                       'Instrumentation overhead can affect deadline behavior.',
                       'No counterfactual game, field-strength, or activation claim.']}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--package', required=True)
    p.add_argument('--seed', type=int, default=17)
    p.add_argument('--seat', type=int, choices=(0, 1), required=True)
    p.add_argument('--steps', type=int, default=720)
    p.add_argument('--output', required=True)
    a = p.parse_args()
    report = run(a.package, a.seed, a.seat, a.steps)
    Path(a.output).write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'witnesses'}, sort_keys=True))
