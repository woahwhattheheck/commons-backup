# SPDX-License-Identifier: Apache-2.0
"""Exact public clock/seat boundaries for the selected-action SELL wrappers."""
from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

import ordered_selected_sell as ordered
from selected_action_sell import SelectedActionSell, absolute_step, observation_player


class SelectedObservationIdentityTests(unittest.TestCase):
    def test_absolute_step_accepts_only_exact_consistent_public_clock(self):
        cfg = {'turnsPerDay': 24}
        self.assertEqual(absolute_step({'step': 25}, cfg), 25)
        self.assertEqual(absolute_step({'day': 1, 'hour': 1}, cfg), 25)
        self.assertEqual(absolute_step({'step': 25, 'day': 1, 'hour': 1}, cfg), 25)
        for value in (None, True, '25', 25.0, -1):
            with self.subTest(step=value), self.assertRaises(ValueError):
                absolute_step({'step': value}, cfg)
        for row in ({'step': 25, 'day': 0, 'hour': 1},
                    {'step': 25, 'day': 1},
                    {'step': 25, 'hour': 1},
                    {'day': True, 'hour': 1},
                    {'day': 1, 'hour': '1'},
                    {'day': 1, 'hour': 24}):
            with self.subTest(clock=row), self.assertRaises(ValueError):
                absolute_step(row, cfg)

    def test_player_is_exact_two_seat_identity(self):
        self.assertEqual(observation_player({'player': 0}), 0)
        self.assertEqual(observation_player({'player': 1}), 1)
        for value in (False, True, -1, 2, '0', 0.0, 1.0):
            with self.subTest(player=value), self.assertRaises(ValueError):
                observation_player({'player': value})

    def test_generic_seller_fails_closed_before_history_on_bad_identity(self):
        selected = {'farmer': ['PASS'], 'hands': [], 'market': []}
        projection = {'end_step': 10, 'observed_step': 10,
                      'future_market': {}, 'stock_events': []}
        for patch_row in ({'player': -1, 'step': 10},
                          {'player': 0, 'step': '10'},
                          {'player': 0, 'step': 10, 'day': 0, 'hour': 9}):
            seller = SelectedActionSell()
            seller.previous = ('sentinel',)
            seller.observed_harvests = {'MILK': [(9, 3)]}
            before = copy.deepcopy((seller.previous, seller.observed_harvests))
            out = seller.transform(patch_row, {'turnsPerDay': 24}, selected,
                                   post_unit_shed={}, projection=projection)
            self.assertEqual(out, selected)
            self.assertEqual((seller.previous, seller.observed_harvests), before)
            self.assertEqual(seller.diagnostics['status'], 'fallback')

    def test_ordered_prepare_rejects_bad_identity_before_projection(self):
        selected = {'farmer': ['PASS'], 'hands': [], 'market': []}
        observation = {'player': -1, 'step': 10}
        tx = ordered.OrderedSelectedSell()
        with patch.object(ordered._projection, 'project_selected',
                          side_effect=AssertionError('projection must not run')) as project:
            with self.assertRaises(ValueError):
                tx.prepare(observation, {'turnsPerDay': 24}, selected,
                           future_actions={}, end_step=10)
        project.assert_not_called()

    def test_ordered_binding_rejects_alias_before_farm_indexing(self):
        selected = {'farmer': ['PASS'], 'hands': [], 'market': []}
        for value in (-1, 2, '0', 0.0, False):
            with self.subTest(player=value), self.assertRaises(ValueError):
                ordered._binding({'player': value, 'step': 10},
                                 {'turnsPerDay': 24}, selected)


if __name__ == '__main__':
    unittest.main()
