# SPDX-License-Identifier: Apache-2.0
"""Independent graph, mutation, source-composition and current-runtime checks.

TITAN_PACKAGE must point to the exact b567 archive unpacking. Missing or changed
fixtures are failures, never skips. No fixture is downloaded by this suite.
"""
from __future__ import annotations
from copy import deepcopy
from itertools import permutations
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

from selected_unit_snapshot import selected_unit_snapshot
from compose_selected_snapshot import compose, git_blob, RUNTIME_BLOB, OLD, NEW

PACKAGE = Path(os.environ.get('TITAN_PACKAGE', '/nonexistent/TITAN_PACKAGE'))
HERE = Path(__file__).resolve().parent
SOURCE_SHA256 = 'e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2'


def predecessor(obs, player, pair):
    post = deepcopy(obs)
    post['farms'][int(player)], post['private'] = pair
    return post


def fingerprint(*roots):
    """Canonical graph encoding: types, key order, values AND alias topology.

    Include the inputs beside the output to also detect an accidental reference
    into original state. Supports the dict/list/tuple graphs tested here.
    """
    seen = {}
    def visit(value):
        kind = type(value)
        if isinstance(value, (dict, list, tuple)):
            ident = id(value)
            if ident in seen:
                return ('ref', seen[ident])
            label = len(seen)
            seen[ident] = label
            header = ('node', label, kind.__module__, kind.__qualname__)
            if isinstance(value, dict):
                return header + (tuple((visit(k), visit(v)) for k,v in value.items()),)
            return header + (tuple(visit(v) for v in value),)
        return ('atom', kind.__module__, kind.__qualname__, repr(value))
    return tuple(visit(root) for root in roots)


def authenticate_package(root):
    source = (root / 'SOURCE.json').read_bytes()
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
        raise ValueError('whole-package source manifest differs')
    manifest = json.loads(source)
    for name, pin in manifest['runtime'].items():
        path = root / name
        if path.resolve().is_relative_to(root.resolve()) is False:
            raise ValueError('unsafe manifest path')
        data = path.read_bytes()
        if len(data) != pin['bytes'] or hashlib.sha256(data).hexdigest() != pin['sha256']:
            raise ValueError('package input mismatch: ' + name)
    data = (root / 'titan_runtime.py').read_bytes()
    if git_blob(data) != RUNTIME_BLOB:
        raise ValueError('runtime input mismatch')
    return manifest


def import_module(name, path, source=None):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    if source is None:
        spec.loader.exec_module(module)
    else:
        exec(compile(source, str(path), 'exec'), module.__dict__)
    return module


class Struct(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key) from None


class FarmList(list):
    pass


class SnapshotGraphTests(unittest.TestCase):
    def equal(self, obs, player, pair):
        before = fingerprint(obs, pair)
        old = predecessor(obs, player, pair)
        new = selected_unit_snapshot(obs, player, pair)
        self.assertEqual(fingerprint(new, obs, pair), fingerprint(old, obs, pair))
        self.assertEqual(fingerprint(obs, pair), before)
        self.assertIs(new['farms'][int(player)], pair[0])
        self.assertIs(new['private'], pair[1])
        return new

    @staticmethod
    def fixture():
        own = {'tiles': [[{'kind': 'COW', 'amount': [3]}]], 'money': 51}
        rival = {'tiles': [[{'kind': 'SHEEP', 'amount': [2]}]], 'money': 78}
        private = {'shed': {'WHEAT': 4}, 'inventories': [{}, {}]}
        return {'player': 0, 'step': 31, 'farms': [own, rival],
                'private': private, 'market': {'inventory': {'WHEAT': 9}}}

    def test_both_seats_and_pair_borrowing(self):
        for seat in (0, 1):
            self.equal(self.fixture(), seat, ({'post': [1]}, {'postprivate': [2]}))

    def test_retained_data_is_detached_and_input_unmodified(self):
        obs = self.fixture()
        pair = ({'post': [1]}, {'postprivate': [2]})
        out = self.equal(obs, 0, pair)
        out['farms'][1]['tiles'][0][0]['amount'].append(99)
        out['market']['inventory']['WHEAT'] = 999
        self.assertEqual(obs['farms'][1]['tiles'][0][0]['amount'], [2])
        self.assertEqual(obs['market']['inventory']['WHEAT'], 9)
        out['farms'][0]['post'].append(7)
        self.assertEqual(pair[0]['post'], [1, 7])  # intentional predecessor borrowing

    def test_aliases_into_discarded_subgraphs_are_not_replaced(self):
        obs = self.fixture()
        obs['own_alias'] = obs['farms'][0]
        obs['private_alias'] = obs['private']
        pair = ({'post': [1]}, {'postprivate': [2]})
        out = self.equal(obs, 0, pair)
        self.assertIsNot(out['own_alias'], pair[0])
        self.assertIsNot(out['private_alias'], pair[1])
        self.assertIsNot(out['own_alias'], obs['farms'][0])

    def test_same_own_and_rival_object(self):
        obs = self.fixture()
        obs['farms'][1] = obs['farms'][0]
        self.equal(obs, 0, ({}, {}))

    def test_private_and_farm_cross_aliases(self):
        obs = self.fixture()
        obs['private']['farm'] = obs['farms'][0]
        obs['farms'][1]['private'] = obs['private']
        obs['farms'][0]['private'] = obs['private']
        self.equal(obs, 0, ({}, {}))

    def test_root_self_cycle(self):
        obs = self.fixture()
        obs['root'] = obs
        obs['farms'][1]['root'] = obs
        self.equal(obs, 0, ({}, {}))

    def test_farms_cycles_and_retained_farms_alias(self):
        obs = self.fixture()
        obs['farm_list_alias'] = obs['farms']
        obs['farms'][1]['farms'] = obs['farms']
        obs['farms'].append(obs['farms'])
        self.equal(obs, 0, ({}, {}))

    def test_private_is_root_or_farms(self):
        for target in ('root', 'farms'):
            obs = self.fixture()
            obs['private'] = obs if target == 'root' else obs['farms']
            self.equal(obs, 0, ({}, {}))

    def test_pair_may_alias_input_or_itself(self):
        obs = self.fixture()
        for pair in [(obs['farms'][0], obs['private']), (obs, obs), (obs['farms'], obs['farms'])]:
            self.equal(obs, 0, pair)

    def test_missing_private_is_added(self):
        obs = self.fixture()
        del obs['private']
        self.equal(obs, 1, ({}, {'shed': {}}))

    def test_all_root_key_orders(self):
        for keys in permutations(('farms', 'private', 'alias', 'player')):
            obs = self.fixture()
            vals = {'farms': obs['farms'], 'private': obs['private'],
                    'alias': [obs['farms'], obs['private'], obs['farms'][0]], 'player': 0}
            self.equal({k: vals[k] for k in keys}, 0, ({}, {}))

    def test_native_descendant_struct_types(self):
        obs = self.fixture()
        obs['farms'][1] = Struct(obs['farms'][1])
        obs['market'] = Struct(obs['market'])
        out = self.equal(obs, 0, ({}, {}))
        self.assertIs(type(out['market']), Struct)

    def test_non_plain_roots_and_farm_lists_use_predecessor(self):
        for root_kind, farms_kind in [(Struct, list), (dict, FarmList), (Struct, FarmList)]:
            obs = root_kind(self.fixture())
            obs['farms'] = farms_kind(obs['farms'])
            self.equal(obs, 0, ({}, {}))

    def test_negative_and_string_indices(self):
        for index in (-1, -2, '0', '1'):
            self.equal(self.fixture(), index, ({}, {}))

    def test_invalid_inputs_retain_exception_classes(self):
        cases = [({}, 0, ({}, {})), ({'farms': []}, 0, ({}, {})),
                 (self.fixture(), 2, ({}, {})), (self.fixture(), -3, ({}, {})),
                 (self.fixture(), 0, ({} ,)), (self.fixture(), 0, None),
                 (self.fixture(), 'bad', ({}, {}))]
        for obs, player, pair in cases:
            errors = []
            for operation in (predecessor, selected_unit_snapshot):
                try:
                    operation(obs, player, pair)
                except Exception as exc:
                    errors.append(type(exc))
                else:
                    errors.append(None)
            self.assertEqual(errors[0], errors[1])
            self.assertIsNotNone(errors[0])

    def test_random_retained_alias_graphs_1000_cases(self):
        for seed in range(500):
            rng = random.Random(seed)
            for seat in (0, 1):
                nodes = [{} if i % 2 else [] for i in range(12)]
                obs = {'farms': [nodes[1], nodes[3]], 'private': nodes[5], 'player': seat}
                refs = nodes + [obs, obs['farms'], None, 0, 'COW']
                for i, node in enumerate(nodes):
                    values = [rng.choice(refs) for _ in range(3)]
                    if isinstance(node, dict):
                        node.update({str(k): v for k,v in enumerate(values)})
                    else:
                        node.extend(values)
                obs['meta'] = nodes[8:]
                with self.subTest(seed=seed, seat=seat):
                    self.equal(obs, seat, ({'after': [seed]}, {'shed': {'WHEAT': seed}}))

    def test_no_cross_call_state(self):
        obs = self.fixture()
        pair = ({}, {})
        a = self.equal(obs, 0, pair)
        b = self.equal(obs, 0, pair)
        self.assertIsNot(a, b)
        self.assertIsNot(a['farms'][1], b['farms'][1])
        self.assertIs(a['farms'][0], b['farms'][0])


class CurrentRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = authenticate_package(PACKAGE)
        sys.path.insert(0, str(PACKAGE))
        cls.before_source = (PACKAGE / 'titan_runtime.py').read_bytes()
        cls.after_source = compose(cls.before_source)
        cls.old = import_module('quarry_runtime_before', PACKAGE / 'titan_runtime.py')
        cls.new = import_module('quarry_runtime_after', PACKAGE / 'titan_runtime.py', cls.after_source)

    def test_complete_package_has_109_authenticated_members(self):
        self.assertEqual(len(self.manifest['runtime']), 109)

    def test_only_declared_method_body_and_import_are_changed(self):
        text = self.after_source.decode()
        from compose_selected_snapshot import IMPORT
        restored = text.replace(IMPORT, '', 1).replace(NEW, OLD, 1)
        self.assertEqual(restored.encode(), self.before_source)

    def agents(self, mode='frozen', pair=None, binding=None, packet=None):
        result = []
        for module in (self.old, self.new):
            a = module.TitanAgent(module.Features(consumer=mode))
            a.consumer = SimpleNamespace(selected_post_units=pair,
                selected_post_units_binding=binding, last_packet=packet)
            result.append(a)
        return result

    def test_actual_class_certified_pair_48_vectors(self):
        returned = {'farmer': ['WEST'], 'hands': [['PASS']], 'market': []}
        for seat in (0, 1):
            for step in range(24):
                obs = SnapshotGraphTests.fixture()
                obs.update(player=seat, step=step)
                pair = ({'post': step}, {'shed': {'WHEAT': step}})
                binding = (step, seat, returned['farmer'], returned['hands'])
                old, new = self.agents(pair=pair, binding=binding)
                a, b = old._selected_snapshot(obs, returned), new._selected_snapshot(obs, returned)
                self.assertEqual(fingerprint(a, obs, pair), fingerprint(b, obs, pair))

    def test_ordered_authority_and_missing_packet(self):
        obs = SnapshotGraphTests.fixture()
        for packet in (None, {'post_unit_observation': obs}):
            old, new = self.agents('ordered', packet=packet)
            self.assertIs(old._selected_snapshot(obs), new._selected_snapshot(obs))

    def test_missing_pair_all_pass_exact_input_identity(self):
        obs = SnapshotGraphTests.fixture()
        for returned in (None, {'farmer': ['PASS'], 'hands': []},
                         {'farmer': ['PASS'], 'hands': [['PASS']]},
                         {'farmer': ['WEST'], 'hands': []},
                         {'farmer': ['PASS'], 'hands': [['WEST']]}):
            old, new = self.agents()
            self.assertIs(old._selected_snapshot(obs, returned), new._selected_snapshot(obs, returned))

    def test_stale_step_seat_or_actor_binding_is_rejected(self):
        obs = SnapshotGraphTests.fixture()
        returned = {'farmer': ['WEST'], 'hands': [['PASS']]}
        for binding in (None, (30, 0, ['WEST'], [['PASS']]),
                        (31, 1, ['WEST'], [['PASS']]), (31, 0, ['EAST'], [['PASS']]),
                        (31, 0, ['WEST'], [])):
            old, new = self.agents(pair=({}, {}), binding=binding)
            self.assertIsNone(old._selected_snapshot(obs, returned))
            self.assertIsNone(new._selected_snapshot(obs, returned))

    def test_no_returned_action_preserves_existing_binding_rule(self):
        obs = SnapshotGraphTests.fixture()
        pair = ({}, {})
        old, new = self.agents(pair=pair, binding=(31, 0, ['WEST'], []))
        self.assertEqual(fingerprint(old._selected_snapshot(obs), obs, pair),
                         fingerprint(new._selected_snapshot(obs), obs, pair))

    def test_transformer_rejects_changed_preimage(self):
        for data in (b'# changed\n' + self.before_source, self.after_source,
                     self.before_source.replace(b'pair is None', b'pair is not None', 1)):
            with self.assertRaises(ValueError):
                compose(data)

    def test_cli_refuses_overwrite_and_changed_input(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source, output = root / 'in.py', root / 'out.py'
            source.write_bytes(self.before_source)
            output.write_text('keep')
            command = [sys.executable, str(HERE / 'compose_selected_snapshot.py'), str(source)]
            for target in (source, output):
                p = subprocess.run(command + [str(target)], capture_output=True)
                self.assertEqual(p.returncode, 2)
                self.assertEqual(source.read_bytes(), self.before_source)
                self.assertEqual(output.read_text(), 'keep')
            fresh = root / 'new.py'
            p = subprocess.run(command + [str(fresh)], capture_output=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(fresh.read_bytes(), self.after_source)
            source.write_bytes(b'# moved\n' + self.before_source)
            bad = root / 'bad.py'
            p = subprocess.run(command + [str(bad)], capture_output=True)
            self.assertEqual(p.returncode, 2)
            self.assertFalse(bad.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
