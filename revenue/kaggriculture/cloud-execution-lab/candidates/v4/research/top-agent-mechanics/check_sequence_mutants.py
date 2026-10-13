#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run isolated behavioral negative controls; no error-only or empty-run credit."""
from __future__ import annotations
import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
MUTANTS = [
    ('skip_ambiguity', 'sequence_contract.py', '            previous.clear()', '            pass'),
    ('csv_market_order', 'sequence_contract.py', 'sorted(group, key=lambda e: e.slot)', 'group'),
    ('merge_actors', 'sequence_contract.py', 'actor_steps[str(actor)][event.step]', 'actor_steps["all"][event.step]'),
    ('skip_unknown_actor', 'sequence_contract.py', 'sorted(set(timeline) | barriers)', 'sorted(timeline)'),
    ('merge_seats', 'sequence_contract.py', '(event.team, event.match, event.player, event.source)',
     '(event.team, event.match, "all", event.source)'),
    ('invent_missing_seat', 'sequence_contract.py', 'if _known(event.player):', 'if True:'),
    ('merge_selfplay_counts', 'mine_top_mechanics.py', '(event.team, event.match, event.player)].append(event)',
     '(event.team, event.match, "all")].append(event)'),
]


def run() -> dict:
    report = {}
    names = ['mine_top_mechanics.py', 'sequence_contract.py',
             'test_sequence_contract.py', 'test_top_mechanics.py']
    original = {name: (HERE/name).read_text() for name in names}
    for mode in ('normal', 'optimized'):
        rows = []
        for label, filename, before, after in MUTANTS:
            if original[filename].count(before) != 1:
                raise ValueError('mutant source drift: ' + label)
            with tempfile.TemporaryDirectory(prefix='replay-order-mutant-') as td:
                root = Path(td)
                for name, text in original.items():
                    (root/name).write_text(text.replace(before, after, 1) if name == filename else text)
                cmd = [sys.executable] + (['-O'] if mode == 'optimized' else [])
                result = subprocess.run(cmd + ['-m', 'unittest', 'test_sequence_contract', 'test_top_mechanics'],
                                        cwd=root, text=True, capture_output=True, timeout=30)
                log = result.stdout + result.stderr
                count = re.search(r'Ran (\d+) tests?', log)
                failed = re.search(r'FAILED \(failures=(\d+)\)', log)
                killed = result.returncode != 0 and count is not None and int(count[1]) == 29 and failed is not None
                rows.append({'mutant': label, 'killed_by_assertion': killed, 'returncode': result.returncode,
                             'tests_run': int(count[1]) if count else None, 'log': log})
                if not killed:
                    raise RuntimeError(f'{mode}/{label}: invalid negative control\n{log}')
        report[mode] = rows
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(run(), indent=2, sort_keys=True) + '\n')
