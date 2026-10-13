# SPDX-License-Identifier: Apache-2.0
"""Focused contracts for TJ-0909-G1 early-capital ordering. No full games."""
import unittest
from copy import deepcopy

import mechanics as m
from early_capital import order_early_capital, PAYBACK_DAYS, EARLY_DAY_LIMIT


def farm(money=3000, unlocked=('NW',), hires=0):
    return {'money': money, 'unlocked_quadrants': list(unlocked), 'hires_today': hires,
            'tiles': [[None] * 10 for _ in range(10)], 'farmer': (4, 4), 'hands': []}


def obs(step=1, money=2643, unlocked=('NW',), seeds=None, player=0,
        shed=None, inventories=None):
    empty = farm(money, unlocked)
    rival = farm(3000)
    stock = ({p: 10 for p in m.PRODUCTS} if shed is None
             else {p: 0 for p in m.PRODUCTS})
    if shed is not None:
        stock.update(shed)
    return {
        'step': step, 'day': step // 24, 'hour': step % 24, 'player': player,
        'farms': [empty, rival] if player == 0 else [rival, empty],
        'private': {'shed': stock,
                    'inventories': deepcopy(inventories) if inventories is not None else [{}],
                    'seeds': dict(seeds or {})},
        'market': {'inventory': {p: 10000 for p in m.PRODUCTS}, 'prices': {}, 'params': None},
    }


CFG = {'episodeSteps': 720, 'turnsPerDay': 24, 'farmHandCostMult': 1,
       'maxMarketOrdersPerTurn': 10, 'shedCapacity': 100, 'boardSize': 10}


class EarlyCapitalContracts(unittest.TestCase):
    def test_land_moves_ahead_of_discretionary_product(self):
        selected = {'farmer': ['PLACE', 'WOOL', 10], 'hands': [],
                    'market': [['SELL', 'WOOL', 10], ['BUY_PRODUCT', 'WHEAT', 2],
                               ['BUY_LAND'], ['BUY_ANIMAL', 'COW', 2]]}
        route = [{'farmer': ['PASS'], 'hands': [], 'market': []} for _ in range(720)]
        result, report = order_early_capital(
            m, obs(150, money=2500, unlocked=['NW'], shed={'WOOL': 10}),
            CFG, selected, route, ((226, 'x', 1, 't'),))
        ops = [o[0] for o in result['market']]
        self.assertEqual(ops[0], 'SELL')
        self.assertIn('BUY_LAND', ops)
        self.assertIn('BUY_PRODUCT', ops)
        self.assertLess(ops.index('BUY_LAND'), ops.index('BUY_PRODUCT'))
        self.assertLess(ops.index('BUY_ANIMAL'), ops.index('BUY_PRODUCT'))
        self.assertTrue(report['changed'])
        self.assertEqual(result['farmer'], selected['farmer'])
        self.assertEqual(sorted(result['market'], key=lambda o: tuple(o)),
                         sorted(selected['market'], key=lambda o: tuple(o)))

    def test_same_day_melon_seed_stays_before_animals(self):
        selected = {'farmer': ['NORTH'], 'hands': [],
                    'market': [['SELL', 'WHEAT', 9], ['BUY_SEED', 'MELON', 12],
                               ['HIRE'], ['BUY_ANIMAL', 'COW', 2]]}
        route = [{'farmer': ['PASS'], 'hands': [], 'market': []} for _ in range(720)]
        route[4] = {'farmer': ['PLANT', 'MELON'], 'hands': [], 'market': []}
        result, report = order_early_capital(m, obs(1, money=2643), CFG, selected, route)
        ops = [o[0] for o in result['market']]
        self.assertLess(ops.index('BUY_SEED'), ops.index('BUY_ANIMAL'))
        self.assertLess(ops.index('HIRE'), ops.index('BUY_ANIMAL'))
        self.assertEqual(result['market'][1][1], 'MELON')

    def test_cross_turn_land_does_not_drop_today_seeds(self):
        selected = {'farmer': ['WEST'], 'hands': [],
                    'market': [['SELL', 'MELON', 12], ['BUY_SEED', 'CARROT', 9],
                               ['HIRE'], ['HIRE']]}
        route = [{'farmer': ['PASS'], 'hands': [], 'market': []} for _ in range(720)]
        route[265] = {'farmer': ['WEST'], 'hands': [], 'market': [['BUY_LAND']]}
        result, report = order_early_capital(
            m, obs(264, money=1800, unlocked=['NW', 'NE']), CFG, selected, route)
        self.assertFalse(report['changed'])
        self.assertEqual(report['reason'], 'no_admitted_capital')
        self.assertEqual(result['market'], selected['market'])
        self.assertEqual(result['farmer'], selected['farmer'])

    def test_never_reduces_purchases_to_pass(self):
        selected = {'farmer': ['PASS'], 'hands': [],
                    'market': [['BUY_PRODUCT', 'WHEAT', 8], ['BUY_SEED', 'CARROT', 9],
                               ['BUY_LAND']]}
        route = [{'farmer': ['PASS'], 'hands': [], 'market': []} for _ in range(720)]
        result, report = order_early_capital(
            m, obs(150, money=1200, unlocked=['NW']), CFG, selected, route)
        ops = [o[0] for o in result['market']]
        self.assertNotIn('PASS', ops)
        self.assertEqual(sorted(ops), sorted(o[0] for o in selected['market']))
        self.assertEqual(report.get('reduced'), [])

    def test_hire_reorder_cannot_consume_land_funding(self):
        selected = {'farmer': ['PASS'], 'hands': [],
                    'market': [['SELL', 'MILK', 1], ['BUY_LAND'], ['HIRE']]}
        route = [{'farmer': ['PASS'], 'hands': [], 'market': []} for _ in range(720)]
        # At the public base quote the original SELL -> LAND path is exactly
        # affordable: 840 + 160 == 1000. Moving HIRE ahead spends $1 first and
        # would turn the existing land purchase into an engine no-op.
        self.assertEqual(m.market_price('MILK', 10000), 160)
        self.assertEqual(840 + 160, m.LAND_PRICES[0])
        result, report = order_early_capital(
            m, obs(1, money=840, shed={'MILK': 1}), CFG, selected, route)
        self.assertEqual(result, selected)
        self.assertFalse(report['changed'])
        self.assertEqual(report['reason'], 'capital_prefix_not_fully_funded')
        self.assertEqual(report['capital_funding']['reason'], 'capital_would_lose_funding')
        self.assertEqual(report['capital_funding']['guaranteed_cash_floor'], 841.0)
        self.assertEqual(report['capital_funding']['required_cash_floor'], 1001.0)

    def test_floor_certified_hire_then_land_reorder_still_fires(self):
        selected = {'farmer': ['PASS'], 'hands': [],
                    'market': [['SELL', 'MILK', 1], ['BUY_LAND'], ['HIRE']]}
        route = [{'farmer': ['PASS'], 'hands': [], 'market': []} for _ in range(720)]
        result, report = order_early_capital(
            m, obs(1, money=1000, shed={'MILK': 1}), CFG, selected, route)
        self.assertEqual(result['market'],
                         [['SELL', 'MILK', 1], ['HIRE'], ['BUY_LAND']])
        self.assertTrue(report['changed'])
        self.assertEqual(report['reason'], 'ordered')
        self.assertEqual(report['capital_funding']['reason'], 'certified')
        self.assertEqual(report['capital_funding']['guaranteed_cash_floor'], 1001.0)
        self.assertEqual(report['capital_funding']['required_cash_floor'], 1001.0)

    def test_public_clock_requires_exact_plain_int_binding(self):
        selected = {'farmer': ['PASS'], 'hands': [],
                    'market': [['SELL', 'MILK', 1], ['BUY_LAND'], ['HIRE']]}
        route = [{'farmer': ['PASS'], 'hands': [], 'market': []} for _ in range(720)]
        good = obs(1, money=1000, shed={'MILK': 1})
        result, report = order_early_capital(m, good, CFG, selected, route)
        self.assertTrue(report['changed'])
        self.assertEqual(result['market'],
                         [['SELL', 'MILK', 1], ['HIRE'], ['BUY_LAND']])

        bad_clocks = []
        for value in ('1', True, 1.0, -1):
            bad = obs(1, money=1000, shed={'MILK': 1})
            bad['step'] = value
            bad_clocks.append(('step', value, bad))
        bad = obs(1, money=1000, shed={'MILK': 1}); bad['step'] = None
        bad_clocks.append(('step_none', None, bad))
        bad = obs(1, money=1000, shed={'MILK': 1}); bad['day'] = 1
        bad_clocks.append(('day_mismatch', 1, bad))
        bad = obs(1, money=1000, shed={'MILK': 1}); bad['hour'] = 2
        bad_clocks.append(('hour_mismatch', 2, bad))
        bad = obs(1, money=1000, shed={'MILK': 1}); bad['hour'] = 24
        bad_clocks.append(('hour_range', 24, bad))
        bad = obs(1, money=1000, shed={'MILK': 1}); bad['day'] = True
        bad_clocks.append(('day_bool', True, bad))
        bad = obs(1, money=1000, shed={'MILK': 1}); bad['hour'] = 1.0
        bad_clocks.append(('hour_float', 1.0, bad))
        bad = obs(1, money=1000, shed={'MILK': 1}); bad.pop('hour')
        bad_clocks.append(('missing_hour', None, bad))
        bad = obs(1, money=1000, shed={'MILK': 1}); bad.pop('day')
        bad_clocks.append(('missing_day', None, bad))

        for label, value, bad in bad_clocks:
            with self.subTest(label=label, value=value):
                out, bad_report = order_early_capital(m, bad, CFG, selected, route)
                self.assertEqual(out, selected)
                self.assertFalse(bad_report['changed'])
                self.assertEqual(bad_report['reason'], 'unsupported_time')

    def test_exact_day_hour_fallback_without_step_is_preserved(self):
        selected = {'farmer': ['PASS'], 'hands': [],
                    'market': [['SELL', 'MILK', 1], ['BUY_LAND'], ['HIRE']]}
        route = [{'farmer': ['PASS'], 'hands': [], 'market': []} for _ in range(720)]
        public = obs(1, money=1000, shed={'MILK': 1})
        public.pop('step')
        result, report = order_early_capital(m, public, CFG, selected, route)
        self.assertTrue(report['changed'])
        self.assertEqual(result['market'],
                         [['SELL', 'MILK', 1], ['HIRE'], ['BUY_LAND']])

    def test_terminal_and_late_day_fail_closed(self):
        selected = {'farmer': ['PASS'], 'hands': [], 'market': [['BUY_LAND'], ['SELL', 'MILK', 1]]}
        route = [selected] * 720
        late, report = order_early_capital(m, obs(718), CFG, selected, route)
        self.assertFalse(report['changed'])
        self.assertEqual(report['reason'], 'terminal_window')
        day21 = 21 * 24
        late2, report2 = order_early_capital(m, obs(day21, money=5000), CFG, selected, route)
        self.assertNotEqual(report2['reason'], 'ordered')

    def test_unknown_order_and_empty_fail_closed(self):
        selected = {'farmer': ['PASS'], 'hands': [], 'market': [['TELEPORT']]}
        out, report = order_early_capital(m, obs(1), CFG, selected, None)
        self.assertFalse(report['changed'])
        empty = {'farmer': ['PASS'], 'hands': [], 'market': []}
        out, report = order_early_capital(m, obs(1), CFG, empty, None)
        self.assertEqual(report['reason'], 'empty_market')

    def test_worker_actions_preserved(self):
        selected = {'farmer': ['WATER'], 'hands': [['HARVEST'], ['PASS']],
                    'market': [['BUY_PRODUCT', 'FERTILIZER', 1], ['BUY_LAND']]}
        route = [deepcopy(selected) for _ in range(720)]
        result, _ = order_early_capital(m, obs(150, money=4000), CFG, selected, route)
        self.assertEqual(result['farmer'], ['WATER'])
        self.assertEqual(result['hands'], [['HARVEST'], ['PASS']])

    def test_payback_table_matches_engine_first_yield(self):
        self.assertEqual(PAYBACK_DAYS['GOOSE'], m.ANIMALS['GOOSE']['first_yield_day'])
        self.assertEqual(PAYBACK_DAYS['COW'], m.ANIMALS['COW']['first_yield_day'])
        self.assertEqual(PAYBACK_DAYS['SHEEP'], m.ANIMALS['SHEEP']['first_yield_day'])
        self.assertEqual(EARLY_DAY_LIMIT, 20)


if __name__ == '__main__':
    unittest.main()