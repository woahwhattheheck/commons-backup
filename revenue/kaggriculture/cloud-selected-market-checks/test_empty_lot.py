# SPDX-License-Identifier: Apache-2.0
"""Selected-action fallback coverage when no non-operating lot is available.

Run separately with TITAN_SELL_FILE, TITAN_SELL_SUPPORT_DIR,
TITAN_ENGINE_FILE and TITAN_UPSTREAM_DIR set as documented in README.
Official market transitions are synthetic, not scored full games.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import os
import random
from pathlib import Path
import sys
import types
from typing import Any, Callable
import unittest
from unittest.mock import patch

ENGINE_SHA256 = 'bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e'


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Cannot load {path}')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class EmptyLotConsumerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(os.environ['TITAN_SELL_FILE']).resolve()
        support = Path(os.environ.get('TITAN_SELL_SUPPORT_DIR', str(source.parent))).resolve()
        engine_path = Path(os.environ['TITAN_ENGINE_FILE']).resolve()
        upstream = Path(os.environ['TITAN_UPSTREAM_DIR']).resolve()
        actual = hashlib.sha256(engine_path.read_bytes()).hexdigest()
        if actual != ENGINE_SHA256:
            raise RuntimeError(f'Expected pinned 28b6d8 engine; received {actual}')
        # Reuse the established offline-loader method: compile the unchanged
        # required utility definition rather than importing unused schema/HTTP
        # machinery. The market tests never initialize an episode or use a seed.
        utility_path = upstream / 'utils.py'
        tree = ast.parse(utility_path.read_text(), filename=str(utility_path))
        nodes = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name == 'resolve_episode_seed']
        if len(nodes) != 1:
            raise RuntimeError('Missing pinned seed utility')
        utility = types.ModuleType('kaggle_environments.utils')
        utility.__dict__.update(Any=Any, Callable=Callable, random=random)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(utility_path), 'exec'), utility.__dict__)
        package = types.ModuleType('kaggle_environments')
        package.__path__ = [str(upstream)]
        temporary = {'kaggle_environments': package, 'kaggle_environments.utils': utility}
        with patch.dict(sys.modules, temporary):
            cls.engine = load_module('wren_empty_lot_engine', engine_path)
        sys.path.insert(0, str(support))
        cls.seller = load_module('wren_empty_lot_seller', source)

    def case(self, *, money=100, shed=None, market=None, seat=0, step=10):
        engine = self.engine
        farms = [engine._new_farm(10, money), engine._new_farm(10, money)]
        obs = {'step': step, 'player': seat, 'day': step // 24, 'hour': step % 24,
               'farms': farms, 'market': engine._new_market(),
               'town': {'unlocked_shops': []}}
        config = {'episodeSteps': 720, 'turnsPerDay': 24, 'shedCapacity': 100,
                  'boardSize': 10, 'maxMarketOrdersPerTurn': 10}
        action = {'farmer': ['PASS'], 'hands': [], 'market': market or []}
        fallback = {'farmer': ['PASS'], 'hands': [], 'market': []}
        projection = {'observed_step': step, 'end_step': step,
                      'stock_events': [], 'future_market': {}}
        return obs, config, action, fallback, dict(shed or {}), projection

    def transform(self, case, reservations=None):
        obs, cfg, action, fallback, shed, projection = case
        policy = self.seller.SelectedActionSell()
        # A missing economic lot must not trigger dummy optimization merely to
        # cause validation. The literal queue has its own feasibility path.
        with patch.object(self.seller, 'optimize_lot', side_effect=AssertionError('Unexpected optimization')):
            result = policy.transform(obs, cfg, action, post_unit_shed=shed,
                                      projection=projection, reservations=reservations,
                                      fallback_action=fallback)
        return result, policy.diagnostics

    def execute_market(self, case, action):
        obs, cfg, _, _, shed, _ = copy.deepcopy(case)
        own = obs['player']
        private = [self.engine._new_private(), self.engine._new_private()]
        private[own]['shed'].update(shed)
        states = [types.SimpleNamespace(
            observation=types.SimpleNamespace(farms=obs['farms'], market=obs['market'], private=private[i]),
            action=action if i == own else {'farmer': ['PASS'], 'hands': [], 'market': []})
            for i in range(2)]
        self.engine._process_market(states, types.SimpleNamespace(configuration=cfg))
        return {'cash': obs['farms'][own]['money'], 'shed': private[own]['shed'],
                'seeds': private[own]['seeds'], 'hires': obs['farms'][own]['hires_today']}

    def cash_floor(self, case, minimum, phase='after_market'):
        return {'cash': [{'step': case[0]['step'], 'phase': phase, 'minimum': minimum}]}

    def test_empty_shed_hire_uses_cash_fallback_both_seats(self):
        for seat in (0, 1):
            with self.subTest(seat=seat):
                case = self.case(market=[['HIRE']], seat=seat)
                original = self.execute_market(case, case[2])
                self.assertEqual(original['cash'], 99)
                result, diagnostic = self.transform(case, self.cash_floor(case, 100))
                self.assertEqual(result, case[3])
                self.assertEqual(diagnostic['status'], 'fallback')
                self.assertEqual(diagnostic['reason'], 'no_certified_feasible_plan')
                fixed = self.execute_market(case, result)
                self.assertEqual((fixed['cash'], fixed['hires']), (100, 0))

    def test_empty_shed_exact_cash_threshold_preserves_hire(self):
        case = self.case(money=101, market=[['HIRE']])
        result, diagnostic = self.transform(case, self.cash_floor(case, 100))
        self.assertEqual(result, case[2])
        self.assertEqual(diagnostic['status'], 'unchanged')
        self.assertEqual(diagnostic['evaluations'], [])
        self.assertEqual(self.execute_market(case, result)['cash'], 100)

    def test_empty_shed_seed_purchase_cannot_spend_reserved_cash(self):
        case = self.case(market=[['BUY_SEED', 'CARROT', 1]])
        self.assertEqual(self.execute_market(case, case[2])['cash'], 80)
        result, diagnostic = self.transform(case, self.cash_floor(case, 100))
        self.assertEqual(result, case[3])
        self.assertEqual(diagnostic['status'], 'fallback')
        self.assertEqual(self.execute_market(case, result)['seeds']['CARROT'], 0)

    def test_before_and_after_cash_floors_remain_distinct(self):
        case = self.case(market=[['BUY_SEED', 'CARROT', 1]])
        reservations = self.cash_floor(case, 100, 'before_market')
        reservations['cash'] += self.cash_floor(case, 80)['cash']
        result, diagnostic = self.transform(case, reservations)
        self.assertEqual(result, case[2])
        self.assertEqual(diagnostic['status'], 'unchanged')
        self.assertEqual(self.execute_market(case, result)['seeds']['CARROT'], 1)

    def test_operating_only_stock_reservation_uses_fallback(self):
        case = self.case(shed={'WHEAT': 1}, market=[['SELL', 'WHEAT', 1]])
        result, diagnostic = self.transform(case, {'stock': {'WHEAT': 1}})
        self.assertEqual(result, case[3])
        self.assertEqual(diagnostic['status'], 'fallback')
        self.assertEqual(self.execute_market(case, result)['shed']['WHEAT'], 1)
        self.assertEqual(self.execute_market(case, case[2])['shed']['WHEAT'], 0)

    def test_unmet_initial_stock_floor_uses_caller_fallback(self):
        case = self.case(shed={'WHEAT': 1})
        result, diagnostic = self.transform(case, {'stock': {'WHEAT': 2}})
        self.assertEqual(result, case[3])
        self.assertEqual(diagnostic['status'], 'fallback')
        # Fallback is caller-owned, not a claim that missing stock was created.
        self.assertEqual(self.execute_market(case, result)['shed']['WHEAT'], 1)

    def test_fully_reserved_product_normalization_stays_feasible(self):
        case = self.case(shed={'MILK': 1}, market=[['SELL', 'MILK', 1]])
        result, diagnostic = self.transform(case, {'stock': {'MILK': 1}})
        self.assertEqual(result['market'], [[]])
        self.assertEqual(diagnostic['status'], 'unchanged')
        self.assertEqual(self.execute_market(case, result)['shed']['MILK'], 1)

    def test_future_purchase_cash_floor_is_checked_without_current_lot(self):
        case = self.case()
        case[5]['end_step'] = 11
        case[5]['future_market'] = {11: [['HIRE']]}
        reservations = {'cash': [{'step': 11, 'phase': 'after_market', 'minimum': 100}]}
        result, diagnostic = self.transform(case, reservations)
        self.assertEqual(result, case[3])
        self.assertEqual(diagnostic['status'], 'fallback')

    def test_seed_storage_is_not_shed_capacity(self):
        case = self.case(money=1000, shed={'WHEAT': 100}, market=[['BUY_SEED', 'CARROT', 10]])
        result, diagnostic = self.transform(case, {'stock': {'WHEAT': 100}})
        self.assertEqual(result, case[2])
        self.assertEqual(diagnostic['status'], 'unchanged')
        actual = self.execute_market(case, result)
        self.assertEqual((actual['cash'], actual['seeds']['CARROT'], sum(actual['shed'].values())), (800, 10, 100))

    def test_operating_buy_honors_supplied_cost_bound_and_cash_floor(self):
        case = self.case(money=30, market=[['BUY_PRODUCT', 'WHEAT', 1]])
        reservations = self.cash_floor(case, 30)
        reservations['order_cost_bounds'] = [{'step': 10, 'slot': 0, 'max_cash_cost': 26}]
        result, diagnostic = self.transform(case, reservations)
        self.assertEqual(result, case[3])
        self.assertEqual(diagnostic['status'], 'fallback')
        self.assertEqual(self.execute_market(case, case[2])['cash'], 4)
        self.assertEqual(self.execute_market(case, result)['cash'], 30)

    def test_empty_lot_keeps_reserved_non_sell_slot_positions(self):
        case = self.case(money=1000, market=[[], ['BUY_SEED', 'CARROT', 1], [], ['HIRE']])
        result, diagnostic = self.transform(case, {'market_slots': {10: [0, 1, 2, 3]}})
        self.assertEqual(result, case[2])
        self.assertEqual(diagnostic['status'], 'unchanged')
        self.assertEqual(self.execute_market(case, result)['cash'], 979)

    def test_failure_does_not_mutate_inputs_or_alias_fallback(self):
        case = self.case(market=[['HIRE']])
        reservations = self.cash_floor(case, 100)
        before = copy.deepcopy((case, reservations))
        result, diagnostic = self.transform(case, reservations)
        self.assertEqual((case, reservations), before)
        self.assertEqual(result, case[3])
        self.assertIsNot(result, case[3])
        result['farmer'].append('consumer-change')
        self.assertEqual(case[3]['farmer'], ['PASS'])
        self.assertEqual(diagnostic['status'], 'fallback')

    def test_terminal_stock_fix_is_used_for_operating_only_inventory(self):
        case = self.case(shed={'WHEAT': 1}, market=[['SELL', 'WHEAT', 1]], step=718)
        result, diagnostic = self.transform(case, {'stock': {'WHEAT': 1}})
        self.assertEqual(result, case[3])
        self.assertEqual(diagnostic['status'], 'fallback')
        self.assertEqual(self.execute_market(case, result)['shed']['WHEAT'], 1)

    def test_ordered_projection_fix_is_used_without_an_optimizable_lot(self):
        for deposit_first in (True, False):
            with self.subTest(deposit_first=deposit_first):
                case = self.case(shed={'WHEAT': 100})
                deposit = {'step': 11, 'phase': 'before_market', 'product': 'MILK', 'quantity_delta': 10}
                pickup = {'step': 11, 'phase': 'before_market', 'product': 'WHEAT', 'quantity_delta': -10}
                case[5]['end_step'] = 11
                case[5]['stock_events'] = [deposit, pickup] if deposit_first else [pickup, deposit]
                result, diagnostic = self.transform(case)
                self.assertEqual(diagnostic['status'], 'fallback' if deposit_first else 'unchanged')
                self.assertEqual(result, case[3] if deposit_first else case[2])

    def test_omitted_fallback_retains_original_without_feasibility_claim(self):
        case = self.case(market=[['HIRE']])
        obs, cfg, action, _, shed, projection = case
        policy = self.seller.SelectedActionSell()
        result = policy.transform(obs, cfg, action, post_unit_shed=shed,
                                  projection=projection, reservations=self.cash_floor(case, 100))
        self.assertEqual(result, action)
        self.assertIsNot(result, action)
        self.assertEqual(policy.diagnostics['status'], 'fallback')


if __name__ == '__main__':
    unittest.main(verbosity=2)
