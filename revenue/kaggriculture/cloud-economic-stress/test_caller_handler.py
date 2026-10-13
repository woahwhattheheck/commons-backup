# SPDX-License-Identifier: Apache-2.0
"""Exercise the existing deadline adapter's caller-handler rebinding contract.

Run in a fresh Unix main-thread process. Deterministic signal/clock cases cover
ordering without wall-time tolerances; real SIGALRM cases retain elapsed times
but assert actions, handler identities and call counts rather than timing speed.
No game engine, policy panel, or provider service is used.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import signal
import sys
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

D = None
MEASUREMENTS = []
OBS = {"player": 0, "step": 1, "farms": [{"hands": []}]}
SELECTED = {"farmer": ["PASS"], "hands": [], "market": [["SELL", "MILK", 1]]}


def load_adapter(path):
    spec = importlib.util.spec_from_file_location("caller_handler_subject", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DefaultSignal(BaseException):
    pass


class FakeSignal:
    """Small timer model; only the platform signal boundary is substituted."""
    SIGALRM = signal.SIGALRM
    SIG_DFL = signal.SIG_DFL
    SIG_IGN = signal.SIG_IGN
    ITIMER_REAL = signal.ITIMER_REAL

    def __init__(self):
        self.now = 0.0
        self.handler = self.SIG_IGN
        self.due = None
        self.interval = 0.0
        self.frame = object()

    def getsignal(self, sig):
        return self.handler

    def signal(self, sig, handler):
        previous = self.handler
        self.handler = handler
        return previous

    def setitimer(self, which, seconds, interval=0.0):
        old = self.getitimer(which)
        self.due = self.now + seconds if seconds else None
        self.interval = interval
        return old

    def getitimer(self, which):
        return (max(0.0, self.due - self.now) if self.due is not None else 0.0,
                self.interval)

    def raise_signal(self, sig):
        if self.handler == self.SIG_DFL:
            raise DefaultSignal()
        if callable(self.handler):
            self.handler(sig, self.frame)

    def advance(self, target):
        count = 0
        while self.due is not None and self.due <= target:
            count += 1
            if count > 100:
                raise AssertionError("signal loop did not make progress")
            self.now = self.due
            self.due = self.now + self.interval if self.interval else None
            self.raise_signal(self.SIGALRM)
        self.now = target


class DeterministicTests(unittest.TestCase):
    def setUp(self):
        self.sig = FakeSignal()
        clock = SimpleNamespace(monotonic=lambda: self.sig.now,
                                perf_counter=lambda: self.sig.now)
        self.signal_patch = patch.object(D, 'signal', self.sig)
        self.clock_patch = patch.object(D, 'time', clock)
        self.signal_patch.start(); self.clock_patch.start()
        self.addCleanup(self.clock_patch.stop)
        self.addCleanup(self.signal_patch.stop)
        self.assertIsNone(D._ACTIVE_TIMER.get())

    def arm(self, handler, remaining=1, interval=0):
        self.sig.signal(signal.SIGALRM, handler)
        self.sig.setitimer(signal.ITIMER_REAL, remaining, interval)

    def own_expiry_after(self, first):
        timer = D._DeadlineTimer(3)
        self.arm(first)
        with self.assertRaises(D.DeadlineExceeded) as caught:
            with timer:
                self.sig.advance(4)
        self.assertIs(caught.exception, timer.expired)
        self.assertIsNone(D._ACTIVE_TIMER.get())

    def test_callable_replacement_does_not_receive_guard_expiry(self):
        events = []
        def replacement(*args): events.append('replacement')
        def first(*args):
            events.append('first')
            self.sig.signal(signal.SIGALRM, replacement)
        self.own_expiry_after(first)
        self.assertEqual(events, ['first'])
        self.assertIs(self.sig.handler, replacement)

    def test_ignore_replacement_does_not_suppress_guard_expiry(self):
        def first(*args): self.sig.signal(signal.SIGALRM, signal.SIG_IGN)
        self.own_expiry_after(first)
        self.assertEqual(self.sig.handler, signal.SIG_IGN)

    def test_default_replacement_does_not_receive_guard_expiry(self):
        def first(*args): self.sig.signal(signal.SIGALRM, signal.SIG_DFL)
        self.own_expiry_after(first)
        self.assertEqual(self.sig.handler, signal.SIG_DFL)

    def test_handler_observes_and_replaces_its_own_binding(self):
        seen = []
        def replacement(*args): pass
        def first(sig, frame):
            seen.append((self.sig.getsignal(sig), self.sig.signal(sig, replacement), frame,
                         D._ACTIVE_TIMER.get()))
        self.arm(first)
        with D._DeadlineTimer(5): self.sig.advance(2)
        self.assertEqual(seen, [(first, first, self.sig.frame, None)])
        self.assertIs(self.sig.handler, replacement)

    def test_periodic_replacement_follows_cadence_not_guard_deadline(self):
        events = []
        def replacement(*args): events.append(('second', self.sig.now))
        def first(*args):
            events.append(('first', self.sig.now)); self.sig.signal(signal.SIGALRM, replacement)
        self.arm(first, 1, 1)
        timer = D._DeadlineTimer(3.5)
        with self.assertRaises(D.DeadlineExceeded) as caught:
            with timer: self.sig.advance(4)
        self.assertIs(caught.exception, timer.expired)
        self.assertEqual(events, [('first', 1), ('second', 2), ('second', 3)])
        self.assertIs(self.sig.handler, replacement)
        self.assertEqual(self.sig.getitimer(signal.ITIMER_REAL), (.5, 1))

    def test_rearmed_replacement_and_own_deadline_both_survive(self):
        events = []
        def replacement(*args): events.append(('second', self.sig.now))
        def first(*args):
            events.append(('first', self.sig.now))
            self.sig.signal(signal.SIGALRM, replacement)
            self.sig.setitimer(signal.ITIMER_REAL, .5)
        self.own_expiry_after(first)
        self.assertEqual(events, [('first', 1), ('second', 1.5)])
        self.assertIs(self.sig.handler, replacement)

    def test_multiple_handler_generations_are_preserved(self):
        events = []
        def third(*args): events.append('third')
        def second(*args):
            events.append('second'); self.sig.signal(signal.SIGALRM, third)
        def first(*args):
            events.append('first'); self.sig.signal(signal.SIGALRM, second)
        self.arm(first, 1, 1)
        with D._DeadlineTimer(10): self.sig.advance(3)
        self.assertEqual(events, ['first', 'second', 'third'])
        self.assertIs(self.sig.handler, third)
        self.assertEqual(self.sig.getitimer(signal.ITIMER_REAL), (1, 1))

    def test_replacement_and_disarm_survive_normal_exit(self):
        def replacement(*args): pass
        def first(*args):
            self.sig.signal(signal.SIGALRM, replacement)
            self.sig.setitimer(signal.ITIMER_REAL, 0)
        self.arm(first, 1, 1)
        with D._DeadlineTimer(5): self.sig.advance(2)
        self.assertIs(self.sig.handler, replacement)
        self.assertEqual(self.sig.getitimer(signal.ITIMER_REAL), (0, 0))

    def test_replacement_survives_foreign_exception_identity(self):
        error = RuntimeError('caller owns this error')
        def replacement(*args): pass
        def first(*args):
            self.sig.signal(signal.SIGALRM, replacement); raise error
        self.arm(first)
        with self.assertRaises(RuntimeError) as caught:
            with D._DeadlineTimer(5): self.sig.advance(2)
        self.assertIs(caught.exception, error)
        self.assertIs(self.sig.handler, replacement)
        self.assertIsNone(D._ACTIVE_TIMER.get())

    def test_replacement_survives_foreign_cancellation_identity(self):
        error = D.DeadlineExceeded('foreign timer')
        def replacement(*args): pass
        def first(*args):
            self.sig.signal(signal.SIGALRM, replacement); raise error
        self.arm(first)
        with self.assertRaises(D.DeadlineExceeded) as caught:
            with D._DeadlineTimer(5): self.sig.advance(2)
        self.assertIs(caught.exception, error)
        self.assertIs(self.sig.handler, replacement)

    def test_rearmed_replacement_exception_reaches_original_caller(self):
        error = KeyboardInterrupt('replacement caller')
        def replacement(*args): raise error
        def first(*args):
            self.sig.signal(signal.SIGALRM, replacement)
            self.sig.setitimer(signal.ITIMER_REAL, 1)
        self.arm(first)
        with self.assertRaises(KeyboardInterrupt) as caught:
            with D._DeadlineTimer(5): self.sig.advance(3)
        self.assertIs(caught.exception, error)
        self.assertIs(self.sig.handler, replacement)

    def test_nested_guards_restore_external_replacement(self):
        events = []
        def replacement(*args): events.append('replacement')
        def first(*args):
            events.append('first'); self.sig.signal(signal.SIGALRM, replacement)
        self.arm(first, 1, 2)
        outer = D._DeadlineTimer(8)
        with outer:
            with D._DeadlineTimer(5): self.sig.advance(2)
            self.assertEqual(self.sig.handler, outer._dispatch)
            self.assertIs(D._ACTIVE_TIMER.get(), outer)
            self.sig.advance(3.5)
        self.assertEqual(events, ['first', 'replacement'])
        self.assertIs(self.sig.handler, replacement)
        self.assertEqual(self.sig.getitimer(signal.ITIMER_REAL), (1.5, 2))

    def test_nested_outer_expiry_remains_outer_exception(self):
        events = []
        def replacement(*args): events.append('replacement')
        def first(*args):
            events.append('first'); self.sig.signal(signal.SIGALRM, replacement)
        self.arm(first)
        outer = D._DeadlineTimer(3)
        inner = D._DeadlineTimer(9)
        with self.assertRaises(D.DeadlineExceeded) as caught:
            with outer:
                with inner: self.sig.advance(5)
        self.assertIs(caught.exception, outer.expired)
        self.assertIsNot(caught.exception, inner.expired)
        self.assertEqual(events, ['first'])
        self.assertIs(self.sig.handler, replacement)
        self.assertIsNone(D._ACTIVE_TIMER.get())

    def test_unchanged_callable_and_schedule_stay_unchanged(self):
        events = []
        def caller(sig, frame): events.append((sig, frame))
        self.arm(caller, 1, 2)
        with D._DeadlineTimer(5): self.sig.advance(2)
        self.assertEqual(events, [(signal.SIGALRM, self.sig.frame)])
        self.assertIs(self.sig.handler, caller)
        self.assertEqual(self.sig.getitimer(signal.ITIMER_REAL), (1, 2))

    def test_default_caller_retains_default_signal_behavior(self):
        self.arm(signal.SIG_DFL)
        with self.assertRaises(DefaultSignal):
            with D._DeadlineTimer(5): self.sig.advance(2)
        self.assertEqual(self.sig.handler, signal.SIG_DFL)

    def test_ignored_caller_does_not_interfere_with_guard(self):
        self.arm(signal.SIG_IGN)
        timer = D._DeadlineTimer(3)
        with self.assertRaises(D.DeadlineExceeded) as caught:
            with timer: self.sig.advance(4)
        self.assertIs(caught.exception, timer.expired)
        self.assertEqual(self.sig.handler, signal.SIG_IGN)


@unittest.skipUnless(hasattr(signal, 'SIGALRM') and hasattr(signal, 'setitimer'),
                     'Unix signal support required')
class RealSignalTests(unittest.TestCase):
    def setUp(self):
        if threading.current_thread() is not threading.main_thread():
            self.skipTest('main-thread process required')
        if signal.getitimer(signal.ITIMER_REAL)[0]:
            self.skipTest('run in a fresh process, not with an active caller timer')
        self.previous = signal.getsignal(signal.SIGALRM)
        self.addCleanup(self.restore)

    def restore(self):
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, self.previous)

    def exercise(self, phase, replacement_kind='callable', error=None, periodic=False):
        events = []
        def replacement(*args): events.append('replacement')
        target = replacement if replacement_kind == 'callable' else signal.SIG_IGN
        def caller(*args):
            events.append('caller')
            signal.signal(signal.SIGALRM, target)
            if error is not None: raise error
        class Production:
            calls = 0
            def act(self, obs):
                self.calls += 1
                if phase == 'production': time.sleep(.1)
                return copy.deepcopy(SELECTED)
        class Integrated:
            production = Production()
            calls = 0
            diagnostics = {'fixture': True}
            def transform(self, obs, cfg, selected, **kwargs):
                self.calls += 1
                if phase == 'transform': time.sleep(.1)
                return selected
        i = Integrated()
        guard = D.DeadlineFallbackAgent(i, .04, .002)
        signal.signal(signal.SIGALRM, caller)
        signal.setitimer(signal.ITIMER_REAL, .008, .05 if periodic else 0)
        started = time.monotonic()
        if error is None:
            action = guard(OBS, {})
            elapsed = time.monotonic() - started
            MEASUREMENTS.append({'phase': phase, 'replacement': replacement_kind,
                'elapsed_seconds': elapsed, 'budget_seconds': .04, 'reserve_seconds': .002,
                'events': events[:], 'production_calls': i.production.calls,
                'transform_calls': i.calls, 'diagnostics': guard.diagnostics,
                'handler_preserved': signal.getsignal(signal.SIGALRM) is target})
            self.assertEqual(guard.diagnostics['status'], 'deadline_fallback')
            self.assertEqual(guard.diagnostics['fallback_stage'], phase)
            self.assertEqual(action, D.legal_pass(OBS) if phase == 'production' else SELECTED)
            self.assertEqual(i.production.calls, 1)
            self.assertEqual(i.calls, 0 if phase == 'production' else 1)
            self.assertEqual(events, ['caller'])
        else:
            with self.assertRaises(type(error)) as caught: guard(OBS, {})
            self.assertIs(caught.exception, error)
        self.assertIs(signal.getsignal(signal.SIGALRM), target)
        if periodic:
            remaining, interval = signal.getitimer(signal.ITIMER_REAL)
            self.assertGreater(remaining, 0)
            self.assertEqual(interval, .05)
        self.assertIsNone(D._ACTIVE_TIMER.get())

    def test_production_rebinding_keeps_exact_fallback(self): self.exercise('production')
    def test_transform_rebinding_keeps_selected_fallback(self): self.exercise('transform')
    def test_production_ignore_does_not_disable_own_deadline(self): self.exercise('production', 'ignore')
    def test_transform_ignore_does_not_disable_own_deadline(self): self.exercise('transform', 'ignore')
    def test_periodic_caller_replacement_survives_fallback(self): self.exercise('production', periodic=True)
    def test_caller_error_rebinding_preserves_error(self): self.exercise('production', error=RuntimeError('real caller'))
    def test_caller_baseexception_rebinding_preserves_error(self): self.exercise('production', error=KeyboardInterrupt('real caller'))


def main():
    global D
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--adapter', type=Path, default=Path(__file__).with_name('deadline_adapter.py'))
    p.add_argument('--report', type=Path)
    args = p.parse_args()
    D = load_adapter(args.adapter)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([
        unittest.defaultTestLoader.loadTestsFromTestCase(DeterministicTests),
        unittest.defaultTestLoader.loadTestsFromTestCase(RealSignalTests)]))
    report = {'adapter_sha256': hashlib.sha256(args.adapter.read_bytes()).hexdigest(),
        'test_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'python': platform.python_version(), 'platform': platform.platform(),
        'tests_run': result.testsRun,
        'failures': [{'test': case.id(), 'traceback': text} for case, text in result.failures],
        'errors': [{'test': case.id(), 'traceback': text} for case, text in result.errors],
        'skipped': [{'test': case.id(), 'reason': text} for case, text in result.skipped],
        'measurements': MEASUREMENTS, 'games': 0,
        'scope': 'Actual adapter; deterministic signal boundary and seven real SIGALRM methods; injected phase bodies, not full policy execution'}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    return not result.wasSuccessful()


if __name__ == '__main__': raise SystemExit(main())
