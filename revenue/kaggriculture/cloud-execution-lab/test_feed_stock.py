# SPDX-License-Identifier: Apache-2.0
"""Final stock/position contracts; no policy trajectory or game is executed."""
from copy import deepcopy
from types import SimpleNamespace
import unittest

import mechanics as m
from operating_stock import protect_feed_stock, protect_operating_stock, _current_room_bound
from titan_runtime import Features, TitanAgent


class FeedStockTests(unittest.TestCase):
    def setUp(self):
        self.farm = {'farmer': [0, 0], 'hands': [[4, 4]], 'money': 50000,
                     'hires_today': 1, 'unlocked_quadrants': ['NW'],
                     'tiles': [[None for _ in range(10)] for _ in range(10)]}
        self.farm['tiles'][4][3] = m._new_animal('COW', 1)
        self.farm['tiles'][4][2] = m._new_animal('SHEEP', 1)
        self.private = {'shed': {'WHEAT': 9}, 'inventories': [{}, {}], 'seeds': {}}
        self.obs = {'step': 460, 'day': 19, 'player': 0,
                    'market': {'inventory': {'WHEAT': 9800, 'FERTILIZER': 10000}},
                    'farms': [self.farm, {}], 'private': self.private}
        self.selected = {'farmer': ['PASS'], 'hands': [['PASS']],
                         'market': [['SELL', 'WHEAT', 9]]}
        self.route = [{'farmer': ['PASS'], 'hands': [['PASS']], 'market': []}
                      for _ in range(720)]
        for step, action in [(461, ['PICKUP', 'WHEAT', 3]), (462, ['WEST']),
                             (463, ['FEED']), (464, ['WEST']), (465, ['FEED'])]:
            self.route[step]['hands'][0] = action

    def propose(self, checkpoints=()):
        return protect_feed_stock(m, self.obs, {}, self.selected, self.farm,
                                  self.private, self.route, checkpoints)

    def unchanged(self, reason):
        result, report = self.propose()
        self.assertIs(result, self.selected)
        self.assertFalse(report['certified'])
        self.assertEqual(report['reason'], reason)

    def test_protect_useful_consumption_and_leave_oversized_pickup_surplus(self):
        before = deepcopy((self.obs, self.selected, self.route))
        result, report = self.propose()
        self.assertEqual(result['market'], [['SELL', 'WHEAT', 7]])
        self.assertEqual(report['required_wheat'], 2)
        self.assertEqual(report['withheld_units'], 2)
        self.assertTrue(report['certified'])
        self.assertEqual((self.obs, self.selected, self.route), before)

    def test_malformed_current_market_row_fails_closed_before_feed_scan(self):
        self.selected['market'] = [17, ['SELL', 'WHEAT', 9]]
        self.unchanged('malformed_market_row')

    def test_operating_stock_market_shape_fails_closed_current_and_future(self):
        farm = {'farmer': [4, 4], 'hands': [[4, 4]], 'money': 50000,
                'tiles': [[None for _ in range(10)] for _ in range(10)]}
        private = {'inventories': [{}, {}], 'shed': {'FERTILIZER': 9}, 'seeds': {}}
        observation = {'step': 460, 'player': 0, 'day': 19,
                       'market': {'inventory': {'FERTILIZER': 10300}}}
        selected = {'farmer': ['PASS'], 'hands': [['PASS']],
                    'market': [17, ['SELL', 'FERTILIZER', 9]]}
        route = [{'farmer': ['PASS'], 'hands': [['PASS']], 'market': []}
                 for _ in range(720)]
        result, report = protect_operating_stock(
            m, observation, {}, selected, farm, private, route, ())
        self.assertIs(result, selected)
        self.assertFalse(report['changed'])
        self.assertEqual(report['reason'], 'malformed_market_row')

        selected = {'farmer': ['PASS'], 'hands': [['PASS']],
                    'market': [['SELL', 'FERTILIZER', 9]]}
        route[461]['market'] = [17]
        result, report = protect_operating_stock(
            m, observation, {}, selected, farm, private, route, ())
        self.assertIs(result, selected)
        self.assertFalse(report['changed'])
        self.assertEqual(report['reason'], 'malformed_market_row')

    def test_runtime_stock_wrappers_fail_closed_before_helper_dispatch(self):
        cases = (
            (17, 'malformed_market'),
            ([17, ['SELL', 'FERTILIZER', 1]], 'malformed_market_row'),
        )
        for market, reason in cases:
            with self.subTest(wrapper='operating', market=market):
                selected = {'farmer': ['PASS'], 'hands': [['PASS']], 'market': market}
                agent = self.agent()
                result = agent._operating_stock_selected(self.obs, {}, selected)
                self.assertIs(result, selected)
                self.assertEqual(agent.diagnostics['operating_stock']['reason'], reason)

        cases = (
            (17, 'malformed_market'),
            ([17, ['SELL', 'WHEAT', 1]], 'malformed_market_row'),
        )
        for market, reason in cases:
            with self.subTest(wrapper='feed', market=market):
                selected = {'farmer': ['PASS'], 'hands': [['PASS']], 'market': market}
                agent = self.agent()
                result = agent._feed_stock_selected(self.obs, {}, selected)
                self.assertIs(result, selected)
                self.assertEqual(agent.diagnostics['feed_stock']['reason'], reason)

    def test_carried_wheat_covers_existing_feeds(self):
        self.private['inventories'][1]['WHEAT'] = 2
        result, report = self.propose()
        self.assertIs(result, self.selected)
        self.assertEqual(report['required_wheat'], 0)

    def test_empty_assets_and_already_fed_assets_are_not_reserved(self):
        self.farm['tiles'][4][3] = {'kind': 'PASTURE'}
        self.farm['tiles'][4][2]['fed_today'] = True
        result, report = self.propose()
        self.assertIs(result, self.selected)
        self.assertEqual(report['required_wheat'], 0)

    def test_unused_earlier_pickup_cannot_return_retained_wheat_at_eod(self):
        self.farm['farmer'] = [4, 4]
        self.route[461]['farmer'] = ['PICKUP', 'WHEAT', 5]
        self.private['shed']['WHEAT'] = 10
        self.selected['market'] = [['SELL', 'WHEAT', 5]]
        self.unchanged('competing_pickup_has_uncertified_wheat_return')

    def test_competing_pickup_with_useful_full_consumption_is_preserved(self):
        self.farm['farmer'] = [4, 4]
        self.farm['tiles'][5][4] = m._new_animal('COW', 1)
        self.route[461]['farmer'] = ['PICKUP', 'WHEAT', 1]
        self.route[462]['farmer'] = ['SOUTH']
        self.route[463]['farmer'] = ['FEED']
        self.selected['market'] = [['SELL', 'WHEAT', 8]]
        result, report = self.propose()
        self.assertEqual(report['required_wheat'], 3)
        self.assertEqual(result['market'], [['SELL', 'WHEAT', 6]])

    def test_later_competing_return_cannot_cause_another_drop_to_overflow(self):
        self.farm['farmer'] = [4, 4]
        self.private['shed'] = {'WHEAT': 3, 'MELON': 96}
        self.selected['market'] = [['SELL', 'WHEAT', 2]]
        self.route[461]['farmer'] = ['PICKUP', 'WHEAT', 2]
        self.route[461]['hands'][0] = ['PICKUP', 'WHEAT', 1]
        self.route[465]['hands'][0] = ['PASS']
        self.route[466]['farmer'] = ['DROP']
        self.route[467]['farmer'] = ['DROP']
        self.unchanged('competing_pickup_has_uncertified_wheat_return')

    def test_intervening_wheat_sale_is_not_assumed_to_preserve_input(self):
        self.route[461]['hands'][0] = ['PASS']
        self.route[461]['market'] = [['SELL', 'WHEAT', 1]]
        self.route[462]['hands'][0] = ['PICKUP', 'WHEAT', 3]
        self.route[463]['hands'][0] = ['WEST']
        self.route[464]['hands'][0] = ['FEED']
        self.route[465]['hands'][0] = ['WEST']
        self.route[466]['hands'][0] = ['FEED']
        self.unchanged('intervening_wheat_sale_before_protected_pickup')

    def test_duplicate_lots_share_one_budget_and_zero_slots_stay(self):
        self.private['shed'] = {'WHEAT': 2, 'WOOL': 1}
        self.selected['market'] = [['SELL', 'WHEAT', 1], [], ['SELL', 'WOOL', 1],
                                   ['SELL', 'WHEAT', 1]]
        result, report = self.propose()
        self.assertTrue(report['changed'])
        self.assertEqual(result['market'], [[], [], ['SELL', 'WOOL', 1], []])
        self.assertEqual(result['farmer'], self.selected['farmer'])
        self.assertEqual(result['hands'], self.selected['hands'])

    def test_current_purchase_does_not_prove_wheat_receipt(self):
        self.selected['market'].append(['BUY_PRODUCT', 'WHEAT', 2])
        self.unchanged('unresolved_wheat_replenishment')

    def test_future_requested_replenishment_is_not_stock(self):
        self.route[461]['market'] = [['BUY_PRODUCT', 'WHEAT', 2]]
        self.unchanged('unresolved_wheat_replenishment')

    def test_uncovered_second_feed_is_not_silently_omitted(self):
        self.route[461]['hands'][0] = ['PICKUP', 'WHEAT', 1]
        self.unchanged('scheduled_feed_has_uncovered_carried_input')

    def test_returned_input_cannot_remain_fictitiously_carried(self):
        self.private['inventories'][1]['WHEAT'] = 2
        self.route[461]['hands'][0] = ['DROP']
        self.unchanged('feed_after_uncertified_input_transfer')

    def test_future_drop_cannot_overflow_another_producers_goods(self):
        self.private['shed'] = {'WHEAT': 9, 'MILK': 90}
        self.route[461]['farmer'] = ['DROP']
        self.unchanged('uncertified_deposit_before_protected_pickup')

    def test_future_physical_buy_keeps_its_room_without_sale_credit(self):
        self.private['shed'] = {'WHEAT': 9, 'MILK': 90}
        self.route[461]['market'] = [['BUY_PRODUCT', 'FERTILIZER', 9]]
        self.route[461]['hands'][0] = ['PASS']
        self.route[462]['hands'][0] = ['PICKUP', 'WHEAT', 3]
        self.route[463]['hands'][0] = ['WEST']
        self.route[464]['hands'][0] = ['FEED']
        self.route[465]['hands'][0] = ['WEST']
        self.route[466]['hands'][0] = ['FEED']
        self.unchanged('withholding_conflicts_with_future_arrival_room')

    def test_boundary_capital_uses_actual_saved_cash(self):
        self.farm['hires_today'] = 9
        self.farm['money'] = m._hire_cost(9) - 1
        self.route[479]['market'] = [['HIRE']]
        self.unchanged('feed_window_not_prepaid')

    def test_unresolved_checkpoint_declines(self):
        result, report = self.propose(checkpoints=(464,))
        self.assertIs(result, self.selected)
        self.assertEqual(report['reason'], 'unresolved_feed_window')

    def eod(self):
        self.obs['step'] = 479
        for step, action in [(480, ['PICKUP', 'WHEAT', 2]), (481, ['WEST']),
                             (482, ['FEED']), (483, ['WEST']), (484, ['FEED'])]:
            self.route[step]['farmer'] = action
        self.private['shed'] = {'WHEAT': 2, 'MILK': 94}
        self.private['inventories'][1] = {'FERTILIZER': 4}
        self.selected['market'] = [['SELL', 'WHEAT', 2]]

    def test_eod_resets_worker_identity_and_fits_all_carried_goods(self):
        self.eod()
        result, report = self.propose()
        self.assertEqual(result['market'], [[]])
        self.assertEqual(report['room']['after_delivery_upper'], 100)
        self.assertEqual(report['window']['obligations'][0]['actor'], 0)

    def test_eod_extra_animal_arrival_cannot_use_discarded_carry_as_room(self):
        self.eod()
        self.selected['market'].append(['BUY_ANIMAL', 'SHEEP', 1])
        self.unchanged('withholding_conflicts_with_reset_delivery')

    def test_eod_returned_wheat_can_cover_next_day_only_when_everything_fits(self):
        self.eod()
        self.private['inventories'][1] = {'WHEAT': 4}
        result, report = self.propose()
        self.assertIs(result, self.selected)
        self.assertEqual(report['eod_wheat_credit'], 4)

    def test_invalid_animal_sale_does_not_make_room(self):
        private = {'shed': {'COW': 1, 'WHEAT': 99}, 'inventories': [{'WOOL': 1}]}
        with self.assertRaisesRegex(ValueError, 'invalid_sale_product'):
            _current_room_bound(m, private, [['SELL', 'COW', 1]], True)

    def test_final_day_has_no_feed_reservation(self):
        self.obs['step'] = 695
        self.unchanged('outside_supported_feed_window')

    def agent(self):
        agent = object.__new__(TitanAgent)
        agent.features = Features(operating_stock=True)
        agent.spatial = None; agent.history = None; agent.quadrant = None
        agent.diagnostics = {'status': 'deadline_fallback'}
        agent.controller = SimpleNamespace(R={'current': self.route}, cur='current')
        agent.consumer = SimpleNamespace(selected_post_units=(self.farm, self.private),
            selected_post_units_binding=(460, 0, ['PASS'], [['PASS']]))
        return agent

    def test_final_selected_fallback_keeps_supported_reservation(self):
        agent = self.agent()
        result = agent._finish_production(self.obs, self.selected, {})
        self.assertEqual(result['market'], [['SELL', 'WHEAT', 7]])
        self.assertTrue(agent.diagnostics['feed_stock']['certified'])

    def test_changed_unit_snapshot_cannot_authorize_a_reservation(self):
        agent = self.agent(); self.selected['hands'][0] = ['PICKUP', 'WHEAT', 3]
        result = agent._feed_stock_selected(self.obs, {}, self.selected)
        self.assertIs(result, self.selected)
        self.assertFalse(agent.diagnostics['feed_stock']['certified'])

    def test_crop_repair_keeps_exclusive_current_receipt_binding(self):
        agent = self.agent(); agent.spatial = SimpleNamespace(_crop_repair={'kind': 'withhold'})
        result = agent._feed_stock_selected(self.obs, {}, self.selected)
        self.assertIs(result, self.selected)
        self.assertEqual(agent.diagnostics['feed_stock']['reason'],
                         'crop_input_repair_owns_current_queue')


if __name__ == '__main__':
    unittest.main()
