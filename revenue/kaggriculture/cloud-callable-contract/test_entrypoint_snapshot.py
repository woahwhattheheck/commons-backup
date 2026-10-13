# SPDX-License-Identifier: Apache-2.0
"""Exact-source tests for the existing executor's entrypoint snapshot boundary.

Imports the complete executor and actual timing observer. Only the unrelated
`cards` import is isolated; no game, engine, policy panel or seed is consumed.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import platform
import py_compile
import sys
import tempfile
import traceback
import types
import unittest
from unittest.mock import patch

DEFAULT_EXECUTOR = Path(__file__).resolve().parents[1] / 'cloud-model-lab' / 'execute_arm.py'
EXECUTOR_PATH = DEFAULT_EXECUTOR
EXECUTOR = None


def load_executor(path):
    spec = importlib.util.spec_from_file_location('_snapshot_executor_test', path)
    module = importlib.util.module_from_spec(spec)
    # `load_callable` does not use this module; use real executor functions.
    with patch.dict(sys.modules, {'cards': types.ModuleType('cards')}):
        spec.loader.exec_module(module)
    return module


class EntrySnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / 'policy.py'
        old_path = sys.path[:]
        existing_modules = set(sys.modules)
        self.addCleanup(lambda: sys.path.__setitem__(slice(None), old_path))

        def cleanup_modules():
            for name in set(sys.modules) - existing_modules:
                if name.startswith(('arm_policy_py_', '_snapshot_dep_')):
                    sys.modules.pop(name, None)
        self.addCleanup(cleanup_modules)

    def write(self, source):
        data = source.encode('utf-8') if isinstance(source, str) else source
        self.path.write_bytes(data)
        return data

    def bind(self):
        return EXECUTOR.load_callable(self.path)

    def test_edit_after_binding_keeps_hashed_source(self):
        original = self.write('def agent(obs, cfg): return "original"\n')
        factory, identity = self.bind()
        self.write('def agent(obs, cfg): return "changed-after-binding"\n')
        self.assertEqual(identity['sha256'], hashlib.sha256(original).hexdigest())
        self.assertEqual(factory()({}, {}), 'original')

    def test_edit_between_matches_keeps_same_snapshot(self):
        self.write('def agent(obs, cfg): return "first"\n')
        factory, identity = self.bind()
        self.assertEqual(factory()({}, {}), 'first')
        self.write('def agent(obs, cfg): return "second-version"\n')
        self.assertEqual(factory()({}, {}), 'first')

    def test_timestamp_valid_stale_pyc_cannot_change_executed_source(self):
        first = self.write('def agent(obs, cfg): return "old"\n')
        stamp = 1_700_000_000
        os.utime(self.path, (stamp, stamp))
        cache = py_compile.compile(str(self.path), doraise=True,
            invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)
        cached_bytes = Path(cache).read_bytes()
        current = self.write('def agent(obs, cfg): return "new"\n')
        self.assertEqual(len(first), len(current))
        os.utime(self.path, (stamp, stamp))
        factory, identity = self.bind()
        self.assertEqual(identity['sha256'], hashlib.sha256(current).hexdigest())
        self.assertEqual(factory()({}, {}), 'new')
        self.assertEqual(Path(cache).read_bytes(), cached_bytes)

    def test_two_bindings_keep_two_distinct_sources(self):
        self.write('def agent(obs, cfg): return "A"\n')
        first, first_id = self.bind()
        self.write('def agent(obs, cfg): return "BBBB"\n')
        second, second_id = self.bind()
        self.assertNotEqual(first_id['sha256'], second_id['sha256'])
        self.assertEqual((first()({}, {}), second()({}, {})), ('A', 'BBBB'))

    def test_source_removed_after_binding_remains_executable(self):
        self.write('def agent(obs): return 73\n')
        factory, _ = self.bind()
        self.path.unlink()
        self.assertEqual(factory()({}, None), 73)

    def test_invalid_later_file_cannot_replace_bound_program(self):
        self.write('def agent(obs): return 89\n')
        factory, _ = self.bind()
        self.write('this is not Python !!!\n')
        self.assertEqual(factory()({}, {}), 89)

    def test_fresh_match_state_and_singleton_persistence(self):
        self.write('counter = 0\ndef agent(obs, cfg=None):\n global counter\n counter += 1\n return counter\n')
        factory, _ = self.bind()
        one, two = factory(), factory()
        self.assertEqual([one({}, {}), one({}, {}), two({}, {})], [1, 2, 1])

    def test_factory_preferred_and_called_once_per_actor(self):
        self.write('''calls = 0
class Actor:
 def __init__(self): self.n = 0
 def __call__(self, obs, cfg):
  self.n += 1
  return calls, self.n
def make_agent():
 global calls
 calls += 1
 return Actor()
def agent(obs, cfg): raise AssertionError("wrong entry")
''')
        factory, _ = self.bind()
        one, two = factory(), factory()
        self.assertEqual([one({}, {}), one({}, {}), two({}, {})], [(1, 1), (1, 2), (1, 1)])

    def test_one_argument_and_optional_configuration_dispatch(self):
        self.write('def agent(obs): return obs["value"]\n')
        factory, _ = self.bind()
        self.assertEqual(factory()({'value': 4}, {}), 4)
        self.write('def agent(obs, cfg=None): return cfg\n')
        factory, _ = self.bind()
        config = {'value': 7}
        self.assertIs(factory()({}, config), config)

    def test_internal_typeerror_propagates_without_retry(self):
        self.write('def agent(obs, cfg=None):\n obs.append(cfg)\n raise TypeError("body-error")\n')
        factory, _ = self.bind()
        action = factory()
        obs, config = [], {'retained': True}
        with self.assertRaisesRegex(TypeError, '^body-error$'):
            action(obs, config)
        self.assertEqual(obs, [config])

    def test_import_failure_stays_a_timed_factory_failure(self):
        self.write('raise RuntimeError("initialization-error")\n')
        factory, _ = self.bind()
        observed = EXECUTOR.TimedFactory(factory)
        with self.assertRaisesRegex(RuntimeError, '^initialization-error$'):
            observed()
        timing = observed.timings()
        self.assertTrue(timing['initialization_failed'])
        self.assertGreaterEqual(timing['initialization_s'], 0)
        self.assertEqual(timing['calls'], 0)
        self.assertIsNone(timing['first_action_s'])

    def test_syntax_error_remains_at_factory_boundary(self):
        self.write('def agent( invalid !!!\n')
        factory, identity = self.bind()
        self.assertEqual(identity['sha256'], hashlib.sha256(self.path.read_bytes()).hexdigest())
        with self.assertRaises(SyntaxError):
            factory()

    def test_python_encoding_cookie_and_raw_hash(self):
        raw = self.write(b'# coding: latin-1\r\ndef agent(obs): return "caf\xe9"\r\n')
        factory, identity = self.bind()
        self.assertEqual(identity['sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(factory()({}, {}), 'caf\u00e9')

    def test_utf8_bom_and_newlines_are_not_normalized_in_hash(self):
        raw = self.write(b'\xef\xbb\xbfdef agent(obs): return "ok"\r\n')
        factory, identity = self.bind()
        self.assertEqual(identity['sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(factory()({}, {}), 'ok')

    def test_module_metadata_registration_and_filename_are_preserved(self):
        self.write('''from dataclasses import dataclass
import sys
@dataclass
class State:
 value: int = 3
def agent(obs, cfg):
 return {"file": __file__, "origin": __spec__.origin,
         "loader": type(__loader__).__name__, "package": __package__,
         "name": __name__, "registered": sys.modules[__name__].State().value,
         "code_file": agent.__code__.co_filename}
''')
        factory, identity = self.bind()
        first, second = factory()({}, {}), factory()({}, {})
        for result in [first, second]:
            self.assertEqual(result['file'], identity['path'])
            self.assertEqual(result['origin'], identity['path'])
            self.assertEqual(result['code_file'], identity['path'])
            self.assertEqual(result['loader'], 'SourceFileLoader')
            self.assertEqual(result['package'], '')
            self.assertEqual(result['registered'], 3)
        self.assertNotEqual(first['name'], second['name'])

    def test_existing_extra_import_roots_remain_available(self):
        dep = '_snapshot_dep_' + self.root.name.replace('-', '_')
        (self.root / (dep + '.py')).write_text('VALUE = 17\n', encoding='utf-8')
        self.write(f'import {dep}\ndef agent(obs): return {dep}.VALUE\n')
        factory, _ = EXECUTOR.load_callable(self.path, [str(self.root)])
        self.assertEqual(factory()({}, {}), 17)
        self.assertEqual(sys.path.count(str(self.root)), 1)

    def test_missing_initial_file_remains_an_input_error(self):
        with self.assertRaises(FileNotFoundError):
            self.bind()

    def test_traceback_keeps_entrypoint_filename(self):
        self.write('def agent(obs):\n raise ValueError("trace-marker")\n')
        factory, identity = self.bind()
        try:
            factory()({}, {})
        except ValueError:
            frames = traceback.extract_tb(sys.exc_info()[2])
        else:
            self.fail('expected body failure')
        self.assertEqual(frames[-1].filename, identity['path'])
        self.assertEqual(frames[-1].lineno, 2)


def main():
    global EXECUTOR_PATH, EXECUTOR
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executor', type=Path, default=DEFAULT_EXECUTOR)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    EXECUTOR_PATH = args.executor.resolve()
    EXECUTOR = load_executor(EXECUTOR_PATH)
    log = io.StringIO()
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(EntrySnapshotTests))
    report = {'scope': 'executor_entrypoint_snapshot_not_games',
              'python': platform.python_version(),
              'executor_sha256': hashlib.sha256(EXECUTOR_PATH.read_bytes()).hexdigest(),
              'test_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'test_methods': result.testsRun, 'failures': len(result.failures),
              'errors': len(result.errors), 'skipped': len(result.skipped),
              'successful': result.wasSuccessful(), 'games': 0, 'game_seeds': [],
              'log': log.getvalue()}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(log.getvalue(), end='')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
