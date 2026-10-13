# SPDX-License-Identifier: Apache-2.0
"""Cooperative completion checks; injected clocks never sleep or run games."""
from __future__ import annotations

import copy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import dated_flow as flow


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class ConsumingProducts(list):
    """A delayed demand iterator exercises the final non-quote phase."""
    def __init__(self, products, clock):
        super().__init__(products)
        self.clock = clock

    def __iter__(self):
        yield from super().__iter__()
        self.clock.now = 2.0


def mechanics(price=None):
    return SimpleNamespace(
        PRODUCTS=('WOOL', 'WHEAT'),
        SHOPS={'YARN_STORE': ('WOOL',)},
        TOWN_CENTER_PRODUCTS=('WHEAT',),
        _resolve_market_params=lambda config: {},
        market_price=price or (lambda product, inventory, params: 189),
    )


def observation(step=718):
    return {'step': step, 'player': 0, 'farms': [{'money': 1000}, {'money': 1000}],
            'market': {'inventory': {'WOOL': 10000, 'WHEAT': 10000}},
            'town': {'unlocked_shops': []}}


def offer(name='alternative', step=718, quantity=1):
    return SimpleNamespace(route_id=name, orders=(
        {'step': step, 'slot': 0, 'order': ['SELL', 'WOOL', quantity], 'delta': 0},))


class CompletionDeadlineTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.timer = patch.object(flow, 'time', SimpleNamespace(perf_counter=self.clock))
        self.timer.start()
        self.addCleanup(self.timer.stop)
        self.cfg = {'episodeSteps': 720}
        self.obs = observation()
        self.scenario = flow.Scenario('current')

    def delayed_price(self, at=2.0):
        def price(product, inventory, params):
            self.clock.now = at
            return 189
        return price

    def test_last_price_callback_cannot_complete_late_route(self):
        with self.assertRaises(flow.BudgetExceeded):
            flow.value_route(offer(), self.obs, self.cfg, mechanics(self.delayed_price()),
                             self.scenario, seconds=1)

    def test_exact_deadline_is_incomplete(self):
        result = flow.evaluate_scenarios([offer()], self.obs, self.cfg,
            mechanics(self.delayed_price(1.0)), [self.scenario], seconds=1)
        self.assertFalse(result['complete'])
        self.assertEqual(result['reason'], 'incomplete_budget')
        self.assertEqual(result['rows'], [])

    def test_last_alternative_discards_entire_vector(self):
        baseline = SimpleNamespace(route_id='incumbent', orders=())
        result = flow.evaluate_scenarios([baseline, offer()], self.obs, self.cfg,
            mechanics(self.delayed_price()), [self.scenario], seconds=1)
        self.assertEqual(result, {'complete': False, 'reason': 'incomplete_budget', 'rows': []})
        with self.assertRaises(ValueError):
            flow.as_cash_scenarios(result, SimpleNamespace)

    def test_last_scenario_discards_preceding_successes(self):
        calls = []
        def price(*args):
            calls.append(args)
            if len(calls) == 2:
                self.clock.now = 2.0
            return 189
        result = flow.evaluate_scenarios([offer()], self.obs, self.cfg, mechanics(price),
            [self.scenario, flow.Scenario('second')], seconds=1)
        self.assertEqual(len(calls), 2)
        self.assertFalse(result['complete'])
        self.assertEqual(result['rows'], [])

    def test_vector_checks_final_return_after_actual_route(self):
        original = flow.value_route
        def late_return(*args, **kwargs):
            result = original(*args, **kwargs)
            self.clock.now = 2.0
            return result
        with patch.object(flow, 'value_route', side_effect=late_return):
            result = flow.evaluate_scenarios([offer()], self.obs, self.cfg,
                mechanics(), [self.scenario], seconds=1)
        self.assertFalse(result['complete'])
        self.assertEqual(result['rows'], [])

    def test_final_shop_consumption_is_inside_deadline(self):
        m = mechanics()
        m.SHOPS['YARN_STORE'] = ConsumingProducts(['WOOL'], self.clock)
        obs = observation(4)
        obs['town']['unlocked_shops'] = ['YARN_STORE']
        with self.assertRaises(flow.BudgetExceeded):
            flow.value_route(SimpleNamespace(route_id='empty', orders=()), obs,
                {'episodeSteps': 6}, m, self.scenario, seconds=1)

    def test_final_town_center_consumption_is_inside_deadline(self):
        m = mechanics()
        m.TOWN_CENTER_PRODUCTS = ConsumingProducts(['WHEAT'], self.clock)
        with self.assertRaises(flow.BudgetExceeded):
            flow.value_route(SimpleNamespace(route_id='empty', orders=()), observation(24),
                {'episodeSteps': 26}, m, self.scenario, seconds=1)

    def test_receipt_construction_is_inside_deadline(self):
        clock = self.clock
        class DelayedIdentity:
            orders = ()
            @property
            def route_id(self):
                clock.now = 2.0
                return 'late_metadata'
        with self.assertRaises(flow.BudgetExceeded):
            flow.value_route(DelayedIdentity(), self.obs, self.cfg, mechanics(),
                             self.scenario, seconds=1)

    def test_on_time_output_and_all_input_values_unchanged(self):
        incumbent = SimpleNamespace(route_id='incumbent', orders=())
        alternative = offer()
        before = copy.deepcopy((self.obs, self.cfg, incumbent, alternative))
        result = flow.evaluate_scenarios([incumbent, alternative], self.obs, self.cfg,
            mechanics(self.delayed_price(.9)), [self.scenario], seconds=1, retain_trace=True)
        self.assertTrue(result['complete'])
        self.assertEqual(result['unit_rounds'], 1)
        self.assertEqual(result['rows'][0][1]['final_marked_cash'], 1189)
        cash = flow.as_cash_scenarios(result, SimpleNamespace)
        self.assertEqual(cash[0].flows['alternative'][(718, 0)], 189)
        self.assertEqual((self.obs, self.cfg, incumbent, alternative), before)

    def test_unlimited_wall_time_preserves_explicit_configuration(self):
        result = flow.evaluate_scenarios([offer()], self.obs, self.cfg,
            mechanics(self.delayed_price()), [self.scenario], seconds=None)
        self.assertTrue(result['complete'])
        self.assertEqual(result['rows'][0][0]['final_marked_cash'], 1189)

    def test_exact_unit_budget_still_completes(self):
        result = flow.evaluate_scenarios([offer(quantity=2)], self.obs, self.cfg,
            mechanics(), [self.scenario], seconds=1, max_units=2)
        self.assertTrue(result['complete'])
        self.assertEqual(result['unit_rounds'], 2)

    def test_unit_limit_not_disabled_by_unlimited_time(self):
        result = flow.evaluate_scenarios([offer(quantity=2)], self.obs, self.cfg,
            mechanics(), [self.scenario], seconds=None, max_units=1)
        self.assertFalse(result['complete'])
        self.assertEqual(result['rows'], [])

    def test_zero_wall_time_does_not_call_mechanics(self):
        def never(*args):
            self.fail('mechanics should not be called')
        result = flow.evaluate_scenarios([offer()], self.obs, self.cfg,
            mechanics(never), [self.scenario], seconds=0)
        self.assertFalse(result['complete'])

    def test_cancellation_propagates(self):
        def cancel(*args):
            raise KeyboardInterrupt('cancelled')
        with self.assertRaises(KeyboardInterrupt):
            flow.evaluate_scenarios([offer()], self.obs, self.cfg,
                mechanics(cancel), [self.scenario], seconds=1)

    def test_dependency_timeout_is_not_misreported_as_success(self):
        def cancel(*args):
            raise TimeoutError('price callback timed out')
        with self.assertRaisesRegex(TimeoutError, 'price callback'):
            flow.evaluate_scenarios([offer()], self.obs, self.cfg,
                mechanics(cancel), [self.scenario], seconds=1)

    def test_invalid_flow_stays_distinct_from_budget(self):
        result = flow.evaluate_scenarios([offer(quantity=-1)], self.obs, self.cfg,
            mechanics(), [self.scenario], seconds=1)
        self.assertEqual(result['reason'], 'invalid_flow')


if __name__ == '__main__':
    unittest.main(verbosity=2)
