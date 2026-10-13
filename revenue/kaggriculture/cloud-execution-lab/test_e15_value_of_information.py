# SPDX-License-Identifier: Apache-2.0
import unittest

import mechanics as m
from e15_value_of_information import information_value


def sale_cash(product, inventory, quantity):
    cash = 0
    for _ in range(quantity):
        price = m.market_price(product, inventory, None)
        cash += price
        if price > 1:
            inventory += 1
    return cash


def paired_cash(product, inventory, own_quantity, rival_quantity):
    own = rival = 0
    for k in range(max(own_quantity, rival_quantity)):
        price = m.market_price(product, inventory, None)
        ours = k < own_quantity
        theirs = k < rival_quantity
        if ours:
            own += price
        if theirs:
            rival += price
        if price > 1:
            inventory += int(ours) + int(theirs)
    return own, rival


class E15ValueOfInformationTests(unittest.TestCase):
    def test_same_winner_is_exact_noop_without_probabilities(self):
        rows = {
            'low_supply': {'sell_now': 12, 'sell_later': 9},
            'high_supply': {'sell_now': 8, 'sell_later': 7},
        }
        r = information_value(rows, incumbent_plan='sell_now')
        self.assertTrue(r['decision_invariant'])
        self.assertEqual(r['selection_without_new_information'], 'sell_now')
        self.assertEqual(r['expected_voi_bounds']['lower'], 0.0)
        self.assertFalse(r['positive_cost_probe_allowed'])
        self.assertEqual(r['collection_recommendation'], 'none_decision_invariant')

    def test_crossing_rankings_allow_passive_information_but_block_paid_probe(self):
        rows = {
            'no_rival_supply': {'sell_now': 1120, 'sell_later': 1559},
            'rival_sell_now': {'sell_now': 598, 'sell_later': 74},
        }
        r = information_value(rows, probe_cost=1)
        self.assertFalse(r['decision_invariant'])
        self.assertTrue(r['passive_information_can_change_choice'])
        self.assertIsNone(r['selection_without_new_information'])
        self.assertEqual(r['expected_voi_bounds']['lower'], 0.0)
        self.assertFalse(r['positive_cost_probe_allowed'])
        self.assertEqual(r['positive_cost_probe_reason'], 'uncalibrated_scenario_probabilities')
        self.assertEqual(r['collection_recommendation'], 'passive_only_if_public_observation_resolves_scenario')

    def test_interval_ambiguity_is_not_collapsed_to_fake_point_values(self):
        rows = {
            'same_public_state': {
                'sell_now': [90, 120],
                'sell_later': [100, 130],
            },
            'after_absorption': {
                'sell_now': [80, 110],
                'sell_later': [95, 125],
            },
        }
        r = information_value(rows, probabilities={'same_public_state': .5, 'after_absorption': .5})
        self.assertTrue(r['interval_ambiguity'])
        self.assertEqual(r['status'], 'ambiguous_intervals')
        self.assertFalse(r['positive_cost_probe_allowed'])
        self.assertNotIn('expected_value_of_perfect_information', r)

    def test_interval_endpoints_reject_coercible_non_numeric_values(self):
        invalid = ([False, 1], [0, True], ['1', 2], [1, '2'], (None, 2))
        for interval in invalid:
            with self.subTest(interval=interval):
                rows = {'public': {'hold': interval, 'sell': 0}}
                with self.assertRaises(ValueError):
                    information_value(rows)

    def test_numeric_interval_endpoints_remain_valid(self):
        rows = {'public': {'hold': [1, 2.5], 'sell': (0.5, 1)}}
        r = information_value(rows)
        self.assertTrue(r['interval_ambiguity'])
        self.assertEqual(r['certain_winners']['public'], ['hold'])
        self.assertEqual(r['conditional_value_spread_upper_bound'], 2.0)

    def test_terminal_window_has_zero_actionable_information_value(self):
        rows = {
            'a': {'now': 5, 'later': 1},
            'b': {'now': 1, 'later': 5},
        }
        r = information_value(rows, terminal=True)
        self.assertTrue(r['passive_information_can_change_choice'])
        self.assertEqual(r['expected_voi_bounds']['upper_bound'], 0.0)
        self.assertFalse(r['positive_cost_probe_allowed'])
        self.assertEqual(r['positive_cost_probe_reason'], 'terminal_no_payback_window')

    def test_explicit_probabilities_require_evpi_above_complete_probe_cost(self):
        rows = {
            'no_rival_supply': {'sell_now': 1120, 'sell_later': 1559},
            'rival_sell_now': {'sell_now': 598, 'sell_later': 74},
        }
        p = 439 / (439 + 524)
        probs = {'no_rival_supply': 1 - p, 'rival_sell_now': p}
        r = information_value(rows, probabilities=probs, probe_cost=238)
        self.assertAlmostEqual(r['expected_value_of_perfect_information'], 238.8743509865, places=9)
        self.assertTrue(r['positive_cost_probe_allowed'])
        expensive = information_value(rows, probabilities=probs, probe_cost=239)
        self.assertFalse(expensive['positive_cost_probe_allowed'])

    def test_exact_mechanics_witness_matches_support_receipt(self):
        self.assertEqual(sale_cash('WOOL', 10040, 20), 1120)
        self.assertEqual(sale_cash('WOOL', 10036, 20), 1559)
        own, _ = paired_cash('WOOL', 10040, 20, 20)
        self.assertEqual(own, 598)

    def test_invalid_probabilities_and_plan_sets_fail_closed(self):
        rows = {'a': {'x': 1, 'y': 2}, 'b': {'x': 2, 'y': 1}}
        with self.assertRaises(ValueError):
            information_value(rows, probabilities={'a': .2, 'b': .2})
        with self.assertRaises(ValueError):
            information_value({'a': {'x': 1}, 'b': {'y': 1}})


if __name__ == '__main__':
    unittest.main(verbosity=2)
