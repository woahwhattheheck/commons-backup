# SPDX-License-Identifier: Apache-2.0
"""Replay retained observations through the pinned native file-agent loader."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import time
from runtime import HERE, load


def verify(entry, fixture):
    loader = load(HERE / 'vendor/cloud-pack/official.py', 't14_native_loader')
    configuration = json.loads((HERE / 'vendor/engine/kaggriculture.json').read_text())['configuration']
    configuration = {k: v.get('default') if isinstance(v, dict) else v
                     for k, v in configuration.items()}
    configuration.update(seed=None, episodeSteps=720, __raw_path__=str(entry.resolve()))
    actor = loader.make_agent(entry)
    times, mismatches = [], []
    with gzip.open(fixture, 'rt') as trace:
        for line in trace:
            row = json.loads(line)
            started = time.perf_counter()
            action = actor(row['observation'], configuration)
            times.append(time.perf_counter() - started)
            if action != row['actions'][row['candidate_seat']]:
                mismatches.append(row['step'])
    return {'method': 'pinned native file-agent loader on retained observations',
            'entry': entry.name, 'entry_sha256': hashlib.sha256(entry.read_bytes()).hexdigest(),
            'observations': len(times), 'mismatched_steps': mismatches,
            'max_call_seconds': max(times), 'first_call_seconds': times[0],
            'new_games': 0, 'fixture': str(fixture.relative_to(HERE)),
            'fixture_sha256': hashlib.sha256(fixture.read_bytes()).hexdigest()}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--entry', type=Path, required=True)
    p.add_argument('--fixture', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    receipt = verify(a.entry.resolve(), a.fixture.resolve())
    a.output.write_text(json.dumps(receipt, indent=2) + '\n')
    if receipt['mismatched_steps']:
        raise SystemExit('Native-loader actions differ from retained trajectory')
    print(json.dumps(receipt))
