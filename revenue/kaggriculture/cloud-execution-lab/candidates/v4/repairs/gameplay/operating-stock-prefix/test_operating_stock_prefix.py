# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from copy import deepcopy
import unittest

import operating_stock_prefix as p


def action(prefix=None, suffix=None):
    prefix = ([['SELL', 'FERTILIZER', 5]] + [[] for _ in range(9)]
              if prefix is None else prefix)
    return {'farmer': ['PASS'], 'hands': [], 'market': deepcopy(prefix + (suffix or [])),
            'opaque': {'keep': [1, 2, 3]}}


class PrefixGuardTests(unittest.TestCase):
    def call(self, delegate, selected, route=None, cfg=None):
        return p.protect_operating_stock_prefix(
            delegate, object(), {'step': 10}, cfg or {'maxMarketOrdersPerTurn': 10},
            selected, {}, {}, route if route is not None else [selected], ())

    def test_dead_tail_hire_and_buy_are_hidden_and_suffix_restored(self):
        tail = [['HIRE'], ['BUY_PRODUCT', 'FERTILIZER', 99]]
        selected = action(suffix=tail)
        route = [selected, action(suffix=[['HIRE'], ['BUY_ANIMAL', 'GOOSE', 5]])]
        before = deepcopy(selected)

        def delegate(_m, _o, _c, bounded, _f, _p, bounded_route, _cp):
            self.assertEqual(len(bounded['market']), 10)
            self.assertFalse(any(row and row[0] == 'HIRE' for row in bounded['market']))
            self.assertEqual(len(bounded_route[1]['market']), 10)
            self.assertFalse(any(row and row[0] == 'HIRE' for row in bounded_route[1]['market']))
            out = deepcopy(bounded)
            out['market'][0] = ['SELL', 'FERTILIZER', 3]
            return out, {'changed': True, 'reason': 'reserve_reachable_fertilizer'}

        out, report = self.call(delegate, selected, route)
        self.assertEqual(out['market'][0], ['SELL', 'FERTILIZER', 3])
        self.assertEqual(out['market'][10:], tail)
        self.assertEqual(selected, before)
        self.assertTrue(report['executable_prefix_guard'])
        self.assertEqual(report['raw_suffix_rows'], 2)

    def test_unchanged_delegate_returns_exact_parent_identity(self):
        selected = action(suffix=[['HIRE']])
        def delegate(_m, _o, _c, bounded, _f, _p, _r, _cp):
            return bounded, {'changed': False, 'reason': 'no_change'}
        out, report = self.call(delegate, selected)
        self.assertIs(out, selected)
        self.assertFalse(report['changed'])

    def test_future_route_slice_is_bounded_too(self):
        row = action(suffix=[['HIRE']])
        view = p.ExecutablePrefixRoute([row, row], 10)
        self.assertEqual(len(view), 2)
        self.assertEqual(len(view[0]['market']), 10)
        self.assertEqual([len(x['market']) for x in view[:2]], [10, 10])

    def test_future_route_delegate_mutation_does_not_touch_original(self):
        row = action(suffix=[['HIRE']])
        route = [row]
        original = deepcopy(route)
        view = p.ExecutablePrefixRoute(route, 10)
        bounded = view[0]
        bounded['market'][0][2] = 1
        self.assertEqual(route, original)

    def test_invalid_limit_fails_closed_without_calling_delegate(self):
        selected = action()
        for bad in (True, 0, -1, 1.0, '10', None):
            called = []
            def delegate(*args):
                called.append(True)
                return args[3], {}
            with self.subTest(bad=bad):
                out, report = self.call(delegate, selected, cfg={'maxMarketOrdersPerTurn': bad})
                self.assertIs(out, selected)
                self.assertEqual(called, [])
                self.assertTrue(report['executable_prefix_guard'])

    def test_full_prefix_length_change_fails_closed_to_exact_parent(self):
        selected = action(suffix=[['HIRE']])
        def delegate(_m, _o, _c, bounded, _f, _p, _r, _cp):
            out = deepcopy(bounded)
            out['market'].pop()
            return out, {'changed': True}
        out, report = self.call(delegate, selected)
        self.assertIs(out, selected)
        self.assertEqual(report['reason'], 'delegate_changed_full_prefix_length')

    def test_nonmarket_delegate_edit_fails_closed(self):
        selected = action()
        def delegate(_m, _o, _c, bounded, _f, _p, _r, _cp):
            out = deepcopy(bounded)
            out['farmer'] = ['NORTH']
            return out, {'changed': True}
        out, report = self.call(delegate, selected)
        self.assertIs(out, selected)
        self.assertEqual(report['reason'], 'delegate_changed_nonmarket_fields')

    def test_short_prefix_may_append_without_suffix_shift(self):
        selected = action(prefix=[['SELL', 'FERTILIZER', 2]], suffix=[])
        def delegate(_m, _o, _c, bounded, _f, _p, _r, _cp):
            out = deepcopy(bounded)
            out['market'].append(['SELL', 'WHEAT', 1])
            return out, {'changed': True}
        out, report = self.call(delegate, selected)
        self.assertEqual(out['market'], [['SELL', 'FERTILIZER', 2], ['SELL', 'WHEAT', 1]])
        self.assertTrue(report['changed'])

    def test_prefix_limit_other_than_ten_is_respected(self):
        selected = action(prefix=[['SELL', 'FERTILIZER', 2], [], []], suffix=[['HIRE']])
        seen = {}
        def delegate(_m, _o, _c, bounded, _f, _p, route, _cp):
            seen['current'] = deepcopy(bounded['market'])
            seen['future'] = deepcopy(route[0]['market'])
            return bounded, {'changed': False}
        out, _ = self.call(delegate, selected, [selected], {'maxMarketOrdersPerTurn': 3})
        self.assertIs(out, selected)
        self.assertEqual(len(seen['current']), 3)
        self.assertEqual(len(seen['future']), 3)
        self.assertNotIn(['HIRE'], seen['current'])


if __name__ == '__main__':
    unittest.main()
