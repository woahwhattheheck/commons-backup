# SPDX-License-Identifier: Apache-2.0
"""Tests for the V4 recovery of #12414, including alias-graph fallbacks."""
import ast
import base64
import copy
import hashlib
import json
import lzma
from pathlib import Path
import sys
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
for directory in (HERE, HERE.parent):
    if (directory / 'r04_fast_tape_clone.py').is_file():
        sys.path.insert(0, str(directory))
        break
import r04_fast_tape_clone as candidate


class CloneTests(unittest.TestCase):
    def clone(self, value, fast=False):
        self.assertIs(candidate.is_fast_tape_action(value), fast)
        result = candidate.apply_fast_tape_clone(value)
        self.assertEqual(result, copy.deepcopy(value))
        self.assertIsNot(result, value)
        return result

    def test_plain_action_detaches_every_list(self):
        value = {'farmer': ['PASS'], 'hands': [['NORTH'], ['PICKUP', 'WHEAT', 1]],
                 'market': [['SELL', 'WOOL', 2]]}
        result = self.clone(value, True)
        for key in value:
            self.assertIsNot(result[key], value[key])
        for key in ('hands', 'market'):
            for a, b in zip(result[key], value[key]):
                self.assertIsNot(a, b)
        result['hands'][0].append('poison')
        self.assertEqual(value['hands'][0], ['NORTH'])

    def test_farmer_and_hands_shared_row(self):
        row = ['PASS']
        value = {'farmer': row, 'hands': [row, row], 'market': []}
        result = self.clone(value)
        self.assertIs(result['farmer'], result['hands'][0])
        self.assertIs(result['hands'][0], result['hands'][1])
        self.assertIsNot(result['farmer'], row)

    def test_hands_and_market_shared_row(self):
        row = ['PASS']
        value = {'farmer': ['PASS'], 'hands': [row], 'market': [row]}
        result = self.clone(value)
        self.assertIs(result['hands'][0], result['market'][0])
        self.assertIsNot(result['hands'][0], row)

    def test_repeated_market_row(self):
        row = ['SELL', 'WOOL', 1]
        value = {'farmer': ['PASS'], 'hands': [], 'market': [row, row]}
        result = self.clone(value)
        self.assertIs(result['market'][0], result['market'][1])

    def test_shared_empty_root_lists(self):
        row = []
        result = self.clone({'farmer': row, 'hands': row, 'market': row})
        self.assertIs(result['farmer'], result['hands'])
        self.assertIs(result['hands'], result['market'])

    def test_row_aliases_container(self):
        row = []
        value = {'farmer': ['PASS'], 'hands': [row], 'market': row}
        result = self.clone(value)
        self.assertIs(result['hands'][0], result['market'])

    def test_list_cycle_falls_back(self):
        row = []; row.append(row)
        value = {'farmer': ['PASS'], 'hands': [], 'market': row}
        self.assertFalse(candidate.is_fast_tape_action(value))
        result = candidate.apply_fast_tape_clone(value)
        self.assertIs(result['market'], result['market'][0])
        self.assertIsNot(result['market'], row)

    def test_dictionary_order_preserved(self):
        value = {'market': [], 'hands': [], 'farmer': ['PASS']}
        result = self.clone(value)
        self.assertEqual(list(result), list(value))

    def test_key_subclass_preserved(self):
        class Key(str):
            pass
        key = Key('farmer'); key.metadata = ['x']
        value = {key: ['PASS'], 'hands': [], 'market': []}
        result = self.clone(value)
        result_key = next(iter(result))
        self.assertIs(type(result_key), Key)
        self.assertIsNot(result_key.metadata, key.metadata)

    def test_root_subclass_preserved(self):
        class Action(dict):
            pass
        result = self.clone(Action(farmer=['PASS'], hands=[], market=[]))
        self.assertIs(type(result), Action)

    def test_list_subclass_preserved(self):
        class Row(list):
            pass
        value = {'farmer': Row(['PASS']), 'hands': [], 'market': []}
        result = self.clone(value)
        self.assertIs(type(result['farmer']), Row)

    def test_unknown_root_field_falls_back(self):
        value = {'farmer': ['PASS'], 'hands': [], 'market': [], 'future': {'x': [1]}}
        result = self.clone(value)
        self.assertIsNot(result['future']['x'], value['future']['x'])

    def test_future_nested_containers(self):
        payloads = [['NORTH'], {'meta': ['x']}, (['x'],), {'x'}]
        for payload in payloads:
            with self.subTest(type=type(payload).__name__):
                value = {'farmer': ['PASS'], 'hands': [], 'market': [['SELL', 'MILK', payload]]}
                result = self.clone(value)
                self.assertIsNot(result['market'][0][2], payload)
                if isinstance(payload, tuple):
                    self.assertIsNot(result['market'][0][2][0], payload[0])

    def test_exact_immutable_scalars(self):
        value = {'farmer': ['PASS', 1, 2.5, False, None], 'hands': [[]], 'market': [[]]}
        self.clone(value, True)

    def test_scalar_subclass_falls_back(self):
        class Scalar(int):
            pass
        scalar = Scalar(1); scalar.metadata = ['x']
        result = self.clone({'farmer': ['PASS'], 'hands': [], 'market': [['SELL', 'WOOL', scalar]]})
        self.assertIs(type(result['market'][0][2]), Scalar)
        self.assertIsNot(result['market'][0][2].metadata, scalar.metadata)

    def test_nonfinite_immutable_values_remain_identical(self):
        value = {'farmer': [float('nan'), float('inf')], 'hands': [], 'market': []}
        self.assertTrue(candidate.is_fast_tape_action(value))
        result = candidate.apply_fast_tape_clone(value)
        self.assertIs(result['farmer'][0], value['farmer'][0])
        self.assertIs(result['farmer'][1], value['farmer'][1])

    def test_plain_string_key_identity_retained(self):
        keys = [bytes(k, 'ascii').decode('ascii') for k in ('farmer', 'hands', 'market')]
        value = dict(zip(keys, (['PASS'], [], [])))
        result = self.clone(value, True)
        for before, after in zip(value, result):
            self.assertIs(before, after)

    def test_scalar_type_equality_does_not_admit_mutable_object(self):
        class SpoofType(type):
            def __hash__(cls):
                return hash(str)
            def __eq__(cls, other):
                return other is str or other is cls
        class Payload(metaclass=SpoofType):
            pass
        payload = Payload(); payload.data = ['x']
        value = {'farmer': [payload], 'hands': [], 'market': []}
        self.assertFalse(candidate.is_fast_tape_action(value))
        sentinel = object()
        with mock.patch.object(candidate.copy, 'deepcopy', return_value=sentinel) as fallback:
            self.assertIs(candidate.apply_fast_tape_clone(value), sentinel)
            fallback.assert_called_once_with(value)

    def test_non_dict_and_missing_fields(self):
        for value in (None, [], (), {'farmer': ['PASS']}):
            self.assertFalse(candidate.is_fast_tape_action(value))
            self.assertEqual(candidate.apply_fast_tape_clone(value), copy.deepcopy(value))

    def test_all_9347_frozen_actions(self):
        path = Path(candidate.__file__).with_name('r01_tapes.py')
        data = path.read_bytes()
        blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        self.assertEqual(blob, 'a43289b9cc5e34a2481fddf652762a7d92f427ef')
        nodes = [n for n in ast.parse(data).body if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == '_B85' for t in n.targets)]
        self.assertEqual(len(nodes), 1)
        encoded = ast.literal_eval(nodes[0].value)
        tapes = json.loads(lzma.decompress(base64.b85decode(encoded)))
        self.assertEqual(len(tapes), 13)
        self.assertTrue(all(len(tape) == 719 for tape in tapes))
        count = 0
        for tape in tapes:
            for value in tape:
                result = self.clone(value, True)
                self.assertEqual(list(result), list(value))
                for key in ('farmer', 'hands', 'market'):
                    self.assertIsNot(result[key], value[key])
                for key in ('hands', 'market'):
                    for a, b in zip(result[key], value[key]):
                        self.assertIsNot(a, b)
                count += 1
        self.assertEqual(count, 9347)


if __name__ == '__main__':
    unittest.main(verbosity=2)
