"""Discriminating cases using the pinned official interpreter, not a mock engine.

Run with T10_SOURCEPACK set to the verified source pack directory.
"""
import copy
import importlib.util
import os
from pathlib import Path
import sys
import unittest

from labor_capital import HiringAgent, View, project_shift, _units, _configuration

ROOT = Path(os.environ['T10_SOURCEPACK']).resolve()
BASE = ROOT/'commons/revenue/kaggriculture'
spec = importlib.util.spec_from_file_location('t10_eval_engine_tests', BASE/'cloud-eval/evaluate.py')
ev = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ev
spec.loader.exec_module(ev)
ENGINE, HASHES = ev.get_engine(ROOT/'engine')
PASS = {'farmer': ['PASS'], 'hands': [], 'market': []}


class Script:
    def __init__(self, actions):
        self.actions = actions

    def act(self, obs):
        return copy.deepcopy(self.actions.get(obs['step'], PASS))


def observation(step, *, money=100, seat=0):
    farms = [ENGINE._new_farm(10, money) for _ in range(2)]
    return View(step=step, day=step//24, hour=step%24, player=seat,
                farms=farms, private=ENGINE._new_private(),
                market=ENGINE._new_market(), town=ENGINE._new_town())


class OfficialEngineTests(unittest.TestCase):
    def test_hire_at_day_close_is_wasted(self):
        obs = observation(23)
        baseline = dict(PASS, market=[['HIRE']])
        agent = HiringAgent(Script({23: baseline}), ENGINE)
        action = agent.act(obs)
        self.assertEqual(action['market'][0], ['SELL', 'WHEAT', 0])
        self.assertEqual(agent.last_decision['control_cash'], 99)
        self.assertEqual(obs['farms'][0]['money'], 100)

    def test_final_hire_cannot_act_in_same_decision(self):
        obs = observation(718)
        baseline = dict(PASS, hands=[['HARVEST']], market=[['HIRE']])
        projection = project_shift(ENGINE, obs, Script({}), baseline)
        self.assertEqual(projection.horizon_step, 718)
        self.assertTrue(projection.final_cash_only)
        self.assertEqual(projection.estimated_cash, 99)
        self.assertEqual(projection.first_spawn_positions, ((5, 4),))
        self.assertEqual(projection.productive_state['private']['inventories'], [{}, {}])
        self.assertEqual(HiringAgent(Script({718: baseline}), ENGINE).act(obs)['market'][0], ['SELL','WHEAT',0])

    def test_spawn_uses_position_after_current_movement(self):
        obs = observation(22)
        action = {'farmer':['WEST'], 'hands':[], 'market':[['HIRE']]}
        result = project_shift(ENGINE, obs, Script({}), action)
        self.assertEqual(result.first_spawn_positions, ((4, 4),))
        self.assertEqual(result.productive_state['farm']['hands'], [])
        self.assertEqual(result.productive_state['farm']['hires_today'], 0)

    def test_productive_hire_is_retained_for_sale_after_drop(self):
        obs = observation(716)
        animal = ENGINE._new_animal('GOOSE', 0)
        animal['yield_units'] = 3
        obs.farms[0]['tiles'][4][5] = animal
        script = Script({716: dict(PASS, market=[['HIRE']]),
                         717: dict(PASS, hands=[['HARVEST']]),
                         718: dict(PASS, hands=[['DROP']], market=[['SELL','EGG',3]])})
        agent = HiringAgent(script, ENGINE)
        action = agent.act(obs)
        self.assertEqual(action['market'], [['HIRE']])
        self.assertGreater(agent.last_decision['control_cash'], 200)
        self.assertEqual(agent.last_decision['candidate_cash']['omit_hire_suffix_1'], 100)

    def test_dated_cash_does_not_credit_carried_final_goods(self):
        obs = observation(718)
        obs.private['inventories'][0]['EGG'] = 3
        no_drop = project_shift(ENGINE, obs, Script({}), dict(PASS, market=[['SELL','EGG',3]]))
        drop = project_shift(ENGINE, obs, Script({}), {'farmer':['DROP'], 'hands':[], 'market':[['SELL','EGG',3]]})
        self.assertEqual(no_drop.estimated_cash, 100)
        self.assertGreater(drop.estimated_cash, 200)

    def test_ordered_drop_overflow_is_real(self):
        obs = observation(718)
        obs.private['shed']['WHEAT'] = 99
        obs.private['inventories'][0].update({'EGG': 3, 'MILK': 2})
        result = project_shift(ENGINE, obs, Script({}), {'farmer':['DROP'], 'hands':[], 'market':[]})
        self.assertEqual(result.productive_state['private']['shed']['EGG'], 1)
        self.assertEqual(result.productive_state['private']['shed']['MILK'], 0)
        self.assertEqual(result.productive_state['private']['inventories'], [{}])

    def test_atomic_seed_rule_includes_missing_worker_requests(self):
        farm, private = ENGINE._new_farm(10, 100), ENGINE._new_private()
        private['seeds']['WHEAT'] = 1
        action = {'farmer':['PLANT','WHEAT'], 'hands':[['PLANT','WHEAT']], 'market':[]}
        _units(ENGINE, farm, private, action, _configuration(None), 0)
        self.assertIsNone(farm['tiles'][4][4])
        self.assertEqual(private['seeds']['WHEAT'], 1)

    def test_productive_input_change_is_not_called_free_savings(self):
        obs = observation(23, money=20)
        baseline = dict(PASS, market=[['HIRE'], ['BUY_SEED','CARROT',1]])
        agent = HiringAgent(Script({23: baseline}), ENGINE, mode='timed')
        self.assertEqual(agent.act(obs), baseline)
        self.assertEqual(agent.last_decision['selected'], 'baseline')

    def test_zero_cost_hires_preserve_baseline(self):
        obs = observation(23)
        action = dict(PASS, market=[['HIRE']])
        agent = HiringAgent(Script({23: action}), ENGINE, configuration={'farmHandCostMult':0})
        self.assertEqual(agent.act(obs), action)

    def test_player_one_uses_own_private_and_money(self):
        obs = observation(23, money=40, seat=1)
        obs.farms[0]['money'] = 9000
        action = dict(PASS, market=[['HIRE']])
        result = project_shift(ENGINE, obs, Script({}), action)
        self.assertEqual(result.estimated_cash, 39)
        self.assertEqual(result.hiring_outflow, 1)


if __name__ == '__main__':
    unittest.main()

class ObserverTests(unittest.TestCase):
    def test_missing_worker_snapshot(self):
        from run_panel import unit_snapshot
        obs = observation(122)
        snap = unit_snapshot(obs.farms[0], obs.private, 4)
        self.assertTrue(snap['missing_unit'])
        self.assertIsNone(snap['position'])
        self.assertEqual(snap['inventory'], {})
