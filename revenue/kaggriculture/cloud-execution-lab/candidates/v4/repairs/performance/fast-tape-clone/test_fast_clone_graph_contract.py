# SPDX-License-Identifier: Apache-2.0
"""Independent deterministic graph oracle for recovered ORBIT clone bytes.

This suite needs no engine, generator, archived router, or tape fixtures.
It checks cloning, not gameplay strength or current-runtime integration.
"""
import copy
import hashlib
import itertools
import random
from pathlib import Path
import unittest
from unittest import mock

import r04_fast_tape_clone as candidate

HELPER_BLOB = 'b7c1fd2f7f786c5dc5f8a3b9a7116815ea40607a'


def graph(value):
    """Canonical ordered graph encoding for exact dict/list/scalar fixtures."""
    seen = {}
    nodes = []

    def visit(item):
        if type(item) not in (dict, list):
            return ('scalar', type(item).__name__, repr(item))
        identity = id(item)
        if identity in seen:
            return ('ref', seen[identity])
        index = len(nodes)
        seen[identity] = index
        nodes.append(None)
        if type(item) is dict:
            content = tuple((visit(k), visit(v)) for k, v in item.items())
        else:
            content = tuple(visit(v) for v in item)
        nodes[index] = (type(item).__name__, content)
        return ('ref', index)

    root = visit(value)
    return root, tuple(nodes), set(seen)


def partitions(n):
    """Enumerate set partitions once using restricted-growth strings."""
    def walk(values, maximum):
        if len(values) == n:
            yield tuple(values)
            return
        for value in range(maximum + 2):
            yield from walk(values + [value], max(maximum, value))
    if n:
        yield from walk([0], 0)
    else:
        yield ()


class GraphContract(unittest.TestCase):
    def same_clone(self, action):
        before_root, before_nodes, before_ids = graph(action)
        expected = copy.deepcopy(action)
        actual = candidate.apply_fast_tape_clone(action)
        self.assertEqual(graph(actual)[:2], graph(expected)[:2])
        self.assertEqual(graph(action)[:2], (before_root, before_nodes))
        self.assertFalse(before_ids & graph(actual)[2], 'mutable source alias escaped')
        return actual

    def test_exact_recovered_helper_bytes(self):
        data = Path(candidate.__file__).read_bytes()
        digest = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        self.assertEqual(digest, HELPER_BLOB)

    def test_2000_generated_plain_actions(self):
        rng = random.Random(0x4C10AE)
        atoms = ['PASS', 'NORTH', 'SELL', 'WOOL', '', -1, 0, 1, 100, 1.25, None, True, False]
        def row():
            return [rng.choice(atoms) for _ in range(rng.randrange(6))]
        for _ in range(2000):
            action = {'farmer': row(), 'hands': [row() for _ in range(rng.randrange(5))],
                      'market': [row() for _ in range(rng.randrange(13))]}
            self.assertTrue(candidate.is_fast_tape_action(action))
            result = self.same_clone(action)
            # Mutating all newly made nested lists must not touch the source.
            snapshot = graph(action)[:2]
            for key in ('hands', 'market'):
                for value in result[key]:
                    value.append('probe')
            result['farmer'].append('probe')
            self.assertEqual(graph(action)[:2], snapshot)

    def test_all_203_six_list_alias_partitions(self):
        count = fast = 0
        for partition in partitions(6):
            lists = [[] for _ in range(max(partition) + 1)]
            farmer, hands, market, hand0, hand1, sale = [lists[i] for i in partition]
            # Merged role identities intentionally generate aliases and cycles.
            farmer.append('PASS')
            hands.extend([hand0, hand1])
            market.append(sale)
            hand0.append('NORTH')
            hand1.append('SOUTH')
            sale.extend(['SELL', 'WOOL', 2])
            action = {'farmer': farmer, 'hands': hands, 'market': market}
            self.same_clone(action)
            fast += candidate.is_fast_tape_action(action)
            count += 1
        self.assertEqual((count, fast), (203, 1))

    def test_400_seeded_nested_graphs(self):
        rng = random.Random(0xB0A7)
        fast = 0
        for _ in range(400):
            nodes = [[] for _ in range(rng.randrange(1, 10))]
            action = {'farmer': ['PASS'], 'hands': [], 'market': [['SELL', 'WOOL', nodes[0]]]}
            for node in nodes:
                for _ in range(rng.randrange(5)):
                    node.append(rng.choice(nodes + [action, 'WHEAT', 1, None]))
            fast += candidate.is_fast_tape_action(action)
            self.same_clone(action)
        self.assertEqual(fast, 0)

    def test_all_six_root_key_orders(self):
        fast = 0
        for keys in itertools.permutations(('farmer', 'hands', 'market')):
            values = {'farmer': ['PASS'], 'hands': [['NORTH']], 'market': []}
            action = {key: values[key] for key in keys}
            fast += candidate.is_fast_tape_action(action)
            self.assertEqual(list(self.same_clone(action)), list(action))
        self.assertEqual(fast, 1)

    def test_independent_successive_clones(self):
        source = {'farmer': ['PASS'], 'hands': [['NORTH']], 'market': [['SELL', 'WOOL', 1]]}
        a = self.same_clone(source)
        b = self.same_clone(source)
        self.assertFalse(graph(a)[2] & graph(b)[2])
        a['hands'][0][0] = 'SOUTH'
        self.assertEqual(b['hands'][0], ['NORTH'])

    def test_fallback_delegates_once_and_preserves_result(self):
        source = {'farmer': ['PASS'], 'hands': [], 'market': [], 'future': []}
        sentinel = object()
        with mock.patch.object(candidate.copy, 'deepcopy', return_value=sentinel) as clone:
            self.assertIs(candidate.apply_fast_tape_clone(source), sentinel)
            clone.assert_called_once_with(source)

    def test_fast_path_does_not_call_deepcopy(self):
        source = {'farmer': ['PASS'], 'hands': [], 'market': [[], ['SELL', 'WOOL', 1]]}
        with mock.patch.object(candidate.copy, 'deepcopy', side_effect=RuntimeError('unexpected fallback')):
            result = candidate.apply_fast_tape_clone(source)
        self.assertEqual(result, source)
        self.assertIsNot(result['market'][0], source['market'][0])


if __name__ == '__main__':
    unittest.main(verbosity=2)
