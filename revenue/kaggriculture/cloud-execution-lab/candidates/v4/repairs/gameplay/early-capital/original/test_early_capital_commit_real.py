# SPDX-License-Identifier: Apache-2.0
"""Commit-real cash/capacity contracts for early-capital ordering."""
from __future__ import annotations

import copy
import types
import unittest

import mechanics as m
from early_capital import order_early_capital
from test_early_capital_executable_prefix import (
    CFG,
    action,
    load_official_engine,
    obs,
)


def prepared_obs(*, money, shed=None, unlocked=('NW',), wheat_inventory=9581):
    result = obs(step=1, shed=shed or {}, money=money)
    result['farms'][0]['unlocked_quadrants'] = list(unlocked)
    result['market']['inventory']['WHEAT'] = wheat_inventory
    result['market']['prices']['WHEAT'] = m.market_price(
        'WHEAT', wheat_inventory, result['market'].get('params'))
    result['market']['prices']['MELON'] = m.market_price(
        'MELON', result['market']['inventory']['MELON'],
        result['market'].get('params'))
    return result


def run_official(
        own_market, *, own_money, own_shed=None, unlocked=('NW',),
        shed_capacity=None, rival_market=None):
    engine = load_official_engine()
    board = CFG['boardSize']
    own = engine._new_farm(board, 8000)
    rival = engine._new_farm(board, 100)

    while len(own['unlocked_quadrants']) < len(unlocked):
        engine._do_buy_land(own, board)
    if own['unlocked_quadrants'] != list(unlocked):
        raise AssertionError((own['unlocked_quadrants'], unlocked))
    own['money'] = float(own_money)

    farms = [own, rival]
    privates = [engine._new_private(), engine._new_private()]
    for item, quantity in (own_shed or {}).items():
        privates[0]['shed'][item] = quantity

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
            action={'market': copy.deepcopy(
                rival_market if rival_market is not None
                else [['BUY_PRODUCT', 'WHEAT', 1]]
            )},
        ),
    ]
    env = types.SimpleNamespace(configuration={
        'boardSize': board,
        'maxMarketOrdersPerTurn': max(
            CFG['maxMarketOrdersPerTurn'], len(own_market)),
        'farmHandCostMult': 1,
        'shedCapacity': (
            CFG['shedCapacity'] if shed_capacity is None else shed_capacity),
    })
    engine._process_market(states, env)
    return farms, privates, market


class EarlyCapitalCommitRealContracts(unittest.TestCase):
    def test_positive_750_plus_exact_row0_melon_funds_1000_land(self):
        source = action([
            ['BUY_LAND'],
            ['SELL', 'MELON', 1],
        ])
        observation = prepared_obs(
            money=750, shed={'MELON': 1}, unlocked=('NW',))

        fixed, report = order_early_capital(
            m, observation, CFG, source, None)

        self.assertTrue(report['changed'])
        self.assertEqual(fixed['market'], [
            ['SELL', 'MELON', 1],
            ['BUY_LAND'],
        ])
        self.assertEqual(report['guaranteed_funding_proceeds'], 250.0)
        self.assertEqual(report['cash_after_operating_lower_bound'], 1000.0)
        self.assertEqual(report['certified_capital_rows'], [0])

        farms, privates, _ = run_official(
            fixed['market'], own_money=750, own_shed={'MELON': 1},
            unlocked=('NW',))
        self.assertEqual(farms[0]['unlocked_quadrants'], ['NW', 'NE'])
        self.assertEqual(farms[0]['money'], 0.0)
        self.assertEqual(privates[0]['shed']['MELON'], 0)

    def test_45_plus_melon_cannot_promote_1000_land(self):
        source = action([
            ['BUY_PRODUCT', 'WHEAT', 1],
            ['BUY_LAND'],
            ['SELL', 'MELON', 1],
        ])
        observation = prepared_obs(
            money=45, shed={'MELON': 1}, unlocked=('NW',))

        fixed, report = order_early_capital(
            m, observation, CFG, source, None)

        self.assertIs(fixed, source)
        self.assertFalse(report['changed'])
        self.assertEqual(report['reason'], 'no_admitted_capital')
        self.assertEqual(report['cash_after_operating_lower_bound'], 295.0)
        self.assertEqual(report['certified_capital_rows'], [])

        farms, privates, market = run_official(
            fixed['market'], own_money=45, own_shed={'MELON': 1},
            unlocked=('NW',))
        self.assertEqual(farms[0]['money'], 250.0)
        self.assertEqual(farms[0]['unlocked_quadrants'], ['NW'])
        self.assertEqual(privates[0]['shed']['MELON'], 0)
        self.assertEqual(privates[0]['shed']['WHEAT'], 1)
        self.assertEqual(market['inventory']['WHEAT'], 9579)

    def test_45_plus_melon_cannot_promote_300_goose(self):
        source = action([
            ['BUY_PRODUCT', 'WHEAT', 1],
            ['BUY_ANIMAL', 'GOOSE', 1],
            ['SELL', 'MELON', 1],
        ])
        observation = prepared_obs(
            money=45, shed={'MELON': 1}, unlocked=('NW',))

        fixed, report = order_early_capital(
            m, observation, CFG, source, None)

        self.assertIs(fixed, source)
        self.assertEqual(report['reason'], 'no_admitted_capital')
        self.assertEqual(report['cash_after_operating_lower_bound'], 295.0)
        self.assertEqual(report['certified_capital_rows'], [])

        farms, privates, market = run_official(
            fixed['market'], own_money=45, own_shed={'MELON': 1})
        self.assertEqual(farms[0]['money'], 250.0)
        self.assertEqual(privates[0]['shed']['GOOSE'], 0)
        self.assertEqual(privates[0]['shed']['WHEAT'], 1)
        self.assertEqual(market['inventory']['WHEAT'], 9579)

    def test_promoted_hire_cost_must_leave_land_executable(self):
        source = action([
            ['BUY_LAND'],
            ['HIRE'],
        ])
        observation = prepared_obs(money=1000, shed={}, unlocked=('NW',))

        fixed, report = order_early_capital(
            m, observation, CFG, source, None)

        self.assertIs(fixed, source)
        self.assertEqual(report['operating_cost_upper_bound'], 1.0)
        self.assertEqual(report['cash_after_operating_lower_bound'], 999.0)
        self.assertEqual(report['certified_capital_rows'], [])

        original_farms, _, _ = run_official(
            source['market'], own_money=1000, rival_market=[])
        unsafe_farms, _, _ = run_official(
            [['HIRE'], ['BUY_LAND']], own_money=1000, rival_market=[])
        self.assertEqual(
            original_farms[0]['unlocked_quadrants'], ['NW', 'NE'])
        self.assertEqual(unsafe_farms[0]['unlocked_quadrants'], ['NW'])

    def test_required_seed_cost_must_leave_land_executable(self):
        source = action([
            ['BUY_LAND'],
            ['BUY_SEED', 'WHEAT', 1],
        ])
        route = [
            {'farmer': ['PASS'], 'hands': [], 'market': []}
            for _ in range(8)
        ]
        route[2] = {
            'farmer': ['PLANT', 'WHEAT'], 'hands': [], 'market': []}
        observation = prepared_obs(money=1009, shed={}, unlocked=('NW',))

        fixed, report = order_early_capital(
            m, observation, CFG, source, route)

        self.assertIs(fixed, source)
        self.assertEqual(report['certified_operating_rows'], [1])
        self.assertEqual(report['operating_cost_upper_bound'], 10.0)
        self.assertEqual(report['cash_after_operating_lower_bound'], 999.0)
        self.assertEqual(report['certified_capital_rows'], [])

    def test_animal_full_quantity_must_fit_shed_capacity(self):
        configuration = dict(CFG, shedCapacity=2)
        source = action([
            ['BUY_PRODUCT', 'WHEAT', 1],
            ['BUY_ANIMAL', 'GOOSE', 2],
        ])
        observation = prepared_obs(
            money=1000, shed={'MELON': 1}, unlocked=('NW',))

        fixed, report = order_early_capital(
            m, observation, configuration, source, None)

        self.assertIs(fixed, source)
        self.assertEqual(report['certified_capital_rows'], [])
        self.assertEqual(report['capital_certificate_reason'],
                         'unproved_capital_sequence')

        original_farms, original_privates, _ = run_official(
            source['market'], own_money=1000, own_shed={'MELON': 1},
            shed_capacity=2, rival_market=[])
        unsafe_farms, unsafe_privates, _ = run_official(
            [['BUY_ANIMAL', 'GOOSE', 2], ['BUY_PRODUCT', 'WHEAT', 1]],
            own_money=1000, own_shed={'MELON': 1},
            shed_capacity=2, rival_market=[])
        self.assertEqual(original_privates[0]['shed']['GOOSE'], 0)
        self.assertEqual(original_privates[0]['shed']['WHEAT'], 1)
        self.assertEqual(unsafe_privates[0]['shed']['GOOSE'], 1)
        self.assertEqual(unsafe_privates[0]['shed']['WHEAT'], 0)
        self.assertEqual(original_farms[0]['money'], 955.0)
        self.assertEqual(unsafe_farms[0]['money'], 700.0)

    def test_first_exact_sale_then_floor_only_for_later_units(self):
        source = action([
            ['BUY_LAND'],
            ['SELL', 'MELON', 3],
        ])
        observation = prepared_obs(
            money=748, shed={'MELON': 3}, unlocked=('NW',))

        fixed, report = order_early_capital(
            m, observation, CFG, source, None)

        # 748 + exact first $250 + two guaranteed $1 floors = exactly $1000.
        self.assertTrue(report['changed'])
        self.assertEqual(report['guaranteed_funding_proceeds'], 252.0)
        self.assertEqual(report['cash_after_operating_lower_bound'], 1000.0)
        self.assertEqual(report['certified_capital_rows'], [0])


if __name__ == '__main__':
    unittest.main()
