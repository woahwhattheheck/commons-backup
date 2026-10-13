# SPDX-License-Identifier: Apache-2.0
"""E13 funded-prefix working-capital regressions."""
import copy
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

_LAB = Path(__file__).resolve().parent
for _extra in (_LAB.parent / 'cloud-runtime-pulse', _LAB.parent / 'cloud-quickstep'):
    _path = str(_extra)
    if _path not in sys.path:
        sys.path.append(_path)

import frozen_selected as fs
import titan_runtime as tr


class FundedPrefixTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            'shedCapacity': 100,
            'farmHandCostMult': 1,
            'maxMarketOrdersPerTurn': 10,
            'turnsPerDay': 24,
            'episodeSteps': 720,
        }
        self.now = 5
        self.inventory = {item: 10000 for item in fs.m.PRODUCTS}
        self.farm = {
            'money': 0,
            'farmer': [4, 4],
            'unlocked_quadrants': ['SOUTHEAST'],
            'hires_today': 0,
            'tiles': [[None for _ in range(10)] for _ in range(10)],
            'hands': [],
        }
        shed = {item: 0 for item in fs.m.PRODUCTS + list(fs.m.ANIMALS)}
        self.private = {
            'shed': shed,
            'seeds': {item: 0 for item in fs.m.CROPS},
            'inventories': [{}],
        }
        self.obs = {
            'step': self.now,
            'player': 0,
            'market': {'inventory': self.inventory, 'params': None},
        }
        self.route = [{} for _ in range(32)]

    def minimum(self, market, current, item='MILK', end=None):
        base = {'market': copy.deepcopy(market)}
        targets = {name: max(0, int(q)) for name, q in self.private['shed'].items()
                   if name in fs.PRODUCTS and q > 0}
        return fs.funded_minimum_now(
            self.obs, self.config, base, self.farm, self.private,
            self.route, self.now if end is None else end,
            current, targets, item,
        )

    def test_sale_before_buy_funds_only_needed_units(self):
        self.private['shed']['MILK'] = 10
        minimum, certificate = self.minimum(
            [['SELL', 'MILK', 10], ['BUY_ANIMAL', 'COW', 1]], {'MILK': 10})
        self.assertEqual(minimum, 3)
        self.assertEqual(certificate['reference_acquisitions'], 1)
        self.assertFalse(certificate['fallback'])

    def test_later_sale_never_prefunds_earlier_buy(self):
        self.private['shed']['MILK'] = 10
        minimum, certificate = self.minimum(
            [['BUY_ANIMAL', 'COW', 1], ['SELL', 'MILK', 10]], {'MILK': 10})
        self.assertEqual(minimum, 0)
        self.assertEqual(certificate['reference_acquisitions'], 0)

    def test_clipped_purchase_does_not_reserve_impossible_tail(self):
        self.farm['money'] = 1000
        self.private['shed']['MILK'] = 10
        self.private['shed']['WHEAT'] = 89
        minimum, certificate = self.minimum(
            [['BUY_ANIMAL', 'COW', 5], ['SELL', 'MILK', 10]], {'MILK': 10})
        self.assertEqual(minimum, 0)
        self.assertEqual(certificate['reference_acquisitions'], 1)

    def test_input_price_stress_is_part_of_certificate(self):
        self.private['shed']['MILK'] = 3
        minimum, certificate = self.minimum(
            [['SELL', 'MILK', 3], ['BUY_PRODUCT', 'FERTILIZER', 3]], {'MILK': 3})
        self.assertEqual(minimum, 3)
        self.assertEqual(certificate['stress_units'], 32)
        self.assertFalse(certificate['fallback'])

    def test_future_sale_bounds_commitment_prefix(self):
        self.private['shed']['MILK'] = 10
        self.private['shed']['WOOL'] = 1
        self.route[self.now + 1] = {'market': [['SELL', 'WOOL', 1]]}
        self.route[self.now + 2] = {'market': [['BUY_ANIMAL', 'COW', 1]]}
        minimum, certificate = self.minimum(
            [['SELL', 'MILK', 10]], {'MILK': 10}, end=self.now + 2)
        self.assertEqual(minimum, 0)
        self.assertEqual(certificate['funding_turn'], self.now + 1)
        self.assertEqual(certificate['prefix_end'], self.now)

    def test_purchase_before_next_funding_event_is_preserved(self):
        self.private['shed']['MILK'] = 10
        self.private['shed']['WOOL'] = 1
        self.route[self.now + 1] = {'market': [['BUY_ANIMAL', 'COW', 1]]}
        self.route[self.now + 2] = {'market': [['SELL', 'WOOL', 1]]}
        minimum, certificate = self.minimum(
            [['SELL', 'MILK', 10]], {'MILK': 10}, end=self.now + 2)
        self.assertEqual(minimum, 3)
        self.assertEqual(certificate['funding_turn'], self.now + 2)

    def test_zero_fill_future_sale_does_not_terminate_prefix(self):
        """A requested future SELL with no executable shed stock is not cash."""
        self.private['shed']['MILK'] = 10
        self.route[self.now + 1] = {'market': [['SELL', 'WOOL', 1]]}
        self.route[self.now + 2] = {'market': [['BUY_ANIMAL', 'COW', 1]]}
        minimum, certificate = self.minimum(
            [['SELL', 'MILK', 10]], {'MILK': 10}, end=self.now + 2)
        self.assertEqual(minimum, 3)
        self.assertEqual(certificate['reference_acquisitions'], 1)
        self.assertIsNone(certificate['funding_turn'])
        self.assertEqual(certificate['prefix_end'], self.now + 2)
        self.assertFalse(certificate['fallback'])

    def test_zero_fill_does_not_hide_later_executable_funding_event(self):
        self.private['shed']['MILK'] = 10
        self.private['shed']['EGG'] = 1
        self.route[self.now + 1] = {'market': [['SELL', 'WOOL', 1]]}
        self.route[self.now + 2] = {'market': [['BUY_ANIMAL', 'COW', 1]]}
        self.route[self.now + 3] = {'market': [['SELL', 'EGG', 1]]}
        minimum, certificate = self.minimum(
            [['SELL', 'MILK', 10]], {'MILK': 10}, end=self.now + 3)
        self.assertEqual(minimum, 3)
        self.assertEqual(certificate['reference_acquisitions'], 1)
        self.assertEqual(certificate['funding_turn'], self.now + 3)
        self.assertEqual(certificate['prefix_end'], self.now + 2)
        self.assertFalse(certificate['fallback'])


class SeedRuntimePrefixTests(unittest.TestCase):
    class ReducingBudget:
        def __init__(self):
            self.calls = 0

        def apply(self, selected, seeds, step, current, maximum, *, extra_requests=None):
            self.calls += 1
            result = copy.deepcopy(selected)
            result['market'][0] = ['BUY_SEED', 'WHEAT', 1]
            return result

    class PassthroughBudget:
        def __init__(self):
            self.calls = 0

        def apply(self, selected, seeds, step, current, maximum, *, extra_requests=None):
            self.calls += 1
            return copy.deepcopy(selected)

    class RejectingFunding:
        def __init__(self):
            self.calls = 0

        def select_seed_queue(self, mechanics, post, original, proposed, config):
            self.calls += 1
            return copy.deepcopy(original), {'applied': False, 'reason': 'test_rejection'}

    def make_agent(self, budget):
        agent = object.__new__(tr.TitanAgent)
        agent.features = tr.Features(seed=True, funding=True)
        agent.consumer = SimpleNamespace(selected_post_units=(
            {'money': 0}, {'seeds': {'WHEAT': 0}}
        ))
        agent.seed_budget = budget
        agent.controller = SimpleNamespace(cur='route')
        agent.spatial = None
        agent.funding_module = self.RejectingFunding()
        agent.diagnostics = {}
        return agent

    @staticmethod
    def observation():
        return {'step': 0, 'player': 0, 'farms': [{}, {}], 'private': {}}

    def test_inert_raw_tail_dependency_cannot_flip_seed_acceptance(self):
        cfg = {'maxMarketOrdersPerTurn': 1}
        head = {'market': [['BUY_SEED', 'WHEAT', 2]]}
        head_tail = {'market': [['BUY_SEED', 'WHEAT', 2], ['HIRE']]}

        plain = self.make_agent(self.ReducingBudget())
        plain_result = plain._seed_selected(self.observation(), cfg, copy.deepcopy(head))
        self.assertEqual(plain_result['market'], [['BUY_SEED', 'WHEAT', 1]])
        self.assertEqual(plain.funding_module.calls, 0)

        tailed = self.make_agent(self.ReducingBudget())
        tailed_result = tailed._seed_selected(self.observation(), cfg, copy.deepcopy(head_tail))
        self.assertEqual(tailed_result['market'], [['BUY_SEED', 'WHEAT', 1], ['HIRE']])
        self.assertEqual(tailed.funding_module.calls, 0)

    def test_tail_only_seed_never_enters_seed_budget(self):
        cfg = {'maxMarketOrdersPerTurn': 1}
        budget = self.PassthroughBudget()
        agent = self.make_agent(budget)
        selected = {'market': [['SELL', 'MILK', 1], ['BUY_SEED', 'WHEAT', 2]]}
        result = agent._seed_selected(self.observation(), cfg, copy.deepcopy(selected))
        self.assertEqual(result, selected)
        self.assertEqual(budget.calls, 0)
        self.assertEqual(agent.funding_module.calls, 0)

    def test_seed_feature_off_does_not_parse_market_cap(self):
        budget = self.ReducingBudget()
        agent = self.make_agent(budget)
        agent.features = tr.Features(seed=False, funding=True)
        selected = {'market': [['BUY_SEED', 'WHEAT', 2]]}
        result = agent._seed_selected(
            self.observation(), {'maxMarketOrdersPerTurn': 'not-an-int'},
            copy.deepcopy(selected))
        self.assertEqual(result, selected)
        self.assertEqual(budget.calls, 0)
        self.assertEqual(agent.funding_module.calls, 0)

    def test_non_list_market_returns_exact_selected_identity(self):
        budget = self.PassthroughBudget()
        agent = self.make_agent(budget)
        selected = {'market': {'not': 'a queue'}}
        result = agent._seed_selected(self.observation(), {}, selected)
        self.assertIs(result, selected)
        self.assertEqual(budget.calls, 0)
        self.assertEqual(agent.funding_module.calls, 0)

    def test_malformed_prefix_row_before_seed_is_engine_inert(self):
        budget = self.PassthroughBudget()
        agent = self.make_agent(budget)
        selected = {'market': [{'malformed': True}, ['BUY_SEED', 'WHEAT', 2]]}
        result = agent._seed_selected(self.observation(), {}, copy.deepcopy(selected))
        self.assertEqual(result, selected)
        self.assertEqual(budget.calls, 1)
        self.assertEqual(agent.funding_module.calls, 0)

    def test_malformed_row_after_seed_edit_does_not_crash_dependency_scan(self):
        budget = self.ReducingBudget()
        agent = self.make_agent(budget)
        selected = {'market': [['BUY_SEED', 'WHEAT', 2], {'malformed': True}]}
        result = agent._seed_selected(self.observation(), {}, copy.deepcopy(selected))
        self.assertEqual(result['market'], [['BUY_SEED', 'WHEAT', 1], {'malformed': True}])
        self.assertEqual(budget.calls, 1)
        self.assertEqual(agent.funding_module.calls, 0)


if __name__ == '__main__':
    unittest.main()
