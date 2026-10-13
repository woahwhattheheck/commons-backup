# SPDX-License-Identifier: Apache-2.0
"""Exact public identity contracts for the stateful SpatialTempo wrapper."""
from copy import deepcopy
import unittest

from spatial_tempo import SpatialTempo, _public_identity


class _Controller:
    def __init__(self, selected):
        self.cur = 'route'
        self.R = {'route': [{'farmer': ['PASS'], 'hands': [], 'market': []}] * 4}
        self.selected = selected
        self.calls = 0

    def act(self, observation):
        self.calls += 1
        return self.selected


class SpatialTempoIdentityContracts(unittest.TestCase):
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

    def test_alias_observation_cannot_clear_owned_stock_receipt(self):
        spatial = SpatialTempo(None)
        spatial.sale_obligation = {
            'step': 10, 'player': 0, 'status': 'awaiting_observed_fill'
        }
        spatial.receipt_events = [{'kind': 'sentinel'}]
        before = deepcopy(spatial.sale_obligation)
        spatial.observe_owned_stock({'player': '1', 'step': '9'})
        self.assertEqual(spatial.sale_obligation, before)
        self.assertEqual(spatial.receipt_events, [{'kind': 'sentinel'}])

    def test_alias_observation_cannot_poison_market_receipt(self):
        spatial = SpatialTempo(None)
        spatial.sale_obligation = {
            'step': 10, 'player': 0, 'status': 'observed_deposit',
            'eod_transfer_step': 10, 'slot': 0,
        }
        result = {
            'binding': {'step': 11, 'player': 0},
            'orders': [{'slot': 0, 'type': 'SELL', 'item': 'FERTILIZER',
                        'requested': 1, 'fill_min': 1, 'fill_max': 1}],
            'status': 'reconciled',
        }
        before = deepcopy(spatial.sale_obligation)
        spatial.observe_market_receipt({'player': 0.0, 'step': 11}, result)
        self.assertEqual(spatial.sale_obligation, before)

    def test_alias_guard_leaves_action_and_state_untouched(self):
        spatial = SpatialTempo(None)
        spatial.sale_obligation = {
            'step': 23, 'player': 0, 'worker': 0, 'status': 'carried',
            'target': (3, 3), 'quantity': 1,
        }
        spatial._sale_proposal = {'step': 23, 'slot': 0, 'worker': 0,
                                  'quantity': 1, 'target': (3, 3)}
        returned = {'farmer': ['PASS'], 'hands': [], 'market': []}
        before_state = deepcopy(spatial.__dict__)
        out = spatial.guard_returned({'player': '0', 'step': 23}, returned,
                                     repair_fallback=True)
        self.assertIs(out, returned)
        self.assertEqual(spatial.__dict__, before_state)

    def test_alias_finish_cannot_publish_pending_plan_state(self):
        spatial = SpatialTempo(None)
        spatial._pending = {'previous': {}, 'plans': {}, 'events': []}
        spatial._selected = {'farmer': ['PASS'], 'hands': [], 'market': []}
        spatial._sale_proposal = {'step': 1, 'slot': 0, 'worker': None,
                                  'quantity': 1, 'target': (4, 4)}
        before = deepcopy(spatial.__dict__)
        spatial.finish({'player': False, 'step': 1}, spatial._selected)
        self.assertEqual(spatial.__dict__, before)

    def test_installed_wrapper_bypasses_spatial_mutation_on_alias(self):
        selected = {'farmer': ['PASS'], 'hands': [], 'market': []}
        controller = _Controller(selected)
        spatial = SpatialTempo(None)
        spatial.events = [{'kind': 'sentinel'}]
        spatial.install(controller)
        before = deepcopy(spatial.__dict__)
        out = controller.act({'player': '0', 'step': 1})
        self.assertIs(out, selected)
        self.assertEqual(controller.calls, 1)
        self.assertEqual(spatial.__dict__, before)

    def test_alias_transform_is_exact_noop(self):
        selected = {'farmer': ['PASS'], 'hands': [], 'market': []}
        spatial = SpatialTempo(None)
        controller = _Controller(selected)
        before = deepcopy(spatial.__dict__)
        out = spatial.transform({'player': 0, 'step': 1.0}, selected, controller)
        self.assertIs(out, selected)
        self.assertEqual(spatial.__dict__, before)


if __name__ == '__main__':
    unittest.main()
