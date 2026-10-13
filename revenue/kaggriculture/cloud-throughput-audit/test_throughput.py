"""Focused tests of the diagnostic against the frozen official primitives.

Fixture changes are unit tests, not new games or a policy performance panel.
"""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path
import sys
import unittest
from audit_throughput import audit_action, load_mechanics
from audit_boundaries import audit_pair, load_engine

ROOT = None


class ThroughputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mechanics = load_mechanics(ROOT / 'candidate/mechanics.py')
        cls.engine, cls.engine_hashes, _ = load_engine(ROOT)

    def fixture(self, step=240):
        e = self.engine
        farm = e._new_farm(4, 1000)
        farm['tiles'] = [[None for _ in range(4)] for _ in range(4)]
        farm['farmer'] = [1, 1]
        farm['hands'] = []
        private = e._new_private()
        cfg = {'episodeSteps': 720, 'turnsPerDay': 24, 'boardSize': 4,
               'shedCapacity': 100, 'maxMarketOrdersPerTurn': 10, 'farmHandCostMult': 1}
        obs = {'player': 0, 'step': step, 'day': step // 24, 'hour': step % 24,
               'farms': [farm, copy.deepcopy(farm)], 'private': private,
               'market': e._new_market(), 'town': {'unlocked_shops': []}}
        return obs, cfg

    def cow(self, obs, units=3):
        cow = self.engine._new_animal('COW', 0)
        cow['yield_units'] = units
        obs['farms'][0]['tiles'][1][1] = cow

    def add_hand(self, obs, xy=(1, 1), inv=None):
        obs['farms'][0]['hands'].append(list(xy))
        obs['private']['inventories'].append(inv or {})

    def run_action(self, obs, cfg, farmer, hands=(), market=()):
        return audit_action(self.mechanics, obs, {'farmer': farmer,
                            'hands': list(hands), 'market': list(market)}, cfg)

    def test_productive_cow(self):
        obs, cfg = self.fixture()
        self.cow(obs)
        r = self.run_action(obs, cfg, ['HARVEST'])
        self.assertEqual(r['harvest_counts'], {'productive': 1})

    def test_ordered_shared_cow_is_not_initial_zero(self):
        obs, cfg = self.fixture()
        self.cow(obs)
        self.add_hand(obs)
        r = self.run_action(obs, cfg, ['HARVEST'], [['HARVEST']])
        self.assertEqual(r['harvest_counts'], {'productive': 1, 'depleted_by_earlier_unit': 1})
        self.assertEqual(r['noops'][0]['earlier_harvester'], 0)
        self.assertEqual(r['noops'][0]['observed_tile']['yield_units'], 3)
        self.assertEqual(r['noops'][0]['pre_unit_tile']['yield_units'], 0)

    def test_empty_cow_no_false_duplicate(self):
        obs, cfg = self.fixture()
        self.cow(obs, 0)
        self.add_hand(obs)
        r = self.run_action(obs, cfg, ['HARVEST'], [['HARVEST']])
        self.assertEqual(r['harvest_counts'], {'zero_yield_before_turn': 2})

    def test_empty_tile(self):
        obs, cfg = self.fixture()
        self.assertEqual(self.run_action(obs, cfg, ['HARVEST'])['harvest_counts'], {'no_yield_tile': 1})

    def test_empty_pasture(self):
        obs, cfg = self.fixture()
        obs['farms'][0]['tiles'][1][1] = {'kind': 'PASTURE'}
        self.assertEqual(self.run_action(obs, cfg, ['HARVEST'])['harvest_counts'], {'zero_yield_before_turn': 1})

    def test_missing_hand_is_separate(self):
        obs, cfg = self.fixture()
        self.assertEqual(self.run_action(obs, cfg, ['PASS'], [['HARVEST']])['harvest_counts'], {'missing_unit': 1})

    def test_immature_crop_not_yield_ready(self):
        obs, cfg = self.fixture()
        obs['farms'][0]['tiles'][1][1] = self.engine._new_plant('WHEAT', 10, 24)
        self.assertEqual(self.run_action(obs, cfg, ['HARVEST'])['harvest_counts'], {'immature_crop': 1})

    def test_nonongoing_crop_second_actor(self):
        obs, cfg = self.fixture()
        obs['farms'][0]['tiles'][1][1] = self.engine._new_plant('WHEAT', 7, 24)
        self.add_hand(obs)
        r = self.run_action(obs, cfg, ['HARVEST'], [['HARVEST']])
        self.assertEqual(r['harvest_counts'], {'productive': 1, 'depleted_by_earlier_unit': 1})
        self.assertIsNone(r['noops'][0]['pre_unit_tile'])

    def test_prior_inventory_not_counted_as_harvest(self):
        obs, cfg = self.fixture()
        self.cow(obs, 0)
        obs['private']['inventories'][0] = {'MILK': 3}
        self.assertEqual(self.run_action(obs, cfg, ['HARVEST'])['harvest_counts'], {'zero_yield_before_turn': 1})

    def test_drop_overflow_detected(self):
        obs, cfg = self.fixture()
        obs['private']['shed'] = {'WHEAT': 98}
        obs['private']['inventories'][0] = {'MILK': 5}
        r = self.run_action(obs, cfg, ['DROP'])
        self.assertEqual(r['drop_losses'][0]['lost'], {'MILK': 3})
        self.assertEqual(r['drop_losses'][0]['deposited'], {'MILK': 2})

    def test_ordered_drops_share_capacity(self):
        obs, cfg = self.fixture()
        obs['private']['shed'] = {'WHEAT': 95}
        obs['private']['inventories'][0] = {'MILK': 4}
        self.add_hand(obs, inv={'WOOL': 4})
        r = self.run_action(obs, cfg, ['DROP'], [['DROP']])
        self.assertEqual(len(r['drop_losses']), 1)
        self.assertEqual(r['drop_losses'][0]['unit'], 1)
        self.assertEqual(r['drop_losses'][0]['lost'], {'WOOL': 3})

    def test_nonadjacent_drop_is_not_overflow_loss(self):
        obs, cfg = self.fixture()
        obs['farms'][0]['farmer'] = [0, 0]
        obs['private']['shed'] = {'WHEAT': 100}
        obs['private']['inventories'][0] = {'MILK': 5}
        self.assertEqual(self.run_action(obs, cfg, ['DROP'])['drop_losses'], [])

    def test_action_does_not_mutate_inputs(self):
        obs, cfg = self.fixture()
        self.cow(obs)
        a = {'farmer': ['HARVEST'], 'hands': [], 'market': []}
        before = copy.deepcopy((obs, cfg, a))
        audit_action(self.mechanics, obs, a, cfg)
        self.assertEqual((obs, cfg, a), before)

    def test_atomic_seed_preflight_includes_all_requests(self):
        obs, cfg = self.fixture()
        obs['private']['seeds'] = {'WHEAT': 1}
        self.add_hand(obs)
        self.add_hand(obs)
        r = self.run_action(obs, cfg, ['PLANT', 'WHEAT'], [['HARVEST'], ['PLANT', 'WHEAT']])
        self.assertEqual(r['harvest_counts'], {'no_yield_tile': 1})

    def test_atomic_preflight_includes_not_yet_hired_slot(self):
        obs, cfg = self.fixture()
        obs['private']['seeds'] = {'WHEAT': 1}
        self.add_hand(obs)
        r = self.run_action(obs, cfg, ['PLANT', 'WHEAT'], [['HARVEST'], ['PLANT', 'WHEAT']])
        self.assertEqual(r['harvest_counts'], {'no_yield_tile': 1})

    def test_malformed_hand_container_is_ignored(self):
        obs, cfg = self.fixture()
        r = audit_action(self.mechanics, obs, {'farmer': ['PASS'], 'hands': None}, cfg)
        self.assertEqual(r['harvest_counts'], {})

    def test_terminal_records_missing_sell(self):
        obs, cfg = self.fixture(718)
        obs['private']['shed'] = {'MILK': 4}
        r = self.run_action(obs, cfg, ['PASS'], market=[['SELL', 'MILK', 3]])
        self.assertEqual(r['terminal']['unoffered_shed'], {'MILK': 1})

    def test_nonterminal_does_not_claim_terminal_closure(self):
        obs, cfg = self.fixture(717)
        self.assertIsNone(self.run_action(obs, cfg, ['PASS'])['terminal'])

    def pair(self, step=23, market=()):
        obs, cfg = self.fixture(step)
        obs['private']['shed'] = {'MILK': 95}
        obs['private']['inventories'][0] = {'WOOL': 10}
        own = {'seat': 0, 'step': step, 'observation': obs, 'configuration': cfg,
               'response': {'action': {'farmer': ['PASS'], 'hands': [], 'market': list(market)}}}
        rival_obs = copy.deepcopy(obs)
        rival_obs['player'] = 1
        rival_obs['private'] = self.engine._new_private()
        rival = {'seat': 1, 'step': step, 'observation': rival_obs, 'configuration': copy.deepcopy(cfg),
                 'response': {'action': {'farmer': ['PASS'], 'hands': [], 'market': []}}}
        return [own, rival]

    def test_automatic_overflow_detected(self):
        r = audit_pair(self.engine, self.pair())
        self.assertEqual(r['losses'][0]['lost'], {'WOOL': 5})

    def test_market_runs_before_automatic_deposit(self):
        r = audit_pair(self.engine, self.pair(market=[['SELL', 'MILK', 5]]))
        self.assertEqual(r['losses'][0]['lost'], {})
        self.assertEqual(r['privates'][0]['shed'], {'MILK': 90, 'WOOL': 10})

    def test_nonboundary_has_no_automatic_deposit(self):
        r = audit_pair(self.engine, self.pair(step=22))
        self.assertFalse(r['automatic_deposit'])
        self.assertEqual(r['privates'][0]['inventories'], [{'WOOL': 10}])

    def test_boundary_does_not_mutate_retained_input(self):
        pair = self.pair()
        before = copy.deepcopy(pair)
        audit_pair(self.engine, pair)
        self.assertEqual(pair, before)

    def test_mismatched_paired_observations_rejected(self):
        pair = self.pair()
        pair[1]['step'] = 24
        with self.assertRaises(ValueError):
            audit_pair(self.engine, pair)

    def test_boundary_exact_sale_fills_not_requested_amount(self):
        pair = self.pair(step=718, market=[['SELL', 'MILK', 200]])
        pair[0]['observation']['private']['inventories'] = [{}]
        r = audit_pair(self.engine, pair)
        self.assertEqual(r['privates'][0]['shed']['MILK'], 0)
        self.assertGreater(r['money'][0], 1000)
        self.assertFalse(r['automatic_deposit'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle-dir', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    ROOT = args.bundle_dir
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ThroughputTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    args.report.write_text(json.dumps({'tests': result.testsRun, 'failures': len(result.failures),
                                      'errors': len(result.errors), 'skipped': len(result.skipped),
                                      'successful': result.wasSuccessful(),
                                      'engine_hashes': ThroughputTests.engine_hashes}, indent=2) + '\n')
    sys.exit(not result.wasSuccessful())
