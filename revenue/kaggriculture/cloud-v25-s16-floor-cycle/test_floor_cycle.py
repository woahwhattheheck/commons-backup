# SPDX-License-Identifier: Apache-2.0
import unittest
from floor_cycle import (CycleState, admit_floor_cycle, exact_floor_cycle,
                         future_scenario_deltas, market_price_fertilizer)


class FloorCycleTests(unittest.TestCase):
    def test_exact_floor_boundary(self):
        self.assertEqual(market_price_fertilizer(10493), 1)
        self.assertEqual(market_price_fertilizer(10492), 2)

    def test_deep_floor_cycle_is_cash_stock_neutral_and_depletes_public_supply(self):
        before = CycleState(50, 7, 10500)
        after = exact_floor_cycle(before, shed_room=3)
        self.assertEqual((after.cash, after.stock), (before.cash, before.stock))
        self.assertEqual(after.public_inventory, before.public_inventory - 1)

    def test_boundary_cycle_is_neutral_at_10494(self):
        before = CycleState(50, 7, 10494)
        after = exact_floor_cycle(before, shed_room=3)
        self.assertEqual(after, CycleState(50, 7, 10493))

    def test_nonfloor_postbuy_is_not_a_free_cycle(self):
        before = CycleState(50, 7, 10493)
        self.assertIsNone(exact_floor_cycle(before, shed_room=3))

    def test_physical_cash_gate(self):
        self.assertIsNone(exact_floor_cycle(CycleState(0, 1, 10500), shed_room=3))
        self.assertEqual(admit_floor_cycle(cash=0, shed_room=2, free_market_slots=2,
                         downstream_steps=1, scenario_deltas={'none': 1}),
                         {'admitted': False, 'reason': 'insufficient_cash', 'orders': (),
                          'immediate_profit_credit': 0})

    def test_physical_room_gate(self):
        self.assertIsNone(exact_floor_cycle(CycleState(50, 1, 10500), shed_room=0))
        self.assertEqual(admit_floor_cycle(cash=10, shed_room=0, free_market_slots=2,
                         downstream_steps=1, scenario_deltas={'none': 1})['reason'], 'no_shed_room')

    def test_two_slot_gate(self):
        self.assertEqual(admit_floor_cycle(cash=10, shed_room=1, free_market_slots=1,
                         downstream_steps=1, scenario_deltas={'none': 1})['reason'],
                         'need_two_market_slots')

    def test_terminal_no_value_gate(self):
        self.assertEqual(admit_floor_cycle(cash=10, shed_room=1, free_market_slots=2,
                         downstream_steps=0, scenario_deltas={'none': 1})['reason'],
                         'no_downstream_opportunity')

    def test_no_rival_boundary_has_local_future_receipt_gain(self):
        d = future_scenario_deltas(10494, absorption_units=1)
        self.assertEqual(d['none'], 1)

    def test_paired_rival_sell_zeroes_relative_gain(self):
        d = future_scenario_deltas(10494, absorption_units=1)
        self.assertEqual(d['sell'], 0)

    def test_mandated_scenario_family_rejects_boundary_case(self):
        d = future_scenario_deltas(10494, absorption_units=1)
        out = admit_floor_cycle(cash=10, shed_room=1, free_market_slots=2,
                                downstream_steps=1, scenario_deltas=d)
        self.assertFalse(out['admitted'])
        self.assertEqual(out['reason'], 'nonpositive_worst_case')
        self.assertEqual(out['immediate_profit_credit'], 0)

    def test_strict_positive_synthetic_control_admits(self):
        out = admit_floor_cycle(cash=10, shed_room=1, free_market_slots=2,
                                downstream_steps=1,
                                scenario_deltas={'a': .25, 'b': 1, 'c': 2})
        self.assertTrue(out['admitted'])
        self.assertEqual(out['immediate_profit_credit'], 0)

    def test_exhaustive_floor_region_never_strictly_positive_with_paired_sell(self):
        checked = 0
        local_positive = 0
        for inventory in range(10494, 11001):
            for absorption in range(0, 17):
                d = future_scenario_deltas(inventory, absorption_units=absorption)
                checked += 1
                local_positive += d['none'] > 0
                self.assertLessEqual(min(d.values()), 0, (inventory, absorption, d))
                self.assertFalse(admit_floor_cycle(cash=10, shed_room=1,
                    free_market_slots=2, downstream_steps=1,
                    scenario_deltas=d)['admitted'])
        self.assertEqual(checked, 8619)
        self.assertGreater(local_positive, 0)


if __name__ == '__main__':
    unittest.main()
