# SPDX-License-Identifier: Apache-2.0
"""Focused contracts for crop-release public observation identity."""
from copy import deepcopy
import unittest

from crop_release import (_public_identity, commit_preparation, observe_crop,
                          observe_crop_sale, observe_input_repair)


class CropReleaseObservationIdentityContracts(unittest.TestCase):
    def test_public_identity_is_plain_and_bounded(self):
        self.assertEqual(_public_identity({'player': 0, 'step': 0}), (0, 0))
        self.assertEqual(_public_identity({'player': 1, 'step': 719}), (1, 719))
        for observation in (
            {'player': False, 'step': 1},
            {'player': True, 'step': 1},
            {'player': '0', 'step': 1},
            {'player': 0.0, 'step': 1},
            {'player': -1, 'step': 1},
            {'player': 2, 'step': 1},
            {'player': 0, 'step': True},
            {'player': 0, 'step': '1'},
            {'player': 0, 'step': 1.0},
            {'player': 0, 'step': -1},
        ):
            with self.subTest(observation=observation):
                self.assertIsNone(_public_identity(observation))

    def test_preparation_commit_rejects_player_and_step_aliases(self):
        returned = {'farmer': ['PASS'], 'hands': [],
                    'market': [['BUY_SEED', 'CARROT', 1]]}
        intent = {'status': 'proposed', 'prepared_step': 372, 'player': 0,
                  'unit_binding': [['PASS']],
                  'seed_order': ['BUY_SEED', 'CARROT', 1]}
        committed = commit_preparation(intent, {'player': 0, 'step': 372}, returned)
        self.assertEqual(committed['status'], 'awaiting_seed_and_site_observation')
        for observation in (
            {'player': False, 'step': 372},
            {'player': '0', 'step': 372},
            {'player': 0.0, 'step': 372},
            {'player': 0, 'step': '372'},
            {'player': 0, 'step': 372.0},
        ):
            with self.subTest(observation=observation):
                self.assertIsNone(commit_preparation(intent, observation, returned))

    def test_alias_observation_cannot_advance_terminal_crop_receipt(self):
        intent = {'status': 'input_recovery_only', 'player': 0,
                  'plant_step': 1, 'last_observed_step': 10,
                  'receipt_failure': 'already_closed'}
        for observation in (
            {'player': '0', 'step': '11'},
            {'player': False, 'step': 11},
            {'player': 0, 'step': 11.0},
        ):
            with self.subTest(observation=observation):
                self.assertEqual(observe_crop(intent, observation, 'irrelevant'), intent)

    def test_alias_observation_cannot_poison_sale_attribution(self):
        intent = {'status': 'awaiting_observed_sale', 'player': 0,
                  'sale_step': 10, 'sale_quantity_remaining': 1,
                  'sale_orders': [(0, 1)], 'sale_action_sha256': 'abc',
                  'crop_receipts': []}
        for observation in (
            {'player': '0', 'step': '11'},
            {'player': False, 'step': 11},
            {'player': 0, 'step': 11.0},
        ):
            with self.subTest(observation=observation):
                self.assertEqual(observe_crop_sale(intent, observation, {}), intent)
        canonical = observe_crop_sale(intent, {'player': 0, 'step': 11}, {})
        self.assertEqual(canonical['status'], 'sale_attribution_unknown')

    def test_alias_observation_cannot_consume_pending_input_receipt(self):
        pending = {'step': 10, 'player': 0, 'kind': 'buy', 'slot': 0,
                   'units': 1, 'action_sha256': 'abc'}
        intent = {'status': 'input_recovery_only', 'player': 0,
                  'input_repair_pending': pending,
                  'input_repair_remaining': 1,
                  'wheat_reserve_required': 1,
                  'input_repair_receipts': []}
        for observation in (
            {'player': '0', 'step': '11'},
            {'player': False, 'step': 11},
            {'player': 0, 'step': 11.0},
        ):
            with self.subTest(observation=observation):
                self.assertEqual(observe_input_repair(intent, observation, {}), intent)
        canonical = observe_input_repair(deepcopy(intent), {'player': 0, 'step': 11}, {})
        self.assertTrue(canonical['input_repair_unknown'])
        self.assertNotIn('input_repair_pending', canonical)


if __name__ == '__main__':
    unittest.main()
