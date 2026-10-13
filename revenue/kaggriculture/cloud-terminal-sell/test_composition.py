# SPDX-License-Identifier: MIT
"""Real visible-input fixture and edge cases for the route/SELL integration."""
import copy
import gzip
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import composition as c

HERE = Path(__file__).resolve().parent
FIXTURE = json.loads(gzip.decompress((HERE / 'test-observations.json.gz').read_bytes()))['snapshots']


def fixture(step=698):
    row = copy.deepcopy(next(x for x in FIXTURE if x['observation']['step'] == step))
    return row['observation'], row['configuration']


def deposit_case(step=717, shed=None, inventories=None):
    obs, cfg = fixture(step)
    me = int(obs['player'])
    farm = obs['farms'][me]
    pos = list(c.terminal.shed_tiles(len(farm['tiles']))[0])
    inventories = inventories or [{'MILK': 8}, {'EGG': 8}]
    farm['farmer'] = pos
    farm['hands'] = [list(pos) for _ in inventories[1:]]
    obs['private']['inventories'] = copy.deepcopy(inventories)
    obs['private']['shed'] = dict(shed or {})
    planner = c.terminal.Planner()
    planner.queues = [[] for _ in inventories]
    planner.last_step = step - 1
    planner.player = me
    return obs, cfg, planner


class CompositionTests(unittest.TestCase):
    def test_parent_exactly_once(self):
        obs, cfg = fixture()
        policy = c.TerminalSell()
        with patch.object(policy.owner.parent, 'act', wraps=policy.owner.parent.act) as counted:
            policy.act(obs, cfg)
        self.assertEqual(counted.call_count, 1)
        self.assertEqual(policy.owner.parent_calls, 1)

    def test_one_parent_constructed(self):
        with patch.object(c.seller.parent, 'Agent', wraps=c.seller.parent.Agent) as counted:
            c.TerminalSell()
        self.assertEqual(counted.call_count, 1)

    def test_before_boundary_exact_frozen_sell(self):
        obs, cfg = fixture(697)
        policy, control = c.TerminalSell(), c.seller.SellScheduler()
        self.assertEqual(policy.act(obs, cfg), control.act(obs, cfg))
        self.assertIsNone(policy.owner.route)
        self.assertIs(policy.owner.R, policy.owner.parent.R)

    def test_no_actor_input_mutation(self):
        obs, cfg = fixture()
        before = copy.deepcopy((obs, cfg))
        c.TerminalSell().act(obs, cfg)
        self.assertEqual((obs, cfg), before)

    def test_frozen_parent_tape_not_modified(self):
        obs, cfg = fixture()
        policy = c.TerminalSell()
        before = copy.deepcopy(policy.owner.parent.R)
        policy.act(obs, cfg)
        self.assertEqual(policy.owner.parent.R, before)

    def test_forecast_does_not_advance_live_planner(self):
        obs, cfg = fixture()
        policy = c.TerminalSell()
        policy.act(obs, cfg)
        before = copy.deepcopy(vars(policy.owner.planner))
        route, snapshots = c.forecast_terminal(obs, cfg, policy.owner.selected_action, policy.owner.planner)
        self.assertEqual(vars(policy.owner.planner), before)
        self.assertEqual(route, policy.owner.route)
        self.assertEqual(snapshots, policy.owner.snapshots)

    def test_current_selected_units_survive_sell(self):
        obs, cfg = fixture()
        policy = c.TerminalSell()
        action = policy.act(obs, cfg)
        for key in ('farmer', 'hands'):
            self.assertEqual(action[key], policy.owner.selected_action[key])
            self.assertEqual(action[key], policy.owner.R[policy.owner.cur][698][key])

    def test_contract_is_detached(self):
        obs, cfg = fixture()
        policy = c.TerminalSell()
        policy.act(obs, cfg)
        original = policy.owner.contract()
        contract = policy.owner.contract()
        contract['snapshots'][0]['post_unit_shed']['MILK'] = 999999
        self.assertEqual(policy.owner.contract(), original)

    def test_forecast_forbids_outside_final_window(self):
        obs, cfg = fixture(697)
        with self.assertRaises(ValueError):
            c.forecast_terminal(obs, cfg, c.PASS, c.terminal.Planner())

    def test_no_after_final_deposit(self):
        obs, cfg, planner = deposit_case(718, inventories=[{'MILK': 8}])
        selected = planner.act(obs, c.PASS, cfg)
        route, snaps = c.forecast_terminal(obs, cfg, selected, planner)
        self.assertEqual(len(route), 719)
        self.assertEqual([(x['step'], x['phase']) for x in snaps], [(718, 'before-market')])
        self.assertEqual(snaps[0]['deposits'], {'MILK': 8})
        self.assertEqual(snaps[0]['post_unit_inventories'], [{}])

    def test_partial_deposits_preserve_overflow(self):
        obs, cfg, planner = deposit_case(shed={'WHEAT': 95})
        selected = planner.act(obs, c.PASS, cfg)
        _, private = c.seller.post_units(obs, selected, cfg)
        self.assertEqual(sum(private['shed'].values()), 100)
        self.assertEqual(sum(sum(x.values()) for x in private['inventories']), 11)
        self.assertNotIn(['DROP'], [selected['farmer'], *selected['hands']])
        _, snaps = c.forecast_terminal(obs, cfg, selected, planner)
        self.assertEqual(sum(snaps[0]['deposits'].values()), 5)
        self.assertEqual(sum(snaps[1]['deposits'].values()), 11)
        self.assertEqual(snaps[1]['admission'], 'conditional-reference-sales')

    def test_arrival_before_sale_cannot_be_rescued_same_turn(self):
        obs, cfg, planner = deposit_case(shed={'MILK': 95}, inventories=[{'EGG': 16}])
        selected = planner.act(obs, c.PASS, cfg)
        route, _ = c.forecast_terminal(obs, cfg, selected, planner)
        policy = c.TerminalSell()
        policy.owner.route = route
        farm, private = c.seller.post_units(obs, selected, cfg)
        ok = policy.execution.receipt_profile(obs, selected, farm, private, 718, 'MILK', cfg)
        self.assertFalse(ok(((718, 95),)))
        self.assertTrue(ok(((717, 95),)))

    def test_last_step_liquidates_same_turn_deposit(self):
        obs, cfg, planner = deposit_case(718, inventories=[{'MILK': 8}])
        policy = c.TerminalSell()
        policy.owner.planner = planner
        action = policy.act(obs, cfg)
        self.assertEqual(action['farmer'], ['DROP'])
        self.assertIn(['SELL', 'MILK', 8], action['market'])

    def test_native_module_without_file_global(self):
        namespace = {}
        exec(compile((HERE / 'main.py').read_bytes(), 'main.py', 'exec'), namespace)
        obs, cfg = fixture()
        cfg['__raw_path__'] = str(HERE / 'main.py')
        self.assertNotIn('__file__', namespace)
        self.assertIsInstance(namespace['agent'](obs, cfg), dict)

    @unittest.skipUnless(os.environ.get('OSPREY_ENGINE_DIR'), 'Set OSPREY_ENGINE_DIR for official-engine comparison')
    def test_exact_post_units_against_official_engine(self):
        base = HERE.parent
        spec = importlib.util.spec_from_file_location('osprey_test_evaluator', base / 'cloud-eval/evaluate.py')
        ev = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = ev
        spec.loader.exec_module(ev)
        engine, _ = ev.get_engine(Path(os.environ['OSPREY_ENGINE_DIR']))
        for row in FIXTURE:
            obs, cfg = copy.deepcopy(row['observation']), row['configuration']
            policy = c.TerminalSell()
            action = policy.act(obs, cfg)
            expected_farm, expected_private = c.seller.post_units(obs, action, cfg)
            farm, private = copy.deepcopy(obs['farms'][obs['player']]), copy.deepcopy(obs['private'])
            for i, act in enumerate([action['farmer'], *action['hands']]):
                engine._apply_unit_action(farm, private, i, act, len(farm['tiles']), obs['step']//24, 24, 100)
            self.assertEqual((farm, private), (expected_farm, expected_private))


if __name__ == '__main__':
    unittest.main()
