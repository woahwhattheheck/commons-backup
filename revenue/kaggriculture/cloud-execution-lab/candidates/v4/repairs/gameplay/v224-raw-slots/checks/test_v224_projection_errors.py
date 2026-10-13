# SPDX-License-Identifier: Apache-2.0
"""Leaf-only regression for frozen V224 projection conversion failures."""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if (ROOT / 'r04_v224_raw_slots.py').is_file():
    sys.path.insert(0, str(ROOT))

from r04_v224_raw_slots import _frozen_projection, sales_first_raw_slots


def action(rows):
    return {'farmer': ['PASS'], 'hands': [], 'market': rows}


class V224ProjectionErrors(unittest.TestCase):
    def test_infinite_quantity_projection_is_unavailable(self):
        for value in (float('inf'), float('-inf')):
            with self.subTest(value=value):
                self.assertIsNone(_frozen_projection([['SELL', 'WOOL', value]]))

    def test_over_cap_infinite_quantity_retains_exact_parent_and_rows(self):
        for value in (float('inf'), float('-inf')):
            rows = [['SELL', 'WOOL', value]] + [['HIRE'] for _ in range(9)]
            rows.append(['SELL', 'MILK', 1])
            parent = action(rows)
            row_ids = tuple(map(id, rows))
            with self.subTest(value=value):
                self.assertIs(sales_first_raw_slots(parent), parent)
                self.assertIs(parent['market'], rows)
                self.assertEqual(tuple(map(id, rows)), row_ids)
                self.assertEqual(len(rows), 11)

    def test_json_exponent_overflow_retains_parent(self):
        for literal in ('1e309', '-1e309'):
            poison = json.loads('["SELL", "WOOL", ' + literal + ']')
            parent = action([poison] + [['HIRE'] for _ in range(9)]
                            + [['SELL', 'MILK', 1]])
            with self.subTest(literal=literal):
                self.assertIs(sales_first_raw_slots(parent), parent)

    def test_valid_frozen_projection_is_unchanged(self):
        rows = [[], ['HIRE'], ['SELL', 'WOOL', 2]]
        before = copy.deepcopy(rows)
        self.assertEqual(_frozen_projection(rows),
                         [['SELL', 'WOOL', 2], ['HIRE']])
        self.assertEqual(rows, before)

    def test_existing_conversion_errors_remain_unavailable(self):
        for value in (float('nan'), 'not-an-integer', None, [], {}):
            with self.subTest(value=value):
                self.assertIsNone(_frozen_projection([['SELL', 'WOOL', value]]))

    def test_nonexecuted_suffix_is_not_inspected(self):
        prefix = [['HIRE'] for _ in range(10)]
        parent = action(prefix + [['SELL', 'WOOL', float('inf')]])
        self.assertIs(sales_first_raw_slots(parent), parent)

    def test_over_cap_valid_compaction_still_hides_tail(self):
        prefix = [[]] + [['HIRE'] for _ in range(9)]
        parent = action(prefix + [['SELL', 'MILK', 1]])
        out = sales_first_raw_slots(parent)
        self.assertIsNot(out, parent)
        self.assertEqual(out['market'], prefix)
        self.assertEqual(len(parent['market']), 11)

    def test_valid_bubbling_and_parent_nonmutation(self):
        parent = action([['HIRE'], ['BUY_SEED', 'WHEAT', 1],
                         ['SELL', 'WOOL', 2]])
        before = copy.deepcopy(parent)
        out = sales_first_raw_slots(parent)
        self.assertEqual(out['market'],
                         [['SELL', 'WOOL', 2], ['HIRE'],
                          ['BUY_SEED', 'WHEAT', 1]])
        self.assertEqual(parent, before)

    def test_inner_infinite_barrier_keeps_its_raw_index(self):
        for value in (float('inf'), float('-inf')):
            barrier = ['BUY_PRODUCT', 'WHEAT', value]
            parent = action([['HIRE'], barrier, ['SELL', 'WOOL', 2]]
                            + [['HIRE'] for _ in range(7)]
                            + [['SELL', 'MILK', 1]])
            with self.subTest(value=value):
                self.assertIs(sales_first_raw_slots(parent), parent)
                self.assertIs(parent['market'][1], barrier)


if __name__ == '__main__':
    unittest.main()
