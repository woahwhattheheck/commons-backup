# SPDX-License-Identifier: Apache-2.0
"""Source-snapshot and module-lifecycle checks for the existing model driver.

Run with --driver pointing to the original or changed model_panel.py. Test
payloads are local synthetic Python modules. The replay integration uses the
unchanged real PR10113 source with an explicit synthetic clock and simulator;
it is not a full game or a repeat of the author's deadline test suite.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import py_compile
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

DRIVER = None
DEPENDENCIES = None


def identity(path):
    body = Path(path).read_bytes()
    return {'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest(),
            'git_blob': hashlib.sha1(b'blob '+str(len(body)).encode()+b'\0'+body).hexdigest()}


def load_driver(path):
    # Test harness loads its subject directly, not through the function under test.
    sys.path.insert(0, str(path.resolve().parent))
    name = 'prism_source_loader_subject'
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    exec(compile(path.read_bytes(), spec.origin, 'exec', dont_inherit=True), module.__dict__)
    return module


class SourceLoadingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.names = []

    def tearDown(self):
        for name in self.names:
            sys.modules.pop(name, None)

    def name(self, suffix='module'):
        value = 'prism_loading_fixture_' + suffix
        self.names.append(value)
        return value

    def file(self, body, filename='subject.py'):
        p = self.root / filename
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body.encode() if isinstance(body, str) else body)
        return p

    def stale(self, old, current, *, mode=py_compile.PycInvalidationMode.TIMESTAMP):
        self.assertLessEqual(len(old), len(current))
        old = old + b' ' * (len(current) - len(old))
        p = self.file(old)
        os.utime(p, (1700000000, 1700000000))
        cache = Path(py_compile.compile(str(p), doraise=True, invalidation_mode=mode))
        p.write_bytes(current)
        os.utime(p, (1700000000, 1700000000))
        return p, cache, cache.read_bytes()

    def test_timestamp_bytecode_cannot_replace_current_source(self):
        p, cache, saved = self.stale(b'VALUE = "OLD"\n', b'VALUE = "NEW"\n')
        self.assertEqual(DRIVER.load(p, self.name()).VALUE, 'NEW')
        self.assertEqual(cache.read_bytes(), saved)

    def test_unchecked_hash_bytecode_cannot_replace_current_source(self):
        p, cache, saved = self.stale(b'VALUE = "OLD"\n', b'VALUE = "NEW"\n',
                                    mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
        self.assertEqual(DRIVER.load(p, self.name()).VALUE, 'NEW')
        self.assertEqual(cache.read_bytes(), saved)

    def test_new_load_does_not_create_bytecode(self):
        p = self.file('VALUE = 3\n')
        self.assertEqual(DRIVER.load(p, self.name()).VALUE, 3)
        self.assertFalse(Path(importlib.util.cache_from_source(str(p))).exists())

    def test_current_syntax_error_is_not_hidden_by_timestamp_cache(self):
        p, _, _ = self.stale(b'VALUE = 1234\n', b'VALUE = @@@@\n')
        name = self.name()
        sentinel = ModuleType(name)
        sys.modules[name] = sentinel
        with self.assertRaises(SyntaxError):
            DRIVER.load(p, name)
        self.assertIs(sys.modules[name], sentinel)

    def test_source_absence_is_not_hidden_by_cache(self):
        p, cache, _ = self.stale(b'VALUE = "OLD"\n', b'VALUE = "NEW"\n')
        p.unlink()
        with self.assertRaises(FileNotFoundError):
            DRIVER.load(p, self.name())
        self.assertTrue(cache.exists())

    def test_existing_module_is_restored_on_runtime_error(self):
        name = self.name()
        previous = ModuleType(name)
        sys.modules[name] = previous
        p = self.file('PARTIAL = True\nraise ValueError("expected")\n')
        with self.assertRaisesRegex(ValueError, 'expected'):
            DRIVER.load(p, name)
        self.assertIs(sys.modules[name], previous)

    def test_absent_binding_removed_on_runtime_error(self):
        name = self.name()
        p = self.file('PARTIAL = True\nraise RuntimeError("expected")\n')
        with self.assertRaises(RuntimeError):
            DRIVER.load(p, name)
        self.assertNotIn(name, sys.modules)

    def test_explicit_none_binding_is_restored(self):
        name = self.name()
        sys.modules[name] = None
        p = self.file('raise RuntimeError("expected")\n')
        with self.assertRaises(RuntimeError):
            DRIVER.load(p, name)
        self.assertIn(name, sys.modules)
        self.assertIsNone(sys.modules[name])

    def test_cancellation_restores_binding_and_exception_identity(self):
        for error in (KeyboardInterrupt('cancel'), SystemExit(17), BaseException('base')):
            with self.subTest(error=type(error).__name__):
                name = self.name(type(error).__name__)
                helper_name = self.name('helper_' + type(error).__name__)
                previous, helper = ModuleType(name), ModuleType(helper_name)
                helper.error = error
                sys.modules[name], sys.modules[helper_name] = previous, helper
                p = self.file(f'from {helper_name} import error\nraise error\n')
                with self.assertRaises(type(error)) as raised:
                    DRIVER.load(p, name)
                self.assertIs(raised.exception, error)
                self.assertIs(sys.modules[name], previous)

    def test_absent_binding_removed_on_cancellation(self):
        name = self.name()
        p = self.file('raise KeyboardInterrupt("cancel")\n')
        with self.assertRaises(KeyboardInterrupt):
            DRIVER.load(p, name)
        self.assertNotIn(name, sys.modules)

    def test_syntax_failure_preserves_existing_binding(self):
        name = self.name()
        previous = ModuleType(name)
        sys.modules[name] = previous
        with self.assertRaises(SyntaxError):
            DRIVER.load(self.file('def missing(:\n'), name)
        self.assertIs(sys.modules[name], previous)

    def test_missing_file_preserves_existing_binding(self):
        name = self.name()
        previous = ModuleType(name)
        sys.modules[name] = previous
        with self.assertRaises(FileNotFoundError):
            DRIVER.load(self.root / 'absent.py', name)
        self.assertIs(sys.modules[name], previous)

    def test_success_preserves_metadata_and_registers_self_import(self):
        p = self.file('import sys\nSELF = sys.modules[__name__]\ndef f(): return 7\n')
        name = self.name()
        module = DRIVER.load(p, name)
        self.assertIs(module, module.SELF)
        self.assertIs(sys.modules[name], module)
        self.assertEqual(module.__name__, name)
        self.assertEqual(Path(module.__file__), p)
        self.assertEqual(module.__spec__.origin, str(p))
        self.assertEqual(module.f.__code__.co_filename, str(p))
        self.assertIsNotNone(module.__loader__)

    def test_dataclass_registration_is_available_during_execution(self):
        p = self.file('from __future__ import annotations\nfrom dataclasses import dataclass\n'
                      '@dataclass\nclass Value:\n    amount: int = 7\n')
        module = DRIVER.load(p, self.name())
        self.assertEqual(module.Value().amount, 7)

    def test_package_relative_import_keeps_metadata(self):
        package = self.name('package')
        self.names.append(package + '.child')
        p = self.file('from .child import VALUE\n', 'package/__init__.py')
        self.file('VALUE = 19\n', 'package/child.py')
        module = DRIVER.load(p, package)
        self.assertEqual(module.VALUE, 19)
        self.assertEqual(module.__package__, package)
        self.assertEqual(list(module.__path__), [str(p.parent)])

    def test_coding_cookie_is_honored(self):
        p = self.file(b'# coding: latin-1\nVALUE = "caf\xe9"\n')
        self.assertEqual(DRIVER.load(p, self.name()).VALUE, 'caf\u00e9')

    def test_driver_future_flags_are_not_inherited(self):
        p = self.file('def f(value: UnknownAnnotation): pass\n')
        with self.assertRaises(NameError):
            DRIVER.load(p, self.name())

    def test_explicit_future_annotations_are_preserved(self):
        p = self.file('from __future__ import annotations\ndef f(value: UnknownAnnotation): pass\n')
        module = DRIVER.load(p, self.name())
        self.assertEqual(module.f.__annotations__, {'value': 'UnknownAnnotation'})

    def test_snapshot_is_not_reread_after_module_construction(self):
        p = self.file('VALUE = "FIRST"\n')
        original = importlib.util.module_from_spec
        def mutate(spec):
            module = original(spec)
            p.write_text('VALUE = "AFTER"\n')
            return module
        with patch.object(importlib.util, 'module_from_spec', mutate):
            module = DRIVER.load(p, self.name())
        self.assertEqual(module.VALUE, 'FIRST')
        self.assertEqual(p.read_text(), 'VALUE = "AFTER"\n')

    def test_repeated_calls_load_fresh_source_once_each(self):
        helper_name = self.name('counter')
        helper = ModuleType(helper_name)
        helper.calls = 0
        sys.modules[helper_name] = helper
        p = self.file(f'import {helper_name} as helper\nhelper.calls += 1\nVALUE = 10\n')
        name = self.name()
        first = DRIVER.load(p, name)
        p.write_text(f'import {helper_name} as helper\nhelper.calls += 1\nVALUE = 200\n')
        second = DRIVER.load(p, name)
        self.assertEqual((first.VALUE, second.VALUE, helper.calls), (10, 200, 2))
        self.assertIsNot(first, second)

    def test_failure_leaves_unrelated_modules_untouched(self):
        unrelated = self.name('unrelated')
        previous = ModuleType(unrelated)
        sys.modules[unrelated] = previous
        with self.assertRaises(RuntimeError):
            DRIVER.load(self.file('raise RuntimeError("expected")\n'), self.name())
        self.assertIs(sys.modules[unrelated], previous)

    def test_failed_retry_can_load_corrected_source(self):
        name = self.name()
        p = self.file('raise RuntimeError("expected")\n')
        with self.assertRaises(RuntimeError):
            DRIVER.load(p, name)
        p.write_text('VALUE = 123\n')
        module = DRIVER.load(p, name)
        self.assertEqual(module.VALUE, 123)

    def test_actual_repaired_replay_ignores_original_timestamp_bytecode(self):
        original = (DEPENDENCIES / 'physical_replay_original.py').read_bytes()
        repaired = (DEPENDENCIES / 'physical_replay.py').read_bytes()
        self.assertEqual(identity(DEPENDENCIES / 'physical_replay.py')['git_blob'],
                         'e299275048d241602541e3329631f169e4de7634')
        p, cache, saved_cache = self.stale(original, repaired)
        module = DRIVER.load(p, self.name('actual_replay'))
        report = deadline_witness(module, late=True)
        self.assertEqual(p.read_bytes(), repaired)
        self.assertFalse(report['complete'])
        self.assertEqual(report['cases'][0]['reason'], 'budget:time')
        self.assertNotIn('final_cash', report['cases'][0])
        self.assertEqual(report['cases'][0]['market_rows'][0]['cash_delta'], 5)
        self.assertEqual(cache.read_bytes(), saved_cache)

    def test_actual_repaired_replay_on_time_case_is_unchanged(self):
        module = DRIVER.load(DEPENDENCIES / 'physical_replay.py', self.name('ontime_replay'))
        report = deadline_witness(module, late=False)
        self.assertTrue(report['complete'])
        self.assertEqual(report['cases'][0]['final_cash'], 15)
        self.assertEqual(report['decisions_executed'], 1)


def deadline_witness(replay, *, late):
    # The exact existing replay executes here; only external clock/physics are
    # small explicit fixtures. This reproduces a LOAD-boundary regression.
    now = [0.0]
    class Controller:
        def __init__(self):
            self.cur = 'first'
            self.R = {'first': [{}]}
            self.calls = 0
        def _switch_ok(self, route, step):
            return True
        def act(self, view):
            self.calls += 1
            return {'farmer': ['PASS'], 'market': [['SELL', 'WHEAT', 1]]}
    class Engine:
        def _process_market(self, state, env):
            state[0].observation.farms[0]['money'] += 5
    controller = Controller()
    observation = {'step': 0, 'player': 0, 'farms': [{'money': 10}]}
    before = deepcopy(controller.__dict__)
    def simulate(engine, obs, cfg, plan, **kwargs):
        action = plan(obs)
        view = SimpleNamespace(step=0, farms=[{'money': 10}], private={}, market={})
        engine._process_market([SimpleNamespace(observation=view, action=action)], None)
        now[0] = 2.0 if late else 0.5
        return {'cash_gain': 5, 'farm': {'money': 15}, 'actions': {0: action}}
    with patch.object(replay, 'monotonic', lambda: now[0]):
        report = replay.replay_routes(controller, ['first'], observation, {'episodeSteps': 2},
                    Engine(), simulate, scenarios={'known': {}}, end_step=0,
                    limits=replay.ReplayLimits(seconds=1, decisions=1))
    assert controller.__dict__ == before
    assert observation == {'step': 0, 'player': 0, 'farms': [{'money': 10}]}
    return report


def main():
    global DRIVER, DEPENDENCIES
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--driver', type=Path, default=Path(__file__).with_name('model_panel.py'))
    parser.add_argument('--deadline-inputs', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    DRIVER = load_driver(args.driver.resolve())
    DEPENDENCIES = args.deadline_inputs.resolve()
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(SourceLoadingTests))
    print(stream.getvalue(), end='')
    report = {'tests_run': result.testsRun, 'failures': len(result.failures),
              'errors': len(result.errors), 'successful': result.wasSuccessful(),
              'source': identity(args.driver), 'test_source': identity(Path(__file__)),
              'replay_source': identity(DEPENDENCIES / 'physical_replay.py'),
              'original_replay_source': identity(DEPENDENCIES / 'physical_replay_original.py'),
              'failure_test_ids': [str(test) for test, _ in result.failures],
              'error_test_ids': [str(test) for test, _ in result.errors],
              'python': sys.version, 'new_games': 0, 'seeds_consumed': [],
              'scope': 'local loader fixtures and real replay with controlled clock/physics'}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2)+'\n')
    return 0 if result.wasSuccessful() else 1

if __name__ == '__main__':
    raise SystemExit(main())
