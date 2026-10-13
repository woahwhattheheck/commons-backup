# SPDX-License-Identifier: Apache-2.0
"""Independent deepcopy/graph and native source-composition contracts."""
from __future__ import annotations

import argparse
import copy
from collections import OrderedDict, defaultdict
import hashlib
import importlib.util
import json
import os
import re
import random
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
PACKAGE = None
UNITFLOW = None
CLONE_PATH = HERE / 'projection_clone.py'
clone = None


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def signature(value):
    """Record values, insertion order, types and alias/cycle topology."""
    seen = {}
    def visit(node):
        if type(node) in (dict, list, tuple):
            ident = id(node)
            if ident in seen:
                return ('ref', seen[ident])
            label = len(seen)
            seen[ident] = label
            items = ([(visit(k), visit(v)) for k, v in node.items()]
                     if type(node) is dict else [visit(v) for v in node])
            return (type(node).__name__, label, items)
        return (type(node).__name__, repr(node))
    return visit(value)


class GraphContracts(unittest.TestCase):
    def equivalent(self, value):
        before = signature(value)
        try:
            candidate = clone(value)
        except Exception as exc:
            self.fail(f'clone rejected deepcopy-supported graph: {type(exc).__name__}')
        self.assertEqual(signature(candidate), signature(copy.deepcopy(value)))
        self.assertEqual(signature(value), before)
        return candidate

    def test_atoms(self):
        for value in (None, True, False, -5, 0, 2**200, 1.25, float('nan'),
                      float('inf'), 3+7j, 'field', b'field', Ellipsis, range(4)):
            self.assertIs(clone(value), copy.deepcopy(value))

    def test_alias_graph_and_isolation(self):
        shared = {'inventory': [1, 2, 3]}
        value = {'first': shared, 'second': [shared, shared['inventory']]}
        result = self.equivalent(value)
        self.assertIs(result['first'], result['second'][0])
        self.assertIs(result['first']['inventory'], result['second'][1])
        self.assertIsNot(result['first'], shared)
        result['first']['inventory'].append(19)
        self.assertEqual(shared['inventory'], [1, 2, 3])

    def test_self_and_mutual_cycles(self):
        a = []; a.append(a)
        b = {}; b['self'] = b
        c = [b]; b['other'] = c
        for graph in (a, b, c):
            with self.subTest(kind=type(graph).__name__):
                self.equivalent(graph)

    def test_tuple_cycle_fallback(self):
        node = []; pair = (node,); node.append(pair)
        result = self.equivalent(pair)
        self.assertIs(result[0][0], result)

    def test_seeded_graphs(self):
        rng = random.Random(923817)
        for trial in range(500):
            nodes = [[], {}]
            for i in range(24):
                value = rng.choice(nodes) if rng.random() < .65 else rng.randrange(100)
                node = [value, value] if rng.random() < .5 else {'v': value, i: value}
                nodes.append(node)
            if trial % 3 == 0:
                nodes[0].append(nodes[-1])
            with self.subTest(trial=trial):
                self.equivalent(nodes[-1])

    def test_separate_top_level_memos(self):
        shared = {'x': []}
        a = clone(shared); b = clone(shared)
        self.assertIsNot(a, b)
        self.assertIsNot(a['x'], b['x'])

    def test_supplied_memo_alias(self):
        shared = []; memo = {}
        a = clone(shared, memo); b = clone(shared, memo)
        self.assertIs(a, b)
        self.assertIs(memo[id(shared)], a)

    def test_prefilled_memo_including_atoms_and_none(self):
        for source in ([], {}, 23, 'field', None):
            with self.subTest(type=type(source).__name__):
                self.assertIsNone(clone(source, {id(source): None}))
                replacement = object()
                self.assertIs(clone(source, {id(source): replacement}), replacement)

    def test_keeps_originals_alive(self):
        source = {'a': [[], {}]}; actual = {}; expected = {}
        clone(source, actual); copy.deepcopy(source, expected)
        self.assertIn(id(actual), actual)
        self.assertEqual([id(x) for x in actual[id(actual)]],
                         [id(x) for x in expected[id(expected)]])

    def test_builtin_subclasses_retain_hooks(self):
        class List(list):
            def __deepcopy__(self, memo):
                return ('list-hook', len(self))
        class Dict(dict):
            def __deepcopy__(self, memo):
                return ('dict-hook', len(self))
        for value in (List([1]), Dict(a=1)):
            self.assertEqual(clone(value), copy.deepcopy(value))

    def test_other_containers_and_foreign_alias(self):
        shared = []
        value = {'a': shared, 'b': defaultdict(list, data=shared),
                 'c': OrderedDict([('x', shared)]), 'd': {1, 2},
                 'e': bytearray(b'field')}
        result = clone(value); reference = copy.deepcopy(value)
        self.assertEqual(result, reference)
        self.assertIs(type(result['b']), defaultdict)
        self.assertIs(type(result['c']), OrderedDict)
        self.assertIs(result['a'], result['b']['data'])
        self.assertIs(result['a'], result['c']['x'])
        self.assertIsNot(result['e'], value['e'])

    def test_custom_key_value_copy_order(self):
        events = []
        class Key:
            def __deepcopy__(self, memo):
                events.append('key'); return self
        class Value:
            def __deepcopy__(self, memo):
                events.append('value'); return self
        value = {Key(): Value()}
        copy.deepcopy(value); expected = list(events); events.clear()
        clone(value)
        self.assertEqual(events, expected)
        self.assertEqual(events, ['value', 'key'])

    def test_hook_can_bind_later_atom_in_memo(self):
        atom = 912341
        class Hook:
            def __deepcopy__(self, memo):
                memo[id(atom)] = 'replacement'; return None
        self.assertEqual(clone([Hook(), atom]), [None, 'replacement'])

    def test_custom_self_and_none_results(self):
        class Self:
            def __deepcopy__(self, memo):
                return self
        class Null:
            def __deepcopy__(self, memo):
                return None
        own = Self(); null = Null()
        value = [own, own, null, null]
        self.assertEqual(clone(value), copy.deepcopy(value))

    def test_custom_exceptions_propagate(self):
        class Foreign:
            def __deepcopy__(self, memo):
                raise ValueError('deliberate custom failure')
        with self.assertRaisesRegex(ValueError, 'deliberate custom failure'):
            clone({'a': Foreign()})


class SourceContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if PACKAGE is None or UNITFLOW is None:
            raise RuntimeError('--package and --unitflow are required; no skipped gates')
        cls.compose = load(HERE / 'compose.py', 'livepath_composer')
        data = UNITFLOW.read_bytes()
        if cls.compose.blob(data) != 'e1127c4aad842278a9e617903b0718d21c00f348':
            raise RuntimeError('UNITFLOW dependency custody mismatch')
        cls.unit = load(UNITFLOW, 'livepath_unitflow')
        cls.frozen = (PACKAGE / 'frozen_selected.py').read_text()
        cls.capital = (PACKAGE / 'early_capital.py').read_text()
        cls.scheduler = (PACKAGE / 'scheduler.py').read_text()

    def test_helper_pin(self):
        self.assertEqual(hashlib.sha256((HERE / 'projection_clone.py').read_bytes()).hexdigest(),
                         self.compose.HELPER_SHA256)

    def test_no_unrelated_byte_changes(self):
        for name, source in (('represented_shed_event', self.frozen),
                             ('_project_post_unit_private', self.capital)):
            result = self.compose.compose_source(source, name)
            a, b, before = self.compose.span(source, name)
            c, d, after = self.compose.span(result, name)
            self.assertEqual(source[:a], result[:c])
            self.assertEqual(source[b:], result[d:])
            for old, new in reversed(self.compose.REPLACEMENTS[name]):
                after = after.replace(new, old, 1)
            self.assertEqual(before, after)

    def test_disjoint_peer_changes_preserved(self):
        suffix = '\n# unrelated peer source must survive\nLIVEPATH_PEER = 71\n'
        a, b = self.compose.compose_sources(self.frozen + suffix, self.capital + suffix)
        self.assertTrue(a.endswith(suffix)); self.assertTrue(b.endswith(suffix))

    def test_drift_repeat_and_duplicate_fail_closed(self):
        for name, source in (('represented_shed_event', self.frozen),
                             ('_project_post_unit_private', self.capital)):
            a, b, before = self.compose.span(source, name)
            changed = source[:a] + before.replace('def ', 'def ', 1) + '# peer\n' + source[b:]
            # A comment outside the function is legal; a body edit is not.
            body_drift = source[:a] + before.replace('\n', '\n    # drift\n', 1) + source[b:]
            for invalid in (body_drift, source + '\n' + before,
                            self.compose.compose_source(source, name)):
                with self.assertRaises((ValueError, SyntaxError)):
                    self.compose.compose_source(invalid, name)

    def test_unitflow_commutes_byte_exact(self):
        unit_s, unit_f = self.unit.compose_sources(self.scheduler, self.frozen)
        uf, uc = self.compose.compose_sources(unit_f, self.capital)
        cf, cc = self.compose.compose_sources(self.frozen, self.capital)
        combined_s, combined_f = self.unit.compose_sources(self.scheduler, cf)
        self.assertEqual(unit_s, combined_s)
        self.assertEqual(uf, combined_f)
        self.assertEqual(uc, cc)
        self.assertIn('apply_projected_units(f,p,action', uf)

    def test_native_dependency_missing_and_changed_controls(self):
        runner = load(HERE / 'run_native.py', 'livepath_runner_auth')
        self.assertEqual(len(runner.authenticate(PACKAGE)), 109)
        names = ('main.py', 'TITAN-CONFIG.json', 'checks/reference/engine/kaggriculture.py',
                 'checks/reference/engine/kaggriculture.json',
                 'checks/reference/engine/utils.py', 'checks/reference/evaluator/loader.py')
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runner.prepare(PACKAGE, root, 'base')
            (root / 'SOURCE.json').write_bytes((PACKAGE / 'SOURCE.json').read_bytes())
            for name in names:
                path = root / name; original = path.read_bytes()
                path.unlink()
                with self.assertRaises(FileNotFoundError):
                    runner.authenticate(root)
                path.write_bytes(original + b'\n')
                with self.assertRaises(ValueError):
                    runner.authenticate(root)
                path.write_bytes(original)
            (root / 'SOURCE.json').write_text('{}\n')
            with self.assertRaises(ValueError):
                runner.authenticate(root)

    def test_inherited_native_regressions_all_four_arms(self):
        runner = load(HERE / 'run_native.py', 'livepath_runner_regressions')
        cases = ('test_early_capital', 'test_funded_prefix', 'test_joint_market_slots',
                 'test_crop_release', 'test_feed_stock')
        with tempfile.TemporaryDirectory() as td:
            for arm in ('base', 'clone', 'unitflow', 'unitflow-clone'):
                root = Path(td) / arm
                runner.prepare(PACKAGE, root, arm, UNITFLOW)
                command = [sys.executable, *(['-O'] if sys.flags.optimize else []),
                           '-m', 'unittest', *cases]
                env = dict(os.environ, PYTHONPATH=os.pathsep.join((str(root), str(root / 'checks'))))
                result = subprocess.run(command, cwd=root, env=env, capture_output=True,
                                        text=True, timeout=40)
                self.assertEqual(result.returncode, 0, f'{arm}: {result.stderr}')
                self.assertRegex(result.stderr, r'Ran \d+ tests')
                count = int(re.search(r'Ran (\d+) tests', result.stderr).group(1))
                print(json.dumps({'inherited_arm': arm, 'tests': count, 'passed': True,
                                  'optimized': bool(sys.flags.optimize)}))

    def test_cli_success_no_overwrite_and_helper_fault(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); output = root / 'output'
            args = [sys.executable, *(['-O'] if sys.flags.optimize else []),
                    str(HERE / 'compose.py'), '--package', str(PACKAGE),
                    '--output', str(output)]
            run = subprocess.run(args, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual((output / 'projection_clone.py').read_bytes(),
                             (HERE / 'projection_clone.py').read_bytes())
            again = subprocess.run(args, capture_output=True, text=True)
            self.assertNotEqual(again.returncode, 0)
            # A tampered dependency must fail before creating output.
            (root / 'compose.py').write_bytes((HERE / 'compose.py').read_bytes())
            (root / 'projection_clone.py').write_text('# wrong helper\n')
            args[1 + bool(sys.flags.optimize)] = str(root / 'compose.py')
            args[-1] = str(root / 'bad-output')
            bad = subprocess.run(args, capture_output=True, text=True)
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn('helper pin', bad.stderr)
            self.assertFalse((root / 'bad-output').exists())


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--unitflow', type=Path, required=True)
    parser.add_argument('--clone-file', type=Path, default=CLONE_PATH)
    parser.add_argument('--case')
    args = parser.parse_args()
    PACKAGE, UNITFLOW = args.package.resolve(), args.unitflow.resolve()
    clone = load(args.clone_file, 'livepath_clone_under_test').clone_projection
    suite = (unittest.defaultTestLoader.loadTestsFromName(args.case, sys.modules[__name__])
             if args.case else unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({'tests': result.testsRun, 'failures': len(result.failures),
                      'errors': len(result.errors), 'skips': len(result.skipped)}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
