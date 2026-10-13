# SPDX-License-Identifier: Apache-2.0
"""Synthetic runtime-hook checks; actual official units, no native policies.

Use --loader-path, --engine-dir and --audit-path as in the delivery tests.
The fake agent mirrors the public TitanAgent/controller hook signatures only.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from runtime import SourceContractMismatch, attach
from test_day_end_delivery import (AUDIT_SHA256, ENGINE_BLOBS, ENGINE_REF,
                                   DayEndDeliveryTests, load_file)


class FakeController:
    def __init__(self, route):
        self.R = [copy.deepcopy(route)]
        self.cur = 0
        self.calls = []
        self.inspect = None

    def act(self, obs):
        if self.inspect is not None:
            self.inspect(obs)
        current = copy.deepcopy(self.R[self.cur][obs['step']])
        self.calls.append({'step': obs['step'], 'current': current,
                           'day_close': copy.deepcopy(self.R[self.cur][599])})
        return copy.deepcopy(current)


class FakeAgent:
    def __init__(self, route):
        self.features = SimpleNamespace(spatial_pathing=False, spatial_tempo=False,
                                        fourth_quadrant=False, terminal_route=False,
                                        market_pressure=True, consumer='frozen')
        self.route = copy.deepcopy(route)
        self.ready = False
        self.controller = None
        self.production = None
        self.diagnostics = {}
        self.initialize_calls = 0
        self.act_calls = 0
        self.finish_calls = []
        self.sell_inputs = []
        self.return_transform = None

    def _initialize(self):
        self.initialize_calls += 1
        self.controller = FakeController(self.route)
        self.production = self.controller
        self.ready = True
        return 'original-initialize-result'

    def _finish_production(self, obs, returned):
        self.finish_calls.append((copy.deepcopy(obs), copy.deepcopy(returned)))
        return 'original-finish-result'

    def act(self, observation, configuration=None, *, entry_started=None):
        self.act_calls += 1
        if not self.ready:
            self._initialize()
        selected = self.production.act(observation)
        self.sell_inputs.append(copy.deepcopy(selected))
        returned = copy.deepcopy(selected)
        if self.return_transform is not None:
            returned = self.return_transform(observation, returned)
        self._finish_production(observation, returned)
        return returned


class RuntimeTests(unittest.TestCase):
    mechanics = None
    audit = None

    @classmethod
    def setUpClass(cls):
        if cls.mechanics is None or cls.audit is None:
            raise RuntimeError('Run with the retained loader, engine and audit paths')

    def setup_case(self, *, shed=0):
        fixture = DayEndDeliveryTests()
        fixture.mechanics = self.mechanics
        fixture.audit = self.audit
        obs, selected, route, cfg = fixture.fixture()
        obs['private']['shed']['WHEAT'] = shed
        route[600]['market'] = [['HIRE']]
        agent = FakeAgent(route)
        state = attach(agent, self.mechanics, self.audit)
        return fixture, obs, cfg, agent, state

    def advance(self, fixture, obs, action, cfg):
        farm, private = fixture.project_official_units(obs, [action], cfg)
        result = copy.deepcopy(obs)
        result['farms'][result['player']] = farm
        result['private'] = private
        result['step'] += 1
        result['day'] = result['step'] // 24
        return result

    def test_future_drop_is_hidden_and_market_only_change_can_commit(self):
        _, obs, cfg, agent, state = self.setup_case()
        def market_change(observation, selected):
            selected['market'] = [['SELL', 'MILK', 1]]
            return selected
        agent.return_transform = market_change
        returned = agent.act(obs, cfg, entry_started=123.0)
        self.assertEqual(returned['hands'][1], ['EAST'])
        self.assertIsNotNone(state.plan)
        self.assertEqual(agent.controller.R[0][599]['hands'][1], ['PASS'])
        self.assertEqual(agent.controller.calls[0]['day_close']['hands'][1], ['PASS'])
        self.assertEqual(returned['market'], [['SELL', 'MILK', 1]])
        self.assertEqual(agent.act_calls, 1)
        self.assertEqual(len(agent.finish_calls), 1)
        self.assertTrue(state.candidate_reports)

    def test_actual_guard_installs_drop_before_original_controller_and_sell(self):
        fixture, obs, cfg, agent, state = self.setup_case(shed=85)
        for step in range(587, 599):
            self.assertEqual(obs['step'], step)
            returned = agent.act(obs, cfg)
            self.assertEqual(agent.controller.R[0][599]['hands'][1], ['PASS'])
            obs = self.advance(fixture, obs, returned, cfg)
        self.assertIsNotNone(state.plan)
        returned = agent.act(obs, cfg)
        self.assertEqual(returned['hands'][1], ['DROP'])
        self.assertEqual(agent.controller.calls[-1]['current']['hands'][1], ['DROP'])
        self.assertEqual(agent.sell_inputs[-1]['hands'][1], ['DROP'])
        farm, private = fixture.project_official_units(obs, [returned], cfg)
        self.assertEqual(sum(private['shed'].values()), 91)
        self.assertEqual(sum(private['shed'].values())
                         + sum(sum(inv.values()) for inv in private['inventories']), 94)
        self.assertEqual(private['inventories'][2], {})
        self.assertEqual(farm['money'], obs['farms'][0]['money'])

    def test_other_worker_mismatch_prevents_all_unit_commit(self):
        _, obs, cfg, agent, state = self.setup_case()
        def other_worker_change(observation, selected):
            selected['hands'][0] = ['PASS']
            return selected
        agent.return_transform = other_worker_change
        returned = agent.act(obs, cfg)
        self.assertEqual(returned['hands'][1], ['EAST'])
        self.assertIsNone(state.plan)
        self.assertEqual(agent.controller.R[0][588]['hands'][1], ['EAST'])
        self.assertEqual(agent.controller.R[0][599]['hands'][1], ['PASS'])

    def test_selected_joint_overflow_fails_closed_after_one_producer_call(self):
        for case in ('producer_mismatch', 'ordinary_refusal'):
            with self.subTest(case=case):
                fixture, obs, cfg, agent, state = self.setup_case(shed=90)
                extra_cow = self.mechanics._new_animal('COW', 0)
                extra_cow['yield_units'] = 3
                obs['farms'][0]['tiles'][0][0] = extra_cow
                for step in range(587, 599):
                    returned = agent.act(obs, cfg)
                    obs = self.advance(fixture, obs, returned, cfg)
                self.assertEqual(obs['step'], 599)
                self.assertEqual(sum(obs['private']['shed'].values()) + sum(
                    sum(inv.values()) for inv in obs['private']['inventories']), 99)
                calls_before = len(agent.controller.calls)
                sell_before = len(agent.sell_inputs)
                finish_before = len(agent.finish_calls)
                if case == 'producer_mismatch':
                    def producer_intervention(observation):
                        row = agent.controller.R[agent.controller.cur][599]
                        self.assertEqual(row['hands'][1], ['DROP'])
                        self.assertEqual(row['farmer'], ['PASS'])
                        row['farmer'] = ['HARVEST']
                    agent.controller.inspect = producer_intervention
                    with self.assertRaises(SourceContractMismatch):
                        agent.act(obs, cfg)
                    self.assertEqual(len(agent.controller.calls), calls_before + 1)
                    self.assertEqual(agent.controller.calls[-1]['current']['farmer'], ['HARVEST'])
                    self.assertEqual(len(agent.sell_inputs), sell_before)
                    self.assertEqual(len(agent.finish_calls), finish_before)
                else:
                    obs['private']['shed']['WHEAT'] += 2
                    returned = agent.act(obs, cfg)
                    self.assertEqual(returned['hands'][1], ['PASS'])
                    self.assertEqual(agent.controller.calls[-1]['current']['hands'][1], ['PASS'])
                    self.assertEqual(len(agent.controller.calls), calls_before + 1)
                    self.assertEqual(len(agent.sell_inputs), sell_before + 1)
                    self.assertEqual(len(agent.finish_calls), finish_before + 1)

    def test_fake_return_cancels_pending_plan_and_restores_route(self):
        _, obs, cfg, agent, state = self.setup_case()
        original = copy.deepcopy(agent.route)
        def fallback(observation, selected):
            return {'farmer': ['PASS'], 'hands': [['PASS'], ['PASS']], 'market': []}
        agent.return_transform = fallback
        returned = agent.act(obs, cfg)
        self.assertEqual(returned['hands'][1], ['PASS'])
        self.assertIsNone(state.plan)
        self.assertEqual(agent.controller.R[0], original)

    def test_recovery_uses_observed_position_before_remaining_task(self):
        fixture, obs, cfg, agent, state = self.setup_case()
        returned = agent.act(obs, cfg)
        obs = self.advance(fixture, obs, returned, cfg)
        self.assertIsNotNone(state.plan)
        # A synthetic externally observed divergence, not an interpreter replay.
        obs['farms'][0]['hands'][1] = [3, 2]
        returned = agent.act(obs, cfg)
        self.assertEqual(returned['hands'][1], ['EAST'])
        obs = self.advance(fixture, obs, returned, cfg)
        returned = agent.act(obs, cfg)
        self.assertEqual(returned['hands'][1], ['EAST'])
        obs = self.advance(fixture, obs, returned, cfg)
        returned = agent.act(obs, cfg)
        self.assertEqual(returned['hands'][1], ['WATER'])

    def test_missed_stationary_water_is_recovered_at_same_position(self):
        fixture, obs, cfg, agent, state = self.setup_case()
        returned = agent.act(obs, cfg)
        obs = self.advance(fixture, obs, returned, cfg)
        self.assertEqual(obs['farms'][0]['hands'][1], [5, 2])
        def miss_water(observation, selected):
            self.assertEqual(selected['hands'][1], ['WATER'])
            selected['hands'][1] = ['PASS']
            return selected
        agent.return_transform = miss_water
        returned = agent.act(obs, cfg)
        obs = self.advance(fixture, obs, returned, cfg)
        self.assertEqual(obs['farms'][0]['hands'][1], [5, 2])
        self.assertFalse(obs['farms'][0]['tiles'][2][5]['watered_today'])
        agent.return_transform = None
        returned = agent.act(obs, cfg)
        self.assertEqual(returned['hands'][1], ['WATER'])
        obs = self.advance(fixture, obs, returned, cfg)
        self.assertTrue(obs['farms'][0]['tiles'][2][5]['watered_today'])
        returned = agent.act(obs, cfg)
        self.assertEqual(returned['hands'][1], ['HARVEST'])
        obs = self.advance(fixture, obs, returned, cfg)
        self.assertEqual(obs['private']['inventories'][2]['CARROT'], 2)

    def test_day_600_expiry_precedes_hire_and_clears_plan(self):
        _, obs, cfg, agent, state = self.setup_case()
        agent.act(obs, cfg)
        self.assertIsNotNone(state.plan)
        obs['step'] = 600
        obs['day'] = 25
        obs['farms'][0]['hands'] = []
        obs['farms'][0]['hires_today'] = 0
        obs['private']['inventories'] = [{}]
        seen = []
        agent.controller.inspect = lambda observation: seen.append(state.plan)
        returned = agent.act(obs, cfg)
        self.assertEqual(seen, [None])
        self.assertIsNone(state.plan)
        self.assertEqual(returned['market'], [['HIRE']])
        self.assertEqual(agent.sell_inputs[-1]['market'], [['HIRE']])

    def test_producer_replaced_water_is_recovered_after_exact_return(self):
        fixture, obs, cfg, agent, state = self.setup_case()
        returned = agent.act(obs, cfg)
        obs = self.advance(fixture, obs, returned, cfg)
        self.assertEqual(obs['step'], 588)
        self.assertEqual(obs['farms'][0]['hands'][1], [5, 2])
        def producer_intervention(observation):
            if observation['step'] == 588:
                row = agent.controller.R[agent.controller.cur][588]
                self.assertEqual(row['hands'][1], ['WATER'])
                row['hands'][1] = ['PASS']
        agent.controller.inspect = producer_intervention
        returned = agent.act(obs, cfg)
        self.assertEqual(returned['hands'][1], ['PASS'])
        self.assertEqual(returned, agent.sell_inputs[-1])
        self.assertEqual(returned, agent.finish_calls[-1][1])
        self.assertIsNotNone(state.plan)
        obs = self.advance(fixture, obs, returned, cfg)
        self.assertEqual(obs['step'], 589)
        self.assertEqual(obs['farms'][0]['hands'][1], [5, 2])
        self.assertFalse(obs['farms'][0]['tiles'][2][5]['watered_today'])
        returned = agent.act(obs, cfg)
        self.assertEqual(returned['hands'][1], ['WATER'])
        obs = self.advance(fixture, obs, returned, cfg)
        self.assertTrue(obs['farms'][0]['tiles'][2][5]['watered_today'])

    def test_original_hooks_are_preserved_and_rebuild_installs_once(self):
        fixture, obs, cfg, agent, state = self.setup_case()
        self.assertEqual(agent._initialize(), 'original-initialize-result')
        returned = agent.act(obs, cfg)
        self.assertEqual(len(agent.controller.calls), 1)
        obs = self.advance(fixture, obs, returned, cfg)
        old_controller = agent.controller
        self.assertEqual(agent._initialize(), 'original-initialize-result')
        self.assertIsNot(agent.controller, old_controller)
        self.assertEqual(agent.initialize_calls, 2)
        returned = agent.act(obs, cfg)
        self.assertEqual(returned['hands'][1], ['WATER'])
        self.assertEqual(len(agent.controller.calls), 1)
        self.assertEqual(agent.act_calls, 2)
        self.assertEqual(len(agent.finish_calls), 2)
        self.assertIsNotNone(state.plan)
        self.assertEqual(agent._finish_production(obs, returned), 'original-finish-result')
        self.assertEqual(len(agent.finish_calls), 3)

    def test_conflicting_route_flags_rejected_before_hook_changes(self):
        fixture = DayEndDeliveryTests()
        fixture.mechanics = self.mechanics
        _, _, route, _ = fixture.fixture()
        for flag in ('spatial_pathing', 'spatial_tempo', 'fourth_quadrant', 'terminal_route'):
            with self.subTest(flag=flag):
                agent = FakeAgent(route)
                setattr(agent.features, flag, True)
                initialize = agent._initialize
                finish = agent._finish_production
                act = agent.act
                with self.assertRaises(ValueError):
                    attach(agent, self.mechanics, self.audit)
                self.assertEqual(agent._initialize, initialize)
                self.assertEqual(agent._finish_production, finish)
                self.assertEqual(agent.act, act)


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
    loader = load_file(args.loader_path, 'runtime_retained_loader')
    if loader.ENGINE_REF != ENGINE_REF:
        parser.error('Pinned loader engine reference mismatch')
    RuntimeTests.mechanics, _ = loader.get_engine(args.engine_dir)
    audit_module = load_file(args.audit_path, 'runtime_retained_audit')
    RuntimeTests.audit = staticmethod(audit_module.duplicate_harvest_targets)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(RuntimeTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({'engine_ref': ENGINE_REF, 'engine_sha256': engine_hashes,
                      'audit_sha256': audit_hash, 'tests_run': result.testsRun,
                      'success': result.wasSuccessful(), 'games': 0, 'policy_calls': 0}))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
