#!/usr/bin/env python3
"""SELL entrypoint clock regression and optional retained-prefix comparison.

The unit seam executes the original scheduler.agent function with a recording
scheduler. The optional prefix check runs the complete original vendor policy
in fresh processes, not a recording replacement or a new engine/game panel.
"""
from __future__ import annotations
import argparse
import ast
import copy
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import zipfile

HERE = Path(__file__).resolve().parent
ARM = HERE / 'arms/sell.py'
ORIGINAL = ("from pathlib import Path\nimport sys\n"
            "sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vendor/sell'))\n"
            "from scheduler import agent\n")
SOURCE_OVERRIDE = None


def digest(value):
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def load_arm(source=None):
    module = types.ModuleType('sell_clock_entrypoint')
    module.__file__ = str(ARM)
    exec(compile(ARM.read_text() if source is None else source, str(ARM), 'exec'), module.__dict__)
    return module


class ClockCases(unittest.TestCase):
    def setUp(self):
        scheduler = types.ModuleType('scheduler')
        scheduler._INSTANCE = None
        scheduler.constructed = []
        scheduler.calls = []

        class RecordingScheduler:
            def __init__(self):
                scheduler.constructed.append(self)
                self.count = 0

            def act(self, observation, configuration):
                # The real scheduler requires step internally as well as at reset.
                step = int(observation['step'])
                self.count += 1
                scheduler.calls.append((observation, configuration))
                return {'step': step, 'count': self.count}

        scheduler.SellScheduler = RecordingScheduler
        vendor = HERE / 'vendor/sell/scheduler.py'
        tree = ast.parse(vendor.read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'agent')
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(vendor), 'exec'), scheduler.__dict__)
        self.original_path = sys.path[:]
        self.scheduler = scheduler
        with patch.dict(sys.modules, {'scheduler': scheduler}):
            self.arm = load_arm(SOURCE_OVERRIDE)

    def tearDown(self):
        sys.path[:] = self.original_path

    def test_explicit_step_preserves_identity_and_configuration(self):
        obs, cfg = {'step': 7, 'day': 0, 'hour': 0}, {'turnsPerDay': 99}
        self.assertEqual(self.arm.agent(obs, cfg)['step'], 7)
        self.assertIs(self.scheduler.calls[-1][0], obs)
        self.assertIs(self.scheduler.calls[-1][1], cfg)

    def test_sparse_clock_preserves_one_actor_across_day_boundary(self):
        for seat in (0, 1):
            self.scheduler._INSTANCE = None
            before = len(self.scheduler.constructed)
            for count, (day, hour) in enumerate([(0, 0), (0, 1), (0, 23), (1, 0), (1, 1)], 1):
                self.assertEqual(self.arm.agent({'day': day, 'hour': hour, 'player': seat}),
                                 {'step': day * 24 + hour, 'count': count})
            self.assertEqual(len(self.scheduler.constructed) - before, 1)

    def test_true_zero_restarts_and_positive_clock_does_not(self):
        self.arm.agent({'day': 0, 'hour': 0})
        previous = self.scheduler._INSTANCE
        self.arm.agent({'day': 1, 'hour': 0})
        self.assertIs(self.scheduler._INSTANCE, previous)
        self.assertEqual(self.arm.agent({'day': 0, 'hour': 0})['count'], 1)
        self.assertIsNot(self.scheduler._INSTANCE, previous)

    def test_none_step_uses_public_clock(self):
        self.assertEqual(self.arm.agent({'step': None, 'day': 2, 'hour': 3})['step'], 51)

    def test_custom_day_length(self):
        self.assertEqual(self.arm.agent({'day': 2, 'hour': 3}, {'turnsPerDay': 10})['step'], 23)

    def test_default_and_empty_configuration(self):
        for cfg in (None, {}):
            self.assertEqual(self.arm.agent({'day': 3, 'hour': 2}, cfg)['step'], 74)
            self.assertIs(self.scheduler.calls[-1][1], cfg)

    def test_clock_input_is_not_modified(self):
        obs = {'day': 1, 'hour': 2, 'private': {'seeds': {'CARROT': 3}}}
        before = copy.deepcopy(obs)
        self.arm.agent(obs)
        self.assertEqual(obs, before)
        self.assertIsNot(self.scheduler.calls[-1][0], obs)
        self.assertIs(self.scheduler.calls[-1][0]['private'], obs['private'])

    def test_integer_text_clock_matches_existing_integer_conversion(self):
        self.assertEqual(self.arm.agent({'day': '2', 'hour': '4'}, {'turnsPerDay': '10'})['step'], 24)

    def test_missing_clock_fails_before_constructing_scheduler(self):
        with self.assertRaises(KeyError):
            self.arm.agent({'player': 1})
        self.assertEqual(self.scheduler.constructed, [])

    def test_malformed_clock_fails_before_constructing_scheduler(self):
        with self.assertRaises(ValueError):
            self.arm.agent({'day': 'bad', 'hour': 0})
        self.assertEqual(self.scheduler.constructed, [])

    def test_explicit_zero_retains_original_reset_contract(self):
        obs = {'step': 0, 'day': 10, 'hour': 2}
        self.arm.agent(obs)
        previous = self.scheduler._INSTANCE
        self.assertEqual(self.arm.agent(obs)['step'], 0)
        self.assertIsNot(self.scheduler._INSTANCE, previous)
        self.assertIs(self.scheduler.calls[-1][0], obs)


def unit_result(source):
    global SOURCE_OVERRIDE
    SOURCE_OVERRIDE = source
    output = io.StringIO()
    result = unittest.TextTestRunner(stream=output, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(ClockCases))
    return {'test_methods': result.testsRun, 'failures': len(result.failures),
            'errors': len(result.errors), 'successful': result.wasSuccessful(),
            'log': output.getvalue()}


def prefix_worker(args):
    random.seed(20260907 + args.seat)
    with zipfile.ZipFile(args.archive) as archive:
        frames = [json.loads(line) for line in gzip.decompress(archive.read(args.member)).splitlines()]
    count = min(args.steps, len(frames) - 1)
    arm = load_arm(ORIGINAL if args.mode in ('original_explicit', 'original_sparse') else None)
    scheduler = sys.modules['scheduler']
    actions, states, identities = [], [], []
    for step, frame in enumerate(frames[:count]):
        obs = copy.deepcopy(frame['state'][args.seat]['observation'])
        obs['remainingOverageTime'] = 0
        if args.mode == 'original_explicit':
            obs['step'] = step
        else:
            obs.pop('step', None)
        cfg = copy.deepcopy(frame['configuration'])
        before = canonical([obs, cfg])
        try:
            action = arm.agent(obs, cfg)
        except Exception as exc:
            print(json.dumps({'status': 'error', 'step': step, 'error_type': type(exc).__name__,
                              'completed_calls': len(actions)}))
            return 2
        if canonical([obs, cfg]) != before:
            raise AssertionError(f'Caller input changed at {step}')
        actions.append(action)
        identities.append(id(scheduler._INSTANCE))
        actor = scheduler._INSTANCE
        states.append({'pending': copy.deepcopy(actor.pending), 'planned': copy.deepcopy(actor.planned),
                       'observed_harvests': copy.deepcopy(actor.observed_harvests),
                       'diagnostics': copy.deepcopy(actor.diagnostics)})
    print(json.dumps({'status': 'complete', 'seat': args.seat, 'calls': len(actions),
                      'one_persistent_actor': len(set(identities)) == 1,
                      'actions': actions, 'states': states}, sort_keys=True))
    return 0


def compare_prefix(args):
    cases = []
    def execute(mode, seat, count):
        env = dict(os.environ, PYTHONHASHSEED=str(20260907 + seat))
        command = [sys.executable, '-B', str(Path(__file__).resolve()), '--worker',
                   '--arm', str(ARM), '--archive', str(args.archive), '--member', args.member,
                   '--mode', mode, '--seat', str(seat), '--steps', str(count)]
        run = subprocess.run(command, env=env, capture_output=True, text=True, timeout=120)
        if run.returncode not in (0, 2):
            raise RuntimeError(run.stderr)
        return json.loads(run.stdout)
    negative = execute('original_sparse', 1, 1)
    if negative != {'status': 'error', 'step': 0, 'error_type': 'KeyError', 'completed_calls': 0}:
        raise AssertionError(f'Unexpected old-source negative: {negative}')
    for seat in (0, 1):
        original = execute('original_explicit', seat, args.steps)
        repaired = execute('repaired_sparse', seat, args.steps)
        if original.get('status') != 'complete' or repaired.get('status') != 'complete':
            raise AssertionError({'original': original, 'repaired': repaired})
        action_parity = original['actions'] == repaired['actions']
        state_parity = original['states'] == repaired['states']
        persistent = original['one_persistent_actor'] and repaired['one_persistent_actor']
        cases.append({'seat': seat, 'calls_per_arm': original['calls'],
                      'action_parity': action_parity, 'scheduler_state_parity': state_parity,
                      'one_persistent_actor_per_arm': persistent,
                      'actions_sha256': digest(canonical(original['actions'])),
                      'scheduler_states_sha256': digest(canonical(original['states']))})
        if not all((action_parity, state_parity, persistent)):
            raise AssertionError(cases[-1])
    return {'kind': 'clock correspondence on retained observations; not a game or profiler',
            'original_sparse_failure': negative, 'cases': cases,
            'successful_policy_calls': sum(c['calls_per_arm'] * 2 for c in cases),
            'expected_failed_old_source_calls': 1, 'engine_calls': 0, 'new_games': 0,
            'archive_sha256': digest(args.archive.read_bytes()), 'member': args.member,
            'python': sys.version, 'actor_seed_by_seat': [20260907, 20260908]}


def main():
    global ARM
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm', type=Path, default=ARM)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--member', default='evaluation/pilot/9965001-p0-control.frames.jsonl.gz')
    parser.add_argument('--steps', type=int, default=72)
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--mode', choices=['original_explicit', 'original_sparse', 'repaired_sparse'])
    parser.add_argument('--seat', type=int, choices=[0, 1], default=0)
    args = parser.parse_args()
    ARM = args.arm.resolve()
    if args.steps <= 0:
        parser.error('--steps must be positive')
    if args.worker:
        if args.archive is None or args.mode is None:
            parser.error('worker requires archive and mode')
        return prefix_worker(args)
    result = {'original_unit': unit_result(ORIGINAL), 'repaired_unit': unit_result(None),
              'original_arm_sha256': digest(ORIGINAL.encode()),
              'repaired_arm_sha256': digest(ARM.read_bytes()),
              'test_sha256': digest(Path(__file__).read_bytes()),
              'vendor_files_sha256': {p.relative_to(HERE).as_posix(): digest(p.read_bytes())
                  for p in sorted((HERE / 'vendor/sell').rglob('*')) if p.is_file() and '__pycache__' not in p.parts}}
    if args.archive is not None:
        result['actual_prefix'] = compare_prefix(args)
    result['successful'] = result['repaired_unit']['successful']
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({key: result[key] for key in ('successful', 'original_arm_sha256', 'repaired_arm_sha256')}, sort_keys=True))
    for label in ('original_unit', 'repaired_unit'):
        print(label, {k: v for k, v in result[label].items() if k != 'log'})
    if 'actual_prefix' in result:
        print(json.dumps(result['actual_prefix'], sort_keys=True))
    return 0 if result['successful'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
