# SPDX-License-Identifier: Apache-2.0
"""Synthetic delivery contracts against pinned official unit mechanics.

Run with --loader-path, --engine-dir and --audit-path. No policies, game
interpreter, market execution, private trace or random daily refresh is used.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

from day_end_delivery import propose_delivery, guard_delivery


ENGINE_REF = '28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c'
ENGINE_BLOBS = {
    'kaggriculture.py': '3c202c7ee921da239356789e266b694635103fc4',
    'kaggriculture.json': 'b354d06b742fe48402513792253f1a5c29366b20',
    'utils.py': '91c8822ee6201ba4a5a8416c7dbe34f95dd61c87',
}
AUDIT_SHA256 = 'f33df1a1e2c601f3ec454deb736f09c4047f2ed06403c368635d86d4be847a7f'


class DayEndDeliveryTests(unittest.TestCase):
    mechanics = None
    audit = None

    @classmethod
    def setUpClass(cls):
        if cls.mechanics is None or cls.audit is None:
            raise RuntimeError('Run with the retained loader, engine and audit paths')

    @staticmethod
    def row():
        return {'farmer': ['PASS'], 'hands': [['PASS'], ['PASS']], 'market': []}

    def fixture(self, *, now=587):
        farm = self.mechanics._new_farm(10, 3000)
        farm['farmer'] = [0, 0]
        farm['hands'] = [[4, 2], [4, 2]]
        farm['hires_today'] = 2
        farm['unlocked_quadrants'].append('NE')
        for row in farm['tiles'][:5]:
            row[5:] = [None] * 5
        cow = self.mechanics._new_animal('COW', 0)
        cow['yield_units'] = 3
        farm['tiles'][2][4] = cow
        farm['tiles'][2][5] = self.mechanics._new_plant('CARROT', now // 24 - 2, 24)
        private = self.mechanics._new_private()
        private['inventories'] = [{}, {}, {'MILK': 4}]
        observation = {'player': 0, 'step': now, 'day': now // 24,
                       'farms': [farm, self.mechanics._new_farm(10, 4000)],
                       'private': private}
        configuration = {'boardSize': 10, 'turnsPerDay': 24,
                         'shedCapacity': 100, 'episodeSteps': 720}
        route = [self.row() for _ in range(720)]
        route[now]['hands'] = [['HARVEST'], ['HARVEST']]
        suffix = [['EAST'], ['WATER'], ['HARVEST'], ['SOUTH'],
                  ['SOUTH'], ['WEST'], ['NORTH']]
        for step, action in enumerate(suffix, start=now + 1):
            if step < len(route):
                route[step]['hands'][1] = action
        return observation, copy.deepcopy(route[now]), route, configuration

    def proposal(self, obs, selected, route, cfg, **kwargs):
        return propose_delivery(self.mechanics, obs, selected, route, cfg,
                                audit=self.audit, **kwargs)

    def project_official_units(self, obs, rows, cfg):
        """Independently call the retained engine's unit primitive in order."""
        farm = copy.deepcopy(obs['farms'][obs['player']])
        private = copy.deepcopy(obs['private'])
        for offset, row in enumerate(rows):
            step = obs['step'] + offset
            for actor, action in enumerate([row['farmer'], *row['hands']]):
                self.mechanics._apply_unit_action(farm, private, actor, action,
                                                  10, step // 24, 24, 100)
            self.mechanics._decay_plants(farm, step)
        return farm, private

    def reset_delivery(self, state):
        farm, private = copy.deepcopy(state)
        self.mechanics._drop_inventories_to_shed(private, 100)
        farm['farmer'] = list(self.mechanics._default_spawn(10))
        farm['hands'] = []
        farm['hires_today'] = 0
        private['inventories'] = [{}]
        return farm, private

    def guard_fixture(self, *, now=599, shed=88, carried=6):
        obs, selected, _, cfg = self.fixture(now=now)
        obs['farms'][0]['hands'] = [[0, 0], [4, 4]]
        obs['private']['shed']['WHEAT'] = shed
        obs['private']['inventories'] = [{}, {}, {'MILK': carried}]
        selected = self.row()
        selected['hands'][1] = ['DROP']
        return obs, selected, cfg

    def test_terminal_719_has_no_executed_day_end(self):
        for now in (718, 719):
            with self.subTest(now=now):
                obs, selected, route, cfg = self.fixture(now=now)
                plan, report = self.proposal(obs, selected, route, cfg)
                self.assertIsNone(plan)
                self.assertEqual(report['reason'], 'no_executed_day_end')
        obs, selected, cfg = self.guard_fixture(now=719)
        allowed, report = guard_delivery(self.mechanics, obs, selected, 2, cfg)
        self.assertFalse(allowed)
        self.assertEqual(report['reason'], 'not_executed_day_close')

    def test_positive_visible_yield_requires_maturity_and_actual_depletion(self):
        for case in ('empty', 'immature', 'mature'):
            with self.subTest(case=case):
                obs, selected, route, cfg = self.fixture()
                if case == 'empty':
                    obs['farms'][0]['tiles'][2][4]['yield_units'] = 0
                else:
                    planted = obs['day'] - (1 if case == 'immature' else 2)
                    obs['farms'][0]['tiles'][2][4] = self.mechanics._new_plant('CARROT', planted, 24)
                    self.assertEqual(obs['farms'][0]['tiles'][2][4]['yield_units'], 1)
                plan, report = self.proposal(obs, selected, route, cfg)
                self.assertEqual(len(report['structural_duplicates']), 1)
                if case == 'mature':
                    self.assertIsNotNone(plan)
                    self.assertEqual(plan['worker'], 2)
                else:
                    self.assertIsNone(plan)
                    self.assertEqual(report['reason'], 'no_ordered_depletion')

    def test_branch_hire_buy_and_shared_pickup_are_rejected(self):
        cases = [('branch', 'branch_in_window'),
                 ('HIRE', 'economic_obligation_in_window'),
                 ('BUY', 'economic_obligation_in_window'),
                 ('PICKUP', 'shared_pickup_in_window')]
        for case, reason in cases:
            with self.subTest(case=case):
                obs, selected, route, cfg = self.fixture()
                kwargs = {}
                if case == 'branch':
                    kwargs['branch_steps'] = [590]
                elif case == 'PICKUP':
                    route[590]['hands'][0] = ['PICKUP', 'WHEAT', 1]
                else:
                    route[590]['market'] = [[case]] if case == 'HIRE' else [['BUY', 'WHEAT', 1]]
                plan, report = self.proposal(obs, selected, route, cfg, **kwargs)
                self.assertIsNone(plan)
                self.assertEqual(report['reason'], reason)

    def test_extra_slack_preserves_mandatory_tasks_and_drops_at_close(self):
        obs, selected, route, cfg = self.fixture()
        plan, report = self.proposal(obs, selected, route, cfg)
        self.assertTrue(report['admitted'])
        self.assertIsNotNone(plan)
        self.assertEqual(plan['drop_step'], report['day_close'])
        self.assertEqual(plan['drop_step'], 599)
        self.assertEqual(plan['replacement'][-1], ['DROP'])
        self.assertEqual(len(plan['replacement']), 13)
        self.assertEqual(plan['mandatory_tasks'], [
            {'position': [5, 2], 'action': ['WATER'], 'offset': 1},
            {'position': [5, 2], 'action': ['HARVEST'], 'offset': 2}])
        position = list(plan['origin'])
        tasks = []
        moves = {'EAST': (1, 0), 'WEST': (-1, 0),
                 'NORTH': (0, -1), 'SOUTH': (0, 1)}
        for action in plan['replacement']:
            if action[0] in ('WATER', 'HARVEST'):
                tasks.append((list(position), action))
            if action[0] in moves:
                dx, dy = moves[action[0]]
                position = [position[0] + dx, position[1] + dy]
        self.assertEqual(tasks, [([5, 2], ['WATER']), ([5, 2], ['HARVEST'])])
        original = [copy.deepcopy(selected)] + copy.deepcopy(route[588:600])
        replacement = copy.deepcopy(original)
        for row, action in zip(replacement, plan['replacement']):
            row['hands'][1] = copy.deepcopy(action)
        before = self.project_official_units(obs, original, cfg)
        after = self.project_official_units(obs, replacement, cfg)
        self.assertEqual(before[0]['tiles'], after[0]['tiles'])
        self.assertEqual(before[1]['inventories'][:2], after[1]['inventories'][:2])
        self.assertEqual(before[1]['inventories'][2], {'MILK': 4, 'CARROT': 2})
        self.assertEqual(after[1]['inventories'][2], {})
        self.assertEqual(after[1]['shed']['CARROT'], 2)
        self.assertEqual(after[1]['shed']['MILK'], 4)
        self.assertEqual(self.reset_delivery(before), self.reset_delivery(after))

    def test_actual_capacity_overflow_and_same_stage_production_are_rejected(self):
        for harvest in (False, True):
            with self.subTest(harvest=harvest):
                obs, selected, cfg = self.guard_fixture(shed=94 if harvest else 95)
                if harvest:
                    obs['farms'][0]['hands'][0] = [4, 2]
                    selected['hands'][0] = ['HARVEST']
                allowed, report = guard_delivery(self.mechanics, obs, selected, 2, cfg)
                self.assertFalse(allowed)
                self.assertEqual(report['reason'], 'no_sale_capacity_bound')

    def test_actual_day_close_permits_94_without_market_gain_claim(self):
        obs, selected, cfg = self.guard_fixture()
        allowed, report = guard_delivery(self.mechanics, obs, selected, 2, cfg)
        self.assertTrue(allowed)
        self.assertEqual(report['max_stock_without_sales'], 94)
        self.assertEqual(report['deliveries'], [
            {'step': 599, 'actor': 2, 'quantities': {'MILK': 6}}])
        self.assertIsNone(report.get('market_receipt_gain'))
        self.assertNotIn('profit', report)
        farm, private = self.project_official_units(obs, [selected], cfg)
        self.assertEqual(sum(private['shed'].values()), 94)
        self.assertEqual(private['shed']['MILK'], 6)
        self.assertEqual(farm['money'], 3000)
        obs['step'] = 598
        allowed, report = guard_delivery(self.mechanics, obs, selected, 2, cfg)
        self.assertFalse(allowed)
        self.assertEqual(report['reason'], 'not_executed_day_close')

    def test_actual_delivery_declines_new_market_resource_obligations(self):
        for order in (['HIRE'], ['BUY_PRODUCT', 'WHEAT', 1],
                      ['BUY_ANIMAL', 'COW', 1], ['BUY_LAND']):
            with self.subTest(order=order):
                obs, selected, cfg = self.guard_fixture()
                selected['market'] = [order]
                before = copy.deepcopy((obs, selected, cfg))
                allowed, report = guard_delivery(self.mechanics, obs, selected, 2, cfg)
                self.assertFalse(allowed)
                self.assertEqual(report['reason'], 'economic_obligation_at_delivery')
                self.assertEqual((obs, selected, cfg), before)

    def test_proposal_is_conditional_and_does_not_claim_sale_gain(self):
        obs, selected, route, cfg = self.fixture()
        obs['private']['shed']['WHEAT'] = 97
        route[599]['market'] = [['SELL', 'MILK', 100]]
        plan, report = self.proposal(obs, selected, route, cfg)
        self.assertTrue(report['admitted'])
        self.assertTrue(plan['delivery_conditional_on_actual_capacity'])
        self.assertEqual(plan['max_stock_without_sales'], 106)
        self.assertIn('market_receipt_gain', report)
        self.assertIsNone(report['market_receipt_gain'])
        self.assertEqual(plan['delivered'], {'MILK': 4, 'CARROT': 2})

    def test_inputs_are_unchanged_and_proposal_is_detached(self):
        obs, selected, route, cfg = self.fixture()
        branches = [586, 600]
        before = copy.deepcopy((obs, selected, route, cfg, branches))
        plan, report = self.proposal(obs, selected, route, cfg, branch_steps=branches)
        self.assertTrue(report['admitted'])
        self.assertEqual((obs, selected, route, cfg, branches), before)
        plan['replacement'][0][0] = 'PASS'
        plan['mandatory_tasks'][0]['action'][0] = 'PASS'
        plan['origin'][0] = 9
        report['structural_duplicates'][0]['position'][0] = 9
        self.assertEqual((obs, selected, route, cfg, branches), before)
        obs, selected, cfg = self.guard_fixture()
        before = copy.deepcopy((obs, selected, cfg))
        allowed, report = guard_delivery(self.mechanics, obs, selected, 2, cfg)
        self.assertTrue(allowed)
        report['deliveries'][0]['quantities']['MILK'] = 1000
        self.assertEqual((obs, selected, cfg), before)


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
    loader = load_file(args.loader_path, 'delivery_retained_loader')
    if loader.ENGINE_REF != ENGINE_REF:
        parser.error('Pinned loader engine reference mismatch')
    DayEndDeliveryTests.mechanics, _ = loader.get_engine(args.engine_dir)
    audit_module = load_file(args.audit_path, 'delivery_retained_audit')
    DayEndDeliveryTests.audit = staticmethod(audit_module.duplicate_harvest_targets)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(DayEndDeliveryTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({'engine_ref': ENGINE_REF, 'engine_sha256': engine_hashes,
                      'audit_sha256': audit_hash, 'tests_run': result.testsRun,
                      'success': result.wasSuccessful(), 'games': 0, 'policy_calls': 0}))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
