# SPDX-License-Identifier: Apache-2.0
"""Bounded, unmodified-parent shadow census; not a paired economics gate.

Use the exact canonical b567 archive. The candidate action is never executed.
Runtime/engine verification is shared with this package's pinned engine gate.
"""
from __future__ import annotations

import argparse
import copy
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

from test_native_eod_capacity_rescue import NativeEOD, ROOT, blob
from native_eod_capacity_rescue import apply_native_eod_capacity_rescue as rescue

PARENT_PINS = {
    'main.py': '4a8cf7bcda1f0fea231a144692cb84a779a9e73e',
    'titan_runtime.py': 'b952c9c228ecbde592bf3d2df01638677abb0d24',
    'TITAN-CONFIG.json': '3a3bef83899d3010fad623b628d9e95d9978111b',
}


def run(seeds, seats, output):
    for name, expected in PARENT_PINS.items():
        if blob((ROOT/name).read_bytes()) != expected:
            raise ValueError('Parent source pin mismatch: ' + name)
    NativeEOD.setUpClass()
    E, S = NativeEOD.engine, NativeEOD.ev.Struct
    plan = {'seeds': seeds, 'seats': seats, 'opponent': 'official starter_agent',
            'max_callbacks_per_game': 719, 'mode': 'unmodified_parent_shadow',
            'parent_pins': PARENT_PINS, 'projection_pins': __import__('test_native_eod_capacity_rescue').PINS,
            'engine_sha256': NativeEOD.hashes}
    Path(str(output)+'.plan.json').write_text(json.dumps(plan, indent=2)+'\n')
    packets = []
    for seed in seeds:
        for seat in seats:
            begin = time.monotonic()
            spec = importlib.util.spec_from_file_location(f'eod_parent_{seed}_{seat}', ROOT/'main.py')
            parent = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(parent)
            cfg = S({k: v.get('default') if isinstance(v, dict) else v
                     for k, v in E.specification['configuration'].items()})
            env = S(configuration=cfg, done=False, info={'seed': seed})
            state = [S(observation=S(), action={}, status='ACTIVE', reward=0) for _ in range(2)]
            E.interpreter(state, env)
            skips, statuses, eod_rows = Counter(), Counter(), []
            trace = hashlib.sha256()
            for step in range(719):
                for s in state:
                    s.observation.step = step
                observation = copy.deepcopy(state[seat].observation)
                action = parent.agent(observation, cfg)
                # Parent may decorate its private observation copy; census reads
                # the exact engine public/private preimage, not that copy.
                candidate, info = rescue(action, state[seat].observation, cfg, enabled=True)
                off, _ = rescue(action, state[seat].observation, cfg, enabled=False)
                if off is not action:
                    raise AssertionError('OFF identity failed')
                skips[info['reason']] += 1
                instance = parent._INSTANCE
                statuses[getattr(instance, 'diagnostics', {}).get('status', 'missing')] += 1
                rival = E.starter_agent(copy.deepcopy(state[1-seat].observation))
                state[seat].action = action
                state[1-seat].action = rival
                raw = {'step': step, 'parent': action, 'rival': rival, 'diagnostic': info}
                trace.update(json.dumps(raw, sort_keys=True, separators=(',', ':')).encode()+b'\n')
                if step <= 695 and step % 24 == 23:
                    row = {'step': step, 'diagnostic': info, 'action': action,
                           'shed': dict(state[seat].observation.private['shed']),
                           'inventories': copy.deepcopy(state[seat].observation.private['inventories'])}
                    if info['changed']:
                        row.update(candidate=candidate, observation=copy.deepcopy(state[seat].observation))
                    eod_rows.append(row)
                E.interpreter(state, env)
                if step % 120 == 119:
                    print(f'seed={seed} seat={seat} callbacks={step+1} elapsed={time.monotonic()-begin:.2f}', flush=True)
                if state[seat].status == 'DONE':
                    break
            banks = [f['money'] for f in state[0].observation.farms]
            packet = {'seed': seed, 'seat': seat, 'callbacks': step+1,
                      'complete': state[seat].status == 'DONE', 'skip_reasons': dict(skips),
                      'parent_statuses': dict(statuses), 'eod_rows': eod_rows,
                      'terminal_banks': banks, 'parent_margin': banks[seat]-banks[1-seat],
                      'action_diagnostic_sha256': trace.hexdigest(),
                      'wall_seconds': time.monotonic()-begin}
            packets.append(packet)
            Path(output).write_text(json.dumps({'plan': plan, 'games': packets,
                    'complete': len(packets)==len(seeds)*len(seats)}, indent=2)+'\n')
            print(json.dumps({k:v for k,v in packet.items() if k!='eod_rows'}), flush=True)
    return packets


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--seeds', nargs='+', type=int, default=[9120701, 9120702])
    parser.add_argument('--seats', nargs='+', type=int, choices=(0, 1), default=[0, 1])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if len(set(args.seeds)) != len(args.seeds) or len(set(args.seats)) != len(args.seats):
        parser.error('duplicate cells are not allowed')
    run(args.seeds, args.seats, args.output)
