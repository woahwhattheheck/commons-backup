# SPDX-License-Identifier: Apache-2.0
"""Consume a private retained two-turn seed-purchase witness with this runtime fix.

No old prefix replay, policy simulation, or provider request. Input schema is
QUARTZ's NATIVE-WITNESSES.json.gz; original input remains untouched.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--witness', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() == args.witness.resolve():
        parser.error('output must differ from retained input')
    begin = time.perf_counter()
    root = args.runtime.resolve()
    sys.path.insert(0, str(root))
    from titan_runtime import TitanAgent, Features
    from scheduler import post_units
    from seed_retry import install_seed_retry
    spec = importlib.util.spec_from_file_location('seed_witness_evaluator', root/'checks/reference/evaluator/evaluate.py')
    ev = importlib.util.module_from_spec(spec); sys.modules[spec.name] = ev; spec.loader.exec_module(ev)
    engine, hashes = ev.get_engine(root/'checks/reference/engine', root/'checks/reference/evaluator/loader.py')
    cfg = {k: v.get('default') if isinstance(v, dict) else v for k, v in engine.specification['configuration'].items()}
    rows = json.load(gzip.open(args.witness, 'rt'))
    earlier, later = rows['unchanged']
    step = earlier['step']; seat = int(earlier['own_before']['player'])
    assert later['step'] == step + 1
    assert all(a['market'] == [] for a in earlier['actions']), 'witness must have an empty first market'
    runtime = TitanAgent(Features(**json.loads((root/'TITAN-CONFIG.json').read_text())))
    runtime._initialize()
    matches = [key for key, route in runtime.controller.R.items()
               if route[step + 1]['farmer'] == later['actions'][seat]['farmer']
               and route[step + 1]['hands'] == later['actions'][seat]['hands']]
    assert matches, 'retained committed program not present in supplied runtime'
    runtime.controller.cur = matches[0]
    install_seed_retry(runtime)
    selected = runtime._seed_selected(earlier['own_before'], cfg, deepcopy(earlier['actions'][seat]))
    assert runtime.diagnostics['committed_seed_retry']['status'] == 'appended'
    assert {k: v for k, v in selected.items() if k != 'market'} == {
        k: v for k, v in earlier['actions'][seat].items() if k != 'market'}
    farm, private = post_units(earlier['own_before'], earlier['actions'][seat], cfg)
    assert farm == earlier['after'][seat]['observation']['farms'][seat]
    assert private == earlier['after'][seat]['observation']['private']
    results = {}
    encode = lambda x: json.dumps(x, sort_keys=True, separators=(',', ':'), allow_nan=False)
    for arm in ('unchanged', 'funded_prior_turn', 'too_late_same_turn'):
        # Retained state after the empty earlier market is also the correct
        # checkpoint for its appendix-only seed purchase. Restore shared native
        # observation aliases lost by JSON, without inventing an earlier prefix.
        state = ev.structify(deepcopy(earlier['after']))
        for key in ('farms', 'market', 'town'):
            state[1].observation[key] = state[0].observation[key]
        env = ev.Struct(configuration=ev.Struct(deepcopy(cfg)), done=False, info={})
        for actor in (0, 1):
            state[actor].action = ev.structify(deepcopy(earlier['actions'][actor]))
        if arm == 'funded_prior_turn':
            state[seat].action = ev.structify(deepcopy(selected))
        engine._process_market(state, env)
        assert encode(state) == encode(rows[arm][0]['after']), arm + ': market checkpoint mismatch'
        for actor in (0, 1):
            state[actor].observation.step = step + 1
            state[actor].observation.remainingOverageTime = 0
            state[actor].action = ev.structify(deepcopy(later['actions'][actor]))
        if arm == 'too_late_same_turn':
            state[seat].action['market'].extend(deepcopy(selected['market']))
        engine.interpreter(state, env)
        assert encode(state) == encode(rows[arm][1]['after']), arm + ': native successor mismatch'
        obs = state[seat].observation
        results[arm] = {'exact_retained_successor_match': True,
                        'own_cash': obs.farms[seat]['money'], 'own_seeds': dict(obs.private['seeds'])}
    report = {'status': 'pass', 'seconds': time.perf_counter() - begin,
              'witness_sha256': hashlib.sha256(args.witness.read_bytes()).hexdigest(),
              'source_sha256': hashlib.sha256((Path(__file__).parent/'seed_retry.py').read_bytes()).hexdigest(),
              'engine_hashes': hashes, 'runtime_diagnostic': runtime.diagnostics['committed_seed_retry'],
              'results': results, 'exact_market_checkpoints': 3, 'exact_next_turn_successors': 3,
              'producer_calls': 0, 'new_full_games': 0,
              'scope': 'existing retained two-turn execution case; no future cash/strength inference'}
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
