# SPDX-License-Identifier: Apache-2.0
"""Execute one source-authenticated full native S1 OFF/ON starter game.

Use a separate process for each arm/seat/seed. This is not Riot's hardened gate.
No network retrieval, simulated parents, suppressed raw action rows, or archive writes.
"""
from __future__ import annotations
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

from native_s1_experiment import install, assess

ARCHIVE_SOURCE_SHA256 = 'e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2'
ENGINE_BLOBS = {'kaggriculture.py': '3c202c7ee921da239356789e266b694635103fc4',
                'kaggriculture.json': 'b354d06b742fe48402513792253f1a5c29366b20',
                'utils.py': '91c8822ee6201ba4a5a8416c7dbe34f95dd61c87'}


def git_hash(raw):
    return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()


def authenticate(root):
    raw = (root/'SOURCE.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != ARCHIVE_SOURCE_SHA256:
        raise ValueError('wrong native source manifest')
    manifest = json.loads(raw)
    for path, record in manifest['runtime'].items():
        data = (root/path).read_bytes()
        if len(data) != record['bytes'] or hashlib.sha256(data).hexdigest() != record['sha256']:
            raise ValueError('native input drift: '+path)
    for path, wanted in ENGINE_BLOBS.items():
        if git_hash((root/'checks/reference/engine'/path).read_bytes()) != wanted:
            raise ValueError('engine drift: '+path)
    return len(manifest['runtime'])


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def run(root, seed, seat, enabled):
    count = authenticate(root)
    loader = load(root/'checks/reference/evaluator/loader.py', '_s1_engine_loader')
    engine, engine_hashes = loader.get_engine(root/'checks/reference/engine')
    native = load(root/'main.py', '_s1_native_entry')
    cfg = loader.Struct()
    for key, value in engine.specification['configuration'].items():
        cfg[key] = value.get('default') if isinstance(value, dict) else value
    cfg.seed = seed
    env = loader.Struct(configuration=cfg, done=False, info={})
    state = [loader.Struct(observation=loader.Struct(), action={}, status='ACTIVE', reward=0) for _ in range(2)]
    engine.interpreter(state, env)
    def tapes_of():
        instance = native._INSTANCE
        controller = getattr(instance, 'controller', None)
        routes = getattr(controller, 'R', None)
        if isinstance(routes, dict):
            return list(routes.values())
        return None
    agent = install(native.agent, tapes_of, enabled=enabled)
    history, observations, changes, daily, statuses = [], [], [], [], Counter()
    elapsed = []
    selected_census, all_census = Counter(), Counter()
    selected_only = []
    for step in range(cfg.episodeSteps):
        for i, s in enumerate(state):
            s.observation.step = step
            if i == seat:
                obs = deepcopy(s.observation)
                started = time.perf_counter()
                output = agent(obs, cfg)
                elapsed.append(time.perf_counter()-started)
                controller = getattr(native._INSTANCE, 'controller', None)
                routes = getattr(controller, 'R', {})
                current = getattr(controller, 'cur', None)
                selected_tape = routes.get(current) if isinstance(routes, dict) else None
                sg = assess(obs, output, cfg, [selected_tape])
                ag = assess(obs, output, cfg, tapes_of())
                selected_census[sg.reason] += 1
                all_census[ag.reason] += 1
                if sg.allowed and not ag.allowed:
                    selected_only.append({'step': step, 'all_tapes_reason': ag.reason})
                instance = native._INSTANCE
                diagnostics = getattr(instance, 'diagnostics', {})
                statuses[diagnostics.get('status', 'missing')] += 1
                report = getattr(agent, 'report', {})
                if report.get('admissions', 0) > len(changes):
                    changes.append({'step': step, 'money': obs['farms'][seat]['money'],
                                    'hires_today': obs['farms'][seat]['hires_today'],
                                    'hands': len(obs['farms'][seat]['hands']),
                                    'price': obs['market']['prices']['FERTILIZER'], 'action': output})
                history.append(deepcopy(output))
            else:
                output = engine.starter_agent(deepcopy(s.observation))
            s.action = output
        # No 'helpful' action repair/truncation: the complete real engine receives it.
        engine.interpreter(state, env)
        observations.append(digest([{'observation': s.observation, 'status': s.status, 'reward': s.reward} for s in state]))
        if step%24 == 23 or any(s.status == 'DONE' for s in state):
            daily.append({'step': step, 'money': state[seat].observation.farms[seat]['money'],
                          'shed': deepcopy(state[seat].observation.private['shed'])})
        if any(s.status == 'DONE' for s in state):
            break
    return {'seed': seed, 'seat': seat, 'enabled': enabled, 'steps': step+1,
            'runtime_members_authenticated': count, 'source_manifest_sha256': ARCHIVE_SOURCE_SHA256,
            'engine_sha256': engine_hashes, 'bank': [s.reward for s in state],
            'margin': state[seat].reward-state[1-seat].reward,
            'statuses': dict(statuses), 'state_trace_sha256': digest(observations),
            'action_trace_sha256': digest(history), 'max_call_seconds': max(elapsed),
            'sum_call_seconds': sum(elapsed), 'report': getattr(agent, 'report', {}),
            'selected_tape_census': dict(selected_census), 'all_tapes_census': dict(all_census),
            'selected_only_admissions': selected_only,
            'admissions': changes, 'daily': daily, 'final_status': [s.status for s in state]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--seed', type=int, required=True)
    parser.add_argument('--seat', type=int, choices=(0,1), required=True)
    parser.add_argument('--enabled', action='store_true')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.runtime.resolve(), args.seed, args.seat, args.enabled)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('daily','engine_sha256')}, sort_keys=True))
