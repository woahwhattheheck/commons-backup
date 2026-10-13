# SPDX-License-Identifier: Apache-2.0
"""Countercases and no-op contracts for joint actor assignment.

Does not execute a producer or official engine transition.
"""
from copy import deepcopy
from types import SimpleNamespace
from pathlib import Path
import json
import unittest

from joint_actors import (
    REASON_ACCEPTED, REASON_CARGO_MASK, REASON_NO_BUNDLES, REASON_UNRESUMABLE,
    reconcile,
)
from titan_runtime import Features


def _tile(yield_units=3, crop='STRAWBERRY', planted_day=0):
    return {'kind': 'PLANT', 'crop': crop, 'planted_day': planted_day,
            'yield_units': yield_units, 'fertilized_until_day': -1,
            'max_lifespan_step': -1, 'consecutive_unwatered': 0,
            'watered_today': True}


def _row(farmer, hand, market=None):
    return {'farmer': list(farmer), 'hands': [list(hand)], 'market': list(market or [])}


class _Controller:
    def __init__(self, route):
        self.cur = 0
        self.R = {0: route}


class JointActorTests(unittest.TestCase):
    def setUp(self):
        self.now = 10
        tiles = [[None for _ in range(10)] for _ in range(10)]
        tiles[4][2] = _tile()
        tiles[4][7] = _tile()
        tiles[2][4] = _tile()
        tiles[6][4] = _tile()
        self.farm = {'farmer': [2, 4], 'hands': [[7, 4]], 'money': 50000,
                     'tiles': tiles, 'hires_today': 1, 'unlocked_quadrants': ['NW']}
        self.private = {'inventories': [{}, {}], 'shed': {}, 'seeds': {}}
        self.obs = {'step': self.now, 'player': 0, 'day': 0, 'hour': 10,
                    'farms': [self.farm, {'tiles': [[None]*10 for _ in range(10)],
                                         'farmer': [0, 0], 'hands': []}],
                    'private': self.private,
                    'market': {'inventory': {'STRAWBERRY': 9000}, 'prices': {}, 'params': {}}}
        self.spatial = SimpleNamespace(plans={}, active={}, events=[], crop_intent=None,
                                       joint_actors_enabled=True, joint_stats=None,
                                       joint_report=None)

    def _route(self, farmer_seq, hand_seq):
        route = [_row(['PASS'], ['PASS']) for _ in range(720)]
        for i, action in enumerate(farmer_seq):
            route[self.now + i]['farmer'] = list(action)
        for i, action in enumerate(hand_seq):
            route[self.now + i]['hands'][0] = list(action)
        return route

    def _selected(self, route):
        return deepcopy(route[self.now])

    def test_features_default_is_noop_flag(self):
        self.assertFalse(Features().joint_actors)
        cfg = json.loads(Path(__file__).resolve().parents[1].joinpath('TITAN-CONFIG.json').read_text())
        self.assertTrue(cfg['joint_actors'])
        self.assertTrue(Features(**cfg).joint_actors)

    def test_identical_position_different_cargo_is_noop(self):
        """Do not exchange actors whose identical position masks different cargo."""
        self.farm['farmer'] = [4, 4]
        self.farm['hands'] = [[4, 4]]
        self.private['inventories'] = [{'FERTILIZER': 1}, {}]
        farmer_seq = [['EAST'], ['EAST'], ['HARVEST'], ['WEST'], ['WEST'], ['DROP']]
        hand_seq = [['NORTH'], ['NORTH'], ['HARVEST'], ['SOUTH'], ['SOUTH'], ['DROP']]
        route = self._route(farmer_seq, hand_seq)
        selected = self._selected(route)
        original = deepcopy(selected)
        result, report = reconcile(self.spatial, self.obs, selected, _Controller(route))
        self.assertIs(result, selected)
        self.assertEqual(result, original)
        self.assertFalse(report['changed'])
        self.assertEqual(report['reason'], REASON_CARGO_MASK)
        self.assertIsNone(report['pair'])

    def test_next_commitment_cannot_resume_is_noop(self):
        """Do not swap when the original rejoin/goal cannot resume after the swap."""
        self.now = 21
        self.obs['step'] = 21
        self.obs['hour'] = 21
        self.farm['farmer'] = [0, 4]
        self.farm['hands'] = [[9, 4]]
        self.farm['tiles'][4][1] = _tile()
        self.farm['tiles'][4][8] = _tile()
        # Window is 3 (21..24). Each bundle is pickup->service locally.
        # Borrowing the opposite tile cannot rejoin the original goal in 3 steps.
        farmer_seq = [['EAST'], ['HARVEST'], ['FERTILIZE']]
        hand_seq = [['WEST'], ['HARVEST'], ['FERTILIZE']]
        route = self._route(farmer_seq, hand_seq)
        selected = self._selected(route)
        original = deepcopy(selected)
        result, report = reconcile(self.spatial, self.obs, selected, _Controller(route))
        self.assertIs(result, selected)
        self.assertEqual(result, original)
        self.assertFalse(report['changed'])
        self.assertEqual(report['reason'], REASON_UNRESUMABLE)

    def test_crossing_harvest_swap_saves_travel(self):
        farmer_seq = ([['EAST']] * 5 + [['HARVEST'], ['WEST'], ['WEST'], ['DROP']]
                      + [['WEST']] * 3)
        hand_seq = ([['WEST']] * 5 + [['HARVEST'], ['EAST'], ['EAST'], ['DROP']]
                    + [['EAST']] * 3)
        route = self._route(farmer_seq, hand_seq)
        selected = self._selected(route)
        result, report = reconcile(self.spatial, self.obs, selected, _Controller(route))
        self.assertTrue(report['changed'])
        self.assertEqual(report['reason'], REASON_ACCEPTED)
        self.assertGreater(report['saved_travel'], 0)
        self.assertEqual(report['owner'], min(report['pair']))
        self.assertIsNotNone(report['collision_trace'])
        self.assertEqual(report['collision_trace']['owner'], report['owner'])
        self.assertNotEqual(result['farmer'], selected['farmer'] if result is not selected else None)
        self.assertIn(0, self.spatial.plans)
        self.assertIn(1, self.spatial.plans)
        self.assertEqual(self.spatial.plans[0]['owner'], self.spatial.plans[1]['owner'])
        self.assertEqual(self.spatial.plans[0]['kind'], 'joint_swap')

    def test_no_complete_bundle_is_explicit_noop(self):
        route = self._route([['PASS']] * 8, [['NORTH'], ['SOUTH'], ['PASS']])
        selected = self._selected(route)
        original = deepcopy(selected)
        result, report = reconcile(self.spatial, self.obs, selected, _Controller(route))
        self.assertIs(result, selected)
        self.assertEqual(result, original)
        self.assertFalse(report['changed'])
        self.assertEqual(report['reason'], REASON_NO_BUNDLES)

    def test_accepted_swap_increments_activation_count(self):
        self.test_crossing_harvest_swap_saves_travel()
        self.assertEqual(self.spatial.joint_stats['activation_count'], 1)
        self.assertGreater(self.spatial.joint_stats['travel_saved_total'], 0)


if __name__ == '__main__':
    unittest.main()
