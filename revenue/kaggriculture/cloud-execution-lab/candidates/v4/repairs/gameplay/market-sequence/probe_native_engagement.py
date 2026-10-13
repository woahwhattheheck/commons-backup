# SPDX-License-Identifier: Apache-2.0
"""Observe, never apply, stockless compaction on an exact artifact-native panel.

The artifact's entrypoint FACTORY is used, not its full agent/outer timer. This
is an engagement census against PASS, not an archive/hosted or economic gate.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import stockless_pressure as candidate
import test_stockless_pressure as checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--seed', type=int, required=True)
    parser.add_argument('--seat', type=int, choices=(0, 1), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.runtime.resolve()
    checks.ROOT = root
    checks.Contracts.setUpClass()
    raw = (root/'main.py').read_bytes()
    if checks.git_blob(raw) != '2e70a9e730eebab94ab16420ae601f3c46663af8':
        raise RuntimeError('artifact entrypoint fixture changed; not the declared panel')
    features = json.loads((root/'TITAN-CONFIG.json').read_text())
    if checks.git_blob((root/'TITAN-CONFIG.json').read_bytes()) != '3a3bef83899d3010fad623b628d9e95d9978111b':
        raise RuntimeError('feature fixture changed')
    entry = checks.load('_stockless_artifact_entry_factory', root/'main.py')
    instance = entry._new_instance(root, features)
    e, S = checks.Contracts.engine, checks.Contracts.ev.Struct
    cfg = S({key: val.get('default') if isinstance(val, dict) else val
             for key, val in e.specification['configuration'].items()})
    cfg.seed = args.seed
    env = S(configuration=cfg, done=False, info={})
    state = [S(observation=S(), action={}, status='ACTIVE', reward=0) for _ in (0, 1)]
    e.interpreter(state, env)
    opportunities, statuses, traces = [], {}, hashlib.sha256()
    sampled = examined = 0
    started = time.perf_counter()
    try:
        for step in range(cfg.episodeSteps):
            for s in state:
                s.observation.step = step
            obs = copy.deepcopy(state[args.seat].observation)
            out = instance.act(obs, cfg)
            status = instance.diagnostics.get('status', 'missing')
            statuses[status] = statuses.get(status, 0)+1
            returned = copy.deepcopy(out)
            state[args.seat].action = out
            state[1-args.seat].action = checks.action()
            if status == 'completed' and candidate._prefix(out.get('market'), cfg) is not None:
                examined += 1
                _, private = checks.Contracts.scheduler.post_units(obs, out, cfg)
                rows = candidate.compact_stockless_sales(out['market'], private['shed'], obs['market'],
                                                         cfg, quote=e.market_price)
                if rows != out['market']:
                    opportunities.append({'step': step, 'shed': private['shed'],
                                          'original': returned, 'candidate_market': rows})
            if out != returned:
                raise RuntimeError('observational probe mutated action')
            traces.update(json.dumps({'step': step, 'action': out}, sort_keys=True).encode()+b'\n')
            sampled += 1
            e.interpreter(state, env)
            if step % 120 == 0:
                print(json.dumps({'step': step, 'opportunities': len(opportunities),
                                  'seconds': time.perf_counter()-started}), flush=True)
            if any(s.status == 'DONE' for s in state):
                break
    finally:
        report = {'scope': 'artifact10123395668 native factory vs PASS; no outer entrypoint/hosted/economic claim',
                  'seed': args.seed, 'seat': args.seat, 'feature_data': features,
                  'callbacks': sampled, 'eligible_prefix_callbacks': examined,
                  'opportunity_count': len(opportunities), 'opportunities': opportunities,
                  'statuses': statuses, 'trace_sha256': traces.hexdigest(),
                  'terminal_reached': all(s.status == 'DONE' for s in state),
                  'cash': [f['money'] for f in state[0].observation.farms],
                  'source_git_blobs': dict(checks.PINNED, **{'main.py': checks.git_blob(raw)}),
                  'seconds': time.perf_counter()-started}
        args.output.write_text(json.dumps(report, sort_keys=True, indent=2)+'\n')
        print(json.dumps({k: v for k,v in report.items() if k not in ('source_git_blobs','opportunities','feature_data')}), flush=True)


if __name__ == '__main__':
    main()
