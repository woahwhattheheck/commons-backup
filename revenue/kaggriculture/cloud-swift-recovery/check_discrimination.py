# SPDX-License-Identifier: Apache-2.0
"""Prove that the retained recovery checks detect deliberately broken behavior.

The four mutations apply only to one temporary actor instance in this process.
No package bytes are edited. An assertion for the named defect is the expected
success of each negative control; it is not a defect in the shipped package.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import sys
import traceback
from check_recovery_contract import run_case
from profile_retained import retained_calls


def shallow_fallback(subject, T):
    def remember(obs):
        subject._seller_fallback_observations.append(
            T.TitanAgent._seller_public_observation(obs, copy_tiles=False))
    subject._remember_seller_fallback = remember


def drop_completed_plan(subject, T):
    restore = subject._restore_seller_state
    def restore_without_plan():
        restore()
        subject.consumer.planned.clear()
        subject.consumer.pending.clear()
    subject._restore_seller_state = restore_without_plan


def omit_fallback_replay(subject, T):
    restore = subject._restore_seller_state
    def restore_without_replay():
        subject._seller_fallback_observations.clear()
        restore()
    subject._restore_seller_state = restore_without_replay


def duplicate_fallback_queue(subject, T):
    def remember(obs):
        subject._seller_fallback_observations.append(
            T.TitanAgent._seller_public_observation(obs))
    subject._remember_seller_fallback = remember


CONTROLS = [
    ('shallow_fallback_snapshot', 'after_transform', shallow_fallback,
     'reconstructed SELL state differs'),
    ('discard_completed_plan', 'after_transform', drop_completed_plan,
     'reconstructed SELL state differs'),
    ('omit_public_fallback_replay', 'after_transform', omit_fallback_replay,
     'reconstructed SELL state differs'),
    ('duplicate_same_step_queue', 'prelude_duplicate', duplicate_fallback_queue,
     'repeated step was queued twice'),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--trace', type=Path, required=True)
    parser.add_argument('--seat', type=int, choices=(0, 1), required=True)
    parser.add_argument('--fault-step', type=int, default=436)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.fault_step < 718:
        parser.error('fault-step must be 1..717')
    rows = retained_calls(args.trace, args.seat)
    specification = json.loads((args.root/'checks/reference/engine/kaggriculture.json').read_text())
    cfg = {k: v.get('default') if isinstance(v, dict) else v
           for k, v in specification['configuration'].items()}
    cfg['seed'] = None
    sys.path.insert(0, str(args.root.resolve()))
    T = importlib.import_module('titan_runtime')
    features = T.Features(**json.loads((args.root/'TITAN-CONFIG.json').read_text()))
    results = []
    for name, mode, mutation, expected in CONTROLS:
        row = {'case': name, 'fault_step': args.fault_step, 'seat': args.seat,
               'deliberate_test_only_mutation': True, 'new_games': 0}
        try:
            run_case(T, features, rows, cfg, args.seat, args.fault_step,
                     mode, 1, mutate_subject=mutation)
        except AssertionError as exc:
            row.update(caught=expected in str(exc), assertion=str(exc))
        except Exception as exc:
            row.update(caught=False, error=str(exc), traceback=traceback.format_exc())
        else:
            row.update(caught=False, error='The deliberately broken behavior was not detected')
        results.append(row)
        print(json.dumps(row), flush=True)
    report = {'schema': 1, 'kind': 'deliberate_negative_controls', 'new_games': 0,
              'package_modified': False,
              'trace_sha256': hashlib.sha256(args.trace.read_bytes()).hexdigest(),
              'runtime_sha256': hashlib.sha256((args.root/'titan_runtime.py').read_bytes()).hexdigest(),
              'results': results, 'passed': all(row['caught'] for row in results)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
