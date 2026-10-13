# SPDX-License-Identifier: Apache-2.0
import unittest

from fourth_quadrant import FourthQuadrant, calendar


OBS = {
    'step': 264,
    'player': 0,
    'farms': [{'hands': []}],
}


def proposal():
    return {
        'start': 264,
        'crop': 'CARROT',
        'tiles': [(5, 5), (6, 5), (5, 6)],
        'workers': 1,
        'cost': 4123,
    }


def row(market):
    return {'farmer': ['PASS'], 'hands': [], 'market': market}


class FourthQuadrantCommitGateTests(unittest.TestCase):
    def finish(self, selected_market, returned_market, configuration=None):
        gate = FourthQuadrant(None, None)
        gate.configure(configuration or {})
        pending = proposal()
        gate.pending = pending
        gate.selected = row(selected_market)
        gate.finish(OBS, row(returned_market))
        return gate, pending

    def test_exact_current_purchase_commitment_can_publish_plan(self):
        market = [['BUY_LAND'], ['BUY_SEED', 'CARROT', 6], ['HIRE']]
        gate, pending = self.finish(market, market)
        self.assertIs(gate.plan, pending)
        self.assertEqual(gate.generation, 1)
        self.assertEqual(gate.events[-1]['kind'], 'bundle_admitted')

    def test_dropped_current_land_purchase_rejects_plan(self):
        selected = [['BUY_LAND'], ['BUY_SEED', 'CARROT', 6], ['HIRE']]
        returned = [['BUY_SEED', 'CARROT', 6], ['HIRE']]
        gate, _ = self.finish(selected, returned)
        self.assertIsNone(gate.plan)
        self.assertEqual(gate.generation, 0)
        self.assertIsNone(gate.pending)
        self.assertIsNone(gate.selected)

    def test_reduced_current_seed_quantity_rejects_plan(self):
        selected = [['BUY_LAND'], ['BUY_SEED', 'CARROT', 6], ['HIRE']]
        returned = [['BUY_LAND'], ['BUY_SEED', 'CARROT', 5], ['HIRE']]
        gate, _ = self.finish(selected, returned)
        self.assertIsNone(gate.plan)
        self.assertEqual(gate.generation, 0)

    def test_split_seed_orders_preserve_equivalent_quantity(self):
        selected = [['BUY_LAND'], ['BUY_SEED', 'CARROT', 6], ['HIRE']]
        returned = [
            ['BUY_LAND'],
            ['BUY_SEED', 'CARROT', 2],
            ['BUY_SEED', 'CARROT', 4],
            ['HIRE'],
        ]
        gate, pending = self.finish(selected, returned)
        self.assertIs(gate.plan, pending)

    def test_future_dated_purchases_are_not_required_at_admission_step(self):
        # A proposal can schedule its first land/seed purchase later in the day.
        # When the producer selected no current purchase, finish must preserve
        # the incumbent admission semantics instead of requiring future orders.
        selected = [['HIRE']]
        gate, pending = self.finish(selected, selected)
        self.assertIs(gate.plan, pending)

    def test_unreachable_tail_purchases_are_not_current_commitments(self):
        selected = [['HIRE'], ['BUY_LAND'], ['BUY_SEED', 'CARROT', 6]]
        returned = [['HIRE']]
        gate, pending = self.finish(
            selected, returned, {'maxMarketOrdersPerTurn': 1})
        self.assertIs(gate.plan, pending)

    def test_hire_identity_uses_only_engine_prefix_and_accepts_trailing_fields(self):
        selected = [['HIRE', 'selected-tag'], ['HIRE']]
        returned = [['HIRE', 'returned-tag']]
        gate, pending = self.finish(
            selected, returned, {'maxMarketOrdersPerTurn': 1})
        self.assertIs(gate.plan, pending)

    def test_seed_commitment_matches_engine_int_coercion_and_inert_rows(self):
        selected = [
            ['BUY_SEED', 'CARROT', 2.9, 'float-tag'],
            ['BUY_SEED', 'CARROT', '2', 'string-tag'],
            ['BUY_SEED', 'CARROT', True],
            ['BUY_SEED', 'POTATO', 9],
            ['BUY_SEED', 'CARROT', 0],
            {'type': 'BUY_SEED'},
        ]
        returned = [['BUY_SEED', 'CARROT', 5]]
        gate, pending = self.finish(selected, returned)
        self.assertIs(gate.plan, pending)

    def test_buy_land_opcode_accepts_trailing_fields_and_nonlist_rows_are_inert(self):
        selected = [42, ['BUY_LAND', 'ignored-by-engine']]
        returned = [['BUY_LAND']]
        gate, pending = self.finish(selected, returned)
        self.assertIs(gate.plan, pending)

    def test_nonlist_market_executes_no_commitment(self):
        gate = FourthQuadrant(None, None)
        gate.configure({})
        pending = proposal()
        gate.pending = pending
        gate.selected = row((['BUY_LAND'],))
        gate.finish(OBS, row([]))
        self.assertIs(gate.plan, pending)

    def test_calendar_ignores_tail_hire_beyond_engine_prefix(self):
        route = [row([]) for _ in range(720)]
        route[264] = row([[], ['HIRE']])
        days = calendar(route, 11, {'maxMarketOrdersPerTurn': 1})
        self.assertEqual(days[11]['step'], 264)
        self.assertEqual(days[11]['hands'], 0)

    def test_calendar_uses_engine_floor_and_trailing_hire_opcode(self):
        route = [row([]) for _ in range(720)]
        route[264] = row([['HIRE', 'metadata'], ['HIRE']])
        days = calendar(route, 11, {'maxMarketOrdersPerTurn': 0})
        self.assertEqual(days[11]['step'], 265)
        self.assertEqual(days[11]['hands'], 1)


if __name__ == '__main__':
    unittest.main()
