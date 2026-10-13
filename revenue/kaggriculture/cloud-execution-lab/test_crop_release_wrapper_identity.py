# SPDX-License-Identifier: Apache-2.0
"""Crop-release wrapper contracts for exact public observation identity."""
from copy import deepcopy
import unittest

from spatial_tempo import SpatialTempo


class CropReleaseWrapperIdentityContracts(unittest.TestCase):
    def test_alias_receipt_observation_cannot_discard_awaiting_intent(self):
        spatial = SpatialTempo(None, crop_release=True)
        intent = {'status': 'awaiting_seed_and_site_observation', 'player': 0,
                  'prepared_step': 372, 'plant_step': 373}
        spatial.crop_intent = deepcopy(intent)
        spatial.observe_crop_receipts({'player': '0', 'step': '374'}, None, 'irrelevant')
        self.assertEqual(spatial.crop_intent, intent)

    def test_alias_finish_does_not_consume_pending_crop_proposal(self):
        spatial = SpatialTempo(None, crop_release=True)
        proposal = {'status': 'proposed', 'player': 0, 'prepared_step': 372,
                    'plant_step': 373, 'unit_binding': [['PASS']],
                    'seed_order': ['BUY_SEED', 'CARROT', 1]}
        spatial._crop_preparation = deepcopy(proposal)
        returned = {'farmer': ['PASS'], 'hands': [],
                    'market': [['BUY_SEED', 'CARROT', 1]]}
        spatial.finish_crop({'player': '0', 'step': '372'}, returned, None, 'irrelevant')
        self.assertEqual(spatial._crop_preparation, proposal)

    def test_alias_snapshot_cancels_unbound_repair_buy(self):
        spatial = SpatialTempo(None, crop_release=True)
        repair = {'step': 455, 'player': 0, 'slot': 0, 'units': 1, 'kind': 'buy',
                  'unit_binding': [['PASS']], 'inherited_market': [],
                  'expected_market': [['BUY_PRODUCT', 'WHEAT', 1]]}
        returned = {'farmer': ['PASS'], 'hands': [],
                    'market': [['BUY_PRODUCT', 'WHEAT', 1]]}
        spatial._crop_repair = deepcopy(repair)
        out = spatial.guard_crop_returned(
            {'player': '0', 'step': '455'}, returned,
            {'player': '0', 'step': '455'})
        self.assertEqual(out['market'], [])
        self.assertEqual(spatial.crop_report['reason'],
                         'final_unit_guard_canceled_unbound_repair')

        spatial._crop_repair = deepcopy(repair)
        canonical = spatial.guard_crop_returned(
            {'player': 0, 'step': 455}, returned,
            {'player': 0, 'step': 455})
        self.assertEqual(canonical['market'], [['BUY_PRODUCT', 'WHEAT', 1]])


if __name__ == '__main__':
    unittest.main()
