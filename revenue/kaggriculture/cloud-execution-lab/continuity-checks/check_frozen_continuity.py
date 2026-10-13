# SPDX-License-Identifier: Apache-2.0
"""Compare the canonical frozen control with retained SELL actions and state.

This consumes saved own observations, not an interpreter or rival actor. Each
cell runs in a fresh process with two persistent real policies. No method body
is replaced. Detailed outputs belong with the private retained-data evidence.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import zipfile

DELVE_SHA256 = 'aaa2d811a919b6b1c2219082753cfe476a0a0fac7567d3ad1d72c9f373a912f9'
CELLS = (
    'evaluation/pilot-completion/9965001-p0-sell',
    'evaluation/sell-seed1-p1/9965001-p1-sell',
    'evaluation/sell-seed2/9965019-p0-sell',
    'evaluation/sell-seed2/9965019-p1-sell',
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def source_map(runtime, pins):
    rows = {}
    for name, expected in pins.items():
        data = (runtime / name).read_bytes()
        actual = sha(data)
        if actual != expected:
            raise ValueError(f'source mismatch: {name}: {actual}')
        rows[name] = {'bytes': len(data), 'sha256': actual}
    return rows


def own_inputs(archive, cell):
    """Align original saved frames and telemetry, without reconstructing state."""
    result = json.loads(archive.read(cell + '.json'))
    if result['status'] != 'complete' or result['arm'] != 'sell':
        raise ValueError('expected a completed retained SELL control')
    streams = {}
    for suffix in ('.frames.jsonl.gz', '.telemetry.jsonl.gz'):
        name = cell + suffix
        raw = archive.read(name)
        meta = result['files'][Path(name).name]
        if sha(raw) != meta['sha256'] or len(raw) != meta['bytes']:
            raise ValueError('input hash/size mismatch: ' + name)
        streams[suffix] = [json.loads(line) for line in gzip.decompress(raw).splitlines()]
    frames, telemetry = streams['.frames.jsonl.gz'], streams['.telemetry.jsonl.gz']
    if len(frames) != 720 or len(telemetry) != 719:
        raise ValueError('expected the complete 0..718 prefix')
    seat, packets = result['candidate_seat'], []
    for step, item in enumerate(telemetry):
        before, after = frames[step:step + 2]
        if before['frame'] != step or after['frame'] != step + 1 or item['step'] != step:
            raise ValueError('frame/telemetry order mismatch')
        if after['state'][seat]['action'] != item['action']:
            raise ValueError('recorded frame/telemetry action mismatch')
        obs, cfg = copy.deepcopy(before['state'][seat]['observation']), copy.deepcopy(before['configuration'])
        # The original cloud evaluator supplied these same shared fields.
        obs['step'], obs['remainingOverageTime'] = step, 0
        if obs['player'] != seat or int(obs['day']) * int(cfg['turnsPerDay']) + int(obs['hour']) != step:
            raise ValueError('wrong own player or clock')
        packets.append({'observation': obs, 'configuration': cfg, 'expected': item['action']})
    if [s['reward'] for s in frames[-1]['state']] != result['scores']:
        raise ValueError('retained terminal identity mismatch')
    return packets, result


def worker(args, pins):
    runtime = args.runtime.resolve()
    sources = source_map(runtime, pins)
    sys.path.insert(0, str(runtime))
    random.seed(20260907)
    from titan_runtime import TitanAgent, Features
    from scheduler import SellScheduler, parent
    packets = json.loads(args.packets.read_text())
    reference = SellScheduler()
    candidate = TitanAgent(Features(consumer='frozen', seed=False))
    counts = {'reference_parent': 0, 'candidate_parent': 0, 'candidate_initialize': 0}
    parent_code, init_code = parent.Agent.act.__code__, TitanAgent._initialize.__code__

    def counter(frame, event, _arg):
        if event != 'call':
            return
        if frame.f_code is parent_code:
            instance = frame.f_locals['self']
            if instance is reference.controller:
                counts['reference_parent'] += 1
            elif instance is getattr(candidate, 'controller', None):
                counts['candidate_parent'] += 1
            else:
                raise AssertionError('unexpected additional producer')
        elif frame.f_code is init_code and frame.f_locals['self'] is candidate:
            counts['candidate_initialize'] += 1

    rows, issues = [], []
    fields = ('mode', 'planned', 'pending', 'previous', 'observed_harvests', 'diagnostics')
    for step, packet in enumerate(packets):
        robs, cobs = copy.deepcopy(packet['observation']), copy.deepcopy(packet['observation'])
        rcfg, ccfg = copy.deepcopy(packet['configuration']), copy.deepcopy(packet['configuration'])
        before = counts.copy()
        try:
            sys.setprofile(counter)
            try:
                expected = reference.act(robs, rcfg)
                actual = candidate.act(cobs, ccfg)
            finally:
                sys.setprofile(None)
            old_state = {name: getattr(reference, name) for name in fields}
            new_state = {name: getattr(candidate.consumer, name) for name in fields}
            checks = {
                'reference_recorded': expected == packet['expected'],
                'candidate_recorded': actual == packet['expected'],
                'complete_action': actual == expected,
                'consumer_state': new_state == old_state,
                'controller_state': vars(candidate.controller) == vars(reference.controller),
                'input_preserved': robs == cobs == packet['observation'] and rcfg == ccfg == packet['configuration'],
                'single_production': counts['reference_parent'] - before['reference_parent'] == 1
                                     and counts['candidate_parent'] - before['candidate_parent'] == 1,
                'completed': candidate.diagnostics.get('status') == 'completed',
                'persistent': candidate.ready and counts['candidate_initialize'] == 1,
            }
            issues.extend({'step': step, 'check': name} for name, ok in checks.items() if not ok)
            rows.append({'step': step, 'checks': checks, 'action_sha256': sha(encode(actual)),
                         'state_sha256': sha(encode(new_state)), 'parent_calls': candidate.diagnostics['parent_calls']})
        except BaseException as error:
            issues.append({'step': step, 'exception': type(error).__name__, 'detail': str(error)})
        if issues:
            break  # Preserve the first discrepancy; do not continue after it.
    if sources != source_map(runtime, pins):
        raise AssertionError('runtime source changed during execution')
    report = {'python': sys.version, 'decisions': len(rows), 'counts': counts, 'issues': issues,
              'rows': rows, 'sources': sources, 'features': vars(candidate.features),
              'new_games': 0, 'engine_calls': 0, 'scope': 'pinned reachable frozen-control source; not default-seed or full-archive game evidence'}
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    return int(bool(issues))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--runtime', type=Path, required=True)
    ap.add_argument('--pins', type=Path, default=Path(__file__).with_name('SOURCE-PINS.json'))
    ap.add_argument('--delve-archive', type=Path)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--cell', action='append', metavar='RETAINED_CELL',
                    help='Retained SELL record prefix; omit for the four original cells')
    ap.add_argument('--worker', action='store_true')
    ap.add_argument('--packets', type=Path)
    args = ap.parse_args()
    pins = json.loads(args.pins.read_text())
    if args.worker:
        return worker(args, pins)
    source_map(args.runtime, pins)
    if args.delve_archive is None:
        ap.error('--delve-archive is required')
    if sha(args.delve_archive.read_bytes()) != DELVE_SHA256:
        raise ValueError('wrong retained DELVE archive')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    reports = []
    with zipfile.ZipFile(args.delve_archive) as archive:
        manifest = json.loads(archive.read('MANIFEST.json'))['files']
        for name, meta in manifest.items():
            data = archive.read(name)
            if len(data) != meta['bytes'] or sha(data) != meta['sha256']:
                raise ValueError('manifest mismatch: ' + name)
        with tempfile.TemporaryDirectory(prefix='titan-continuity-') as folder:
            packet_path = Path(folder) / 'packets.json'
            for cell in args.cell or CELLS:
                packets, retained = own_inputs(archive, cell)
                packet_path.write_bytes(encode(packets))
                report_path = output / (Path(cell).name + '.json')
                if report_path.exists():
                    raise FileExistsError('preserve earlier evidence: ' + str(report_path))
                command = [sys.executable, '-B', str(Path(__file__).resolve()), '--worker',
                           '--runtime', str(args.runtime.resolve()), '--pins', str(args.pins.resolve()),
                           '--packets', str(packet_path), '--output', str(report_path)]
                env = dict(os.environ, PYTHONHASHSEED='20260907', PYTHONDONTWRITEBYTECODE='1')
                completed = subprocess.run(command, capture_output=True, text=True, env=env, timeout=90)
                (output / (Path(cell).name + '.log')).write_text(completed.stdout + completed.stderr)
                if not report_path.exists():
                    raise RuntimeError(completed.stderr)
                report = json.loads(report_path.read_text())
                report.update(retained_cell=cell, retained_trace_sha256=retained['trace_sha256'],
                              packet_sha256=sha(packet_path.read_bytes()), returncode=completed.returncode)
                report_path.write_text(json.dumps(report, indent=2) + '\n')
                compact = {k: v for k, v in report.items() if k not in ('rows', 'sources')}
                reports.append(compact)
                print(json.dumps(compact), flush=True)
    summary = {'schema': 'titan-frozen-continuity-v1', 'source_commit': '4f743f8ec29bddc36220b2169a2609fe159776e2',
               'input_archive_sha256': DELVE_SHA256, 'manifest_members': len(manifest),
               'sources': source_map(args.runtime, pins), 'cells': reports,
               'total_decisions': sum(r['decisions'] for r in reports), 'new_games': 0, 'engine_calls': 0,
               'success': all(not r['issues'] and r['returncode'] == 0 for r in reports)}
    (output / 'SUMMARY.json').write_text(json.dumps(summary, indent=2) + '\n')
    return int(not summary['success'])


if __name__ == '__main__':
    raise SystemExit(main())
