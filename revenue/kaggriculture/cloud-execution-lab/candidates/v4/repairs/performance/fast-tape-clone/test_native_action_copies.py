# SPDX-License-Identifier: Apache-2.0
"""Native-corpus and source-boundary acceptance; all fixtures are mandatory."""
import ast
import copy
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import port_native_action_copies as port

ROOT = Path(os.environ['TAPEPORT_ROOT']).resolve()
HELPER = Path(os.environ.get('TAPEPORT_HELPER', str(Path(__file__).with_name('r04_fast_tape_clone.py'))))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def graph(value):
    """Identity-independent graph signature, including order and repeated lists."""
    seen = {}
    def visit(item):
        if type(item) not in (dict, list):
            return type(item).__name__, repr(item)
        key = id(item)
        if key in seen:
            return 'ref', seen[key]
        index = len(seen)
        seen[key] = index
        if type(item) is list:
            return 'list', index, tuple(map(visit, item))
        return 'dict', index, tuple((visit(k), visit(v)) for k, v in item.items())
    return visit(value)


class NativeCopies(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = {p: (ROOT/p).read_bytes() for p in port.PINS}
        cls.helper_bytes = HELPER.read_bytes()
        if port.blob(cls.helper_bytes) != port.HELPER_BLOB:
            raise RuntimeError('helper fixture drift')
        cls.h = load('_tapeport_helper_test', HELPER)
        cls.original_clone = cls.h.apply_fast_tape_clone
        # Behavioral faults do not alter fixture pins or suppress source checks.
        mutant = os.environ.get('TAPEPORT_MUTANT')
        faults = {
            'identity': lambda a: a,
            'shallow': lambda a: dict(a),
            'hands_alias': lambda a: dict(copy.deepcopy(a), hands=a['hands']),
            'market_reverse': lambda a: dict(copy.deepcopy(a), market=list(reversed(copy.deepcopy(a['market'])))),
            'drop_tail': lambda a: dict(copy.deepcopy(a), hands=copy.deepcopy(a['hands'][:-1])),
            'graph_flatten': lambda a: {k: copy.deepcopy(v) for k, v in a.items()},
        }
        if mutant:
            cls.h.apply_fast_tape_clone = faults[mutant]
        cls.vendor = load('_tapeport_native_routes', ROOT/'reference/next-panel/vendor/arlene.py')
        cls.actions = [a for route in cls.vendor.routes().values() for a in route]
        cls.on = port.compose(cls.sources, cls.helper_bytes, enabled=True)

    def assertClone(self, action):
        before = graph(action)
        out = self.h.apply_fast_tape_clone(action)
        self.assertEqual(graph(out), graph(copy.deepcopy(action)))
        self.assertEqual(graph(action), before)
        self.assertIsNot(out, action)
        if type(action) is dict:
            for key in ('farmer', 'hands', 'market'):
                if type(action.get(key)) is list:
                    self.assertIsNot(out[key], action[key])
        return out

    def test_all_native_routes_and_detachment(self):
        self.assertEqual(len(self.actions), 2880)
        self.assertTrue(all(self.h.is_fast_tape_action(a) for a in self.actions))
        for a in self.actions:
            before = graph(a)
            out = self.assertClone(a)
            out['farmer'].append('MUTATED')
            for group in ('hands', 'market'):
                for row in out[group]:
                    row.append('MUTATED')
            self.assertEqual(graph(a), before)

    def test_alias_graph_and_cycle_fallback(self):
        row = ['PASS']
        cases = [dict(farmer=row, hands=[row, row], market=[row])]
        cyc = []; cyc.append(cyc)
        cases.append(dict(farmer=cyc, hands=[], market=[]))
        for a in cases:
            self.assertFalse(self.h.is_fast_tape_action(a))
            self.assertClone(a)

    def test_future_nested_schema(self):
        a = dict(farmer=['PASS'], hands=[['PASS']], market=[['PASS']])
        a['future'] = {'nested': [a['farmer']]}
        self.assertFalse(self.h.is_fast_tape_action(a))
        out = self.assertClone(a)
        self.assertIs(out['future']['nested'][0], out['farmer'])

    def test_dictionary_order_and_empty_rows(self):
        for a in [dict(market=[[], ['SELL', 'MILK', 2]], farmer=[], hands=[[], ['PASS']]),
                  dict(farmer=['PASS'], hands=[[], ['PASS']], market=[[], ['PASS']])]:
            self.assertClone(a)

    def test_duplicate_calls_do_not_share_output(self):
        a = dict(farmer=['PASS'], hands=[['PASS']], market=[['SELL', 'MILK', 1]])
        first, second = self.assertClone(a), self.assertClone(a)
        first['hands'][0].append('MUTATED')
        first['market'][0][2] = 99
        self.assertEqual(graph(second), graph(a))

    def test_subclass_and_custom_deepcopy_fallback(self):
        class Action(dict):
            pass
        class Marker:
            def __deepcopy__(self, memo):
                return 'CUSTOM-COPY'
        a = Action(farmer=['PASS'], hands=[], market=[])
        out = self.h.apply_fast_tape_clone(a)
        self.assertIs(type(out), Action)
        self.assertIsNot(out, a)
        a = dict(farmer=[Marker()], hands=[], market=[])
        self.assertEqual(self.h.apply_fast_tape_clone(a)['farmer'], ['CUSTOM-COPY'])

    def test_off_bytes_and_mapping_are_unchanged(self):
        off = port.compose(self.sources, self.helper_bytes)
        self.assertEqual(off, self.sources)
        self.assertIsNot(off, self.sources)
        self.assertNotIn('r04_fast_tape_clone.py', off)

    def test_exact_copy_site_counts(self):
        counts = {}
        for name in port.PINS:
            tree = ast.parse(self.on[name])
            calls = [(scope, arg) for scope, arg, n in port._calls(tree)
                     if ast.unparse(n.func) == port.ALIAS]
            self.assertEqual(port.Counter(calls), port.Counter(port.TARGETS[name]))
            counts[name] = len(calls)
        self.assertEqual(counts, {'integrated_selected.py': 9,
                                 'frozen_selected.py': 2, 'spatial_tempo.py': 16})

    def test_non_action_copy_calls_preserved(self):
        for name, data in self.sources.items():
            def remaining(code):
                return [(scope, arg) for scope, arg, node in port._calls(ast.parse(code))
                        if 'deepcopy' in ast.unparse(node.func)
                        and (scope, arg) not in port.TARGETS[name]]
            self.assertEqual(remaining(data), remaining(self.on[name]))

    def test_peer_edits_survive_explicit_reviewed_pin(self):
        sources = dict(self.sources)
        sources['spatial_tempo.py'] += b'\n# reviewed disjoint peer marker\n'
        pins = {name: port.blob(data) for name, data in sources.items()}
        out = port.compose(sources, self.helper_bytes, enabled=True, pins=pins)
        self.assertTrue(out['spatial_tempo.py'].endswith(b'# reviewed disjoint peer marker\n'))
        self.assertIn(b'copy.deepcopy(base[', out['frozen_selected.py'])

    def test_input_and_helper_drift_reject(self):
        sources = dict(self.sources)
        sources['integrated_selected.py'] += b'\n'
        with self.assertRaises(ValueError):
            port.compose(sources, self.helper_bytes, enabled=True)
        with self.assertRaises(ValueError):
            port.compose(self.sources, self.helper_bytes+b'\n', enabled=True)

    def test_scope_or_cardinality_drift_reject(self):
        for old, new in [(b'deepcopy(route[step])', b'deepcopy(route[step+1])'),
                         (b'def _projection(', b'def _other_projection(')]:
            sources = dict(self.sources)
            sources['integrated_selected.py'] = sources['integrated_selected.py'].replace(old, new)
            pins = {name: port.blob(data) for name, data in sources.items()}
            with self.assertRaises(ValueError):
                port.compose(sources, self.helper_bytes, enabled=True, pins=pins)

    def test_double_application_and_missing_file_reject(self):
        sources = {name: self.on[name] for name in port.PINS}
        pins = {name: port.blob(data) for name, data in sources.items()}
        with self.assertRaises(ValueError):
            port.compose(sources, self.helper_bytes, enabled=True, pins=pins)
        with self.assertRaises(ValueError):
            port.compose({}, self.helper_bytes)

    def test_nonliteral_enable_reject(self):
        for value in (1, 'yes', None):
            with self.assertRaises(ValueError):
                port.compose(self.sources, self.helper_bytes, enabled=value)

    def test_stage_never_overwrites_input_or_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/'source'; source.mkdir()
            for name, data in self.sources.items():
                (source/name).write_bytes(data)
            (source/'untouched.bin').write_bytes(b'unchanged')
            with self.assertRaises(ValueError):
                port.stage(source, source/'nested', HELPER, enabled=True)
            out = Path(tmp)/'on'
            hashes = port.stage(source, out, HELPER, enabled=True)
            self.assertEqual(len(hashes), 4)
            self.assertEqual((out/'untouched.bin').read_bytes(), b'unchanged')
            with self.assertRaises(ValueError):
                port.stage(source, out, HELPER, enabled=True)
            self.assertEqual({p:(source/p).read_bytes() for p in port.PINS}, self.sources)


if __name__ == '__main__':
    unittest.main(verbosity=2)
