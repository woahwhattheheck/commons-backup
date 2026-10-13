# SPDX-License-Identifier: Apache-2.0
"""Current realized-sale funding for the existing joint frozen SELL path."""
import unittest
from copy import deepcopy

from frozen_selected import joint_resource_bound, sale_quantities
from scheduler import m, post_units
from test_joint_market_slots import consumer, fixture


class JointCurrentSaleFunding(unittest.TestCase):
    def setUp(self):
        self.obs, self.route, self.base = fixture(shed={'MILK': 1})
        self.obs['farms'][0].update(money=0, hires_today=9)
        self.route[109]['market'] = [['HIRE']]
        self.base['market'] = [['SELL', 'MILK', 1]]

    def bound(self, *, current_market=None, rival_quantity=None, config=None):
        cfg = dict(config or {})
        farm, private = post_units(self.obs, self.base, cfg)
        return joint_resource_bound(
            self.obs, cfg, self.base, farm, private, self.route, 108,
            current_market=self.base['market'] if current_market is None else current_market,
            rival_quantity=rival_quantity,
        )

    def test_current_sale_prepays_boundary_hire_without_mutating_observation(self):
        before = deepcopy((self.obs, self.route, self.base))
        bound = self.bound()
        self.assertIsNotNone(bound)
        self.assertEqual(bound['fixed_cost'], m._hire_cost(9, 1))
        self.assertEqual(bound['capital_end'], 109)
        self.assertEqual((self.obs, self.route, self.base), before)

    def test_same_cash_without_current_sale_cannot_fund_hire(self):
        self.assertIsNone(self.bound(current_market=[]))

    def test_future_sale_before_future_hire_is_never_current_cash(self):
        self.base['market'] = []
        self.route[102]['market'] = [['SELL', 'MILK', 1]]
        self.assertIsNone(self.bound())

    def test_later_current_sale_cannot_rescue_unfunded_earlier_purchase(self):
        self.obs['private']['shed']['MILK'] = 3
        self.base['market'] = [['BUY_ANIMAL', 'COW', 1], ['SELL', 'MILK', 3]]
        self.assertIsNone(self.bound())
        self.base['market'].reverse()
        self.assertIsNotNone(self.bound())

    def test_partially_funded_current_purchase_cannot_be_treated_as_complete(self):
        self.obs['private']['shed']['MILK'] = 3
        self.base['market'] = [['SELL', 'MILK', 3], ['BUY_ANIMAL', 'COW', 2]]
        self.assertIsNone(self.bound())

    def test_current_spend_must_leave_enough_cash_for_every_future_hire(self):
        self.base['market'] = [['SELL', 'MILK', 1], ['HIRE']]
        self.route[109]['market'] = [['HIRE'], ['HIRE']]
        self.assertIsNone(self.bound())
        self.route[109]['market'] = [['HIRE']]
        self.assertIsNotNone(self.bound())

    def test_duplicate_sales_share_one_physical_stock_budget(self):
        self.base['market'] = [['SELL', 'MILK', 1], ['SELL', 'MILK', 1]]
        self.route[109]['market'] = [['HIRE'], ['HIRE'], ['HIRE']]
        farm, private = deepcopy(self.obs['farms'][0]), deepcopy(self.obs['private'])
        market = deepcopy(self.obs['market'])
        price = m.market_price('MILK', market['inventory']['MILK'])
        self.assertTrue(m._commit_unit('SELL', 'MILK', price, farm, private, market))
        self.assertFalse(m._commit_unit('SELL', 'MILK', price, farm, private, market))
        self.assertLess(farm['money'], sum(m._hire_cost(n, 1) for n in (9, 10, 11)))
        self.assertIsNone(self.bound())
        self.obs['private']['shed']['MILK'] = 2
        self.assertIsNotNone(self.bound())

    def test_observed_rival_stress_can_remove_current_sale_funding(self):
        self.assertGreater(m.market_price('MILK', 10000), m._hire_cost(9, 1))
        self.assertLess(m.market_price('MILK', 10100), m._hire_cost(9, 1))
        self.assertIsNotNone(self.bound(rival_quantity={'MILK': 0}))
        self.assertIsNone(self.bound(rival_quantity={'MILK': 100}))
        self.assertIsNone(self.bound(rival_quantity=lambda item: 100 if item == 'MILK' else 0))

    def test_sale_outside_executable_prefix_never_funds_a_purchase(self):
        self.base['market'] = [[], ['SELL', 'MILK', 1]]
        self.assertIsNone(self.bound(config={'maxMarketOrdersPerTurn': 1}))
        self.base['market'] = [['SELL', 'MILK', 1]]
        self.assertIsNotNone(self.bound(config={'maxMarketOrdersPerTurn': 1}))

    def test_current_cash_credit_does_not_release_physical_capacity(self):
        self.route[104]['farmer'] = ['PLACE', 'WOOL', 100]
        self.assertIsNone(self.bound())

    def test_current_sale_does_not_admit_variable_price_future_spend(self):
        self.route[104]['market'] = [['BUY_PRODUCT', 'FERTILIZER', 1]]
        self.assertIsNone(self.bound())

    def test_cash_rich_legacy_bound_is_unchanged(self):
        self.obs['farms'][0]['money'] = m._hire_cost(9, 1)
        farm, private = post_units(self.obs, self.base, {})
        legacy = joint_resource_bound(self.obs, {}, self.base, farm, private, self.route, 108)
        self.assertEqual(legacy, {
            'fixed_cost': 55, 'capital_end': 109, 'stock_upper': {'MILK': 1},
            'stock_total_upper': 1, 'capacity': 100,
        })
        self.assertEqual(self.bound(), legacy)


class JointSaleFundingSelection(unittest.TestCase):
    def test_real_optimizer_combines_two_lots_using_retained_current_sale(self):
        obs, route, base = fixture(now=241, shed={'MILK': 8, 'WOOL': 8, 'FERTILIZER': 1})
        obs['farms'][0].update(money=0, hires_today=9)
        obs['town']['unlocked_shops'] = ['SMOOTHIE_SHOP'] * 4 + ['YARN_STORE'] * 4
        base['market'] = [['SELL', 'FERTILIZER', 1], ['SELL', 'MILK', 8], ['SELL', 'WOOL', 8]]
        route[249]['market'] = [['HIRE']]
        before = deepcopy((obs, route, base))

        bot = consumer(route)
        out = bot.transform(obs, {}, base)

        self.assertEqual(set(bot.diagnostics['chosen']['items']), {'MILK', 'WOOL'})
        self.assertGreater(bot.diagnostics['chosen']['worst_relative_gain'], 0)
        self.assertEqual(sale_quantities(out['market']), {'FERTILIZER': 1})
        self.assertEqual((out['farmer'], out['hands']), (base['farmer'], base['hands']))
        self.assertEqual(len(out['market']), len(base['market']))
        self.assertEqual((obs, route, base), before)


if __name__ == '__main__':
    unittest.main()
