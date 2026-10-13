# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
import json
from pathlib import Path
import random
from types import SimpleNamespace
import unittest
import trace_current as trace
from summarize_census import sales


class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.cfg = {'maxMarketOrdersPerTurn': 2, 'turnsPerDay': 24}
        self.obs = {'step': 25, 'player': 1, 'day': 1, 'hour': 1}
        self.action = {'farmer': ['PASS'], 'hands': [],
                       'market': [['SELL', 'WHEAT', 10], [], ['SELL', 'FERTILIZER', 99]]}

    def test_original_raw_prefix_before_filter(self):
        snap = trace.capture(self.action, {}, self.cfg)
        self.assertEqual(sales(snap), [(0, 'WHEAT', 10)])

    def test_raw_suffix_preserved(self):
        snap = trace.capture(self.action, {}, self.cfg)
        self.assertEqual(snap['action']['market'][2], ['SELL', 'FERTILIZER', 99])
        self.assertEqual(len(snap['executable_prefix']), 2)

    def test_minimum_one_slot(self):
        for cap in (-100, -1, 0, 1):
            with self.subTest(cap=cap):
                snap = trace.capture(self.action, {}, dict(self.cfg, maxMarketOrdersPerTurn=cap))
                self.assertEqual(sales(snap), [(0, 'WHEAT', 10)])
                self.assertEqual(snap['market_limit'], 1)

    def test_engine_numeric_count(self):
        for value, expected in [('3', 3), (3.9, 3), (True, 1), (0, 0), (-3, 0), ('bad', 0), (None, 0)]:
            action = dict(self.action, market=[['SELL', 'WHEAT', value]])
            result = sales(trace.capture(action, {}, self.cfg))
            self.assertEqual(result, [(0, 'WHEAT', expected)] if expected else [])

    def test_zero_sell_is_not_residual(self):
        action = dict(self.action, market=[['SELL', 'WHEAT', 0], ['SELL', 'FERTILIZER', -3]])
        self.assertEqual(sales(trace.capture(action, {}, self.cfg)), [])

    def test_malformed_raw_slots_remain_slots(self):
        for invalid in (None, False, [], {}, ['SELL'], ('SELL', 'WHEAT', 5)):
            action = dict(self.action, market=[invalid, ['SELL', 'WHEAT', 7], ['SELL', 'WHEAT', 99]])
            self.assertEqual(sales(trace.capture(action, {}, self.cfg)), [(1, 'WHEAT', 7)])

    def test_non_operating_product_ignored(self):
        action = dict(self.action, market=[['SELL', 'MILK', 999]])
        self.assertEqual(sales(trace.capture(action, {}, self.cfg)), [])

    def test_snapshot_detaches_and_does_not_mutate(self):
        before = deepcopy(self.action)
        diagnostics = {'operating_stock': {'nested': [1]}}
        snap = trace.capture(self.action, diagnostics, self.cfg)
        self.assertEqual(self.action, before)
        self.action['market'][0][2] = 500
        diagnostics['operating_stock']['nested'][0] = 6
        self.assertEqual(sales(snap), [(0, 'WHEAT', 10)])
        self.assertEqual(snap['diagnostics']['operating_stock']['nested'], [1])

    def test_tampered_prefix_rejected(self):
        snap = trace.capture(self.action, {}, self.cfg)
        snap['executable_prefix'].pop()
        with self.assertRaises(ValueError): sales(snap)

    def test_opaque_non_market_action(self):
        self.assertEqual(sales(trace.capture(['PASS'], {}, self.cfg)), [])

    def test_exact_once_identity_and_final_pressure(self):
        calls = []
        collector = trace.Collector()
        class Actor:
            diagnostics = {'status': 'completed'}
            def _operating_stock_selected(self, obs, cfg, action):
                calls.append('operating'); return action
            def _feed_stock_selected(self, obs, cfg, action):
                calls.append('feed'); return action
            def _early_capital_selected(self, obs, cfg, action):
                calls.append('capital-and-final-pressure')
                result = deepcopy(action)
                result['market'][0][2] = 9
                return result
        actor = trace.attach(Actor(), collector)
        collector.begin(self.obs, self.cfg)
        a = actor._operating_stock_selected(self.obs, self.cfg, self.action)
        self.assertIs(a, self.action)
        # Simulate existing crop/final-return guards between A and B.
        a = deepcopy(a); a['market'][0][2] = 8
        a = actor._feed_stock_selected(self.obs, self.cfg, a)
        a = actor._early_capital_selected(self.obs, self.cfg, a)
        row = collector.finish(a, self.cfg)
        self.assertEqual(calls, ['operating', 'feed', 'capital-and-final-pressure'])
        self.assertEqual([sales(row['stages'][s])[0][2] for s in trace.STAGES], [10, 8, 8, 9])
        self.assertTrue(row['D_matches_returned'])
        self.assertEqual(self.action['market'][0][2], 10)

    def test_deadline_baseexception_not_swallowed(self):
        class Deadline(BaseException): pass
        def abort(*args): raise Deadline()
        actor = SimpleNamespace(_operating_stock_selected=abort, _feed_stock_selected=abort,
                                _early_capital_selected=abort, diagnostics={})
        collector = trace.Collector(); collector.begin(self.obs, self.cfg)
        trace.attach(actor, collector)
        with self.assertRaises(Deadline): actor._feed_stock_selected(self.obs, self.cfg, self.action)
        self.assertIn('B', collector.row['stages'])
        self.assertNotIn('C', collector.row['stages'])

    def test_duplicate_boundary_is_error_not_overwrite(self):
        c = trace.Collector(); c.begin(self.obs, self.cfg)
        actor = SimpleNamespace(diagnostics={})
        c.observe('A', actor, self.cfg, self.action)
        c.observe('A', actor, self.cfg, {})
        self.assertEqual(len(c.row['capture_errors']), 1)
        self.assertEqual(sales(c.row['stages']['A']), [(0, 'WHEAT', 10)])

    def test_callback_reset_prevents_stale_stages(self):
        c = trace.Collector(); c.begin(self.obs, self.cfg)
        c.observe('A', SimpleNamespace(diagnostics={}), self.cfg, self.action)
        c.begin(dict(self.obs, step=26), self.cfg)
        self.assertEqual(c.row['stages'], {})
        self.assertIsNone(c.instance)

    def test_fallback_bypass_not_fabricated(self):
        c = trace.Collector(); c.begin(self.obs, self.cfg)
        c.instance = SimpleNamespace(diagnostics={'status': 'deadline_fallback', 'fallback_stage': 'cold_start'})
        row = c.finish(self.action, self.cfg)
        self.assertFalse(row['all_stages'])
        self.assertFalse(row['D_matches_returned'])
        self.assertEqual(row['stages'], {})
        self.assertEqual(sales(row['returned']), [(0, 'WHEAT', 10)])

    def test_suffix_invariance_500_cases(self):
        rng = random.Random(61)
        for _ in range(500):
            cap = rng.randrange(-2, 12)
            prefix = [[rng.choice(['SELL', 'BUY_PRODUCT']), rng.choice(['WHEAT', 'MILK', 'FERTILIZER']), rng.randrange(-2, 100)] for __ in range(max(1, cap))]
            a = dict(self.action, market=prefix)
            b = dict(self.action, market=prefix + [['SELL', 'WHEAT', 10**9], ['SELL', 'FERTILIZER', 10**9]])
            cfg = dict(self.cfg, maxMarketOrdersPerTurn=cap)
            self.assertEqual(sales(trace.capture(a, {}, cfg)), sales(trace.capture(b, {}, cfg)))


if __name__ == '__main__': unittest.main()
