# SPDX-License-Identifier: Apache-2.0
"""Native lazy-history correctness, official-transition and cancellation gates.

Run with --runtime pointing at an extracted canonical TITAN package. No network,
full-game driver, flag promotion, or archive mutation is performed.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
import time

from build_lazy_history import compose, BASE_GIT_BLOB, EAGER, LAZY, METHODS, NEW_OBSERVE

COUNTS = {'official_transitions': 0, 'dependency_cancellations': 0,
          'constructor_cancellations': 0, 'runtime_calls': 0,
          'real_deadlines': 0}


def git_blob(data):
    return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()


def load_text(name, text, path):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(text, str(path), 'exec'), module.__dict__)
    return module


class Cancel(BaseException):
    pass


class LazyHistory(unittest.TestCase):
    def candidate(self, **kwargs):
        return CAND.TerminalHistoryJoin(terminal_enabled=False, **kwargs)

    def test_no_dependencies_until_real_demand(self):
        with patch.object(CAND, 'load', side_effect=AssertionError('eager import')):
            join = self.candidate()
            self.assertIsNone(join._history_components)
            join.observe({'step': 0})
            join.remember({}, {}, {}, None)
            selected = {'farmer': ['PASS'], 'hands': [], 'market': []}
            self.assertIs(join.transform({}, {}, selected, None, deadline=0), selected)
            self.assertIsNone(join._history_components)

    def test_pending_snapshot_does_not_force_import(self):
        with patch.object(CAND, 'load', side_effect=AssertionError('eager import')):
            join = self.candidate()
            obs, cfg, _state, _env = HELPER.fixture(100)
            action = {'farmer': ['PASS'], 'hands': [['PASS']], 'market': []}
            join.remember(obs, cfg, action, copy.deepcopy(obs))
            before = copy.deepcopy(join.pending)
            obs['step'] = 101
            action['market'].append(['SELL', 'CARROT', 10])
            join.observe({'step': 100})
            self.assertEqual(join.pending, before)
            self.assertIsNone(join._history_components)

    def test_first_access_publishes_once_and_preserves_period(self):
        with patch.object(CAND, 'load', wraps=CAND.load) as called:
            join = self.candidate(period=7)
            bridge = join.bridge
            self.assertEqual(called.call_count, 5)
            self.assertIs(join.bridge, bridge)
            self.assertIs(join.m, bridge.mechanics)
            self.assertEqual(bridge.history.period, 7)
            self.assertEqual(called.call_count, 5)

    def test_independent_agents_share_only_stateless_dependencies(self):
        first, second = self.candidate(), self.candidate()
        self.assertIs(first.m, second.m)
        self.assertIsNot(first.bridge, second.bridge)
        self.assertIsNot(first.bridge.history, second.bridge.history)
        self.assertIsNot(first.bridge.ledger, second.bridge.ledger)
        first.bridge.player = 1
        first.bridge.last_consumed_step = 95
        self.assertIsNone(second.bridge.player)
        self.assertEqual(second.bridge.last_consumed_step, -1)

    def test_public_property_assignments_are_retained(self):
        obj = self.candidate()
        original = obj.bridge
        marker = object()
        obj.m = marker
        self.assertIs(obj.m, marker)
        self.assertIs(obj.bridge, original)
        replacement = object()
        obj.bridge = replacement
        self.assertIs(obj.bridge, replacement)
        self.assertIs(obj.m, marker)

    def test_terminal_mode_remains_eager_and_restores_solver_binding(self):
        marker = types.ModuleType('solver')
        with patch.dict(sys.modules, {'solver': marker}):
            obj = CAND.TerminalHistoryJoin(terminal_enabled=True, hypotheses=HYP)
            self.assertIsNotNone(obj._history_components)
            self.assertIsNotNone(obj.selector)
            self.assertIs(sys.modules['solver'], marker)
        self.assertIs(obj.bridge.mechanics, obj.m)

    def test_dependency_failure_never_publishes_partial_components(self):
        for cut in range(5):
            with self.subTest(cut=cut):
                obj = self.candidate()
                original = obj.dependency
                count = [0]
                def cancelled(name):
                    count[0] += 1
                    if count[0] == cut+1:
                        raise Cancel('dependency cut')
                    return original(name)
                obj.dependency = cancelled
                with self.assertRaises(Cancel):
                    _ = obj.bridge
                self.assertIsNone(obj._history_components)
                obj.dependency = original
                self.assertIs(obj.bridge.mechanics, obj.m)
                COUNTS['dependency_cancellations'] += 1

    def test_constructor_failure_never_publishes_partial_components(self):
        cases = [('observed_fills', 'ObservedFillLedger'),
                 ('flow', 'FlowHistory'),
                 ('selected_action_history', 'SelectedActionHistory')]
        for name, cls in cases:
            with self.subTest(constructor=cls):
                obj = self.candidate()
                dependency = obj.dependency(name)
                with patch.object(dependency, cls, side_effect=Cancel('constructor cut')):
                    with self.assertRaises(Cancel):
                        _ = obj.bridge
                self.assertIsNone(obj._history_components)
                self.assertIs(obj.bridge.mechanics, obj.m)
                COUNTS['constructor_cancellations'] += 1

    def test_first_use_cancellation_retains_pending_for_retry(self):
        obj = self.candidate()
        before, cfg, state, env = HELPER.fixture(100, shed={'CARROT': 3})
        selected = {'farmer': ['PASS'], 'hands': [['PASS']],
                    'market': [['SELL', 'CARROT', 3]]}
        obj.remember(before, cfg, selected, copy.deepcopy(before))
        pending = obj.pending
        HELPER.advance(state, env, selected, 100)
        after = copy.deepcopy(state[0].observation)
        after['step'] = 101
        with patch.object(obj, 'dependency', side_effect=Cancel('first use')):
            with self.assertRaises(Cancel):
                obj.observe(after)
        self.assertIs(obj.pending, pending)
        self.assertIsNone(obj._history_components)
        obj.observe(after)
        self.assertIsNone(obj.pending)
        self.assertIsNotNone(obj.fill_result)
        self.assertEqual(obj.diagnostics['observed_fills']['status'], 'recorded')
        COUNTS['official_transitions'] += 1

    def test_official_transition_receipts_equal_eager_in_both_seats(self):
        for seat in (0, 1):
            for step in (0, 22, 23, 100, 358, 694, 718):
                for quantity in (0, 3, 100):
                    with self.subTest(seat=seat, step=step, quantity=quantity):
                        obs, cfg, state, env = HELPER.fixture(step)
                        own = state[seat].observation
                        own['private']['shed'] = {'CARROT': quantity, 'WHEAT': 5}
                        actions = []
                        for player in (0, 1):
                            action = {'farmer': ['PASS'],
                                      'hands': [['PASS'] for _ in own['farms'][player]['hands']],
                                      'market': [['SELL', 'CARROT', quantity], [], ['SELL', 'WHEAT', 2]]
                                      if player == seat else []}
                            actions.append(action)
                        baseline = BASE.TerminalHistoryJoin(terminal_enabled=False)
                        candidate = self.candidate()
                        before = copy.deepcopy(own)
                        for obj in (baseline, candidate):
                            obj.remember(before, cfg, actions[seat], copy.deepcopy(before))
                        for player in (0, 1):
                            state[player].action = copy.deepcopy(actions[player])
                            state[player].observation['step'] = step
                        HELPER.engine.interpreter(state, env)
                        after = copy.deepcopy(state[seat].observation)
                        after['step'] = step+1
                        baseline.observe(after)
                        candidate.observe(after)
                        self.assertEqual(candidate.diagnostics, baseline.diagnostics)
                        self.assertEqual(candidate.fill_result, baseline.fill_result)
                        self.assertEqual(candidate.bridge.history.__dict__, baseline.bridge.history.__dict__)
                        self.assertEqual(candidate.bridge.last_consumed_step, baseline.bridge.last_consumed_step)
                        self.assertEqual(candidate.pending, baseline.pending)
                        COUNTS['official_transitions'] += 1

    def test_real_signal_and_worker_deadlines_leave_retryable_state(self):
        from titan_runtime import deadline
        def exercise():
            obj = self.candidate()
            original = obj.dependency
            def slow(name):
                end = time.perf_counter()+0.06
                while time.perf_counter() < end:
                    pass
                return original(name)
            obj.dependency = slow
            timer = deadline._DeadlineTimer(0.01)
            with self.assertRaises(deadline.DeadlineExceeded) as caught:
                with timer:
                    _ = obj.bridge
            self.assertIs(caught.exception, timer.expired)
            self.assertIsNone(obj._history_components)
            obj.dependency = original
            self.assertIsNotNone(obj.bridge)
            return 1
        COUNTS['real_deadlines'] += exercise()
        with ThreadPoolExecutor(max_workers=1) as executor:
            COUNTS['real_deadlines'] += executor.submit(exercise).result(timeout=2)

    def test_native_returned_actions_and_state_match(self):
        import titan_runtime as runtime
        import terminal_history_join as native
        import main
        config = json.loads((RUNTIME/'TITAN-CONFIG.json').read_text())
        config['budget_seconds'] = 1.0
        for seat in (0, 1):
            for step in (0, 22, 23, 100, 226, 360, 433, 694, 718):
                obs, cfg, state, _env = HELPER.fixture(step, shed={'WHEAT': 3, 'CARROT': 5})
                observation = state[seat].observation
                actors=[]; outputs=[]
                for cls in (BASE.TerminalHistoryJoin, CAND.TerminalHistoryJoin):
                    with patch.object(native, 'TerminalHistoryJoin', cls):
                        actor = main._new_instance(RUNTIME, config)
                        output = actor.act(copy.deepcopy(observation), copy.deepcopy(cfg))
                    self.assertEqual(actor.diagnostics['status'], 'completed')
                    actors.append(actor); outputs.append(output)
                    COUNTS['runtime_calls'] += 1
                self.assertEqual(outputs[0], outputs[1])
                self.assertEqual(actors[0].controller.cur, actors[1].controller.cur)
                self.assertEqual(actors[0].history.pending, actors[1].history.pending)
                self.assertEqual(actors[0].history.fill_result, actors[1].history.fill_result)
                self.assertEqual(actors[0].spatial.events, actors[1].spatial.events)
                self.assertEqual(actors[0].seed_budget.events, actors[1].seed_budget.events)

    def test_composer_is_idempotent_and_preserves_peer_edits(self):
        peer = SOURCE.replace('from copy import deepcopy',
                              '# independent peer import comment\nfrom copy import deepcopy')
        transformed = compose(peer)
        self.assertIn('# independent peer import comment\n', transformed)
        self.assertEqual(compose(transformed), transformed)
        self.assertEqual(compose(SOURCE), CANDIDATE_SOURCE)

    def test_composer_rejects_drift_partial_and_ambiguous_sources(self):
        for text in (SOURCE.replace(EAGER, EAGER.replace('period=period', 'period=12')),
                     SOURCE + '\n'+EAGER, SOURCE.replace(EAGER, LAZY),
                     CANDIDATE_SOURCE.replace('bridge=self.bridge', 'bridge=None'),
                     CANDIDATE_SOURCE.replace(METHODS, ''), SOURCE.replace('class TerminalHistoryJoin:', 'class Other:')):
            with self.subTest(source_hash=hashlib.sha256(text.encode()).hexdigest()):
                with self.assertRaises((ValueError, SyntaxError)):
                    compose(text)


def main_test():
    global RUNTIME, SOURCE, CANDIDATE_SOURCE, BASE, CAND, HELPER, HYP
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args()
    RUNTIME = args.runtime.resolve()
    sys.path[:0] = [str(RUNTIME), str(RUNTIME/'checks')]
    path = RUNTIME/'terminal_history_join.py'
    SOURCE = path.read_text()
    if git_blob(SOURCE.encode()) != BASE_GIT_BLOB:
        parser.error('runtime history source is not the reviewed f878320d baseline')
    CANDIDATE_SOURCE = args.candidate.read_text() if args.candidate else compose(SOURCE)
    BASE = load_text('_foundry_eager_history', SOURCE, path)
    CAND = load_text('_foundry_lazy_history', CANDIDATE_SOURCE, path)
    from test_ordered_selected_sell import OrderedSelectedSellTests
    from test_terminal_history_join import HYP
    OrderedSelectedSellTests.setUpClass()
    HELPER = OrderedSelectedSellTests()
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(LazyHistory))
    receipt = {'tests': result.testsRun, 'passed': result.wasSuccessful(),
               'failures': len(result.failures), 'errors': len(result.errors),
               'optimized_python': sys.flags.optimize, 'python': sys.version,
               'source_git_blob': git_blob(SOURCE.encode()),
               'candidate_sha256': hashlib.sha256(CANDIDATE_SOURCE.encode()).hexdigest(),
               'engine_sha256': hashlib.sha256((RUNTIME/'checks/reference/engine/kaggriculture.py').read_bytes()).hexdigest(),
               'counts': COUNTS, 'full_games': 0, 'production_changed': False}
    if args.receipt:
        args.receipt.write_text(json.dumps(receipt, indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__':
    main_test()
