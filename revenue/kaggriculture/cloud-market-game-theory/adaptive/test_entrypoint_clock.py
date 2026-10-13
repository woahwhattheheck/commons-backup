# SPDX-License-Identifier: Apache-2.0
"""Loader-boundary regressions for the three existing adaptive entrypoints.

The sibling runtime is an explicit recording fixture, not a game or economic
model. Its clock is compiled unchanged from the real selected-action seller.
No external packages, games, credentials, workflow, or source export are needed.
"""
from __future__ import annotations

import argparse
import ast
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ENTRYPOINT_DIR = HERE
CLOCK_SOURCE = HERE.parent.parent / 'cloud-execution-lab' / 'selected_action_sell.py'
MODES = {'main.py': 'adaptive', 'fixed_main.py': 'fixed', 'static_main.py': 'static'}


def clock_text(path):
    source = path.read_text(encoding='utf-8')
    node = next(n for n in ast.parse(source).body
                if isinstance(n, ast.FunctionDef) and n.name == 'absolute_step')
    return ast.get_source_segment(source, node)


class EntrypointClockTests(unittest.TestCase):
    def fixture(self, filename, *, raw=False, compile_name=None, behavior='normal'):
        temp = tempfile.TemporaryDirectory(prefix='titan-entrypoint-clock-')
        self.addCleanup(temp.cleanup)
        directory = Path(temp.name)
        original_path = list(sys.path)
        self.addCleanup(lambda: sys.path.__setitem__(slice(None), original_path))
        runtime = clock_text(CLOCK_SOURCE) + '\n' + '''
from types import SimpleNamespace
from copy import deepcopy
sale = SimpleNamespace(absolute_step=absolute_step)
CONSTRUCTIONS = []
CALLS = []
class BoundaryError(RuntimeError): pass
class Agent:
    def __init__(self, mode):
        self.mode = mode
        self.calls = 0
        CONSTRUCTIONS.append(self)
        if BEHAVIOR == 'constructor_error': raise BoundaryError('constructor-body')
    def act(self, obs, cfg):
        self.calls += 1
        CALLS.append((self, deepcopy(obs), deepcopy(cfg)))
        if BEHAVIOR == 'action_error': raise BoundaryError('action-body')
        self.action = {'farmer': ['PASS'], 'hands': [], 'market': [],
                       'mode': self.mode, 'calls': self.calls, 'step': obs.get('step')}
        return self.action
'''
        (directory / 'runtime.py').write_text('BEHAVIOR = ' + repr(behavior) + '\n' + runtime,
                                             encoding='utf-8')
        entry = directory / filename
        source = (ENTRYPOINT_DIR / filename).read_text(encoding='utf-8')
        entry.write_text(source, encoding='utf-8')
        namespace = {} if raw else {'__file__': str(entry)}
        exec(compile(source, compile_name or str(entry), 'exec'), namespace)
        return namespace, entry

    def test_day_hour_inputs_retain_actor_and_deliver_clock(self):
        for filename in MODES:
            with self.subTest(entrypoint=filename):
                ns, _ = self.fixture(filename)
                a = ns['agent']({'day': 0, 'hour': 0}, {})
                actor = ns['_AGENT']
                b = ns['agent']({'day': 0, 'hour': 1}, {})
                self.assertIs(ns['_AGENT'], actor)
                self.assertEqual((a['step'], b['step'], b['calls']), (0, 1, 2))

    def test_explicit_step_takes_precedence(self):
        for filename in MODES:
            with self.subTest(entrypoint=filename):
                ns, _ = self.fixture(filename)
                ns['agent']({'step': 4, 'day': 0, 'hour': 0}, {})
                actor = ns['_AGENT']
                result = ns['agent']({'step': 5, 'day': 0, 'hour': 0}, {})
                self.assertIs(ns['_AGENT'], actor)
                self.assertEqual((result['step'], result['calls']), (5, 2))

    def test_none_step_uses_public_clock(self):
        for filename in MODES:
            with self.subTest(entrypoint=filename):
                ns, _ = self.fixture(filename)
                ns['agent']({'step': None, 'day': 0, 'hour': 3}, {})
                actor = ns['_AGENT']
                result = ns['agent']({'step': None, 'day': 0, 'hour': 4}, {})
                self.assertIs(ns['_AGENT'], actor)
                self.assertEqual((result['step'], result['calls']), (4, 2))

    def test_configured_day_length(self):
        for filename in MODES:
            with self.subTest(entrypoint=filename):
                ns, _ = self.fixture(filename)
                result = ns['agent']({'day': 2, 'hour': 3}, {'turnsPerDay': 9})
                self.assertEqual(result['step'], 21)

    def test_new_day_is_not_new_episode(self):
        for filename in MODES:
            with self.subTest(entrypoint=filename):
                ns, _ = self.fixture(filename)
                ns['agent']({'day': 0, 'hour': 23}, {})
                actor = ns['_AGENT']
                result = ns['agent']({'day': 1, 'hour': 0}, {})
                self.assertIs(ns['_AGENT'], actor)
                self.assertEqual((result['step'], result['calls']), (24, 2))

    def test_true_zero_resets_actor_not_runtime(self):
        for filename in MODES:
            with self.subTest(entrypoint=filename):
                ns, _ = self.fixture(filename)
                ns['agent']({'step': 12}, {})
                actor = ns['_AGENT']
                runtime = ns['_RUNTIME']
                result = ns['agent']({'day': 0, 'hour': 0}, {})
                self.assertIsNot(ns['_AGENT'], actor)
                self.assertIs(ns['_RUNTIME'], runtime)
                self.assertEqual((result['step'], result['calls']), (0, 1))
                self.assertEqual(len(runtime.CONSTRUCTIONS), 2)

    def test_raw_compile_without_private_path(self):
        for filename in MODES:
            with self.subTest(entrypoint=filename):
                ns, _ = self.fixture(filename, raw=True)
                result = ns['agent']({'day': 0, 'hour': 1}, {})
                self.assertEqual(result['step'], 1)
                self.assertNotIn('__file__', ns)

    def test_legacy_raw_path_remains_supported(self):
        for filename in MODES:
            with self.subTest(entrypoint=filename):
                ns, path = self.fixture(filename, raw=True, compile_name='<legacy-loader>')
                result = ns['agent']({'step': 3}, {'__raw_path__': str(path)})
                self.assertEqual(result['step'], 3)

    def test_module_path_precedes_private_override(self):
        for filename in MODES:
            with self.subTest(entrypoint=filename):
                ns, _ = self.fixture(filename)
                result = ns['agent']({'step': 3}, {'__raw_path__': '/not-used/main.py'})
                self.assertEqual(result['step'], 3)

    def test_input_clock_normalization_does_not_mutate_caller(self):
        for filename in MODES:
            with self.subTest(entrypoint=filename):
                ns, _ = self.fixture(filename)
                obs = {'day': 1, 'hour': 2, 'private': {'shed': {'WHEAT': 3}}}
                cfg = {'turnsPerDay': 9}
                before = deepcopy((obs, cfg))
                ns['agent'](obs, cfg)
                self.assertEqual((obs, cfg), before)
                self.assertNotIn('step', obs)
                self.assertEqual(ns['_RUNTIME'].CALLS[0][1]['step'], 11)

    def test_mode_and_action_identity_are_preserved(self):
        for filename, mode in MODES.items():
            with self.subTest(entrypoint=filename):
                ns, _ = self.fixture(filename)
                result = ns['agent']({'step': 7}, {})
                self.assertIs(result, ns['_AGENT'].action)
                self.assertEqual(result['mode'], mode)
                self.assertNotIn('__adaptive_evaluation__', result)

    def test_action_body_error_is_not_retried(self):
        for filename in MODES:
            with self.subTest(entrypoint=filename):
                ns, _ = self.fixture(filename, behavior='action_error')
                with self.assertRaisesRegex(RuntimeError, '^action-body$'):
                    ns['agent']({'step': 5}, {})
                self.assertEqual(ns['_AGENT'].calls, 1)

    def test_constructor_body_error_is_not_retried(self):
        for filename in MODES:
            with self.subTest(entrypoint=filename):
                ns, _ = self.fixture(filename, behavior='constructor_error')
                with self.assertRaisesRegex(RuntimeError, '^constructor-body$'):
                    ns['agent']({'step': 5}, {})
                self.assertEqual(len(ns['_RUNTIME'].CONSTRUCTIONS), 1)

    def test_distinct_raw_namespaces_do_not_share_actors(self):
        for filename in MODES:
            with self.subTest(entrypoint=filename):
                left, _ = self.fixture(filename, raw=True)
                right, _ = self.fixture(filename, raw=True)
                left['agent']({'step': 3}, {})
                right['agent']({'step': 3}, {})
                self.assertIsNot(left['_AGENT'], right['_AGENT'])
                left['agent']({'step': 4}, {})
                self.assertEqual((left['_AGENT'].calls, right['_AGENT'].calls), (2, 1))

    def test_explicit_step_needs_no_day_or_hour(self):
        for filename in MODES:
            with self.subTest(entrypoint=filename):
                ns, _ = self.fixture(filename, raw=True)
                self.assertEqual(ns['agent']({'step': 8}, {})['step'], 8)

    def test_missing_all_clock_fields_is_not_fabricated_zero(self):
        for filename in MODES:
            with self.subTest(entrypoint=filename):
                ns, _ = self.fixture(filename)
                with self.assertRaises(KeyError):
                    ns['agent']({}, {})
                self.assertIsNone(ns['_AGENT'])

    def test_invalid_clock_is_not_silently_repaired(self):
        for filename in MODES:
            with self.subTest(entrypoint=filename):
                ns, _ = self.fixture(filename)
                with self.assertRaises(ValueError):
                    ns['agent']({'step': 'not-an-integer'}, {})
                self.assertIsNone(ns['_AGENT'])

    def test_none_configuration_uses_existing_defaults(self):
        for filename in MODES:
            with self.subTest(entrypoint=filename):
                ns, _ = self.fixture(filename)
                self.assertEqual(ns['agent']({'day': 1, 'hour': 1}, None)['step'], 25)


def main():
    global ENTRYPOINT_DIR, CLOCK_SOURCE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--entrypoint-dir', type=Path, default=ENTRYPOINT_DIR)
    parser.add_argument('--clock-source', type=Path, default=CLOCK_SOURCE)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    ENTRYPOINT_DIR, CLOCK_SOURCE = args.entrypoint_dir.resolve(), args.clock_source.resolve()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(EntrypointClockTests)
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    text = stream.getvalue()
    print(text, end='')
    if args.report:
        paths = [ENTRYPOINT_DIR / n for n in MODES] + [CLOCK_SOURCE]
        report = {'scope': 'entrypoint fixtures; no games or economic-policy evidence',
                  'python': sys.version.split()[0], 'methods': result.testsRun,
                  'entrypoints_per_method': len(MODES), 'successful': result.wasSuccessful(),
                  'failures': len(result.failures), 'errors': len(result.errors),
                  'sources': {p.name: {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
                                      'git_blob': hashlib.sha1(b'blob ' + str(p.stat().st_size).encode()
                                                               + b'\0' + p.read_bytes()).hexdigest()}
                              for p in paths},
                  'failure_details': [(str(t), detail) for t, detail in result.failures + result.errors],
                  'log': text}
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
