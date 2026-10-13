"""Official money representation regression; no tournament games are run here."""
from __future__ import annotations
import copy
import importlib.util
import os
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get('TITAN_REPOSITORY_ROOT', HERE.parents[3]))
AREA = ROOT / 'revenue/kaggriculture'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


funding = load(Path(os.environ.get('TITAN_FUNDING_FILE', AREA / 'cloud-integration-differentials/seed_funding.py')), 'cash_number_funding')
ev = load(Path(os.environ.get('TITAN_EVALUATOR_FILE', AREA / 'cloud-eval/evaluate.py')), 'cash_number_evaluator')


class CashNumberTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine, _ = ev.get_engine(Path(os.environ['KAG_ENGINE_DIR']))

    def states(self, cash=40319):
        cfg = ev.Struct({k: v.get('default') if isinstance(v, dict) else v
                         for k, v in self.engine.specification['configuration'].items()})
        cfg.seed = 7  # Deterministic manufactured initialization, not a scored seed.
        cfg.startingMoney = cash
        env = ev.Struct(configuration=cfg, done=False, info={})
        states = [ev.Struct(observation=ev.Struct(), action={}, status='ACTIVE', reward=0) for _ in range(2)]
        self.engine.interpreter(states, env)
        return states, env

    def inputs(self, cash=40319, player=0):
        states, env = self.states(cash)
        # These scalar amounts/queue shape came from development9965001 at600.
        # The complete farm in this unit test is manufactured, not that replay.
        base = {'farmer':['PASS'], 'hands':[], 'market':[['BUY_SEED','WHEAT',17], *[['HIRE'] for _ in range(7)]]}
        proposed = copy.deepcopy(base)
        proposed['market'][0] = ['BUY_SEED','WHEAT',3]
        return states, env, base, proposed

    def test_official_float_money_certifies(self):
        for player in (0, 1):
            states, env, base, proposed = self.inputs(player=player)
            obs = states[player].observation
            self.assertIsInstance(obs.farms[player]['money'], float)
            chosen, report = funding.select_seed_queue(self.engine, obs, base, proposed, env.configuration)
            self.assertEqual(report['status'], 'certified')
            self.assertEqual(chosen, proposed)
            self.assertEqual(report['paired_current_market_cash_delta'], 140)

    def test_both_player_market_states_preserved(self):
        for player in (0, 1):
            states, env, base, proposed = self.inputs(player=player)
            chosen, report = funding.select_seed_queue(self.engine, states[player].observation, base, proposed, env.configuration)
            left, right = copy.deepcopy(states), copy.deepcopy(states)
            left[player].action, right[player].action = base, chosen
            self.engine._process_market(left, env)
            self.engine._process_market(right, env)
            self.assertEqual(right[player].observation.farms[player]['money']-left[player].observation.farms[player]['money'], 140)
            right[player].observation.farms[player]['money'] -= 140
            right[player].observation.private['seeds']['WHEAT'] += 14
            for i in (0, 1):
                right[i].action = copy.deepcopy(left[i].action)
            self.assertEqual(left, right)

    def test_integer_and_float_reports_match(self):
        for cash in (0, 1, 130, 40319, 41478, 2**53):
            states, env, base, proposed = self.inputs(cash)
            obs = states[0].observation
            float_report = funding.certify_seed_funding(self.engine, obs, base, proposed, env.configuration)
            obs.farms[0]['money'] = int(obs.farms[0]['money'])
            integer_report = funding.certify_seed_funding(self.engine, obs, base, proposed, env.configuration)
            self.assertEqual(float_report, integer_report)

    def test_fractional_nonfinite_or_negative_not_coerced(self):
        for cash in (True, False, '40319', None, -1, -1.0, 0.1, 499.5, float('inf'), float('-inf'), float('nan')):
            states, env, base, proposed = self.inputs()
            states[0].observation.farms[0]['money'] = cash
            chosen, report = funding.select_seed_queue(self.engine, states[0].observation, base, proposed, env.configuration)
            with self.subTest(cash=repr(cash)):
                self.assertEqual(report['status'], 'not_certified')
                self.assertEqual(chosen, base)

    def test_underfunded_float_preserves_selected(self):
        states, env, base, proposed = self.inputs(130)
        chosen, report = funding.select_seed_queue(self.engine, states[0].observation, base, proposed, env.configuration)
        self.assertEqual(report['reason'], 'original_queue_needs_additional_cash')
        self.assertEqual(chosen, base)

    def test_counts_remain_integer_only(self):
        for value in (1.0, 2.0, True, '1'):
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                funding._whole(value, 'count')
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                funding._quantity(['BUY_SEED','WHEAT',value])

    def test_input_is_unchanged(self):
        states, env, base, proposed = self.inputs()
        before = copy.deepcopy((states, base, proposed))
        funding.select_seed_queue(self.engine, states[0].observation, base, proposed, env.configuration)
        self.assertEqual((states, base, proposed), before)

    def test_product_bound_remains_separate(self):
        states, env, base, proposed = self.inputs()
        base['market'].append(['BUY_PRODUCT','WHEAT',1])
        proposed['market'].append(['BUY_PRODUCT','WHEAT',1])
        chosen, report = funding.select_seed_queue(self.engine, states[0].observation, base, proposed, env.configuration)
        self.assertEqual(report['status'],'not_certified')
        self.assertIn('paired-flow', report['reason'])
        self.assertEqual(chosen,base)


if __name__ == '__main__':
    unittest.main()
