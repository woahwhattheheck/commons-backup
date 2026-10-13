# SPDX-License-Identifier: Apache-2.0
"""Test the actual TitanAgent/timer join with controlled phase callbacks.

This invokes TitanAgent.act, not a duplicate guard. It does not initialize real
policies, import an engine, exercise the full archive, or run games. Use in a
fresh main-thread POSIX subprocess. --runtime names the actual runtime file;
its reference/titan-current/deadline_adapter.py must remain beside it.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import signal
import sys
import time
from types import SimpleNamespace
import unittest

R = None
DETAILS = []
SELECTED = {'farmer': ['WEST'], 'hands': [['PASS']], 'market': [['SELL', 'MILK', 2]]}
OUTPUT = {'farmer': ['WEST'], 'hands': [['PASS']], 'market': [['SELL', 'MILK', 1]]}
OBS = {'player': 0, 'step': 100, 'day': 4, 'hour': 4, 'farms': [{'hands': [[0, 0]]}]}


def digest(path):
    data = Path(path).read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
            'git_blob': hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()}


def actor(budget=.04, production=None, transform=None):
    obj = R.TitanAgent(R.Features(budget_seconds=budget, reserve_seconds=0))
    counts = {'initialize': 0, 'production': 0, 'transform': 0}
    def produce(obs):
        counts['production'] += 1
        return production(obs) if production else copy.deepcopy(SELECTED)
    def consume(*args):
        counts['transform'] += 1
        return transform(*args) if transform else copy.deepcopy(OUTPUT)
    def initialize():
        counts['initialize'] += 1
        obj.production = SimpleNamespace(act=produce)
        obj.transform_selected = consume
        obj.ready = True
    obj._initialize = initialize
    return obj, counts


class TimerJoinTests(unittest.TestCase):
    def setUp(self):
        self.handler = signal.getsignal(signal.SIGALRM)
        self.timer = signal.getitimer(signal.ITIMER_REAL)
        if self.timer[0]:
            raise RuntimeError('Use a fresh subprocess without a pre-existing timer')

    def tearDown(self):
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, self.handler)
        signal.setitimer(signal.ITIMER_REAL, *self.timer)

    def broad_case(self, stage):
        swallowed = []
        def pause(*_):
            try:
                time.sleep(.12)
            except Exception:
                swallowed.append(True)
            return copy.deepcopy(SELECTED if stage == 'production' else OUTPUT)
        obj, counts = actor(production=pause if stage == 'production' else None,
                            transform=pause if stage == 'selected_transform' else None)
        if stage == 'cold_start':
            initialize = obj._initialize
            def cold():
                pause(); initialize()
            obj._initialize = cold
        started = time.perf_counter()
        result = obj.act(copy.deepcopy(OBS))
        DETAILS.append({'case': 'broad_'+stage, 'elapsed_seconds': time.perf_counter()-started,
                        'swallowed': bool(swallowed), 'counts': dict(counts),
                        'status': obj.diagnostics.get('status'), 'ready': obj.ready})
        self.assertFalse(swallowed)
        self.assertEqual(obj.diagnostics['fallback_stage'], stage)
        self.assertEqual(result, SELECTED if stage == 'selected_transform' else R.deadline.legal_pass(OBS))
        self.assertFalse(obj.ready)
        self.assertEqual(counts['production'], 0 if stage == 'cold_start' else 1)
        self.assertEqual(counts['transform'], 1 if stage == 'selected_transform' else 0)

    def test_broad_cold_handler_cannot_consume_expiry(self):
        self.broad_case('cold_start')

    def test_broad_production_handler_cannot_consume_expiry(self):
        self.broad_case('production')

    def test_broad_transform_handler_cannot_consume_expiry(self):
        self.broad_case('selected_transform')

    def test_foreign_cancellation_preserves_exception_identity(self):
        error = R.deadline.DeadlineExceeded('foreign')
        def fail(*_): raise error
        obj, counts = actor(transform=fail)
        with self.assertRaises(R.deadline.DeadlineExceeded) as caught:
            obj.act(copy.deepcopy(OBS))
        self.assertIs(caught.exception, error)
        self.assertNotEqual(obj.diagnostics.get('status'), 'deadline_fallback')
        self.assertEqual((counts['production'], counts['transform']), (1, 1))

    def test_nested_caller_timer_expiry_is_not_our_fallback(self):
        def pause(*_): time.sleep(.09); return OUTPUT
        obj, _ = actor(.2, transform=pause)
        timer = R.deadline._DeadlineTimer(.02)
        with self.assertRaises(R.deadline.DeadlineExceeded) as caught:
            with timer:
                obj.act(copy.deepcopy(OBS))
        self.assertIs(caught.exception, timer.expired)
        self.assertNotEqual(obj.diagnostics.get('status'), 'deadline_fallback')

    def test_earlier_caller_handler_exception_propagates(self):
        error = LookupError('caller alarm')
        def outer(*_): raise error
        def pause(*_): time.sleep(.09); return OUTPUT
        obj, _ = actor(.2, transform=pause)
        signal.signal(signal.SIGALRM, outer)
        signal.setitimer(signal.ITIMER_REAL, .02)
        with self.assertRaises(LookupError) as caught:
            obj.act(copy.deepcopy(OBS))
        self.assertIs(caught.exception, error)
        self.assertIs(signal.getsignal(signal.SIGALRM), outer)
        self.assertNotEqual(obj.diagnostics.get('status'), 'deadline_fallback')

    def test_later_caller_timer_retains_remaining_time(self):
        def outer(*_): pass
        obj, _ = actor(.1)
        signal.signal(signal.SIGALRM, outer)
        signal.setitimer(signal.ITIMER_REAL, .4)
        self.assertEqual(obj.act(copy.deepcopy(OBS)), OUTPUT)
        remaining, interval = signal.getitimer(signal.ITIMER_REAL)
        self.assertGreater(remaining, .1)
        self.assertLess(remaining, .4)
        self.assertEqual(interval, 0)
        self.assertIs(signal.getsignal(signal.SIGALRM), outer)

    def test_periodic_caller_timer_keeps_cadence(self):
        fired = []
        def outer(*_): fired.append(time.monotonic())
        def pause(*_): time.sleep(.07); return OUTPUT
        obj, _ = actor(.25, transform=pause)
        signal.signal(signal.SIGALRM, outer)
        signal.setitimer(signal.ITIMER_REAL, .01, .015)
        self.assertEqual(obj.act(copy.deepcopy(OBS)), OUTPUT)
        remaining, interval = signal.getitimer(signal.ITIMER_REAL)
        self.assertGreaterEqual(len(fired), 2)
        self.assertGreater(remaining, 0)
        self.assertAlmostEqual(interval, .015, places=5)
        DETAILS.append({'case': 'periodic_caller', 'ticks': len(fired), 'interval': interval})

    def test_production_and_transform_share_one_budget(self):
        completed = []
        def production(*_): time.sleep(.035); return copy.deepcopy(SELECTED)
        def transform(*_): time.sleep(.055); completed.append(True); return OUTPUT
        obj, counts = actor(.06, production=production, transform=transform)
        self.assertEqual(obj.act(copy.deepcopy(OBS)), SELECTED)
        self.assertFalse(completed)
        self.assertEqual(obj.diagnostics['fallback_stage'], 'selected_transform')
        self.assertEqual((counts['production'], counts['transform']), (1, 1))

    def test_own_expiry_reinitializes_before_next_selection(self):
        first = []
        def transform(*_):
            if not first:
                first.append(True); time.sleep(.12)
            return copy.deepcopy(OUTPUT)
        obj, counts = actor(transform=transform)
        self.assertEqual(obj.act(copy.deepcopy(OBS)), SELECTED)
        self.assertFalse(obj.ready)
        self.assertEqual(obj.act(copy.deepcopy(OBS)), OUTPUT)
        self.assertTrue(obj.ready)
        self.assertEqual(counts, {'initialize': 2, 'production': 2, 'transform': 2})
        self.assertEqual(obj.diagnostics['parent_calls'], 1)
        DETAILS.append({'case': 'next_call_reinitialization', 'counts': dict(counts)})


def main():
    global R
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--runtime', type=Path, required=True)
    ap.add_argument('--report', type=Path, required=True)
    ap.add_argument('--broad-only', action='store_true')
    args = ap.parse_args()
    runtime = args.runtime.resolve()
    spec = importlib.util.spec_from_file_location('titan_timer_join_runtime', runtime)
    R = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = R
    spec.loader.exec_module(R)
    names = unittest.defaultTestLoader.getTestCaseNames(TimerJoinTests)
    if args.broad_only:
        names = [n for n in names if n.startswith('test_broad_')]
    suite = unittest.TestSuite(TimerJoinTests(n) for n in names)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {'schema': 'titan.timer.join.v1', 'runtime': digest(runtime),
              'adapter': digest(R.deadline.__file__), 'test': digest(__file__),
              'tests_run': result.testsRun, 'failures': [[str(t), e] for t, e in result.failures],
              'errors': [[str(t), e] for t, e in result.errors], 'details': DETAILS,
              'policy_phases': 'controlled callbacks; actual TitanAgent.act and timer',
              'full_archive_executed': False, 'full_games': 0, 'new_game_seeds': [],
              'engine_transitions': 0, 'broad_only': args.broad_only}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2)+'\n')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
