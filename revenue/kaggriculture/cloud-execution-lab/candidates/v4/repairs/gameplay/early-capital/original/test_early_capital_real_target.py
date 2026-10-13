# SPDX-License-Identifier: Apache-2.0
"""Atomic-parent and structural-target contracts for early-capital ordering."""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import types
import unittest

import mechanics as m
from early_capital import _project_post_unit_private, order_early_capital
from test_early_capital_executable_prefix import (
    CFG,
    ENGINE_BLOB,
    ENGINE_PATH,
    MECHANICS_BLOB,
    MECHANICS_PATH,
    action,
    load_official_engine,
    obs,
)


EARLY_CAPITAL_PATH = Path('early_capital.py')
EARLY_CAPITAL_BLOB = 'c87f1d1c9d7b416c5316837634f7e721c85811fa'


def git_blob(data):
    return hashlib.sha1(
        b'blob ' + str(len(data)).encode() + b'\0' + data
    ).hexdigest()


def land_obs(unlocked, *, money=100, shed=None):
    result = obs(step=1, shed=shed or {'MELON': 1}, money=money)
    result['farms'][0]['unlocked_quadrants'] = copy.deepcopy(unlocked)
    return result


def with_one_hand(observation, position=(3, 4)):
    result = copy.deepcopy(observation)
    result['farms'][0]['hands'] = [list(position)]
    result['private']['inventories'] = [{}, {}]
    return result


def future_wheat_route():
    route = [
        {'farmer': ['PASS'], 'hands': [], 'market': []}
        for _ in range(32)
    ]
    route[2] = {
        'farmer': ['PLANT', 'WHEAT'],
        'hands': [],
        'market': [],
    }
    return route


def run_official_market(own_market):
    """Execute the literal two-player hidden-demand discriminator."""
    engine = load_official_engine()
    board = CFG['boardSize']
    own = engine._new_farm(board, 8000)
    rival = engine._new_farm(board, 100)
    for _ in engine.LAND_ORDER:
        engine._do_buy_land(own, board)
    if own['unlocked_quadrants'] != ['NW', 'NE', 'SW', 'SE']:
        raise AssertionError(own['unlocked_quadrants'])
    own['money'] = 100.0

    farms = [own, rival]
    privates = [engine._new_private(), engine._new_private()]
    privates[0]['shed']['MELON'] = 1
    market = engine._new_market()
    market['inventory']['WHEAT'] = 9581
    engine._refresh_prices(market)

    observations = [
        types.SimpleNamespace(market=market, farms=farms, private=privates[0]),
        types.SimpleNamespace(market=market, farms=farms, private=privates[1]),
    ]
    states = [
        types.SimpleNamespace(
            observation=observations[0],
            action={'market': copy.deepcopy(own_market)},
        ),
        types.SimpleNamespace(
            observation=observations[1],
            action={'market': [['BUY_PRODUCT', 'WHEAT', 1]]},
        ),
    ]
    env = types.SimpleNamespace(configuration={
        'boardSize': board,
        'maxMarketOrdersPerTurn': CFG['maxMarketOrdersPerTurn'],
        'farmHandCostMult': 1,
        'shedCapacity': CFG['shedCapacity'],
    })
    engine._process_market(states, env)
    return farms, privates, market


class EarlyCapitalRealTargetContracts(unittest.TestCase):
    def setUp(self):
        self.market = [
            ['BUY_PRODUCT', 'WHEAT', 1],
            ['BUY_LAND'],
            ['SELL', 'MELON', 1],
        ]

    def test_bound_sources_and_atomic_interpreter_gate_are_exact(self):
        self.assertEqual(
            git_blob(EARLY_CAPITAL_PATH.read_bytes()), EARLY_CAPITAL_BLOB)
        self.assertEqual(git_blob(ENGINE_PATH.read_bytes()), ENGINE_BLOB)
        self.assertEqual(git_blob(MECHANICS_PATH.read_bytes()), MECHANICS_BLOB)
        self.assertEqual(m.LAND_ORDER, ['NE', 'SW', 'SE'])
        engine_source = ENGINE_PATH.read_text()
        self.assertIn(
            'blocked = {crop for crop, n in plant_demand.items() if n > seeds.get(crop, 0)}',
            engine_source,
        )
        self.assertIn('_allowed(farmer_action)', engine_source)
        self.assertIn('_allowed(hand_action)', engine_source)

    def test_atomic_oversubscribed_current_plants_remain_all_pass(self):
        source = action(
            [
                ['BUY_LAND'],
                ['BUY_SEED', 'WHEAT', 1],
                ['SELL', 'MELON', 1],
            ],
            farmer_action=['PLANT', 'WHEAT'],
            hands=[['PLANT', 'WHEAT']],
        )
        observation = with_one_hand(obs(
            step=1,
            shed={'MELON': 1},
            seeds={'WHEAT': 1},
            money=750,
        ))

        projected = _project_post_unit_private(
            m, observation, CFG, source, 1)
        self.assertIsNotNone(projected)
        self.assertEqual(projected['seeds']['WHEAT'], 1)

        fixed, report = order_early_capital(
            m, observation, CFG, source, future_wheat_route())
        self.assertTrue(report['changed'])
        self.assertEqual(fixed['market'], [
            ['SELL', 'MELON', 1],
            ['BUY_LAND'],
            ['BUY_SEED', 'WHEAT', 1],
        ])

    def test_fully_unlocked_land_does_not_activate_transform(self):
        source = action(self.market)
        observation = land_obs(['NW', 'NE', 'SW', 'SE'])
        source_before = copy.deepcopy(source)
        observation_before = copy.deepcopy(observation)

        out, report = order_early_capital(
            m, observation, CFG, source, None)

        self.assertIs(out, source)
        self.assertEqual(source, source_before)
        self.assertEqual(observation, observation_before)
        self.assertFalse(report['changed'])
        self.assertEqual(report['reason'], 'no_admitted_capital')
        self.assertEqual(report['certified_land_rows'], [])
        self.assertEqual(report['certified_funding_rows'], [2])

    def test_one_remaining_unlock_preserves_existing_ordering(self):
        source = action(self.market)
        # Final SE unlock costs $4,000; one exact row-0 MELON sale supplies
        # the remaining $250 from a $3,750 starting balance.
        observation = land_obs(['NW', 'NE', 'SW'], money=3750)

        out, report = order_early_capital(
            m, observation, CFG, source, None)

        self.assertIsNot(out, source)
        self.assertTrue(report['changed'])
        self.assertEqual(report['certified_land_rows'], [1])
        self.assertEqual(report['certified_capital_rows'], [1])
        self.assertEqual(out['market'], [
            ['SELL', 'MELON', 1],
            ['BUY_LAND'],
            ['BUY_PRODUCT', 'WHEAT', 1],
        ])

    def test_duplicate_land_rows_cannot_claim_one_remaining_unlock(self):
        configuration = dict(CFG, maxMarketOrdersPerTurn=4)
        source = action([
            ['BUY_PRODUCT', 'WHEAT', 1],
            ['BUY_LAND'],
            ['BUY_LAND'],
            ['SELL', 'MELON', 1],
        ])
        observation = land_obs(['NW', 'NE', 'SW'], money=3750)

        out, report = order_early_capital(
            m, observation, configuration, source, None)

        self.assertTrue(report['changed'])
        self.assertEqual(report['certified_land_rows'], [1])
        self.assertEqual(report['certified_capital_rows'], [1])
        self.assertEqual(out['market'], [
            ['SELL', 'MELON', 1],
            ['BUY_LAND'],
            ['BUY_PRODUCT', 'WHEAT', 1],
            ['BUY_LAND'],
        ])

    def test_malformed_land_state_fails_closed(self):
        malformed = (
            None,
            'NW,NE,SW',
            [],
            ['NW', 'SW'],
            ['NW', 'NE', 'SW', 'SE', 'EXTRA'],
        )
        for unlocked in malformed:
            with self.subTest(unlocked=unlocked):
                source = action(self.market)
                observation = land_obs(unlocked)
                out, report = order_early_capital(
                    m, observation, CFG, source, None)
                self.assertIs(out, source)
                self.assertFalse(report['changed'])
                expected_reason = (
                    'capital_certificate_failed'
                    if unlocked in (None, 'NW,NE,SW', [])
                    else 'no_admitted_capital'
                )
                self.assertEqual(report['reason'], expected_reason)
                self.assertIsNone(report['certified_land_rows'])

    def test_official_engine_noop_land_reorder_loses_one_dollar(self):
        source = action(self.market)
        observation = land_obs(
            ['NW', 'NE', 'SW', 'SE'], money=100, shed={'MELON': 1})
        fixed, report = order_early_capital(
            m, observation, CFG, source, None)
        self.assertIs(fixed, source)
        self.assertEqual(report['reason'], 'no_admitted_capital')

        predecessor_reorder = [
            ['SELL', 'MELON', 1],
            ['BUY_LAND'],
            ['BUY_PRODUCT', 'WHEAT', 1],
        ]
        self.assertEqual(m.market_price('WHEAT', 9580, None), 45)
        self.assertEqual(m.market_price('WHEAT', 9579, None), 46)

        original_farms, original_privates, original_market = (
            run_official_market(source['market']))
        reordered_farms, reordered_privates, reordered_market = (
            run_official_market(predecessor_reorder))

        self.assertEqual(original_farms[0]['money'], 305.0)
        self.assertEqual(reordered_farms[0]['money'], 304.0)
        self.assertEqual(
            original_farms[0]['money'] - reordered_farms[0]['money'], 1.0)
        self.assertEqual(
            original_farms[0]['unlocked_quadrants'],
            ['NW', 'NE', 'SW', 'SE'],
        )
        self.assertEqual(
            reordered_farms[0]['unlocked_quadrants'],
            ['NW', 'NE', 'SW', 'SE'],
        )
        self.assertEqual(
            original_privates[0]['shed'], reordered_privates[0]['shed'])
        self.assertEqual(
            original_market['inventory'], reordered_market['inventory'])
        self.assertEqual(original_market['inventory']['WHEAT'], 9579)
        self.assertEqual(original_market['inventory']['MELON'], 10001)


if __name__ == '__main__':
    unittest.main()
