# SPDX-License-Identifier: Apache-2.0
import ast
import copy
import hashlib
import json
from pathlib import Path
import unittest
from features import extract, predict
from runtime import HERE, Portfolio, make_agent, load


class PortfolioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads((HERE / 'fixtures/checkpoint-observations.json').read_text())

    def test_pins_and_static_feature_boundary(self):
        base = HERE / 'vendor/t08/vendor/sell/reference/next-panel/vendor/arlene.py'
        self.assertEqual(hashlib.sha256(base.read_bytes()).hexdigest(), '1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4')
        tree = ast.parse(base.read_text())
        callers = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == '_feature']
        self.assertEqual(len(callers), 1)
        parent = load(base, 't14_test_parent')
        self.assertEqual([(t, f) for t, f, _, _ in parent.DECISIONS if f == 'px_CARROT'], [(360, 'px_CARROT')])
        self.assertEqual(hashlib.sha256((HERE / 'vendor/t08/vendor/carrot/carrot_demand.py').read_bytes()).hexdigest(), 'ffcea52d086283d4b466f26ccec1e0d563687a7dab225f9c528c8313138a2cd0')

    def test_feature_leakage_and_missing(self):
        obs = copy.deepcopy(self.fixture['0'])
        expected = extract(obs)
        obs.update(seed=123, outcome='W', opponent='apex', future_shops=['PET_CAFE'])
        self.assertEqual(extract(obs), expected)
        del obs['market']['prices']['CARROT']
        self.assertIsNone(extract(obs)['price_CARROT'])
        self.assertNotIn('seed', expected)

    def test_tree_missing_and_boundary(self):
        tree = {'feature': 'x', 'threshold': 2, 'missing': 'right', 'left': {'policy': 'sell'}, 'right': {'policy': 'carrot_sell'}}
        self.assertEqual(predict(tree, {'x': 2}), 'sell')
        self.assertEqual(predict(tree, {}), 'carrot_sell')

    def test_no_extra_parent_or_state_reset_at_selection(self):
        portfolio = Portfolio({'policy': 'carrot_sell'})
        original = portfolio.policy
        parent = original.controller
        original.pending['MILK'] = 13
        original.planned['MILK'] = [(362, 13)]
        original.previous = {'sentinel': True}
        before_parent_state = copy.deepcopy(parent.__dict__)
        portfolio._select(self.fixture['360'])
        self.assertIs(portfolio.policy, original)
        self.assertIs(portfolio.policy.controller, parent)
        self.assertEqual(parent.__dict__, before_parent_state)
        self.assertEqual(original.pending['MILK'], 13)
        self.assertEqual(original.planned['MILK'], [(362, 13)])
        self.assertEqual(original.previous, {'sentinel': True})
        self.assertEqual(portfolio.selection['step'], 360)

    def test_nonsequential_first_observation(self):
        portfolio = Portfolio({'policy': 'sell'})
        with self.assertRaises(ValueError):
            portfolio.act(self.fixture['360'])

    def test_single_live_call_and_match_reset(self):
        entry = make_agent({'policy': 'sell'}, checkpoint=0)
        entry(copy.deepcopy(self.fixture['0']))
        first = entry.portfolio
        self.assertEqual(first.last_step, 0)
        entry(copy.deepcopy(self.fixture['0']))
        self.assertIsNot(first, entry.portfolio)
        self.assertEqual(entry.portfolio.last_step, 0)

    def test_step0_seeds_are_observationally_identical(self):
        ev = load(HERE / 'vendor/cloud-eval/evaluate.py', 't14_step0_eval')
        engine, _ = ev.get_engine(HERE / 'vendor/engine')
        samples = []
        for seed in (1, 2):
            cfg = ev.Struct({k: v.get('default') if isinstance(v, dict) else v for k, v in engine.specification['configuration'].items()})
            cfg.seed = seed
            state = [ev.Struct(observation=ev.Struct(), action={}, status='ACTIVE', reward=0) for _ in range(2)]
            env = ev.Struct(configuration=cfg, done=False, info={})
            engine.interpreter(state, env)
            self.assertIsNone(cfg.seed)
            samples.append(extract(state[0].observation))
        self.assertEqual(*samples)


if __name__ == '__main__':
    unittest.main()
