# SPDX-License-Identifier: Apache-2.0
"""Public-clock and raw-file checks for the existing same-actor seed consumer.

Loads actual frozen policies and saved observations. This suite runs no engine,
new game, prior test suite, or external request. --source-dir can supply the
three earlier entry files for a source-bound negative run.
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
import unittest
from unittest.mock import patch

ROOT = None
T13 = None
S = None
ARMS = None
CAPITAL = None
FRAMES = {}
SOURCE_BYTES = {}
COUNTS = {'parent_calls': 0, 'capital_calls': 0, 'compared_actions': 0}
RECEIPTS = []


def load(path, name, data=None):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    exec(compile(path.read_bytes() if data is None else data, str(path), 'exec'), module.__dict__)
    return module


def observation(seat=0, step=0, *, sparse=False, null=False):
    frame = FRAMES[seat][step]
    obs = deepcopy(frame['state'][seat]['observation'])
    obs.update(step=step, remainingOverageTime=0)
    if sparse:
        obs.pop('step')
    if null:
        obs['step'] = None
    return obs, deepcopy(frame['configuration'])


def checked_call(run, obs, cfg):
    before = deepcopy((obs, cfg))
    with patch.object(run.policy, 'act', wraps=run.policy.act) as called:
        result = run(obs, cfg)
    if called.call_count != 1:
        raise AssertionError(f'Expected one original policy call, got {called.call_count}')
    COUNTS['parent_calls'] += called.call_count
    if (obs, cfg) != before:
        raise AssertionError('Caller observation or configuration changed')
    return result


def compare_state(a, b):
    def state(run):
        scheduler = getattr(run.policy, 'scheduler', run.policy)
        return {
            'route': run.controller.cur,
            'planned': getattr(scheduler, 'planned', None),
            'pending': getattr(scheduler, 'pending', None),
            'previous': getattr(scheduler, 'previous', None),
            'observed_harvests': getattr(scheduler, 'observed_harvests', None),
            'budget_events': run.budget.events,
            'funding': run.seed_funding,
        }
    if state(a) != state(b):
        raise AssertionError('Live controller, SELL history, or seed state differs')


class ClockTests(unittest.TestCase):
    def setUp(self):
        S._policy = None
        ARMS._INSTANCES.clear()
        CAPITAL._INSTANCES.clear()

    def test_direct_factory_normalizes_both_positions_before_parent(self):
        for seat in (0, 1):
            explicit, sparse = S.make_agent(T13), S.make_agent(T13)
            for step in (0, 1, 2):
                obs, cfg = observation(seat, step)
                other, _ = observation(seat, step, sparse=True)
                self.assertEqual(checked_call(explicit, obs, cfg), checked_call(sparse, other, cfg))
                compare_state(explicit, sparse)
                COUNTS['compared_actions'] += 1

    def test_seed_disabled_still_normalizes_for_actual_parent(self):
        for seat in (0, 1):
            run = S.make_agent(T13, enabled=False)
            obs, cfg = observation(seat, sparse=True)
            self.assertEqual(checked_call(run, obs, cfg), FRAMES[seat][1]['state'][seat]['action'])

    def test_null_step_uses_public_day_hour(self):
        a, b = S.make_agent(T13), S.make_agent(T13)
        obs, cfg = observation(step=100)
        other, _ = observation(step=100, null=True)
        self.assertEqual(checked_call(a, obs, cfg), checked_call(b, other, cfg))
        compare_state(a, b)

    def test_explicit_step_has_priority(self):
        run = S.make_agent(T13, enabled=False)
        obs, cfg = observation(step=2)
        obs['day'], obs['hour'] = 99, 99
        with patch.object(run.policy, 'act', wraps=run.policy.act) as called:
            run(obs, cfg)
        self.assertEqual(called.call_count, 1)
        self.assertEqual(called.call_args.args[0]['step'], 2)
        self.assertEqual(obs['step'], 2)

    def test_custom_turns_per_day_reaches_same_actual_policy(self):
        a, b = S.make_agent(T13), S.make_agent(T13)
        obs, cfg = observation(step=100)
        cfg['turnsPerDay'] = 50
        obs['day'], obs['hour'] = 2, 0
        sparse = deepcopy(obs); sparse.pop('step')
        self.assertEqual(checked_call(a, obs, cfg), checked_call(b, sparse, cfg))
        compare_state(a, b)

    def test_none_configuration_uses_default_period(self):
        a, b = S.make_agent(T13), S.make_agent(T13)
        obs, _ = observation(step=25)
        other, _ = observation(step=25, sparse=True)
        self.assertEqual(checked_call(a, obs, None), checked_call(b, other, None))
        compare_state(a, b)

    def test_plain_arlene_keeps_one_argument_and_one_call(self):
        a, b = S.make_agent(T13, sell=False), S.make_agent(T13, sell=False)
        obs, cfg = observation()
        other, _ = observation(sparse=True)
        expected = checked_call(a, obs, cfg)
        with patch.object(b.policy, 'act', wraps=b.policy.act) as called:
            result = b(other, cfg)
        self.assertEqual(called.call_count, 1)
        self.assertEqual(len(called.call_args.args), 1)
        self.assertEqual(called.call_args.args[0]['step'], 0)
        self.assertEqual(result, expected)
        self.assertNotIn('step', other)
        COUNTS['parent_calls'] += 1

    def test_singleton_retains_actor_for_nonzero_sparse_calls(self):
        with patch.object(S, 'make_agent', wraps=S.make_agent) as factory:
            identities = []
            for step in (0, 1, 2, 3):
                obs, cfg = observation(step=step, sparse=True)
                before = deepcopy((obs, cfg))
                S.agent(obs, cfg)
                identities.append(id(S._policy.policy))
                self.assertEqual((obs, cfg), before)
            self.assertEqual(factory.call_count, 1)
            self.assertEqual(len(set(identities)), 1)
        RECEIPTS.append({'case': 'sparse_singleton_continuity', 'calls': 4, 'actors': 1})

    def test_singleton_resets_on_real_zero_not_missing_step(self):
        obs, cfg = observation(sparse=True)
        S.agent(obs, cfg)
        first = S._policy
        S._policy.policy.planned['sentinel'] = [(1, 1)]
        S.agent(obs, cfg)
        self.assertIsNot(S._policy, first)
        self.assertNotIn('sentinel', S._policy.policy.planned)

    def test_missing_clock_fails_before_parent_without_retry(self):
        run = S.make_agent(T13)
        obs, cfg = observation(sparse=True); obs.pop('hour')
        with patch.object(run.policy, 'act', wraps=run.policy.act) as called:
            with self.assertRaises(KeyError):
                run(obs, cfg)
        called.assert_not_called()

    def test_original_policy_exception_identity_is_preserved(self):
        run = S.make_agent(T13)
        obs, cfg = observation(sparse=True)
        error = TypeError('existing-policy-body')
        with patch.object(run.policy, 'act', side_effect=error) as called:
            with self.assertRaises(TypeError) as caught:
                run(obs, cfg)
        self.assertIs(caught.exception, error)
        self.assertEqual(called.call_count, 1)
        self.assertEqual(called.call_args.args[0]['step'], 0)

    def test_raw_file_no_file_or_name_uses_compilation_filename(self):
        namespace = {}
        exec(compile(SOURCE_BYTES['seed_main.py'], str(T13/'seed_main.py'), 'exec'), namespace)
        for seat in (0, 1):
            expected = S.make_agent(T13)
            for step in (0, 1):
                obs, cfg = observation(seat, step)
                other, _ = observation(seat, step, sparse=True)
                self.assertEqual(namespace['agent'](other, cfg), checked_call(expected, obs, cfg))
                compare_state(namespace['_policy'], expected)
        self.assertNotIn('__file__', namespace)
        self.assertNotIn('__name__', namespace)

    def test_raw_path_override_remains_available(self):
        namespace = {}
        exec(compile(SOURCE_BYTES['seed_main.py'], '<generated>', 'exec'), namespace)
        obs, cfg = observation(sparse=True)
        cfg['__raw_path__'] = str(T13/'seed_main.py')
        explicit, _ = observation()
        self.assertEqual(namespace['agent'](obs, cfg), checked_call(S.make_agent(T13), explicit, cfg))

    def test_existing_frozen_arm_entrypoints_retain_each_instance(self):
        for mode, fn in (('funded', ARMS.agent), ('legacy', ARMS.legacy), ('sell', ARMS.sell)):
            expected = ARMS.make_agent(mode)
            for step in (0, 1, 2):
                obs, cfg = observation(step=step)
                sparse, _ = observation(step=step, sparse=True)
                self.assertEqual(fn(sparse, cfg), checked_call(expected, obs, cfg))
                compare_state(ARMS._INSTANCES[mode], expected)
            self.assertEqual(ARMS._INSTANCES[mode].policy.controller, ARMS._INSTANCES[mode].controller)

    def test_existing_capital_entrypoints_use_the_supplied_actor(self):
        for mode, fn in (('funded', CAPITAL.agent), ('legacy', CAPITAL.legacy), ('capital', CAPITAL.capital)):
            expected = CAPITAL.make_agent(mode)
            for step in (0, 1, 2):
                obs, cfg = observation(step=step)
                sparse, _ = observation(step=step, sparse=True)
                self.assertEqual(fn(sparse, cfg), checked_call(expected, obs, cfg))
                actual = CAPITAL._INSTANCES[mode]
                self.assertIs(actual.controller, actual.policy.scheduler.controller)
                compare_state(actual, expected)

    def test_supplied_capital_observes_real_checkpoint_before_budget(self):
        for seat in (0, 1):
            explicit, sparse = CAPITAL.make_agent('funded'), CAPITAL.make_agent('funded')
            for step in range(227):
                obs, cfg = observation(seat, step)
                other, _ = observation(seat, step, sparse=True)
                self.assertEqual(checked_call(explicit, obs, cfg), checked_call(sparse, other, cfg))
                compare_state(explicit, sparse)
                COUNTS['compared_actions'] += 1
            self.assertEqual(sparse.controller.cur, 'dc76e4003029ac51')
            self.assertTrue(sparse.policy.selection['changed'])
            RECEIPTS.append({'case': 'saved_pre_checkpoint_prefix', 'seat': seat,
                             'compared_actions': 227, 'route_after': sparse.controller.cur,
                             'scope': 'saved SELL observations, not a new policy game'})

    def test_raw_internal_arms_without_file_globals(self):
        for filename in ('arms.py', 'capital_arms.py'):
            namespace = {}
            exec(compile(SOURCE_BYTES[filename], str(T13/'juniper-funding'/filename), 'exec'), namespace)
            expected = (ARMS if filename == 'arms.py' else CAPITAL).make_agent('funded')
            for step in (0, 1):
                obs, cfg = observation(step=step)
                sparse, _ = observation(step=step, sparse=True)
                self.assertEqual(namespace['agent'](sparse, cfg), checked_call(expected, obs, cfg))
            self.assertNotIn('__file__', namespace)


def main():
    global ROOT, T13, S, ARMS, CAPITAL, FRAMES
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--prefix-dir', type=Path, required=True,
                        help='Directory with recorded 9989001-p{0,1}-sell.frames.jsonl.gz')
    parser.add_argument('--source-dir', type=Path, help='Optional three-file source override for negative controls')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    ROOT = args.root.resolve(); T13 = ROOT/'cloud-hosted-loss-response'
    paths = {'seed_main.py': T13/'seed_main.py',
             'arms.py': T13/'juniper-funding/arms.py',
             'capital_arms.py': T13/'juniper-funding/capital_arms.py'}
    for name, path in paths.items():
        SOURCE_BYTES[name] = (args.source_dir/name if args.source_dir else path).read_bytes()
    S = load(paths['seed_main.py'], 'seed_main', SOURCE_BYTES['seed_main.py'])
    ARMS = load(paths['arms.py'], 'juniper_clock_arms', SOURCE_BYTES['arms.py'])
    CAPITAL = load(paths['capital_arms.py'], 'juniper_clock_capital', SOURCE_BYTES['capital_arms.py'])
    inputs = {}
    for seat in (0, 1):
        path = args.prefix_dir/f'9989001-p{seat}-sell.frames.jsonl.gz'
        data = path.read_bytes(); inputs[path.name] = hashlib.sha256(data).hexdigest()
        FRAMES[seat] = [json.loads(line) for line in gzip.decompress(data).splitlines()]
    start = time.perf_counter()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ClockTests))
    report = {'schema': 'juniper-seed-clock-v1', 'methods': result.testsRun,
              'failures': len(result.failures), 'errors': len(result.errors), 'successful': result.wasSuccessful(),
              'counts': COUNTS, 'cases': RECEIPTS,
              'sources': {name: hashlib.sha256(data).hexdigest() for name, data in SOURCE_BYTES.items()},
              'inputs': inputs, 'wall_seconds': time.perf_counter()-start,
              'interpreter_transitions': 0, 'new_games': 0,
              'failure_details': [(t.id(), text) for t, text in result.failures],
              'error_details': [(t.id(), text) for t, text in result.errors]}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2)+'\n')
    return not result.wasSuccessful()


if __name__ == '__main__':
    raise SystemExit(main())
