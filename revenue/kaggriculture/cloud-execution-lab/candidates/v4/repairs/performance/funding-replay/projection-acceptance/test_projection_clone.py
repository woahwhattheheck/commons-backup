# SPDX-License-Identifier: Apache-2.0
"""Independent graph, fallback and source-custody tests. No network required."""
from __future__ import annotations
import copy
import gc
import importlib.util
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import compose_projection_clone as composer

HERE = Path(__file__).resolve().parent
helper_path = Path(os.environ.get('PROJECTION_HELPER', HERE / 'projection_state_clone.py'))
spec = importlib.util.spec_from_file_location('projection_helper_under_test', helper_path)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
clone = helper.clone_projection_state

class SpecialDict(dict):
    pass
class SpecialList(list):
    pass
class Token:
    def __init__(self):
        self.calls = 0
        self.memo_sizes = []
    def __deepcopy__(self, memo):
        self.calls += 1
        self.memo_sizes.append(len(memo))
        out = Token()
        memo[id(self)] = out
        return out
class Cancel(BaseException):
    pass
class Canceller:
    def __deepcopy__(self, memo):
        raise Cancel('propagate cancellation')

class GraphTests(unittest.TestCase):
    def equal_graph(self, left, right):
        """Compare graph structure, ordering and bijective container identities."""
        forward, reverse = {}, {}
        def visit(a, b):
            self.assertIs(type(a), type(b))
            if type(a) in (dict, list):
                if id(a) in forward:
                    self.assertEqual(forward[id(a)], id(b))
                    return
                self.assertNotIn(id(b), reverse)
                forward[id(a)], reverse[id(b)] = id(b), id(a)
                self.assertIsNot(a, b)
                self.assertEqual(len(a), len(b))
                if type(a) is dict:
                    self.assertEqual(list(a), list(b))
                    for k in a: visit(a[k], b[k])
                else:
                    for x, y in zip(a, b): visit(x, y)
            else:
                self.assertIs(a, b)
        visit(left, right)

    def test_acyclic_outputs_release_without_cyclic_gc(self):
        leaf = 'lifetime-' + str(id(self)) + 'x' * 2000
        source = {'nested': [{'leaf': leaf}]}
        was_enabled = gc.isenabled()
        gc.collect(); gc.disable()
        try:
            before = sys.getrefcount(leaf)
            for _ in range(40): clone(source)
            self.assertEqual(sys.getrefcount(leaf) - before, 0)
        finally:
            gc.collect()
            if was_enabled: gc.enable()

    def test_partial_cyclic_fallback_adds_no_extra_retention(self):
        leaf = 'fallback-' + str(id(self)) + 'x' * 2000
        source = {'leaf': leaf}
        source['self'] = source
        source['foreign'] = set()
        was_enabled = gc.isenabled()
        deltas = []
        gc.disable()
        try:
            for fn in (copy.deepcopy, clone):
                gc.collect()
                before = sys.getrefcount(leaf)
                for _ in range(24): fn(source)
                deltas.append(sys.getrefcount(leaf) - before)
            self.assertEqual(deltas, [24, 24])
        finally:
            gc.collect()
            if was_enabled: gc.enable()

    def test_scalar_identity(self):
        for value in (None, True, False, 0, 1, -100001, 'wheat', 0.0, float('nan'), float('inf')):
            self.assertIs(clone(value), copy.deepcopy(value))

    def test_nested_detached_and_ordered(self):
        src = {'z': [{'milk': 1}], 'a': [], 'q': {'wheat': 9, 'fert': 2}}
        out = clone(src)
        self.equal_graph(src, out)
        out['z'][0]['milk'] = 99
        self.assertEqual(src['z'][0]['milk'], 1)
        out['a'].append(1)
        self.assertEqual(src['a'], [])

    def test_shared_graph(self):
        shared = [1, {'x': []}]
        src = {'first': shared, 'again': shared, 'deep': [shared]}
        out = clone(src)
        self.equal_graph(src, out)
        self.assertIs(out['first'], out['deep'][0])
        self.assertIsNot(out['first'], src['first'])

    def test_cycles(self):
        a, b = [], {}
        a.extend([b, a]); b['root'] = a; b['self'] = b
        self.equal_graph(a, clone(a))

    def test_random_graphs(self):
        rng = random.Random(391117)
        for case in range(1200):
            nodes = [([] if rng.randrange(2) else {}) for _ in range(rng.randrange(1, 18))]
            for i, node in enumerate(nodes):
                for j in range(rng.randrange(5)):
                    child = (rng.choice(nodes) if rng.randrange(3) else
                             rng.choice([None, 0, 33, True, 2.5, 'FERT']))
                    if type(node) is list: node.append(child)
                    else: node[f'{j}-{i}'] = child
            self.equal_graph(copy.deepcopy(nodes[0]), clone(nodes[0]))
            self.equal_graph(nodes[0], clone(nodes[0]))

    def test_scalar_keys_preserve_order(self):
        src = {None: [], 'z': {}, 33: [True], 3.25: 'value'}
        self.equal_graph(src, clone(src))

    def test_two_calls_do_not_share_memo(self):
        value = {'x': [1]}
        a, b = clone(value), clone(value)
        self.assertIsNot(a['x'], b['x'])
        a['x'].append(2)
        self.assertEqual(b['x'], [1])

    def test_subclasses_delegate(self):
        for root in (SpecialDict(x=[1]), SpecialList([1, []])):
            with patch.object(helper, 'deepcopy', wraps=copy.deepcopy) as spy:
                out = clone(root)
                spy.assert_called_once_with(root)
            self.assertIs(type(out), type(root))
            self.assertEqual(out, root)
            self.assertIsNot(out, root)

    def test_unknown_leaf_whole_root_fallback(self):
        token = Token()
        shared = []
        src = {'first': shared, 'second': shared, 'unknown': token}
        with patch.object(helper, 'deepcopy', wraps=copy.deepcopy) as spy:
            out = clone(src)
            spy.assert_called_once_with(src)
        self.assertEqual(token.calls, 1)
        self.assertIs(out['first'], out['second'])
        self.assertIsNot(out['first'], shared)
        expected_token = Token()
        reference = {'first': shared, 'second': shared, 'unknown': expected_token}
        copy.deepcopy(reference)
        self.assertEqual(token.memo_sizes, expected_token.memo_sizes)

    def test_tuple_key_delegates(self):
        root = {('MILK', 1): {'q': [3]}}
        with patch.object(helper, 'deepcopy', wraps=copy.deepcopy) as spy:
            out = clone(root)
            spy.assert_called_once_with(root)
        self.assertEqual(out, root)
        self.assertIsNot(out[('MILK', 1)]['q'], root[('MILK', 1)]['q'])

    def test_deep_graph_fallback(self):
        root = []
        tip = root
        for _ in range(80):
            tip.append([]); tip = tip[0]
        with patch.object(helper, 'deepcopy', wraps=copy.deepcopy) as spy:
            out = clone(root)
            spy.assert_called_once_with(root)
        self.equal_graph(root, out)

    def test_cancellation_propagates(self):
        with self.assertRaises(Cancel):
            clone({'nested': [Canceller()]})

    def test_original_not_touched_on_failed_fallback(self):
        shared = [1]
        root = {'shared': shared, 'a': [Canceller()]}
        with self.assertRaises(Cancel): clone(root)
        self.assertIs(root['shared'], shared)
        self.assertEqual(shared, [1])

    def test_fallback_tuple_cycle(self):
        a = []
        root = (a,); a.append(root)
        out = clone(root)
        self.assertIs(out[0][0], out)
        self.assertIsNot(out[0], a)

class ComposerTests(unittest.TestCase):
    def setUp(self):
        self.edits, self.helper = composer.authenticated_inputs()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.source = self.home / 'native'
        self.source.mkdir()
        for name in {x['file'] for x in self.edits}:
            (self.source / name).write_text('# prefix\n' + '\n'.join(
                x['before'] for x in self.edits if x['file'] == name) + '\n# suffix\n')
        (self.source / 'peer.py').write_text('UNCHANGED = 1\n')

    def test_method_pins_and_idempotence(self):
        for name in {x['file'] for x in self.edits}:
            src = (self.source / name).read_bytes()
            out = composer.compose_bytes(name, src, self.edits)
            self.assertNotEqual(src, out)
            self.assertEqual(out, composer.compose_bytes(name, out, self.edits))
            restored = out.decode()
            for x in self.edits:
                if x['file'] == name: restored = restored.replace(x['after'], x['before'])
            self.assertEqual(restored.encode(), src)

    def test_funding_ablation_preserves_peer_projection_methods(self):
        out = self.home / 'funding-only'
        composer.compose_package(self.source, out, 'funding')
        self.assertEqual((self.source/'early_capital.py').read_bytes(),
                         (out/'early_capital.py').read_bytes())
        text = (out/'frozen_selected.py').read_text()
        for item in self.edits:
            if item['function'] == 'represented_shed_event':
                self.assertIn(item['before'], text)
        with self.assertRaises(composer.CompositionError):
            composer.compose_package(self.source, self.home/'invalid', 'bad')

    def test_same_method_drift_rejected(self):
        for item in self.edits:
            src = (self.source / item['file']).read_bytes()
            mutated = src.replace(item['before'].encode(),
                                  item['before'].replace('\n', '\n    # drift\n', 1).encode())
            with self.assertRaises(composer.CompositionError):
                composer.compose_bytes(item['file'], mutated, self.edits)

    def test_duplicate_method_rejected(self):
        item = self.edits[0]
        src = (self.source / item['file']).read_bytes() + item['before'].encode()
        with self.assertRaises(composer.CompositionError):
            composer.compose_bytes(item['file'], src, self.edits)

    def test_missing_method_rejected(self):
        with self.assertRaises(composer.CompositionError):
            composer.compose_bytes('frozen_selected.py', b'x=1\n', self.edits)

    def test_foreign_file_rejected(self):
        with self.assertRaises(composer.CompositionError):
            composer.compose_bytes('runtime.py', b'x=1\n', self.edits)

    def test_packet_tamper_rejected(self):
        for name in ('projection_state_clone.py', 'edits.json'):
            packet = self.home / ('packet-' + name)
            packet.mkdir()
            for other in ('projection_state_clone.py', 'edits.json'):
                (packet / other).write_bytes((HERE / other).read_bytes())
            with (packet / name).open('ab') as f: f.write(b'\n')
            with patch.object(composer, 'HERE', packet):
                with self.assertRaises(composer.CompositionError):
                    composer.authenticated_inputs()

    def test_separate_copy_and_source_readback(self):
        before = {p.name: p.read_bytes() for p in self.source.iterdir()}
        out = self.home / 'composed'
        receipt = composer.compose_package(self.source, out)
        self.assertEqual(len(receipt['files']), 2)
        for name, value in before.items(): self.assertEqual((self.source / name).read_bytes(), value)
        self.assertEqual((out / 'peer.py').read_bytes(), before['peer.py'])
        self.assertEqual((out / 'projection_state_clone.py').read_bytes(), self.helper)
        out2 = self.home / 'repeat'
        composer.compose_package(out, out2)
        self.assertEqual({x.name: x.read_bytes() for x in out.iterdir()},
                         {x.name: x.read_bytes() for x in out2.iterdir()})

    def test_alias_existing_and_nested_destinations_rejected(self):
        for dest in (self.source, self.source/'child', self.home):
            with self.assertRaises(composer.CompositionError):
                composer.compose_package(self.source, dest)
        existing = self.home / 'already'; existing.mkdir()
        marker = existing/'keep'; marker.write_text('keep')
        with self.assertRaises(composer.CompositionError):
            composer.compose_package(self.source, existing)
        self.assertEqual(marker.read_text(), 'keep')

    def test_validate_before_copy(self):
        (self.source/'early_capital.py').write_text('x=1\n')
        out = self.home/'candidate'
        with self.assertRaises(composer.CompositionError): composer.compose_package(self.source, out)
        self.assertFalse(out.exists())

    def test_symlink_rejected(self):
        (self.source/'link').symlink_to(self.source/'peer.py')
        out = self.home/'candidate'
        with self.assertRaises(composer.CompositionError): composer.compose_package(self.source, out)
        self.assertFalse(out.exists())

    def test_existing_helper_mismatch(self):
        (self.source/'projection_state_clone.py').write_text('fake=1\n')
        with self.assertRaises(composer.CompositionError):
            composer.compose_package(self.source, self.home/'candidate')

    def test_cli_receipt_cannot_clobber_source(self):
        before = (self.source/'peer.py').read_bytes()
        out = self.home/'candidate'
        result = subprocess.run([sys.executable, str(HERE/'compose_projection_clone.py'),
                                 str(self.source), str(out), '--receipt', str(self.source/'peer.py')],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(out.exists())
        self.assertEqual(before, (self.source/'peer.py').read_bytes())

if __name__ == '__main__':
    unittest.main(verbosity=2)
