# SPDX-License-Identifier: Apache-2.0
"""Offline actual main.py::agent / official-interpreter comparison.

Never truncates raw hands or market rows. No Kaggle RPC, field EV, production
activation, or whole-current-V4 claim. Each game gets an isolated process.
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
import subprocess
import sys
import tempfile
import time
import port_native_action_copies as port


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def authenticate(root):
    manifest = json.loads((root/'SOURCE.json').read_text())
    changed = {}
    for name, meta in manifest['runtime'].items():
        data = (root/name).read_bytes()
        if hashlib.sha256(data).hexdigest() != meta['sha256']:
            changed[name] = port.blob(data)
    if set(changed)-set(port.PINS):
        raise ValueError('unaccounted archive-map differences: '+str(changed))
    if port.blob((root/'checks/reference/engine/kaggriculture.py').read_bytes()) != '3c202c7ee921da239356789e266b694635103fc4':
        raise ValueError('official engine identity mismatch')
    return {'members': len(manifest['runtime']), 'changed': changed,
            'source_manifest_sha256': hashlib.sha256((root/'SOURCE.json').read_bytes()).hexdigest()}


def episode(root, seed, seat, steps=720, audit=False, ordered=False):
    root = root.resolve()
    custody = authenticate(root)
    sys.path.insert(0, str(root))
    counts, fast = Counter(), Counter()
    if (root/'r04_fast_tape_clone.py').exists() and audit:
        import r04_fast_tape_clone as helper
        original = helper.apply_fast_tape_clone
        def counted(action):
            frame = sys._getframe(1)
            site = Path(frame.f_code.co_filename).name+':'+frame.f_code.co_name
            counts[site] += 1
            fast[site] += int(helper.is_fast_tape_action(action))
            result = original(action)
            if result != copy.deepcopy(action) or result is action:
                raise AssertionError('native clone mismatch: '+site)
            return result
        helper.apply_fast_tape_clone = counted
    loader = load('_tapeport_evaluator', root/'checks/reference/evaluator/loader.py')
    engine, engine_hashes = loader.get_engine(root/'checks/reference/engine')
    cfg = loader.Struct({k:v.get('default') if isinstance(v,dict) else v
                         for k,v in engine.specification['configuration'].items()})
    cfg.seed = seed
    env = loader.Struct(configuration=cfg, done=False, info={})
    state = [loader.Struct(observation=loader.Struct(), action={}, status='ACTIVE', reward=0)
             for _ in range(2)]
    engine.interpreter(state, env)
    agent = load('_tapeport_main', root/'main.py')
    direct = None
    if ordered:
        from titan_runtime import TitanAgent, Features
        direct = TitanAgent(Features(consumer='ordered'))
    trace, planner_trace = hashlib.sha256(), hashlib.sha256()
    statuses, timings, excess = Counter(), [], 0
    for step in range(min(steps, cfg.episodeSteps)):
        for s in state:
            s.observation.step = step
        obs = copy.deepcopy(state[seat].observation)
        start = time.perf_counter()
        action = direct.act(obs, cfg) if direct is not None else agent.agent(obs, cfg)
        timings.append(time.perf_counter()-start)
        if not isinstance(action, dict):
            raise AssertionError('non-dict native action')
        excess += int(len(action.get('hands', [])) > len(obs['farms'][seat]['hands']))
        instance = direct if direct is not None else agent._INSTANCE
        diag = instance.diagnostics
        statuses[diag.get('status')] += 1
        if diag.get('status') != 'completed' or diag.get('parent_calls') != 1:
            raise AssertionError(('incomplete native call', step, diag))
        planner_trace.update(digest({'selected': instance.selected, 'route': instance.controller.cur,
            'pending': getattr(instance.consumer, 'pending', None),
            'planned': getattr(instance.consumer, 'planned', None)}).encode())
        state[seat].action = action
        state[1-seat].action = engine.starter_agent(copy.deepcopy(state[1-seat].observation))
        engine.interpreter(state, env)
        trace.update(digest(state).encode())
        if any(s.status == 'DONE' for s in state):
            break
    return {'seed': seed, 'seat': seat, 'calls': len(timings), 'steps_requested': steps,
        'opponent': 'official_starter', 'audit': audit, 'statuses': dict(statuses),
        'caller': 'TitanAgent.act(ordered)' if ordered else 'main.py::agent(package config)',
        'state_action_trace_sha256': trace.hexdigest(), 'planner_trace_sha256': planner_trace.hexdigest(),
        'final_routes_sha256': digest(instance.controller.R),
        'final_status': [s.status for s in state], 'reward': [s.reward for s in state],
        'raw_surplus_hand_callbacks': excess, 'clone_calls': dict(counts), 'fast_calls': dict(fast),
        'native_wall_total': sum(timings), 'native_wall_max': max(timings),
        'custody': custody, 'engine_sha256': engine_hashes, 'python': sys.version}


def microbenchmark(root, helper_path, rounds=9):
    vendor = load('_tapeport_benchmark_routes', root/'reference/next-panel/vendor/arlene.py')
    helper = load('_tapeport_benchmark_helper', helper_path)
    if port.blob(helper_path.read_bytes()) != port.HELPER_BLOB:
        raise ValueError('helper pin mismatch')
    rows = [a for tape in vendor.routes().values() for a in tape]
    samples = {'deepcopy': [], 'existing_helper': []}
    functions = [('deepcopy', copy.deepcopy), ('existing_helper', helper.apply_fast_tape_clone)]
    for i in range(rounds):
        for name, function in (functions if i % 2 == 0 else functions[::-1]):
            start = time.perf_counter()
            result = [function(a) for a in rows]
            samples[name].append(time.perf_counter()-start)
            if result != rows:
                raise AssertionError('benchmark output mismatch')
    return {'scope': 'native 4x720 route-action corpus, alternating order; not whole-agent speed',
        'actions': len(rows), 'rounds': rounds, 'seconds': samples,
        'median_ratio': statistics.median(samples['deepcopy'])/statistics.median(samples['existing_helper'])}


def verify(root, helper, output, seeds, steps, audit, ordered=False):
    source_custody = authenticate(root)
    with tempfile.TemporaryDirectory(prefix='tapeport-proof-') as tmp:
        tmp = Path(tmp)
        candidate = tmp/'on'
        postimages = port.stage(root, candidate, helper, enabled=True)
        cases = []
        for index, (seed, seat) in enumerate((s,t) for s in seeds for t in (0,1)):
            result = {}
            order = [('base', root), ('candidate', candidate)]
            for label, package in (order if index % 2 == 0 else order[::-1]):
                target = tmp/(str(seed)+'-'+str(seat)+'-'+label+'.json')
                cmd = [sys.executable] + (['-O'] if sys.flags.optimize else []) + [
                    str(Path(__file__).resolve()), '--child', str(package), '--seed', str(seed),
                    '--seat', str(seat), '--steps', str(steps), '--output', str(target)]
                if audit:
                    cmd.append('--audit')
                if ordered:
                    cmd.append('--ordered')
                run = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
                if run.returncode:
                    raise RuntimeError(run.stdout+run.stderr)
                result[label] = json.loads(target.read_text())
            for key in ('state_action_trace_sha256', 'planner_trace_sha256', 'final_routes_sha256',
                        'reward', 'statuses', 'calls', 'final_status', 'raw_surplus_hand_callbacks'):
                if result['base'][key] != result['candidate'][key]:
                    raise AssertionError((seed, seat, key, result))
            cases.append(result)
            print(json.dumps({'seed': seed, 'seat': seat, 'identical': True,
                'calls': result['base']['calls'], 'clones': sum(result['candidate']['clone_calls'].values())}), flush=True)
        report = {'scope': 'artifact b567 checked release plus 3 staged consumer modules; not all current V4',
            'source_custody': source_custody, 'postimages': postimages, 'cases': cases,
            'microbenchmark': microbenchmark(root, helper), 'python': sys.version,
            'optimized': bool(sys.flags.optimize)}
        output.write_text(json.dumps(report, indent=2)+'\n')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path)
    p.add_argument('--child', type=Path)
    p.add_argument('--helper', type=Path, default=Path(__file__).with_name('r04_fast_tape_clone.py'))
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--seed', type=int, default=9922999)
    p.add_argument('--seeds', default='9922999,2027')
    p.add_argument('--seat', type=int, choices=(0,1), default=0)
    p.add_argument('--steps', type=int, default=720)
    p.add_argument('--audit', action='store_true')
    p.add_argument('--ordered', action='store_true', help='direct actual ordered runtime; not package entrypoint')
    a = p.parse_args()
    if a.child:
        a.output.write_text(json.dumps(episode(a.child, a.seed, a.seat, a.steps, a.audit, a.ordered), indent=2)+'\n')
    elif a.root:
        verify(a.root.resolve(), a.helper.resolve(), a.output,
               [int(s) for s in a.seeds.split(',')], a.steps, a.audit, a.ordered)
    else:
        p.error('--root or --child required')
