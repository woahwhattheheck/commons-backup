# SPDX-License-Identifier: Apache-2.0
"""Shared-capacity bounds for prior non-buyable sale history.

These are deterministic component tests. They use no controller, game seed,
opponent private state, current rival action, or provider operation.
"""
from __future__ import annotations

from copy import deepcopy
import itertools
import json
from pathlib import Path
import unittest

from flow import FlowHistory, FlowInterval
import selected_action_history as subject

S = FlowInterval
PRODUCTS = ('WHEAT', 'CARROT', 'TOMATO', 'STRAWBERRY', 'MELON',
            'EGG', 'MILK', 'WOOL', 'FERTILIZER')


def row(product='MILK', low=0, high=100, *, step=646,
        reason='floor_censored', admitted=None):
    admitted_low, admitted_high = admitted if admitted is not None else (low, high)
    return S(step, product, low, high, admitted_low, admitted_high, reason)


class BoundsTests(unittest.TestCase):
    def test_canonical_reference_matches_upstream(self):
        upstream = Path(__file__).resolve().with_name('selected_action_history.py')
        mirror = (upstream.parent.parent / 'cloud-execution-lab' / 'reference' /
                  'titan-history' / 'selected_action_history.py')
        self.assertEqual(upstream.read_bytes(), mirror.read_bytes())

    def test_saturated_known_sale_proves_other_product_zero(self):
        refined, diagnostic = subject.tighten_joint_sales([
            row('MILK', 100, 100, reason='identified'),
            row('WOOL', admitted=(0, 0)),
        ], 100, S)
        self.assertEqual((refined[1].lower, refined[1].upper, refined[1].reason),
                         (0, 0, 'identified'))
        self.assertEqual(diagnostic['changes'][0]['source_reason'], 'floor_censored')
        self.assertEqual(diagnostic['changes'][0]['admitted_after'], [0, 0])
        self.assertIsNone(diagnostic['cash_receipts'])

    def test_partial_capacity_stays_uncertain(self):
        refined, _ = subject.tighten_joint_sales([
            row('MILK', 80, 80, reason='identified'),
            row('WOOL', admitted=(0, 0)),
        ], 100, S)
        self.assertEqual((refined[1].lower, refined[1].upper, refined[1].exact),
                         (0, 20, False))

    def test_multiple_known_products_share_one_capacity(self):
        refined, _ = subject.tighten_joint_sales([
            row('MILK', 60, 60, reason='identified'),
            row('EGG', 40, 40, reason='identified'),
            row('WOOL'),
        ], 100, S)
        self.assertEqual(refined[2].upper, 0)

    def test_admission_range_tightens_without_inventing_cash(self):
        refined, diagnostic = subject.tighten_joint_sales([
            row('MILK', 80, 80, reason='identified'),
            row('WOOL', 5, 100, admitted=(5, 50)),
        ], 100, S)
        self.assertEqual((refined[1].lower, refined[1].upper,
                          refined[1].admitted_lower, refined[1].admitted_upper),
                         (5, 20, 5, 20))
        self.assertFalse(refined[1].exact)
        self.assertIsNone(diagnostic['cash_receipts'])

    def test_quiet_or_missing_product_is_not_invented(self):
        quiet = [row('MILK', 0, 0, reason='identified'),
                 row('WOOL', admitted=(0, 0))]
        refined, diagnostic = subject.tighten_joint_sales(quiet, 100, S)
        self.assertEqual(refined, quiet)
        self.assertIsNone(diagnostic)

        only_milk = [row('MILK', 100, 100, reason='identified')]
        refined, diagnostic = subject.tighten_joint_sales(only_milk, 100, S)
        self.assertEqual(refined, only_milk)
        self.assertIsNone(diagnostic)
        self.assertNotIn('WOOL', [entry.product for entry in refined])

    def test_operating_products_and_inconsistent_rows_are_rejected(self):
        malformed = [
            [row('WHEAT')],
            [row('FERTILIZER')],
            [row('UNSUPPORTED')],
            [row(), row()],
            [row(), row('WOOL', step=647)],
            [row(low=80, high=80), row('WOOL', 30, 30)],
            [row(low=-1)],
            [row(low=2, high=1)],
            [row(low=True)],
            [row(reason='unknown')],
        ]
        for rows in malformed:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                subject.tighten_joint_sales(rows, 100, S)
        for capacity in (0, -1, False, 100.0, None):
            with self.subTest(capacity=capacity), self.assertRaises(ValueError):
                subject.tighten_joint_sales([], capacity, S)

    def test_exhaustive_small_integer_relaxation(self):
        products = ('MILK', 'EGG', 'WOOL')
        checked = feasible = portfolios = 0
        for capacity in range(1, 6):
            bounds = list(itertools.combinations_with_replacement(range(capacity + 1), 2))
            for dimensions in (1, 2, 3):
                for intervals in itertools.product(bounds, repeat=dimensions):
                    rows = [row(product, low, high, admitted=(low, low))
                            for product, (low, high) in zip(products, intervals)]
                    possible = [values for values in itertools.product(*(
                        range(low, high + 1) for low, high in intervals))
                        if sum(values) <= capacity]
                    checked += 1
                    if not possible:
                        with self.assertRaises(ValueError):
                            subject.tighten_joint_sales(rows, capacity, S)
                        continue
                    refined, _ = subject.tighten_joint_sales(rows, capacity, S)
                    after = [values for values in itertools.product(*(
                        range(entry.lower, entry.upper + 1) for entry in refined))
                        if sum(values) <= capacity]
                    self.assertEqual(after, possible)
                    for index, entry in enumerate(refined):
                        self.assertEqual(entry.lower, min(values[index] for values in possible))
                        self.assertEqual(entry.upper, max(values[index] for values in possible))
                    feasible += 1
                    portfolios += len(possible)
        self.assertEqual((checked, feasible, portfolios), (14745, 9109, 56604))


class BridgeIntegrationTests(unittest.TestCase):
    class Mechanics:
        PRODUCTS = PRODUCTS
        SHOPS = {}
        TOWN_CENTER_PRODUCTS = ()

        @staticmethod
        def market_price(_item, _inventory, _params):
            return 1

    class Ledger:
        def observe(self, _observation):
            raise AssertionError('supplied fill result must be consumed without a ledger call')

    @staticmethod
    def inference(_before, _after, _queue, _cfg, **_kwargs):
        products = {}
        for product in PRODUCTS:
            if product in ('WHEAT', 'FERTILIZER'):
                products[product] = {'status': 'identified_interval',
                                     'rival_sale_units_range': [0, 1000],
                                     'rival_market_supply_units_range': [0, 1000],
                                     'floor_nonadmission_possible': True}
            elif product == 'MILK':
                products[product] = {'status': 'identified_interval',
                                     'rival_sale_units_range': [100, 100],
                                     'rival_market_supply_units_range': [100, 100],
                                     'floor_nonadmission_possible': False}
            elif product == 'WOOL':
                products[product] = {'status': 'identified_interval',
                                     'rival_sale_units_range': [0, 100],
                                     'rival_market_supply_units_range': [0, 0],
                                     'floor_nonadmission_possible': True}
            else:
                products[product] = {'status': 'identified_interval',
                                     'rival_sale_units_range': [0, 0],
                                     'rival_market_supply_units_range': [0, 0],
                                     'floor_nonadmission_possible': False}
        return {'status': 'identified_intervals', 'products': products}

    def test_observe_appends_jointly_identified_quantity(self):
        history = FlowHistory(period=24)
        bridge = subject.SelectedActionHistory(
            ledger=self.Ledger(), history=history, interval_type=S,
            infer=self.inference, mechanics=self.Mechanics())
        before = {
            'step': 646,
            'player': 0,
            'market': {'inventory': {product: 100 for product in PRODUCTS}, 'params': None},
            'town': {'unlocked_shops': []},
        }
        action = {'farmer': ['PASS'], 'hands': [], 'market': []}
        binding = {'status': 'recorded', 'step': 646, 'player': 0,
                   'action_sha256': subject._action_hash(action)}
        bridge.bind(before, {'turnsPerDay': 24, 'shedCapacity': 100,
                             'maxMarketOrdersPerTurn': 10}, action, binding)
        after = deepcopy(before)
        after['step'] = 647
        result = bridge.observe(after, fill_result={
            'status': 'reconciled', 'binding': {k: binding[k] for k in (
                'step', 'player', 'action_sha256')}, 'orders': []})
        wool = next(entry for entry in result['intervals'] if entry['product'] == 'WOOL')
        self.assertEqual((wool['lower'], wool['upper'], wool['exact']), (0, 0, True))
        self.assertTrue(history.records['WOOL'][646].exact)
        self.assertEqual(result['joint_sale_bounds']['sum_sale_lower_bounds'], 100)
        self.assertNotIn('WHEAT', history.records)
        self.assertIsNone(result['cash_receipts'])

    def test_impossible_joint_lower_bounds_append_nothing(self):
        def impossible(*args, **kwargs):
            result = self.inference(*args, **kwargs)
            for product in ('MILK', 'EGG'):
                result['products'][product].update(
                    rival_sale_units_range=[60, 60],
                    rival_market_supply_units_range=[60, 60],
                    floor_nonadmission_possible=False)
            return result

        history = FlowHistory(period=24)
        bridge = subject.SelectedActionHistory(
            ledger=self.Ledger(), history=history, interval_type=S,
            infer=impossible, mechanics=self.Mechanics())
        before = {
            'step': 646,
            'player': 0,
            'market': {'inventory': {product: 100 for product in PRODUCTS}, 'params': None},
            'town': {'unlocked_shops': []},
        }
        action = {'farmer': ['PASS'], 'hands': [], 'market': []}
        binding = {'status': 'recorded', 'step': 646, 'player': 0,
                   'action_sha256': subject._action_hash(action)}
        bridge.bind(before, {'turnsPerDay': 24, 'shedCapacity': 100,
                             'maxMarketOrdersPerTurn': 10}, action, binding)
        after = deepcopy(before)
        after['step'] = 647
        result = bridge.observe(after, fill_result={
            'status': 'reconciled', 'binding': {k: binding[k] for k in (
                'step', 'player', 'action_sha256')}, 'orders': []})
        self.assertEqual(result['reason'], 'flow_inputs_unavailable')
        self.assertFalse(history.records)


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromModule(__import__(__name__))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {
        'tests': result.testsRun,
        'failures': len(result.failures),
        'errors': len(result.errors),
        'success': result.wasSuccessful(),
        'scope': 'component and supplied-fill bridge tests; no games or provider actions',
    }
    Path(__file__).with_name('JOINT-SALE-CAPACITY-TEST.json').write_text(
        json.dumps(report, indent=2, sort_keys=True) + '\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
