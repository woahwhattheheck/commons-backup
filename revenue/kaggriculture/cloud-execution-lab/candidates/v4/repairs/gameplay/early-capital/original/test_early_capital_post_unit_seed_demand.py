# SPDX-License-Identifier: Apache-2.0
"""Regression contracts for post-unit seed demand in early-capital ordering."""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import types
import unittest

import mechanics as m
from early_capital import order_early_capital
from test_early_capital_executable_prefix import CFG, action, load_official_engine, obs


EARLY_CAPITAL_PATH = Path('early_capital.py')
EARLY_CAPITAL_BLOB = 'c87f1d1c9d7b416c5316837634f7e721c85811fa'


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def route_with(*, step: int, action_row: dict | None = None) -> list[dict]:
    route = [
        {'farmer': ['PASS'], 'hands': [], 'market': []}
        for _ in range(32)
    ]
    if action_row is not None:
        route[step] = copy.deepcopy(action_row)
    return route


def run_official_unit_then_market(market_orders: list[list]) -> tuple[dict, dict, dict]:
    """Run the exact current PLANT stage followed by the exact market stage."""
    engine = load_official_engine()
    board = 10
    farms = [engine._new_farm(board, 750), engine._new_farm(board, 0)]
    privates = [engine._new_private(), engine._new_private()]
    privates[0]['shed']['MELON'] = 1
    privates[0]['seeds']['WHEAT'] = 1

    engine._apply_unit_action(
        farms[0], privates[0], 0, ['PLANT', 'WHEAT'], board, 0, 24, 100,
    )
    if privates[0]['seeds']['WHEAT'] != 0:
        raise AssertionError('official current PLANT did not consume its seed')

    market = engine._new_market()
    market['inventory']['MELON'] = 10000
    engine._refresh_prices(market)
    observations = [
        types.SimpleNamespace(market=market, farms=farms, private=privates[0]),
        types.SimpleNamespace(market=market, farms=farms, private=privates[1]),
    ]
    states = [
        types.SimpleNamespace(
            observation=observations[0],
            action={'market': copy.deepcopy(market_orders)},
        ),
        types.SimpleNamespace(
            observation=observations[1],
            action={'market': []},
        ),
    ]
    env = types.SimpleNamespace(configuration={
        'boardSize': board,
        'maxMarketOrdersPerTurn': 3,
        'farmHandCostMult': 1,
        'shedCapacity': 100,
    })
    engine._process_market(states, env)
    return farms[0], privates[0], market


class PostUnitSeedDemandContracts(unittest.TestCase):
    def _source(self, *, farmer_action=None):
        return action(
            [
                ['BUY_LAND'],
                ['BUY_SEED', 'WHEAT', 1],
                ['SELL', 'MELON', 1],
            ],
            farmer_action=farmer_action,
        )

    def test_source_blob_is_exact(self):
        self.assertEqual(git_blob(EARLY_CAPITAL_PATH.read_bytes()), EARLY_CAPITAL_BLOB)

    def test_executed_current_plant_is_not_future_seed_demand(self):
        source = self._source(farmer_action=['PLANT', 'WHEAT'])
        observation = obs(
            step=1,
            shed={'MELON': 1},
            seeds={'WHEAT': 1},
            money=750,
        )
        fixed, report = order_early_capital(
            m, observation, CFG, source, route_with(step=2),
        )

        self.assertTrue(report['changed'])
        self.assertEqual(report['certified_funding_rows'], [2])
        self.assertEqual(fixed['market'], [
            ['SELL', 'MELON', 1],
            ['BUY_LAND'],
            ['BUY_SEED', 'WHEAT', 1],
        ])

    def test_real_future_plant_keeps_seed_purchase_operating(self):
        source = self._source(farmer_action=['PASS'])
        observation = obs(
            step=1,
            shed={'MELON': 1},
            seeds={'WHEAT': 0},
            money=750,
        )
        future = route_with(
            step=2,
            action_row={'farmer': ['PLANT', 'WHEAT'], 'hands': [], 'market': []},
        )
        fixed, report = order_early_capital(m, observation, CFG, source, future)

        # SELL certifies $250, but the required $10 WHEAT seed is OPERATING.
        # Promoting both ahead of LAND would leave only $990, so the stronger
        # commit-real certificate must preserve the authored order unchanged.
        self.assertIs(fixed, source)
        self.assertFalse(report['changed'])
        self.assertEqual(report['reason'], 'no_admitted_capital')
        self.assertEqual(report['certified_operating_rows'], [1])
        self.assertEqual(report['certified_capital_rows'], [])
        self.assertEqual(report['cash_after_operating_lower_bound'], 990.0)

    def test_post_unit_residual_seed_covers_one_future_plant(self):
        source = self._source(farmer_action=['PLANT', 'WHEAT'])
        observation = obs(
            step=1,
            shed={'MELON': 1},
            seeds={'WHEAT': 2},
            money=750,
        )
        future = route_with(
            step=2,
            action_row={'farmer': ['PLANT', 'WHEAT'], 'hands': [], 'market': []},
        )
        fixed, _ = order_early_capital(m, observation, CFG, source, future)

        self.assertEqual(fixed['market'], [
            ['SELL', 'MELON', 1],
            ['BUY_LAND'],
            ['BUY_SEED', 'WHEAT', 1],
        ])

    def test_official_unit_then_market_transition_decides_land_unlock(self):
        source = self._source(farmer_action=['PLANT', 'WHEAT'])
        observation = obs(
            step=1,
            shed={'MELON': 1},
            seeds={'WHEAT': 1},
            money=750,
        )
        fixed, _ = order_early_capital(
            m, observation, CFG, source, route_with(step=2),
        )
        predecessor = [
            ['SELL', 'MELON', 1],
            ['BUY_SEED', 'WHEAT', 1],
            ['BUY_LAND'],
        ]

        fixed_farm, fixed_private, fixed_market = run_official_unit_then_market(
            fixed['market'],
        )
        old_farm, old_private, old_market = run_official_unit_then_market(predecessor)

        self.assertEqual(fixed_farm['unlocked_quadrants'], ['NW', 'NE'])
        self.assertEqual(fixed_farm['money'], 0.0)
        self.assertEqual(fixed_private['seeds']['WHEAT'], 0)
        self.assertEqual(old_farm['unlocked_quadrants'], ['NW'])
        self.assertEqual(old_farm['money'], 990.0)
        self.assertEqual(old_private['seeds']['WHEAT'], 1)
        self.assertEqual(fixed_market['inventory']['MELON'], 10001)
        self.assertEqual(old_market['inventory']['MELON'], 10001)


if __name__ == '__main__':
    unittest.main()
