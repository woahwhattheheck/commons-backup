# SPDX-License-Identifier: Apache-2.0
"""Independent cold-start acceptance gate for the ONE V4 lifecycle package.

Executes the complete supplied TitanAgent/Features and the pinned real deadline
adapter. Planner/economic collaborators are deterministic doubles: no game or
strength claim. The candidate must be supplied with its independently read Git
blob; no source transformer or alternate runtime is installed by this suite.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import signal
import sys
import tempfile
import threading
import time
from types import ModuleType, SimpleNamespace as NS
import unittest
from unittest.mock import patch

BASELINE_BLOB = 'b952c9c228ecbde592bf3d2df01638677abb0d24'
DEADLINE_BLOB = '664aa4f8a21368c388dfa6714406519b6535ef7f'
BASELINE = CANDIDATE = DEADLINE = b''
COUNTS = {'initialization_cut_cells': 0, 'baseline_crash_witnesses': 0,
          'real_alarm_cases': 0, 'real_worker_trace_cases': 0}


def git_blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def observation(seat=0, step=0, hands=0):
    farms = [dict(farmer=[4, 4], hands=[[4, 5] for _ in range(hands)],
                  tiles=[[{} for _ in range(10)] for _ in range(10)]) for _ in range(2)]
    return dict(player=seat, step=step, day=step//24, hour=step%24,
                farms=farms, private=dict(shed={'WHEAT': 5, 'MILK': 2},
                inventories=[{'WHEAT': 1}] + [{} for _ in range(hands)], seeds={}))


def module(name, **attributes):
    result = ModuleType(name)
    result.__dict__.update(attributes)
    return result


class Rig:
    """Real runtime methods/timer; only collaborators and fault delivery vary."""
    def __init__(self, source, *, features=None, fault=None, cut=None):
        self.source = source
        self.features = features or {}
        self.fault = fault
        self.cut = cut
        self.events = []
        self.init_lines = []
        self.finish_calls = 0
        self.producer_calls = 0
        self.foreign = None

    def trip(self, point):
        if self.fault == point:
            raise self.m.deadline._ACTIVE_TIMER.get().expired
        if self.fault == 'foreign:' + point:
            raise self.foreign
        if self.fault == 'value:' + point:
            raise ValueError('deliberate collaborator failure')
        if self.fault == 'alarm:' + point:
            self.events.append(('fault_reached', point))
            # The real main-thread SIGALRM, not a fake timer or a sleep-based
            # assertion, supplies the exact owned exception.
            time.sleep(0.08)
        if self.fault == 'worker:' + point:
            self.events.append(('fault_reached', point))
            # Pure Python execution is interrupted by the real worker trace.
            until = time.monotonic() + 0.08
            while time.monotonic() < until:
                pass

    def __enter__(self):
        self.directory = tempfile.TemporaryDirectory(prefix='v4-cold-')
        root = Path(self.directory.name)
        runtime = root/'titan_runtime.py'
        runtime.write_bytes(self.source)
        target = root/'reference/titan-current/deadline_adapter.py'
        target.parent.mkdir(parents=True)
        target.write_bytes(DEADLINE)
        rig = self

        class Controller:
            def __init__(self):
                self.R = [[], []]
                self.cur = 0
            def act(self, obs):
                rig.producer_calls += 1
                rig.trip('producer')
                return {'farmer': ['NORTH'],
                        'hands': [['PASS'] for _ in obs['farms'][obs['player']]['hands']],
                        'market': []}

        class Consumer:
            def __init__(self, **kwargs):
                rig.trip('consumer_constructor')
                self.controller = Controller()
                self.production = self.controller
                self.planned = {}; self.pending = {}; self.previous = None
                self.observed_harvests = {}; self.last_packet = None
                self.selected_post_units = None
                self.selected_post_units_binding = None
            def transform(self, obs, cfg, selected, **kwargs):
                self.pending['interrupted'] = obs['step']
                rig.trip('transform')
                self.previous = deepcopy(obs)
                return deepcopy(selected)
            def observe(self, obs):
                rig.events.append(('observe', obs['step']))
                rig.trip('restore_observer')

        class Budget:
            def __init__(self, routes):
                rig.trip('budget_constructor')
            def remaining(self, *args):
                return 0
            def apply(self, selected, *args, **kwargs):
                return selected

        class Spatial:
            def __init__(self, *args, **kwargs):
                self.plans = []; self._pending = None; self.crop_intent = None
                self.sale_obligation = None; self._crop_repair = None
                self.events = []; self.receipt_events = []; self.crop_report = {}
                self.installed = False
            def transform(self, obs, selected, controller):
                return selected
            def install(self, controller):
                rig.trip('spatial_install')
                self.installed = True
            def configure(self, cfg):
                pass
            def observe_market_receipt(self, *args):
                rig.trip('spatial_observe')
            def observe_crop_receipts(self, *args):
                pass
            def guard_returned(self, obs, selected, **kwargs):
                return selected
            def guard_crop_returned(self, obs, selected, post):
                return selected
            def crop_market(self, obs, selected, *args):
                return selected
            def finish(self, *args):
                rig.events.append(('spatial_finish', self.installed))
            def finish_crop(self, *args, **kwargs):
                pass

        class Quadrant:
            def __init__(self, *args):
                self.plan = None; self.pending = None; self.events = []
            def install(self, controller):
                rig.trip('quadrant_install')
            def configure(self, cfg):
                pass
            def finish(self, *args):
                rig.events.append(('quadrant_finish',))

        class History:
            def __init__(self, **kwargs):
                rig.trip('history_constructor')
                self.fill_result = None; self.diagnostics = {}
            def observe(self, obs):
                rig.trip('history_observe')
            def transform(self, obs, cfg, selected, post, **kwargs):
                rig.trip('history_transform')
                return selected
            def remember(self, obs, cfg, returned, post):
                rig.events.append(('remember', obs['step'], deepcopy(returned)))

        def early_capital(mechanics, obs, cfg, selected, route, decisions):
            rig.events.append(('early_capital',))
            return selected, {'changed': False}

        doubles = {
            'frozen_selected': module('frozen_selected', FrozenSelected=Consumer),
            'integrated_selected': module('integrated_selected', IntegratedSelectedAgent=Consumer),
            'spatial_tempo': module('spatial_tempo', SpatialTempo=Spatial),
            'fourth_quadrant': module('fourth_quadrant', FourthQuadrant=Quadrant),
            'terminal_history_join': module('terminal_history_join', TerminalHistoryJoin=History),
            'scheduler': module('scheduler', m=NS(), parent=NS(DECISIONS=[])),
            'mechanics': module('mechanics'),
            'early_capital': module('early_capital', order_early_capital=early_capital),
            'operating_stock': module('operating_stock', protect_feed_stock=lambda *a: (a[3], {})),
        }
        self.modules = patch.dict(sys.modules, doubles)
        self.modules.__enter__()
        name = '_cold_test_runtime'
        self.m = module(name, __file__=str(runtime))
        sys.modules[name] = self.m
        exec(compile(self.source, str(runtime), 'exec'), self.m.__dict__)
        self.foreign = self.m.deadline.DeadlineExceeded('foreign caller cancellation')

        def load(name, path, **kwargs):
            if name == '_titan_funding':
                rig.trip('funding_load')
                return NS(select_seed_queue=None)
            if name == '_titan_seed_budget':
                return NS(SeedBudget=Budget)
            if name == '_titan_terminal_composition':
                return NS(TerminalOwner=lambda controller: controller)
            if name == '_titan_committed_seed_retry':
                return NS(apply_committed_seed_retry=lambda agent, obs, cfg, selected: (selected, {}))
            if name == '_titan_redundant_hire':
                return NS(propose_redundant_hires=lambda m, obs, cfg, selected, **kw: (selected, {}))
            if name == '_titan_fourth_quadrant_mechanics':
                return NS()
            raise AssertionError('unexpected collaborator load: ' + name)

        self.m.load = load
        self.agent = self.m.TitanAgent(self.m.Features(**self.features))
        actual_finish = self.agent._finish_production
        def finish(*args, **kwargs):
            rig.finish_calls += 1
            return actual_finish(*args, **kwargs)
        self.agent._finish_production = finish
        return self

    def __exit__(self, *exc):
        self.modules.__exit__(*exc)
        self.directory.cleanup()

    @contextmanager
    def trace_initialization(self):
        previous = sys.gettrace()
        code = self.m.TitanAgent._initialize.__code__
        def trace(frame, event, arg):
            if frame.f_code is code and event == 'line':
                index = len(self.init_lines)
                self.init_lines.append(frame.f_lineno)
                if self.cut == index:
                    raise self.m.deadline._ACTIVE_TIMER.get().expired
            return trace
        sys.settrace(trace)
        try:
            yield
        finally:
            sys.settrace(previous)

    def run(self, obs, **kwargs):
        if self.cut is not None or kwargs.pop('capture', False):
            with self.trace_initialization():
                return self.agent.act(obs, {}, **kwargs)
        return self.agent.act(obs, {}, **kwargs)


class ColdStartAcceptance(unittest.TestCase):
    def test_predecessor_early_capital_crashes_in_actual_finalizer(self):
        for seat in (0, 1):
            with self.subTest(seat=seat), Rig(BASELINE, features={'early_capital': True},
                                           fault='funding_load') as r:
                with self.assertRaisesRegex(AttributeError, 'controller'):
                    r.run(observation(seat))
                self.assertEqual(r.finish_calls, 1)
                self.assertEqual(r.producer_calls, 0)
                COUNTS['baseline_crash_witnesses'] += 1

    def test_predecessor_terminal_feed_crashes_in_actual_snapshot(self):
        for seat in (0, 1):
            with self.subTest(seat=seat), Rig(BASELINE, features={'operating_stock': True},
                                           fault='funding_load') as r:
                with self.assertRaisesRegex(AttributeError, 'consumer'):
                    r.run(observation(seat, 718))
                self.assertEqual(r.finish_calls, 1)
                COUNTS['baseline_crash_witnesses'] += 1

    def test_candidate_exact_fallback_before_first_consumer(self):
        for seat in (0, 1):
            for step in (0, 23, 372, 695, 718):
                for hands in (0, 1, 5, 8):
                    with self.subTest(seat=seat, step=step, hands=hands), Rig(CANDIDATE,
                         features={'early_capital': True, 'operating_stock': True},
                         fault='funding_load') as r:
                        obs = observation(seat, step, hands); saved = deepcopy(obs)
                        expected = (r.m.deadline.terminal_liquidation_fallback(obs, {}) if step == 718
                                    else r.m.deadline.legal_pass(obs))
                        self.assertEqual(r.run(obs), expected)
                        self.assertEqual(obs, saved)
                        self.assertEqual(r.finish_calls, 0)
                        self.assertEqual(r.producer_calls, 0)
                        self.assertFalse(r.agent.ready)
                        self.assertIsNone(r.agent._completed_route)
                        self.assertIsNone(r.agent._completed_seller_state)
                        self.assertEqual(len(r.agent._seller_fallback_observations), 1)
                        self.assertEqual(r.agent.diagnostics['fallback_stage'], 'cold_start')

    def test_each_reached_initialize_line_before_binding_or_install(self):
        configurations = [
            {'consumer': 'frozen', 'early_capital': True, 'operating_stock': True,
             'fourth_quadrant': True, 'idle_fertilizer': True, 'crop_release': True,
             'committed_seed_retry': True, 'redundant_hire': True},
            {'consumer': 'ordered', 'terminal_history': True, 'history_hypotheses': {}},
            {'consumer': 'parent'},
            {'consumer': 'frozen', 'terminal_route': True},
        ]
        for features in configurations:
            with Rig(CANDIDATE, features=features) as clean:
                clean.run(observation(), capture=True)
                cuts = len(clean.init_lines)
            self.assertGreater(cuts, 10)
            for cut in range(cuts):
                for seat in (0, 1):
                    with self.subTest(features=features, cut=cut, seat=seat), Rig(
                            CANDIDATE, features=features, cut=cut) as r:
                        obs = observation(seat)
                        self.assertEqual(r.run(obs), r.m.deadline.legal_pass(obs))
                        self.assertEqual(len(r.init_lines), cut + 1)
                        self.assertEqual(r.finish_calls, 0)
                        self.assertEqual(r.producer_calls, 0)
                        self.assertFalse(r.agent.ready)
                        self.assertIsNone(r.agent._completed_seller_state)
                        COUNTS['initialization_cut_cells'] += 1

    def test_partial_collaborator_construction_does_not_finalize(self):
        for fault in ('consumer_constructor', 'budget_constructor', 'history_constructor',
                      'quadrant_install', 'spatial_install'):
            with self.subTest(fault=fault), Rig(CANDIDATE, features={
                    'fourth_quadrant': True, 'idle_fertilizer': True}, fault=fault) as r:
                obs = observation()
                self.assertEqual(r.run(obs), r.m.deadline.legal_pass(obs))
                self.assertEqual(r.finish_calls, 0)
                self.assertFalse(any(event[0].endswith('finish') for event in r.events))

    def test_cold_failure_then_reconstruction_replays_public_observation(self):
        with Rig(CANDIDATE, fault='funding_load') as r:
            r.run(observation(step=12))
            r.fault = None
            output = r.run(observation(step=13))
            self.assertEqual(output['farmer'], ['NORTH'])
            self.assertIn(('observe', 12), r.events)
            self.assertEqual(r.producer_calls, 1)
            self.assertEqual(r.finish_calls, 1)
            self.assertEqual(r.agent._seller_fallback_observations, [])
            self.assertTrue(r.agent.ready)

    def test_duplicate_cold_fallback_observation_is_not_double_counted(self):
        with Rig(CANDIDATE, fault='funding_load') as r:
            for _ in range(3):
                r.run(observation(step=12))
            self.assertEqual(len(r.agent._seller_fallback_observations), 1)
            r.run(observation(step=11))
            self.assertEqual(len(r.agent._seller_fallback_observations), 1)
            self.assertEqual(r.agent._seller_fallback_observations[0]['step'], 11)

    def test_later_producer_deadline_still_finalizes(self):
        for consumer in ('frozen', 'ordered', 'parent'):
            with self.subTest(consumer=consumer), Rig(CANDIDATE,
                  features={'consumer': consumer}, fault='producer') as r:
                obs = observation()
                self.assertEqual(r.run(obs), r.m.deadline.legal_pass(obs))
                self.assertEqual(r.producer_calls, 1)
                self.assertEqual(r.finish_calls, 1)
                self.assertEqual(r.agent.diagnostics['fallback_stage'], 'production')
                self.assertIsNone(r.agent._completed_seller_state)

    def test_selected_fallback_still_finalizes_and_commits_only_route(self):
        for consumer in ('frozen', 'ordered'):
            with self.subTest(consumer=consumer), Rig(CANDIDATE,
                  features={'consumer': consumer}, fault='transform') as r:
                obs = observation()
                output = r.run(obs)
                self.assertEqual(output, r.agent.selected)
                self.assertEqual(r.producer_calls, 1)
                self.assertEqual(r.finish_calls, 1)
                self.assertEqual(r.agent._completed_route, 0)
                self.assertIsNone(r.agent._completed_seller_state)
                self.assertFalse(r.agent.ready)

    def test_warm_selected_fallback_preserves_last_completed_seller_state(self):
        with Rig(CANDIDATE) as r:
            r.run(observation(step=5))
            completed = deepcopy(r.agent._completed_seller_state)
            r.fault = 'transform'
            result = r.run(observation(step=6))
            self.assertEqual(result, r.agent.selected)
            self.assertEqual(r.agent._completed_seller_state, completed)
            self.assertEqual(r.finish_calls, 2)
            self.assertEqual(r.producer_calls, 2)
            self.assertEqual(len(r.agent._seller_fallback_observations), 1)

    def test_history_observation_deadline_after_init_still_finalizes(self):
        for consumer in ('frozen', 'ordered'):
            with self.subTest(consumer=consumer), Rig(CANDIDATE, features={
                    'consumer': consumer, 'terminal_history': True,
                    'history_hypotheses': {}}, fault='history_observe') as r:
                obs = observation()
                self.assertEqual(r.run(obs), r.m.deadline.legal_pass(obs))
                self.assertEqual(r.finish_calls, 1)
                self.assertEqual(r.producer_calls, 0)
                self.assertIsNone(r.agent.history)

    def test_post_init_spatial_observation_deadline_keeps_finalizer(self):
        # stage is still 'cold_start' here although _initialize returned. A
        # stage-name guard would drop this already-initialized finalizer.
        with Rig(CANDIDATE, fault='spatial_observe') as r:
            obs = observation()
            self.assertEqual(r.run(obs), r.m.deadline.legal_pass(obs))
            self.assertEqual(r.finish_calls, 1)
            self.assertEqual(r.producer_calls, 0)
            self.assertTrue(r.agent.spatial.installed)

    def test_reconstruction_failure_preserves_previous_completed_state(self):
        with Rig(CANDIDATE) as r:
            r.run(observation(step=5))
            completed = deepcopy(r.agent._completed_seller_state)
            route = r.agent._completed_route
            r.agent.ready = False
            r.fault = 'funding_load'
            obs = observation(step=6)
            self.assertEqual(r.run(obs), r.m.deadline.legal_pass(obs))
            self.assertEqual(r.agent._completed_seller_state, completed)
            self.assertEqual(r.agent._completed_route, route)
            self.assertEqual(r.finish_calls, 1)  # only the earlier success
            self.assertEqual(r.producer_calls, 1)
            r.fault = None
            self.assertEqual(r.run(observation(step=7))['farmer'], ['NORTH'])
            self.assertIn(('observe', 6), r.events)
            self.assertEqual(r.finish_calls, 2)

    def test_successful_baseline_and_candidate_action_state_equality(self):
        for consumer in ('frozen', 'ordered', 'parent'):
            results = []
            for source in (BASELINE, CANDIDATE):
                with Rig(source, features={'consumer': consumer}) as r:
                    outputs = [r.run(observation(step=s)) for s in range(6)]
                    results.append((outputs, r.agent._completed_route,
                                    r.agent._completed_seller_state,
                                    r.finish_calls, r.producer_calls))
            self.assertEqual(results[0], results[1])
            self.assertEqual(results[1][-2:], (6, 6))

    def test_entrypoint_prelude_remains_no_finalizer(self):
        for consumer in ('frozen', 'ordered', 'parent'):
            with Rig(CANDIDATE, features={'consumer': consumer}) as r:
                obs = observation(step=718)
                expected = r.m.deadline.terminal_liquidation_fallback(obs, {})
                self.assertEqual(r.run(obs, entry_started=time.perf_counter()-2), expected)
                self.assertEqual(r.finish_calls, 0)
                self.assertEqual(r.producer_calls, 0)
                self.assertEqual(r.agent.diagnostics['fallback_stage'], 'entrypoint_prelude')

    def test_foreign_deadline_exception_is_not_consumed(self):
        for fault in ('funding_load', 'producer', 'transform'):
            with Rig(CANDIDATE, fault='foreign:' + fault) as r:
                with self.assertRaises(r.m.deadline.DeadlineExceeded) as caught:
                    r.run(observation())
                self.assertIs(caught.exception, r.foreign)
                self.assertEqual(r.finish_calls, 0)
                self.assertIsNone(r.agent._completed_seller_state)

    def test_non_deadline_exception_is_not_converted_into_success(self):
        with Rig(CANDIDATE, fault='value:funding_load') as r:
            with self.assertRaisesRegex(ValueError, 'deliberate'):
                r.run(observation())
            self.assertEqual(r.finish_calls, 0)

    def test_actual_alarm_cold_cancel_restores_outer_signal(self):
        before_handler = signal.getsignal(signal.SIGALRM)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))
        with Rig(CANDIDATE, features={'early_capital': True,
                'budget_seconds': 0.03, 'reserve_seconds': 0.01},
                fault='alarm:funding_load') as r:
            obs = observation()
            self.assertEqual(r.run(obs), r.m.deadline.legal_pass(obs))
            self.assertEqual(r.finish_calls, 0)
            self.assertIsNone(r.m.deadline._ACTIVE_TIMER.get())
            self.assertEqual(r.agent.diagnostics['fallback_stage'], 'cold_start')
            self.assertIn(('fault_reached', 'funding_load'), r.events)
        self.assertEqual(signal.getsignal(signal.SIGALRM), before_handler)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))
        COUNTS['real_alarm_cases'] += 1

    def test_actual_worker_trace_cold_cancel_restores_trace(self):
        result = []
        def worker():
            try:
                before = sys.gettrace()
                with Rig(CANDIDATE, features={'early_capital': True,
                        'budget_seconds': 0.03, 'reserve_seconds': 0.01},
                        fault='worker:funding_load') as r:
                    obs = observation()
                    output = r.run(obs)
                    result.append((output == r.m.deadline.legal_pass(obs),
                                   r.finish_calls, r.m.deadline._ACTIVE_TIMER.get(),
                                   sys.gettrace() is before,
                                   r.agent.diagnostics['fallback_stage'],
                                   ('fault_reached', 'funding_load') in r.events))
            except BaseException as error:
                result.append(error)
        t = threading.Thread(target=worker)
        t.start(); t.join(3)
        self.assertFalse(t.is_alive())
        self.assertEqual(result, [(True, 0, None, True, 'cold_start', True)])
        COUNTS['real_worker_trace_cases'] += 1


def main(argv=None):
    global BASELINE, CANDIDATE, DEADLINE
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--candidate', type=Path, required=True)
    p.add_argument('--candidate-blob', required=True)
    p.add_argument('--deadline', type=Path, required=True)
    args = p.parse_args(argv)
    try:
        BASELINE = args.baseline.read_bytes()
        CANDIDATE = args.candidate.read_bytes()
        DEADLINE = args.deadline.read_bytes()
        for name, data, expected in [('baseline', BASELINE, BASELINE_BLOB),
                                     ('candidate', CANDIDATE, args.candidate_blob),
                                     ('deadline', DEADLINE, DEADLINE_BLOB)]:
            if git_blob(data) != expected:
                raise ValueError(name + ' Git blob mismatch')
        if len(args.candidate_blob) != 40 or any(c not in '0123456789abcdef' for c in args.candidate_blob):
            raise ValueError('candidate-blob must be a full lowercase Git SHA-1')
    except (OSError, ValueError) as error:
        print('INPUT_REFUSED: ' + str(error), file=sys.stderr)
        return 2
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ColdStartAcceptance)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({'schema': 'v4-cold-start-acceptance/v1',
        'baseline_blob': git_blob(BASELINE), 'candidate_blob': git_blob(CANDIDATE),
        'deadline_blob': git_blob(DEADLINE), 'python': sys.version.split()[0],
        'optimized': not __debug__, 'tests': result.testsRun,
        'failures': len(result.failures), 'errors': len(result.errors),
        'counts': COUNTS, 'full_game_economics': False,
        'production_promoted': False}, sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
