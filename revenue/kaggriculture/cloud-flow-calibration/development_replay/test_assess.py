# SPDX-License-Identifier: MIT
"""Tests for the new recorded-trace consumer against actual pinned dependencies."""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace

import assess

PORTFOLIO = CALIBRATION = None


class ReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(PORTFOLIO)); sys.path.insert(0, str(CALIBRATION))
        cls.flow = assess.load(PORTFOLIO / 'revision2/vendor/t12/flow.py', 'quill_test_flow')
        cls.cal = assess.load(CALIBRATION / 'calibration.py', 'quill_test_cal')
        ev = assess.load(PORTFOLIO / 'vendor/cloud-eval/evaluate.py', 'quill_test_ev')
        cls.engine, _ = ev.get_engine(PORTFOLIO / 'vendor/engine')
        cls.name, cls.member, cls.rows, cls.archive = next(assess.retained(PORTFOLIO))

    def model(self):
        return assess.PublicReplay(self.engine, self.flow, self.cal, 'opaque-game')

    def obs(self):
        return deepcopy(self.rows[0]['observation'])

    def pass_action(self):
        return dict(farmer=['PASS'], hands=[], market=[])

    def test_exact_dependency_and_development_binding(self):
        self.assertEqual(assess.blob(PORTFOLIO / 'revision2/vendor/t12/flow.py'),
                         '7b3c1c383e98ce1eb5bf539caddf0ab4351f8633')
        self.assertEqual(assess.blob(CALIBRATION / 'calibration.py'),
                         '75e67d65583ab83847b95dee426ff3a49dee1c87')
        self.assertEqual(len(self.rows), 719)
        self.assertTrue(all(n.startswith('development-v') for n in assess.TRACE_NAMES))
        self.assertEqual(len(set(assess.TRACE_NAMES)), 6)
        self.assertEqual(set(assess.PRODUCTS), set(self.engine.PRODUCTS) - self.flow.OPERATING)

    def test_duplicate_sale_requests_do_not_duplicate_fills(self):
        obs = self.obs(); obs['private']['shed']['MILK'] = 5
        a = self.pass_action(); a['market'] = [['SELL', 'MILK', 4], ['SELL', 'MILK', 4]]
        self.assertEqual(assess.own_sales(self.engine, obs, a, {})['MILK'], 5)

    def test_order_limit_and_malformed_orders(self):
        obs = self.obs(); obs['private']['shed']['MILK'] = 5
        a = self.pass_action(); a['market'] = [['HIRE'], ['SELL', 'MILK', 5]]
        self.assertEqual(assess.own_sales(self.engine, obs, a, {'maxMarketOrdersPerTurn': 1})['MILK'], 0)
        a['market'] = [None, [], ['SELL', 'MILK', 'invalid'], ['SELL', 'MILK', -1], ['SELL', 'MILK', 2]]
        self.assertEqual(assess.own_sales(self.engine, obs, a, {})['MILK'], 2)

    def test_operating_purchases_do_not_create_nonoperating_stock(self):
        obs = self.obs(); a = self.pass_action()
        a['market'] = [['BUY_PRODUCT', 'MILK', 5], ['SELL', 'MILK', 5], ['BUY_PRODUCT', 'WHEAT', 1]]
        out = assess.own_sales(self.engine, obs, a, {})
        self.assertEqual(out['MILK'], 0)
        self.assertNotIn('WHEAT', out); self.assertNotIn('FERTILIZER', out)

    def test_floor_sale_still_depletes_own_stock(self):
        obs = self.obs(); obs['private']['shed']['MILK'] = 5
        obs['market']['inventory']['MILK'] = 1000000
        a = self.pass_action(); a['market'] = [['SELL', 'MILK', 5]]
        self.assertEqual(assess.own_sales(self.engine, obs, a, {})['MILK'], 5)

    def test_selected_drop_runs_before_sale(self):
        obs = self.obs(); obs['private']['inventories'][0] = {'MILK': 5}
        a = self.pass_action(); a['farmer'] = ['DROP']; a['market'] = [['SELL', 'MILK', 5]]
        self.assertEqual(assess.own_sales(self.engine, obs, a, {})['MILK'], 5)
        a['farmer'] = ['PASS']
        self.assertEqual(assess.own_sales(self.engine, obs, a, {})['MILK'], 0)

    def test_capacity_limited_drop_uses_physical_quantity(self):
        obs = self.obs(); obs['private']['shed'] = {'CARROT': 98}
        obs['private']['inventories'][0] = {'MILK': 5}
        a = self.pass_action(); a['farmer'] = ['DROP']; a['market'] = [['SELL', 'MILK', 5]]
        self.assertEqual(assess.own_sales(self.engine, obs, a, {})['MILK'], 2)

    def test_observation_and_action_not_mutated(self):
        obs = self.obs(); a = deepcopy(self.rows[0]['actions'][obs['player']])
        before = deepcopy((obs, a))
        assess.own_sales(self.engine, obs, a, {})
        self.assertEqual((obs, a), before)
        self.model().feed(obs, a)
        self.assertEqual((obs, a), before)

    def test_consumption_matches_official_function_with_duplicates(self):
        shops = list(self.engine.SHOPS)
        for t in (0, 1, 4, 23, 24, 28, 718):
            for chosen in ([], shops[:2], [shops[0], shops[0]]):
                obs = self.obs(); obs['town']['unlocked_shops'] = chosen
                market = deepcopy(obs['market']); before = deepcopy(market['inventory'])
                state = [SimpleNamespace(observation=SimpleNamespace(market=market, town=obs['town']))]
                self.engine._town_consume(SimpleNamespace(configuration={}), state, t)
                for p in assess.PRODUCTS:
                    self.assertEqual(assess.absorption(self.engine, p, t, chosen, {}),
                                     before[p] - market['inventory'][p])

    def test_public_clock_parity_and_precedence(self):
        explicit = self.model(); derived = self.model()
        for r in self.rows[:96]:
            obs = deepcopy(r['observation']); a = r['actions'][r['candidate_seat']]
            explicit.feed(obs, a); obs.pop('step', None); derived.feed(obs, a)
        self.assertEqual(explicit.outcomes, derived.outcomes)
        obs = self.obs(); obs['day'] = 99; obs['step'] = 7
        self.assertEqual(assess.clock(obs, {}), 7)

    def test_start_gap_duplicate_reverse_rejected(self):
        m = self.model(); r = self.rows[0]; m.feed(r['observation'], r['actions'][r['candidate_seat']])
        with self.assertRaises(ValueError): m.feed(r['observation'], r['actions'][r['candidate_seat']])
        with self.assertRaises(ValueError): m.feed(self.rows[2]['observation'], self.pass_action())
        with self.assertRaises(ValueError): self.model().feed(self.rows[1]['observation'], self.pass_action())

    def test_current_rival_action_and_outcome_poisoning_do_not_enter(self):
        first = self.model(); poisoned = self.model()
        # Include enough prefix to reach actual same-hour history readiness.
        for r in self.rows[:120]:
            r2 = deepcopy(r)
            r2['actions'][1-r2['candidate_seat']] = {'market': [['SELL', 'MILK', 999]]}
            r2['post_cash'] = [-999999, 999999]
            r2['future_seed'] = 314159
            r2['observation']['evaluation_only_future'] = {'next_action': 'BUY', 'truth': 999}
            for m, x in ((first, r), (poisoned, r2)):
                m.feed(x['observation'], x['actions'][x['candidate_seat']])
        self.assertEqual(first.outcomes, poisoned.outcomes)
        self.assertEqual(first.intervals, poisoned.intervals)
        self.assertTrue(any(r['forecast']['support'] >= 3 for r in first.outcomes))

    def test_game_reset_and_cold_unknown(self):
        m = self.model()
        for r in self.rows[:120]: m.feed(r['observation'], r['actions'][r['candidate_seat']])
        fresh = self.model(); r = self.rows[0]; fresh.feed(r['observation'], r['actions'][r['candidate_seat']])
        for f, labels in fresh.pending.values():
            self.assertEqual(f['unknown_mass'], 1); self.assertEqual(f['prior_rate_control'], .5)
            self.assertEqual(labels, [])
        self.assertEqual(fresh.history.identified, 0)

    def test_frozen_target_is_resolved_only_after_window(self):
        m = self.model()
        for r in self.rows[:3]: m.feed(r['observation'], r['actions'][r['candidate_seat']])
        self.assertEqual(m.outcomes, [])
        frozen = deepcopy(m.pending['MILK'][0]); r = self.rows[3]
        m.feed(r['observation'], r['actions'][r['candidate_seat']])
        out = next(x for x in m.outcomes if x['forecast']['product'] == 'MILK')
        self.assertEqual(out['forecast'], frozen)
        self.assertEqual(out['observed_at'], 3)
        self.assertEqual(out['forecast']['now'], 0)

    def test_comparison_counts_match_each_experts_available_windows(self):
        m = self.model()
        for r in self.rows[:120]: m.feed(r['observation'], r['actions'][r['candidate_seat']])
        totals = assess.aggregate(m.outcomes)
        self.assertEqual(totals['all']['windows'], totals['cold']['windows'] + totals['warm']['windows'])
        for tag in ('all', 'cold', 'warm'):
            g = totals[tag]
            self.assertEqual(g['windows'], g['identified'] + g['censored'])
            for n in ('model', 'prior_rate_control', 'zero_control'):
                self.assertEqual(g['scores'][n]['n'], g['identified'])
        self.assertEqual(totals['all']['scores']['same_phase']['n'], totals['warm']['identified'])

    def test_existing_output_directory_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory); sentinel = out / 'existing.txt'; sentinel.write_text('preserve')
            with self.assertRaises(FileExistsError): assess.assess(PORTFOLIO, CALIBRATION, out)
            self.assertEqual(sentinel.read_text(), 'preserve')
            self.assertEqual(len(list(out.iterdir())), 1)


def main():
    global PORTFOLIO, CALIBRATION
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--portfolio', type=Path, required=True)
    p.add_argument('--calibration-dir', type=Path, default=Path(__file__).resolve().parents[1])
    args = p.parse_args(); PORTFOLIO = args.portfolio.resolve(); CALIBRATION = args.calibration_dir.resolve()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ReplayTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
