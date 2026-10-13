# SPDX-License-Identifier: Apache-2.0
"""Pinned-engine market grammar contracts for scheduler accounting."""
from copy import deepcopy
from unittest import TestCase, main, mock

import mechanics as m
import scheduler as s


class _Controller:
    cur = 'route'
    R = {'route': [{'market': []}]}


def _scheduler():
    value = s.SellScheduler.__new__(s.SellScheduler)
    value.controller = _Controller()
    return value


def _cash_observation():
    return {
        'step': 0,
        'player': 0,
        'farms': [
            {'unlocked_quadrants': [], 'hires_today': 0},
            {'unlocked_quadrants': [], 'hires_today': 0},
        ],
        'market': {'inventory': {}, 'params': None},
    }


def _receipt_snapshot():
    farm = {'farmer': [0, 0], 'hands': [], 'tiles': [[None]]}
    private = {'shed': {}, 'inventories': [{}]}
    return farm, private


class SchedulerMarketGrammarContracts(TestCase):
    def test_parser_matches_engine_shape_quantity_and_domains(self):
        inert = [
            (),
            {'op': 'HIRE'},
            [],
            ['SELL'],
            ['SELL', 'CARROT'],
            ['SELL', 'CARROT', 'x'],
            ['SELL', 'CARROT', 0],
            ['SELL', 'CARROT', -1],
            ['SELL', 'NOT_A_PRODUCT', 1],
            ['BUY_SEED', 'NOT_A_CROP', 1],
            ['BUY_ANIMAL', 'NOT_AN_ANIMAL', 1],
            ['BUY_PRODUCT', 'NOT_A_PRODUCT', 1],
            ['UNKNOWN', 'CARROT', 1],
        ]
        for row in inert:
            with self.subTest(row=row):
                self.assertIsNone(s._parse_market_order(row))

        self.assertEqual(s._parse_market_order(['HIRE']), ('HIRE', None, 1))
        self.assertEqual(s._parse_market_order(['BUY_LAND']), ('BUY_LAND', None, 1))
        self.assertEqual(s._parse_market_order(['HIRE', 'ignored']), ('HIRE', None, 1))
        self.assertEqual(s._parse_market_order(['BUY_LAND', 'ignored', 'trailing']),
                         ('BUY_LAND', None, 1))
        self.assertEqual(s._parse_market_order(['SELL', 'CARROT', '2', 'metadata']),
                         ('SELL', 'CARROT', 2))
        self.assertEqual(s._parse_market_order(['SELL', 'CARROT', 2.9]),
                         ('SELL', 'CARROT', 2))
        self.assertEqual(s._parse_market_order(['SELL', 'CARROT', True]),
                         ('SELL', 'CARROT', 1))
        self.assertEqual(s._parse_market_order(['BUY_PRODUCT', 'WHEAT', '2', 'metadata']),
                         ('BUY_PRODUCT', 'WHEAT', 2))

    def test_cash_reserve_ignores_inert_rows_and_uses_engine_prefix_floor(self):
        actor = _scheduler()
        obs = _cash_observation()
        malformed = {
            'market': [
                ('HIRE', 'ignored'),
                {'op': 'HIRE'},
                ['SELL'],
                ['BUY_PRODUCT', 'WHEAT', 'x'],
                ['BUY_PRODUCT', 'NOT_A_PRODUCT', 99],
                ['HIRE'],
            ]
        }
        original = deepcopy(malformed)
        expected = m._hire_cost(0, 1)
        self.assertEqual(actor.cash_reserve(obs, {}, malformed, 0), expected)
        self.assertEqual(malformed, original)

        two_hires = {'market': [['HIRE'], ['HIRE', 'suffix']]}
        for cap in (0, -3):
            with self.subTest(cap=cap):
                self.assertEqual(
                    actor.cash_reserve(obs, {'maxMarketOrdersPerTurn': cap}, two_hires, 0),
                    expected,
                )

        land_obs = _cash_observation()
        land_obs['farms'][0]['unlocked_quadrants'] = ['NW']
        one_land = {'market': [['BUY_LAND']]}
        self.assertEqual(
            actor.cash_reserve(land_obs, {'maxMarketOrdersPerTurn': 1}, one_land, 0),
            m.LAND_PRICES[0],
        )
        two_lands = {'market': [['BUY_LAND'], ['BUY_LAND']]}
        self.assertEqual(
            actor.cash_reserve(land_obs, {'maxMarketOrdersPerTurn': 2}, two_lands, 0),
            m.LAND_PRICES[0] + m.LAND_PRICES[1],
        )

    def test_receipt_profile_only_applies_parsed_executable_prefix(self):
        actor = _scheduler()
        obs = {'step': 0, 'player': 0}
        farm, private = _receipt_snapshot()

        def profile(base, config):
            def fresh_post_units(*_args, **_kwargs):
                f, p = _receipt_snapshot()
                return deepcopy(f), deepcopy(p)
            with mock.patch.object(s, 'post_units', side_effect=fresh_post_units):
                return actor.receipt_profile(
                    obs, base, farm, private, 0, 'CARROT', config
                )

        inert_rows = [
            ('BUY_PRODUCT', 'WHEAT', 2),
            {'op': 'BUY_PRODUCT', 'item': 'WHEAT', 'qty': 2},
            ['BUY_PRODUCT'],
            ['BUY_PRODUCT', 'WHEAT', 'x'],
            ['BUY_PRODUCT', 'NOT_A_PRODUCT', 2],
        ]
        for row in inert_rows:
            with self.subTest(row=row):
                feasible = profile({'market': [row]}, {'shedCapacity': 1})
                self.assertTrue(feasible(()))

        for quantity in ('2', 2.9, True):
            with self.subTest(quantity=quantity):
                row = ['BUY_PRODUCT', 'WHEAT', quantity, 'trailing']
                feasible = profile({'market': [row]}, {'shedCapacity': 1})
                self.assertFalse(feasible(()))

        first_inert_then_valid = {
            'market': [
                ['BUY_PRODUCT', 'WHEAT', 'x'],
                ['BUY_PRODUCT', 'WHEAT', 2],
            ]
        }
        for cap in (0, -7):
            with self.subTest(cap=cap):
                feasible = profile(
                    first_inert_then_valid,
                    {'shedCapacity': 1, 'maxMarketOrdersPerTurn': cap},
                )
                self.assertTrue(feasible(()))

        first_valid_then_suffix = {
            'market': [
                ['BUY_PRODUCT', 'WHEAT', '2', 'trailing'],
                ['BUY_PRODUCT', 'WHEAT', 99],
            ]
        }
        for cap in (0, -7):
            with self.subTest(cap=cap):
                feasible = profile(
                    first_valid_then_suffix,
                    {'shedCapacity': 1, 'maxMarketOrdersPerTurn': cap},
                )
                self.assertFalse(feasible(()))


if __name__ == '__main__':
    main()
