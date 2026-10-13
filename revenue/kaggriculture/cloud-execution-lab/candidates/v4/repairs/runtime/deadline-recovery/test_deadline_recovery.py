# SPDX-License-Identifier: Apache-2.0
"""Actual TitanAgent lifecycle tests; collaborators are controlled test doubles.

Required inputs are never skipped. The deadline adapter's fallback functions and
exception type are real; deterministic timer injection is separate from the two
real-timer checks. No engine game or production-strength claim is made.
"""
from __future__ import annotations
import ast
from copy import deepcopy
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch

from repair_deadline_recovery import AFTER, BEFORE, act_span, blob, repair

ROOT = next((p for p in Path(__file__).resolve().parents if (p/'titan_runtime.py').is_file()), None)
RUNTIME = Path(os.environ.get('TITAN_RUNTIME', str(ROOT/'titan_runtime.py') if ROOT else 'MISSING_RUNTIME'))
ADAPTER = Path(os.environ.get('TITAN_DEADLINE', str(RUNTIME.parent/'reference/titan-current/deadline_adapter.py')))
SOURCE = RUNTIME.read_bytes()
FIXED = repair(SOURCE)
if blob(ADAPTER.read_bytes()) != '664aa4f8a21368c388dfa6714406519b6535ef7f':
    raise RuntimeError('deadline adapter is not the pinned current source')
spec = importlib.util.spec_from_file_location('_recovery_real_deadline', ADAPTER)
REAL = importlib.util.module_from_spec(spec)
spec.loader.exec_module(REAL)
COUNTS = {'initialization_cutpoints': 0, 'warm_cancellations': 0}
COMPILED = {}


def obs(seat=0, step=718):
    farm = {'tiles': [[{} for _ in range(10)] for _ in range(10)],
            'farmer': [4, 4], 'hands': [[4, 4], [0, 0]]}
    return {'step': step, 'player': seat, 'day': step//24, 'hour': step%24,
            'farms': [deepcopy(farm), deepcopy(farm)],
            'private': {'shed': {'WHEAT': 2}, 'inventories': [{}, {}, {}], 'seeds': {}, 'cash': 100}}


class Harness:
    """Execute unmodified class methods with injected external collaborators."""
    def __init__(self, source=FIXED, features=None, target=None, error=None, real_timer=False):
        self.events, self.lines, self.finalizers = [], [], []
        self.target, self.error, self.fired = target, error, False
        self.cut = None
        self.timer = None
        self.selected = {'farmer': ['PASS'], 'hands': [['PASS'], ['PASS']], 'market': [['SELL', 'MILK', 1]]}
        h = self
        class Timer:
            def __init__(self, seconds):
                self.expired = REAL.DeadlineExceeded('injected own deadline')
                h.timer = self
            def __enter__(self):
                h.hit('timer_enter')
                return self
            def __exit__(self, exc_type, value, tb):
                if exc_type is None:
                    h.hit('timer_exit')
                return False
        name = '_recovery_runtime_' + str(id(self))
        self.m = types.ModuleType(name)
        self.m.__file__ = str(RUNTIME)
        self.m.deadline = REAL if real_timer else types.SimpleNamespace(
            DeadlineExceeded=REAL.DeadlineExceeded, _DeadlineTimer=Timer,
            legal_pass=REAL.legal_pass, terminal_liquidation_fallback=REAL.terminal_liquidation_fallback)
        if source not in COMPILED:
            tree = ast.parse(source)
            # Substitute only the module-level dependency loader, not class code.
            tree.body = [n for n in tree.body if not (isinstance(n, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == 'deadline' for t in n.targets))]
            COMPILED[source] = compile(tree, '<actual-titan-runtime>', 'exec')
        with patch.dict(sys.modules, {name: self.m}):
            exec(COMPILED[source], self.m.__dict__)
        self.a = self.m.TitanAgent(self.m.Features(**(features or {})))
        actual_finish = self.a._finish_production
        def finish(*args, **kwargs):
            self.finalizers.append(deepcopy(args[1]))
            self.hit('finalizer')
            return actual_finish(*args, **kwargs)
        self.a._finish_production = finish
        self.m.load = self.load

        class Controller:
            def __init__(self):
                self.cur = 2
                self.R = [[] for _ in range(10)]
            def act(self, observation):
                self.cur = 3
                h.hit('production')
                return deepcopy(h.selected)
        class Consumer:
            def __init__(self, **kwargs):
                h.hit('consumer_create')
                self.controller = self.production = Controller()
                self.planned, self.pending, self.observed_harvests = {}, {}, {}
                self.previous = None
                self.selected_post_units = self.selected_post_units_binding = self.last_packet = None
            def transform(self, observation, cfg, selected, **kwargs):
                h.hit('transform')
                return deepcopy(selected)
            def observe(self, observation):
                h.hit('seller_observe')
                self.previous = deepcopy(observation)
        class Spatial:
            def __init__(self, *args, **kwargs):
                h.hit('spatial_create')
                self._crop_repair = self._pending = self.crop_intent = self.sale_obligation = None
                self.plans, self.events, self.receipt_events = [], [], []
                self.crop_report = {}
            def transform(self, observation, selected, controller): return selected
            def install(self, controller): h.hit('spatial_install')
            def configure(self, cfg): h.hit('spatial_configure')
            def observe_market_receipt(self, *args): h.hit('market_receipt')
            def observe_crop_receipts(self, *args): h.hit('crop_receipt')
            def guard_returned(self, observation, selected, **kwargs): return selected
            def guard_crop_returned(self, observation, selected, post): return selected
            def finish(self, *args): h.hit('spatial_finish')
            def finish_crop(self, *args, **kwargs): pass
            def crop_market(self, observation, selected, *args): return selected
        class History:
            def __init__(self, **kwargs):
                h.hit('history_create')
                self.fill_result, self.diagnostics = None, {}
            def observe(self, observation): h.hit('history_observe')
            def transform(self, observation, cfg, selected, *args, **kwargs):
                h.hit('history_transform')
                return selected
            def remember(self, *args): h.hit('history_remember')
        class Quadrant:
            def __init__(self, *args):
                h.hit('quadrant_create')
                self.pending = self.plan = None
                self.events = []
            def install(self, controller): h.hit('quadrant_install')
            def configure(self, cfg): pass
            def finish(self, *args): h.hit('quadrant_finish')
        def capital(m, observation, cfg, selected, *args):
            h.hit('capital')
            return selected, {'test_double': True}
        def feed(m, observation, cfg, selected, *args):
            h.hit('feed')
            return selected, {'test_double': True}
        self.modules = {
            'frozen_selected': types.SimpleNamespace(FrozenSelected=Consumer),
            'integrated_selected': types.SimpleNamespace(IntegratedSelectedAgent=Consumer),
            'spatial_tempo': types.SimpleNamespace(SpatialTempo=Spatial),
            'terminal_history_join': types.SimpleNamespace(TerminalHistoryJoin=History),
            'fourth_quadrant': types.SimpleNamespace(FourthQuadrant=Quadrant),
            'scheduler': types.SimpleNamespace(m=object(), parent=types.SimpleNamespace(DECISIONS=[])),
            'mechanics': types.SimpleNamespace(),
            'early_capital': types.SimpleNamespace(order_early_capital=capital),
            'operating_stock': types.SimpleNamespace(protect_feed_stock=feed),
        }

    def hit(self, point):
        self.events.append(point)
        if self.target == point and not self.fired:
            self.fired = True
            raise self.error if self.error is not None else self.timer.expired

    def load(self, name, path, **kwargs):
        self.hit('load:' + name)
        if name == '_titan_funding':
            return types.SimpleNamespace(select_seed_queue=None)
        if name == '_titan_seed_budget':
            return types.SimpleNamespace(SeedBudget=lambda r: types.SimpleNamespace(remaining=lambda *a: 0))
        if name == '_titan_terminal_composition':
            return types.SimpleNamespace(TerminalOwner=lambda controller: controller)
        return types.SimpleNamespace()

    def run(self, observation=None, cfg=None, **kwargs):
        def trace(frame, event, arg):
            if frame.f_code.co_filename == '<actual-titan-runtime>' and frame.f_code.co_name == '_initialize':
                if event == 'line':
                    self.lines.append(frame.f_lineno)
                if event == 'line' and self.cut == frame.f_lineno and not self.fired:
                    self.fired = True
                    raise self.timer.expired
            return trace
        previous_trace = sys.gettrace()
        try:
            with patch.dict(sys.modules, self.modules):
                if self.m.deadline is not REAL:
                    sys.settrace(trace)
                return self.a.act(observation or obs(), cfg or {}, **kwargs)
        finally:
            sys.settrace(previous_trace)

    def warm(self, observation=None):
        target, self.target = self.target, None
        self.run(observation or obs(step=100))
        self.target, self.fired = target, False
        self.events.clear()
        self.lines.clear()
        self.finalizers.clear()


class RecoveryTests(unittest.TestCase):
    def test_exact_predecessor_loses_terminal_fallback(self):
        h = Harness(SOURCE, {'operating_stock': True}, 'load:_titan_funding')
        with self.assertRaisesRegex(AttributeError, 'consumer'):
            h.run()
        self.assertEqual(h.a.diagnostics['fallback_stage'], 'cold_start')

    def test_terminal_fallback_survives_missing_consumer(self):
        for seat in (0, 1):
            h = Harness(features={'operating_stock': True}, target='load:_titan_funding')
            observation = obs(seat)
            self.assertEqual(h.run(observation), REAL.terminal_liquidation_fallback(observation))
            self.assertEqual(h.finalizers, [])
            self.assertEqual(h.a.diagnostics['finalizer_skipped'], 'incomplete_initialization')

    def test_early_capital_without_controller(self):
        h = Harness(features={'early_capital': True}, target='load:_titan_funding')
        observation = obs(step=0)
        self.assertEqual(h.run(observation), REAL.legal_pass(observation))
        self.assertFalse(hasattr(h.a, 'controller'))
        self.assertNotIn('capital', h.events)

    def test_all_executed_initialization_lines(self):
        profiles = [
            {}, {'consumer': 'parent'}, {'consumer': 'ordered'},
            {'operating_stock': True, 'early_capital': True, 'fourth_quadrant': True,
             'terminal_history': True, 'history_hypotheses': {}, 'crop_release': True,
             'idle_fertilizer': True, 'spatial_pathing': True, 'spatial_tempo': True},
            {'terminal_route': True, 'terminal_history': True, 'history_hypotheses': {}},
            {'consumer': 'ordered', 'terminal_history': True, 'history_hypotheses': {}},
        ]
        for profile in profiles:
            for stale in (False, True):
                probe = Harness(features=profile)
                if stale:
                    probe.warm()
                    probe.a.ready = False
                probe.run()
                for line in sorted(set(probe.lines)):
                    for seat in (0, 1):
                        for step in (0, 718):
                            with self.subTest(profile=profile, stale=stale, line=line, seat=seat, step=step):
                                h = Harness(features=profile)
                                if stale:
                                    h.warm()
                                    h.a.ready = False
                                checkpoint = deepcopy(h.a._completed_seller_state)
                                route = h.a._completed_route
                                h.cut = line
                                observation = obs(seat, step)
                                before = deepcopy(observation)
                                actual = h.run(observation)
                                expected = REAL.terminal_liquidation_fallback(observation) if step == 718 else REAL.legal_pass(observation)
                                self.assertTrue(h.fired)
                                self.assertEqual(actual, expected)
                                self.assertEqual(h.finalizers, [])
                                self.assertFalse(h.a.ready)
                                self.assertEqual(h.a._completed_seller_state, checkpoint)
                                self.assertEqual(h.a._completed_route, route)
                                self.assertEqual(observation, before)
                                self.assertEqual(h.a.diagnostics['parent_calls'], 0)
                                self.assertEqual(len(h.a._seller_fallback_observations), int(profile.get('consumer', 'frozen') == 'frozen'))
                                COUNTS['initialization_cutpoints'] += 1

    def test_stale_controller_does_not_authorize_finalizer(self):
        h = Harness(features={'early_capital': True}, target='load:_titan_funding')
        h.warm()
        h.a.ready = False
        self.assertTrue(hasattr(h.a, 'controller'))
        h.run()
        self.assertEqual(h.finalizers, [])

    def test_warm_cancellation_keeps_finalization(self):
        for consumer in ('frozen', 'ordered', 'parent'):
            for point in ('timer_enter', 'production', 'timer_exit') + (('transform',) if consumer != 'parent' else ()):
                for seat in (0, 1):
                    for step in (0, 718):
                        with self.subTest(consumer=consumer, point=point, seat=seat, step=step):
                            h = Harness(features={'consumer': consumer}, target=point)
                            h.warm()
                            previous_route = h.a._completed_route
                            previous_checkpoint = deepcopy(h.a._completed_seller_state)
                            observation = obs(seat, step)
                            actual = h.run(observation)
                            expected = h.selected if point in ('transform', 'timer_exit') else (
                                REAL.terminal_liquidation_fallback(observation) if step == 718 else REAL.legal_pass(observation))
                            self.assertEqual(actual, expected)
                            self.assertEqual(len(h.finalizers), 1)
                            self.assertNotIn('finalizer_skipped', h.a.diagnostics)
                            self.assertEqual(h.a._completed_seller_state, previous_checkpoint)
                            self.assertEqual(h.a._completed_route, 3 if point in ('transform', 'timer_exit') else previous_route)
                            self.assertEqual(h.a.diagnostics['parent_calls'], int(point != 'timer_enter'))
                            COUNTS['warm_cancellations'] += 1

    def test_cold_stage_is_not_initialization_state(self):
        h = Harness(target='market_receipt')
        h.warm()
        h.run()
        self.assertEqual(h.a.diagnostics['fallback_stage'], 'cold_start')
        self.assertEqual(len(h.finalizers), 1)
        self.assertNotIn('finalizer_skipped', h.a.diagnostics)

    def test_history_cancellation_runs_safe_warm_finalizer(self):
        h = Harness(features={'terminal_history': True, 'history_hypotheses': {}}, target='history_observe')
        h.warm()
        h.run()
        self.assertIsNone(h.a.history)
        self.assertEqual(len(h.finalizers), 1)

    def test_completed_initialization_then_first_production_timeout(self):
        h = Harness(target='production')
        h.run()
        self.assertEqual(len(h.finalizers), 1)
        self.assertEqual(h.a.diagnostics['fallback_stage'], 'production')
        self.assertIsNone(h.a._completed_route)

    def test_recovery_after_partial_initialization(self):
        h = Harness(target='spatial_install')
        h.run(obs(step=100))
        self.assertFalse(h.a.ready)
        self.assertEqual(len(h.a._seller_fallback_observations), 1)
        self.assertEqual(h.run(obs(step=101)), h.selected)
        self.assertTrue(h.a.ready)
        self.assertEqual(h.a._seller_fallback_observations, [])
        self.assertIn('seller_observe', h.events)

    def test_duplicate_fallback_observation_recorded_once(self):
        h = Harness(target='load:_titan_funding')
        h.run(obs(step=100))
        h.fired = False
        h.run(obs(step=100))
        self.assertEqual(len(h.a._seller_fallback_observations), 1)

    def test_foreign_deadline_propagates_unchanged(self):
        error = REAL.DeadlineExceeded('foreign')
        h = Harness(target='load:_titan_funding', error=error)
        with self.assertRaises(REAL.DeadlineExceeded) as caught:
            h.run()
        self.assertIs(caught.exception, error)
        self.assertEqual(h.finalizers, [])
        self.assertEqual(h.a._seller_fallback_observations, [])

    def test_other_failures_are_not_swallowed(self):
        for error in (RuntimeError('fault'), KeyboardInterrupt('caller')):
            h = Harness(target='load:_titan_funding', error=error)
            with self.assertRaises(type(error)) as caught:
                h.run()
            self.assertIs(caught.exception, error)

    def test_finalizer_failure_propagates(self):
        error = RuntimeError('finalizer')
        h = Harness(target='finalizer', error=error)
        with self.assertRaises(RuntimeError) as caught:
            h.run()
        self.assertIs(caught.exception, error)

    def test_expired_entrypoint_does_not_initialize_or_finalize(self):
        h = Harness()
        observation = obs()
        self.assertEqual(h.run(observation, entry_started=time.perf_counter()-10), REAL.terminal_liquidation_fallback(observation))
        self.assertEqual(h.events, [])
        self.assertEqual(h.finalizers, [])

    def test_successful_callbacks_unchanged(self):
        for consumer in ('frozen', 'ordered', 'parent'):
            for seat in (0, 1):
                old, new = Harness(SOURCE, {'consumer': consumer}), Harness(FIXED, {'consumer': consumer})
                for step in (0, 1, 24, 100, 717, 718):
                    self.assertEqual(old.run(obs(seat, step)), new.run(obs(seat, step)))
                    self.assertEqual(old.a._completed_route, new.a._completed_route)
                    self.assertEqual(old.a._completed_seller_state, new.a._completed_seller_state)
                    self.assertEqual(old.events, new.events)
                    self.assertNotIn('finalizer_skipped', new.a.diagnostics)

    def test_terminal_fallback_keeps_drop_and_shed_capacity(self):
        h = Harness(target='load:_titan_funding')
        observation = obs()
        observation['private']['shed']['WHEAT'] = 98
        observation['private']['inventories'][0] = {'WHEAT': 7}
        actual = h.run(observation)
        self.assertEqual(actual['farmer'], ['DROP'])
        self.assertEqual(actual['market'], [['SELL', 'WHEAT', 100]])
        self.assertEqual(observation['private']['inventories'][0]['WHEAT'], 7)

    def test_custom_terminal_configuration(self):
        h = Harness(target='load:_titan_funding')
        observation = obs(step=98)
        actual = h.run(observation, {'episodeSteps': 100})
        self.assertEqual(actual, REAL.terminal_liquidation_fallback(observation, {'episodeSteps': 100}))

    def test_instances_do_not_share_recovery_queues(self):
        left, right = Harness(target='load:_titan_funding'), Harness()
        left.run()
        self.assertEqual(right.a._seller_fallback_observations, [])
        self.assertIsNone(right.a._completed_route)

    def _real_timeout(self, worker=False):
        h = Harness(features={'operating_stock': True, 'budget_seconds': 0.08, 'reserve_seconds': 0.01}, real_timer=True)
        def expire(*args, **kwargs):
            until = time.monotonic() + 2
            while time.monotonic() < until:
                pass
            raise RuntimeError('actual timer failed to interrupt within watchdog')
        h.m.load = expire
        values, errors = [], []
        def run():
            try: values.append(h.run())
            except BaseException as error: errors.append(error)
        if worker:
            thread = threading.Thread(target=run)
            thread.start()
            thread.join(3)
            self.assertFalse(thread.is_alive())
        else:
            run()
        self.assertEqual(errors, [])
        self.assertEqual(values, [REAL.terminal_liquidation_fallback(obs())])
        self.assertEqual(h.finalizers, [])
        self.assertFalse(h.a.ready)

    def test_real_main_thread_alarm(self): self._real_timeout()
    def test_real_worker_thread_trace(self): self._real_timeout(worker=True)

    def test_four_incorrect_repairs_are_detected(self):
        replacements = [
            ('initialization_completed = self.ready', 'initialization_completed = False', 'production', False),
            ('initialization_completed = self.ready', 'initialization_completed = True', 'load:_titan_funding', False),
            ('if initialization_completed:', "if stage != 'cold_start':", 'market_receipt', True),
            ('if initialization_completed:', "if hasattr(self, 'controller'):", 'load:_titan_funding', True),
        ]
        for old, new, point, stale in replacements:
            mutant = FIXED.replace(old.encode(), new.encode(), 1)
            h = Harness(mutant, {'early_capital': True}, target=point)
            if stale:
                h.warm()
                if point.startswith('load:'): h.a.ready = False
            expected_count = int(point in ('production', 'market_receipt'))
            try:
                h.run()
            except AttributeError:
                self.assertEqual(expected_count, 0)
            else:
                self.assertNotEqual(len(h.finalizers), expected_count)


class TransformTests(unittest.TestCase):
    def test_exact_output(self):
        self.assertEqual(blob(SOURCE), 'b952c9c228ecbde592bf3d2df01638677abb0d24')
        self.assertEqual(blob(FIXED), 'c42344489a3f50d91e2abe8d85d4ee15f34732a1')

    def test_idempotent(self): self.assertEqual(repair(FIXED), FIXED)

    def test_unrelated_source_bytes_preserved(self):
        composed = SOURCE.replace(b"    early_capital: bool = False", b"    peer_flag: bool = False\n    early_capital: bool = False")
        expected = FIXED.replace(b"    early_capital: bool = False", b"    peer_flag: bool = False\n    early_capital: bool = False")
        self.assertEqual(repair(composed), expected)

    def test_changed_method_rejected(self):
        with self.assertRaises(ValueError):
            repair(SOURCE.replace(b"stage = 'production'", b"stage = 'changed'"))

    def test_invalid_input_rejected(self):
        for source in (b'\xff', b'def broken(', b'class Other: pass\n', SOURCE + b'\nclass TitanAgent: pass\n'):
            with self.assertRaises((UnicodeError, SyntaxError, ValueError)):
                repair(source)

    def test_cli_is_create_only_and_fail_closed(self):
        tool = Path(__file__).with_name('repair_deadline_recovery.py')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root/'in.py', root/'out.py'
            source.write_bytes(SOURCE)
            command = [sys.executable, str(tool), str(source), str(output)]
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual(output.read_bytes(), FIXED)
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 2)
            self.assertEqual(source.read_bytes(), SOURCE)
            self.assertEqual(output.read_bytes(), FIXED)
            source.write_bytes(b'broken: (')
            output.unlink()
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 2)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    program = unittest.main(verbosity=2, exit=False)
    print('CASE_COUNTS', COUNTS)
    raise SystemExit(not program.result.wasSuccessful())
