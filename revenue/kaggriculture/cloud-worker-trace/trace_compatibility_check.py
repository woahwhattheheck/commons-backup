# SPDX-License-Identifier: Apache-2.0
"""Standalone regression tests for TITAN worker trace coexistence.

Pass --source to an exact deadline_adapter.py. No engine, game, or network input
is used. A separate subprocess/daemon watchdog bounds infinite-loop probes.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import signal
import subprocess
import sys
import threading
import time
import traceback
import unittest
from pathlib import Path
from unittest.mock import patch

parser = argparse.ArgumentParser()
parser.add_argument('--source', type=Path, required=True)
parser.add_argument('--report', type=Path, required=True)
parser.add_argument('--case', action='append', help='Run only named test methods')
args = parser.parse_args()
spec = importlib.util.spec_from_file_location('tested_deadline', args.source.resolve())
D = importlib.util.module_from_spec(spec)
spec.loader.exec_module(D)
PROBES = []


def fixture():
    value = 1
    value += 2
    for i in range(3):
        value += i
    try:
        raise ValueError('fixture')
    except ValueError:
        value += 4
    return value


def generator_fixture():
    value = 1
    yield value
    value += 1
    yield value


class TraceCompatibility(unittest.TestCase):
    def worker(self, fn):
        result = []
        def run():
            try:
                result.append((True, fn()))
            except BaseException as error:
                result.append((False, error, traceback.format_exc()))
            finally:
                sys.settrace(None)
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        thread.join(2.0)
        self.assertFalse(thread.is_alive(), 'bounded worker did not return')
        self.assertTrue(result, 'worker returned no result')
        if not result[0][0]:
            raise AssertionError(result[0][2]) from result[0][1]
        return result[0][1]

    def probe(self, mode):
        command = [sys.executable, '-B', str(Path(__file__).with_name('probe_trace_flags.py')),
                   str(args.source.resolve()), mode]
        run = subprocess.run(command, text=True, capture_output=True, timeout=3)
        data = json.loads(run.stdout)
        PROBES.append({'command': command, 'returncode': run.returncode,
                       'stdout': run.stdout, 'stderr': run.stderr})
        self.assertEqual(run.returncode, 0, data)
        self.assertTrue(data.get('cancelled'), data)
        self.assertTrue(data.get('identity_preserved'), data)
        self.assertTrue(data.get('trace_restored'), data)
        self.assertTrue(data.get('line_flag_restored'), data)
        self.assertTrue(data.get('context_restored'), data)
        self.assertFalse(data.get('watchdog_expired'), data)
        self.assertLess(data['elapsed_seconds'], 0.25, data)

    def test_normal_inline_deadline(self): self.probe('normal')
    def test_muted_caller_deadline(self): self.probe('caller_muted')
    def test_muted_callee_deadline(self): self.probe('callee_muted')
    def test_muted_without_global_tracer(self): self.probe('muted_no_global')
    def test_callee_dynamically_mutes_lines(self): self.probe('dynamic_mute')
    def test_nested_outer_identity(self): self.probe('nested_outer')
    def test_nested_inner_identity(self): self.probe('nested_inner')

    def compare_trace(self, kind):
        def run():
            def collect(guarded):
                events = []
                def local(frame, event, arg):
                    if frame.f_code.co_name not in ('fixture', 'generator_fixture'):
                        return local
                    events.append((frame.f_code.co_name, event, frame.f_lineno,
                                   frame.f_trace_lines, frame.f_trace_opcodes))
                    if kind == 'dynamic' and event == 'line':
                        frame.f_trace_lines = False
                    if kind == 'clear' and event == 'line':
                        frame.f_trace = None
                        return None
                    if kind == 'none':
                        return None
                    return local
                def trace(frame, event, arg):
                    if frame.f_code.co_name not in ('fixture', 'generator_fixture'):
                        return None
                    if kind in ('muted', 'opcode'):
                        frame.f_trace_lines = False
                    if kind == 'opcode':
                        frame.f_trace_opcodes = True
                    events.append((frame.f_code.co_name, event, frame.f_lineno,
                                   frame.f_trace_lines, frame.f_trace_opcodes))
                    return local
                # Prime opcode monitoring before installation in both arms.
                # CPython 3.13.5 otherwise instruments the first cold target
                # differently from later invocations, independent of the guard.
                capture_frame = sys._getframe()
                prior_opcodes = capture_frame.f_trace_opcodes
                if kind == 'opcode':
                    capture_frame.f_trace_opcodes = True
                sys.settrace(trace)
                try:
                    if guarded:
                        with D._DeadlineTimer(0.5):
                            value = fixture()
                    else:
                        value = fixture()
                    self.assertIs(sys.gettrace(), trace)
                    self.assertIsNone(D._ACTIVE_TIMER.get())
                    return value, events
                finally:
                    sys.settrace(None)
                    capture_frame.f_trace_opcodes = prior_opcodes
            # CPython 3.13.5's first opcode-instrumented invocation is cold.
            # A reference-only priming call stabilizes the same target before
            # comparing either arm; this is not an executed TITAN game.
            if kind == 'opcode':
                collect(False)
            expected = collect(False)
            actual = collect(True)
            self.assertEqual(actual, expected)
            return {'kind': kind, 'events': len(actual[1])}
        return self.worker(run)

    def test_previous_tracer_event_parity(self): self.compare_trace('normal')
    def test_muted_tracer_no_forced_lines_leak(self): self.compare_trace('muted')
    def test_opcode_only_tracer_event_parity(self): self.compare_trace('opcode')
    def test_dynamic_line_flag_event_parity(self): self.compare_trace('dynamic')
    def test_local_none_return_matches_cpython(self): self.compare_trace('none')
    def test_explicit_local_trace_clear_preserved(self): self.compare_trace('clear')

    def test_suspended_generator_trace_restoration(self):
        def run():
            def trace(frame, event, arg):
                if frame.f_code.co_name == 'generator_fixture':
                    frame.f_trace_lines = False
                    return trace
                return None
            sys.settrace(trace)
            gen = generator_fixture()
            try:
                with D._DeadlineTimer(.5):
                    self.assertEqual(next(gen), 1)
                self.assertIs(gen.gi_frame.f_trace, trace)
                self.assertFalse(gen.gi_frame.f_trace_lines)
                self.assertEqual(next(gen), 2)
                self.assertIs(sys.gettrace(), trace)
                self.assertIsNone(D._ACTIVE_TIMER.get())
            finally:
                sys.settrace(None)
                gen.close()
        self.worker(run)

    def test_muted_caller_restored_on_normal_and_exception(self):
        def run():
            def trace(frame, event, arg): return trace
            frame = sys._getframe()
            sys.settrace(trace)
            frame.f_trace = trace
            frame.f_trace_lines = False
            sentinel = RuntimeError('caller sentinel')
            try:
                for mode in ('normal', 'exception'):
                    try:
                        with D._DeadlineTimer(.5):
                            if mode == 'exception':
                                raise sentinel
                            fixture()
                    except RuntimeError as error:
                        self.assertIs(error, sentinel)
                    self.assertIs(sys.gettrace(), trace)
                    self.assertIs(frame.f_trace, trace)
                    self.assertFalse(frame.f_trace_lines)
                    self.assertIsNone(D._ACTIVE_TIMER.get())
            finally:
                sys.settrace(None)
                frame.f_trace = None
                frame.f_trace_lines = True
        self.worker(run)

    def test_previous_tracer_exception_identity_and_cleanup(self):
        def run():
            sentinel = RuntimeError('previous tracer')
            def trace(frame, event, arg):
                if frame.f_code.co_name == 'fixture':
                    raise sentinel
                return trace
            sys.settrace(trace)
            try:
                with self.assertRaises(RuntimeError) as caught:
                    with D._DeadlineTimer(.5):
                        fixture()
                self.assertIs(caught.exception, sentinel)
                self.assertIs(sys.gettrace(), trace)
                self.assertIsNone(D._ACTIVE_TIMER.get())
            finally:
                sys.settrace(None)
        self.worker(run)

    def test_worker_never_touches_process_signal_state(self):
        def run():
            def forbidden(*a, **k):
                raise AssertionError('worker signal access')
            with patch.object(signal, 'getsignal', forbidden), \
                 patch.object(signal, 'signal', forbidden), \
                 patch.object(signal, 'setitimer', forbidden):
                with D._DeadlineTimer(.5):
                    self.assertEqual(fixture(), 10)
            self.assertIsNone(sys.gettrace())
            self.assertIsNone(D._ACTIVE_TIMER.get())
        self.worker(run)

    def test_native_sleep_checks_on_return(self):
        def run():
            timer = D._DeadlineTimer(.01)
            start = time.perf_counter()
            with self.assertRaises(D.DeadlineExceeded) as caught:
                with timer:
                    time.sleep(.025)
            self.assertIs(caught.exception, timer.expired)
            self.assertGreaterEqual(time.perf_counter() - start, .025)
            self.assertIsNone(sys.gettrace())
            self.assertIsNone(D._ACTIVE_TIMER.get())
        self.worker(run)

    def test_untraced_suspended_generator_restores_flags(self):
        def run():
            for muted in (False, True):
                gen = generator_fixture()
                gen.gi_frame.f_trace_lines = not muted
                try:
                    with D._DeadlineTimer(.5):
                        self.assertEqual(next(gen), 1)
                    self.assertIsNone(gen.gi_frame.f_trace)
                    self.assertEqual(gen.gi_frame.f_trace_lines, not muted)
                    self.assertEqual(next(gen), 2)
                    self.assertIsNone(sys.gettrace())
                    self.assertIsNone(D._ACTIVE_TIMER.get())
                finally:
                    gen.close()
        self.worker(run)

    def test_untraced_nested_scopes_restore_outer_dispatch(self):
        def run():
            outer = D._DeadlineTimer(.04)
            inner = D._DeadlineTimer(.008)
            with self.assertRaises(D.DeadlineExceeded) as outer_caught:
                with outer:
                    outer_trace = sys.gettrace()
                    with self.assertRaises(D.DeadlineExceeded) as inner_caught:
                        with inner:
                            while True:
                                pass
                    self.assertIs(inner_caught.exception, inner.expired)
                    self.assertIs(sys.gettrace(), outer_trace)
                    self.assertIs(D._ACTIVE_TIMER.get(), outer)
                    while True:
                        pass
            self.assertIs(outer_caught.exception, outer.expired)
            self.assertIsNone(sys.gettrace())
            self.assertIsNone(D._ACTIVE_TIMER.get())
        self.worker(run)

    def test_untraced_callee_frame_restored_after_cancel(self):
        def run():
            held = []
            def loop():
                held.append(sys._getframe())
                while True:
                    pass
            timer = D._DeadlineTimer(.01)
            with self.assertRaises(D.DeadlineExceeded) as caught:
                with timer:
                    loop()
            self.assertIs(caught.exception, timer.expired)
            self.assertEqual(len(held), 1)
            self.assertIsNone(held[0].f_trace)
            self.assertTrue(held[0].f_trace_lines)
            self.assertIsNone(sys.gettrace())
            self.assertIsNone(D._ACTIVE_TIMER.get())
            held.clear()
        self.worker(run)

    def test_two_workers_keep_independent_timers(self):
        barrier = threading.Barrier(2, timeout=1.)
        records = []
        def run(index):
            timer = D._DeadlineTimer(.02)
            barrier.wait()
            try:
                with timer:
                    while True:
                        pass
            except D.DeadlineExceeded as error:
                records.append((index, error is timer.expired,
                                sys.gettrace() is None,
                                D._ACTIVE_TIMER.get() is None))
        threads = [threading.Thread(target=run, args=(i,), daemon=True)
                   for i in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(2.)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(sorted(records), [(0, True, True, True), (1, True, True, True)])

    def test_main_thread_caller_alarm_restored(self):
        original = signal.getsignal(signal.SIGALRM)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0., 0.))
        def handler(signum, frame):
            raise AssertionError('caller alarm fired too soon')
        try:
            signal.signal(signal.SIGALRM, handler)
            signal.setitimer(signal.ITIMER_REAL, .5)
            timer = D._DeadlineTimer(.015)
            with self.assertRaises(D.DeadlineExceeded) as caught:
                with timer:
                    while True:
                        pass
            self.assertIs(caught.exception, timer.expired)
            self.assertIs(signal.getsignal(signal.SIGALRM), handler)
            self.assertGreater(signal.getitimer(signal.ITIMER_REAL)[0], 0.)
            self.assertIsNone(D._ACTIVE_TIMER.get())
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, original)


started = time.perf_counter()
suite = (unittest.TestSuite(TraceCompatibility(name) for name in args.case)
         if args.case else unittest.defaultTestLoader.loadTestsFromTestCase(TraceCompatibility))
result = unittest.TextTestRunner(verbosity=2).run(suite)
report = {'source': str(args.source.resolve()), 'python': sys.version,
          'tests': result.testsRun, 'failures': len(result.failures),
          'errors': len(result.errors), 'passed': result.wasSuccessful(),
          'elapsed_seconds': time.perf_counter() - started, 'probes': PROBES,
          'failure_details': [{'test': str(test), 'traceback': text}
                              for test, text in result.failures + result.errors],
          'full_games_executed': 0}
args.report.parent.mkdir(parents=True, exist_ok=True)
args.report.write_text(json.dumps(report, indent=2) + '\n')
raise SystemExit(0 if result.wasSuccessful() else 1)
