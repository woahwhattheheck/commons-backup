# SPDX-License-Identifier: Apache-2.0
"""Focused official unit-mechanics checks; no policies or full games.

Run this file with --loader-path, --engine-dir and --audit-path pointing to
the retained pinned sources. The runner checks engine and audit identities before
loading them, and checks the loader's ENGINE_REF after importing the loader.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

from ordered_yield import account_ordered_yield, apply_joint_units


ENGINE_REF = '28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c'
ENGINE_BLOBS = {
    'kaggriculture.py': '3c202c7ee921da239356789e266b694635103fc4',
    'kaggriculture.json': 'b354d06b742fe48402513792253f1a5c29366b20',
    'utils.py': '91c8822ee6201ba4a5a8416c7dbe34f95dd61c87',
}
AUDIT_SHA256 = 'f33df1a1e2c601f3ec454deb736f09c4047f2ed06403c368635d86d4be847a7f'


class OrderedYieldTests(unittest.TestCase):
    mechanics = None
    audit = None

    @classmethod
    def setUpClass(cls):
        if cls.mechanics is None or cls.audit is None:
            raise RuntimeError('Use the documented runner with retained loader, engine and audit paths')

    def fixture(self, tile, *, day=10, hands=1, farmer_on_tile=True, seat=0):
        farm = self.mechanics._new_farm(10, 3000)
        farm['farmer'] = [4, 2] if farmer_on_tile else [0, 0]
        farm['hands'] = [[4, 2] for _ in range(hands)]
        farm['tiles'][2][4] = tile
        private = self.mechanics._new_private()
        private['inventories'] = [{} for _ in range(hands + 1)]
        other = self.mechanics._new_farm(10, 7777)
        farms = [farm, other] if seat == 0 else [other, farm]
        obs = {'player': seat, 'farms': farms, 'private': private,
               'step': day * 24, 'day': day}
        cfg = {'boardSize': 10, 'turnsPerDay': 24, 'shedCapacity': 100}
        return obs, cfg

    def cow(self, units=3):
        tile = self.mechanics._new_animal('COW', 0)
        tile['yield_units'] = units
        return tile

    def wheat(self):
        return self.mechanics._new_plant('WHEAT', 0, 24)

    def account(self, obs, action, cfg):
        return account_ordered_yield(self.mechanics, obs, action, cfg, audit=self.audit)

    def test_hand_one_and_eight_receive_three_and_zero_in_order(self):
        obs, cfg = self.fixture(self.cow(), hands=8, farmer_on_tile=False)
        for hand in range(1, 7):
            obs['farms'][0]['hands'][hand] = [0, 0]
        action = {'farmer': ['PASS'], 'hands': [['HARVEST']]
                  + [['PASS'] for _ in range(6)] + [['HARVEST']], 'market': []}
        result = self.account(obs, action, cfg)
        receipts = result['unit_receipts']
        self.assertEqual([r['actor'] for r in receipts], list(range(9)))
        self.assertEqual(result['structural_duplicates'], [{
            'position': [4, 2], 'actors': [1, 8], 'redundant_orders': 1,
            'visible_yield_units': 3, 'tile_kind': 'PASTURE'}])
        self.assertEqual(receipts[1]['received'], {'MILK': 3})
        self.assertEqual(receipts[1]['received_units'], 3)
        self.assertEqual(receipts[1]['status'], 'harvest_received')
        self.assertEqual(receipts[8]['received'], {})
        self.assertEqual(receipts[8]['received_units'], 0)
        self.assertEqual(receipts[8]['status'], 'harvest_depleted')
        self.assertEqual((receipts[1]['visible_yield_before'], receipts[1]['visible_yield_after']), (3, 0))
        self.assertEqual(result['depletion_groups'], [{
            'position': [4, 2], 'claimant': 1, 'received': {'MILK': 3}, 'depleted_actors': [8]}])
        self.assertEqual(result['final_private']['inventories'][1], {'MILK': 3})
        self.assertEqual(result['final_private']['inventories'][8], {})
        self.assertEqual(result['final_farm']['tiles'][2][4]['yield_units'], 0)

    def test_harvest_is_not_limited_by_inventory_or_shed_capacity(self):
        obs, cfg = self.fixture(self.cow(), hands=0)
        cfg['shedCapacity'] = 1
        obs['private']['inventories'][0] = {'WHEAT': 123}
        obs['private']['shed']['WHEAT'] = 100
        result = self.account(obs, {'farmer': ['HARVEST'], 'market': []}, cfg)
        row = result['unit_receipts'][0]
        self.assertEqual(row['inventory_before'], {'WHEAT': 123})
        self.assertEqual(row['inventory_after'], {'WHEAT': 123, 'MILK': 3})
        self.assertEqual(row['received'], {'MILK': 3})
        self.assertEqual(result['final_private']['shed'], obs['private']['shed'])

    def test_positive_visible_crop_yield_requires_maturity(self):
        for day, mature in [(1, False), (2, True)]:
            with self.subTest(day=day):
                obs, cfg = self.fixture(self.wheat(), day=day)
                action = {'farmer': ['HARVEST'], 'hands': [['HARVEST']]}
                result = self.account(obs, action, cfg)
                self.assertEqual(result['structural_duplicates'][0]['visible_yield_units'], 1)
                rows = result['unit_receipts']
                if mature:
                    self.assertEqual(rows[0]['received'], {'WHEAT': 1})
                    self.assertEqual(rows[1]['status'], 'harvest_depleted')
                    self.assertIsNone(result['final_farm']['tiles'][2][4])
                    self.assertEqual(result['depletion_groups'], [{
                        'position': [4, 2], 'claimant': 0,
                        'received': {'WHEAT': 1}, 'depleted_actors': [1]}])
                else:
                    self.assertEqual([r['status'] for r in rows], ['harvest_no_transfer'] * 2)
                    self.assertEqual([r['received_units'] for r in rows], [0, 0])
                    self.assertEqual(result['depletion_groups'], [])
                    self.assertEqual(result['final_farm']['tiles'][2][4], obs['farms'][0]['tiles'][2][4])

    def test_earlier_water_changes_yield_received_by_later_harvester(self):
        obs, cfg = self.fixture(self.wheat(), day=2, hands=2)
        action = {'farmer': ['WATER'], 'hands': [['HARVEST'], ['HARVEST']]}
        result = self.account(obs, action, cfg)
        rows = result['unit_receipts']
        self.assertEqual((rows[0]['visible_yield_before'], rows[0]['visible_yield_after']), (1, 2))
        self.assertEqual(rows[1]['received'], {'WHEAT': 2})
        self.assertEqual(rows[2]['status'], 'harvest_depleted')
        self.assertEqual(result['depletion_groups'][0]['claimant'], 1)
        self.assertEqual(result['depletion_groups'][0]['received'], {'WHEAT': 2})
        self.assertIsNone(result['final_farm']['tiles'][2][4])

    def test_earlier_dig_does_not_create_a_positive_harvest_claim(self):
        obs, cfg = self.fixture(self.wheat(), day=2, hands=2)
        result = self.account(obs, {'farmer': ['DIG'], 'hands': [['HARVEST'], ['HARVEST']]}, cfg)
        self.assertEqual(result['structural_duplicates'][0]['actors'], [1, 2])
        self.assertEqual([r['status'] for r in result['unit_receipts'][1:]], ['harvest_no_transfer'] * 2)
        self.assertEqual(result['depletion_groups'], [])
        self.assertIsNone(result['final_farm']['tiles'][2][4])
        self.assertTrue(all(not inv for inv in result['final_private']['inventories']))

    def test_intervening_resource_replacement_clears_old_claim(self):
        obs, cfg = self.fixture(self.wheat(), day=2, hands=3)
        obs['private']['seeds']['WHEAT'] = 1
        action = {'farmer': ['HARVEST'], 'hands': [['PLANT', 'WHEAT'], ['DIG'], ['HARVEST']]}
        result = self.account(obs, action, cfg)
        self.assertEqual(result['unit_receipts'][0]['received'], {'WHEAT': 1})
        self.assertEqual(result['unit_receipts'][3]['status'], 'harvest_no_transfer')
        self.assertEqual(result['depletion_groups'], [])
        self.assertIsNone(result['final_farm']['tiles'][2][4])
        self.assertEqual(result['final_private']['seeds']['WHEAT'], 0)

    def test_absent_hand_is_not_created_by_market_hire_or_daily_refresh(self):
        obs, cfg = self.fixture(self.cow(), farmer_on_tile=False)
        obs['step'] += 23
        action = {'farmer': ['PASS'], 'hands': [['HARVEST'], ['HARVEST']], 'market': [['HIRE']]}
        result = self.account(obs, action, cfg)
        row = result['unit_receipts'][2]
        self.assertFalse(row['exists'])
        self.assertIsNone(row['position'])
        self.assertEqual(row['status'], 'absent_actor')
        self.assertEqual(row['received_units'], 0)
        self.assertEqual(result['structural_duplicates'], [])
        self.assertEqual(result['depletion_groups'], [])
        self.assertEqual(len(result['final_farm']['hands']), 1)
        self.assertEqual(result['final_farm']['money'], 3000)
        self.assertEqual(result['final_private']['inventories'], [{}, {'MILK': 3}])
        self.assertEqual(result['final_private']['shed'], obs['private']['shed'])
        self.assertEqual(result['final_farm']['tiles'][2][4]['yield_units'], 0)

    def test_inputs_and_returned_snapshots_do_not_alias(self):
        obs, cfg = self.fixture(self.cow(), seat=1)
        action = {'farmer': ['HARVEST'], 'hands': [['HARVEST']], 'market': []}
        before = copy.deepcopy((obs, action, cfg))
        result = self.account(obs, action, cfg)
        self.assertEqual((obs, action, cfg), before)
        self.assertEqual(result['final_farm']['money'], 3000)
        self.assertEqual(result['final_private']['inventories'][0], {'MILK': 3})
        result['final_farm']['tiles'][2][4]['yield_units'] = 99
        result['final_private']['inventories'][0]['MILK'] = 99
        result['unit_receipts'][0]['action'].append('detachment-check')
        self.assertEqual((obs, action, cfg), before)

    def test_plant_demand_gate_counts_absent_submitted_hand(self):
        for seeds, blocked in [(1, True), (2, False)]:
            with self.subTest(seeds=seeds):
                obs, cfg = self.fixture(None, day=2, hands=0)
                farm, private = obs['farms'][0], obs['private']
                private['seeds']['WHEAT'] = seeds
                action = {'farmer': ['PLANT', 'WHEAT'], 'hands': [['PLANT', 'WHEAT']], 'market': [['HIRE']]}
                before_action, before_cfg = copy.deepcopy(action), copy.deepcopy(cfg)
                result = apply_joint_units(self.mechanics, farm, private, action, cfg, 2)
                self.assertEqual(result['blocked_plant_products'], ['WHEAT'] if blocked else [])
                self.assertEqual(result['unit_receipts'][0]['effective_action'], ['PASS'] if blocked else ['PLANT', 'WHEAT'])
                self.assertEqual(result['unit_receipts'][1]['status'], 'absent_actor')
                self.assertEqual(private['seeds']['WHEAT'], 1)
                self.assertEqual(len(farm['hands']), 0)
                if blocked:
                    self.assertIsNone(farm['tiles'][2][4])
                else:
                    self.assertEqual(farm['tiles'][2][4]['crop'], 'WHEAT')
                self.assertEqual(action, before_action)
                self.assertEqual(cfg, before_cfg)


def load_file(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--loader-path', type=Path, required=True)
    parser.add_argument('--engine-dir', type=Path, required=True)
    parser.add_argument('--audit-path', type=Path, required=True)
    args = parser.parse_args()
    engine_hashes = {}
    for name, expected in ENGINE_BLOBS.items():
        raw = (args.engine_dir / name).read_bytes()
        actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        if actual != expected:
            parser.error('Pinned engine blob mismatch: ' + name)
        engine_hashes[name] = hashlib.sha256(raw).hexdigest()
    audit_hash = hashlib.sha256(args.audit_path.read_bytes()).hexdigest()
    if audit_hash != AUDIT_SHA256:
        parser.error('Pinned PR10488 audit mismatch')
    loader = load_file(args.loader_path, 'ordered_yield_retained_loader')
    if loader.ENGINE_REF != ENGINE_REF:
        parser.error('Pinned loader engine reference mismatch')
    OrderedYieldTests.mechanics, _ = loader.get_engine(args.engine_dir)
    audit_module = load_file(args.audit_path, 'ordered_yield_retained_audit')
    OrderedYieldTests.audit = staticmethod(audit_module.duplicate_harvest_targets)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(OrderedYieldTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({'engine_ref': ENGINE_REF, 'engine_sha256': engine_hashes,
                      'audit_sha256': audit_hash, 'tests_run': result.testsRun,
                      'success': result.wasSuccessful(), 'games': 0, 'policy_calls': 0}))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
