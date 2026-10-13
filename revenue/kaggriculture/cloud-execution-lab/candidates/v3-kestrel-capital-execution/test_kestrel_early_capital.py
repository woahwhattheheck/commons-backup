import unittest
from copy import deepcopy

from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
for source in (HERE, LAB):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

import mechanics as m
from kestrel_early_capital import (
    order_early_capital,
    PAYBACK_DAYS,
    EARLY_DAY_LIMIT,
)


def farm(money=3000, unlocked=('NW',), hires=0):
    tiles = [[None] * 10 for _ in range(10)]
    return {
        'money': money,
        'unlocked_quadrants': list(unlocked),
        'hires_today': hires,
        'tiles': tiles,
        'farmer': [4, 4],
        'hands': [],
    }


def obs(step=1, money=2643, unlocked=('NW',), seeds=None, shed=None,
        inventory=None, player=0, farmer_inventory=None):
    own = farm(money, unlocked)
    rival = farm(3000)
    market_inventory = {p: 10000 for p in m.PRODUCTS}
    market_inventory.update(inventory or {})
    return {
        'step': step,
        'day': step // 24,
        'hour': step % 24,
        'player': player,
        'farms': [own, rival] if player == 0 else [rival, own],
        'private': {
            'shed': dict(shed or {}),
            'inventories': [dict(farmer_inventory or {})],
            'seeds': dict(seeds or {}),
        },
        'market': {
            'inventory': market_inventory,
            'prices': {},
            'params': None,
        },
    }


def route():
    return [
        {'farmer': ['PASS'], 'hands': [], 'market': []}
        for _ in range(720)
    ]


CFG = {
    'episodeSteps': 720,
    'turnsPerDay': 24,
    'farmHandCostMult': 1,
    'maxMarketOrdersPerTurn': 10,
    'shedCapacity': 100,
}


class EarlyCapitalContracts(unittest.TestCase):
    def test_sell_funds_land_without_losing_existing_work(self):
        selected = {
            'farmer': ['PASS'],
            'hands': [],
            'market': [['BUY_LAND'], ['SELL', 'WOOL', 1]],
        }
        result, report = order_early_capital(
            m,
            obs(150, money=900, shed={'WOOL': 1}),
            CFG,
            selected,
            route(),
        )
        self.assertEqual(result['market'][0], ['SELL', 'WOOL', 1])
        self.assertEqual(result['market'][1], ['BUY_LAND'])
        self.assertTrue(report['changed'])
        self.assertEqual(report['reason'], 'execution_gain_proved')
        self.assertEqual(report['capital_execution_gain'], 1)

    def test_full_shed_sale_can_admit_animal(self):
        full = {'WOOL': 100}
        selected = {
            'farmer': ['PASS'],
            'hands': [],
            'market': [
                ['BUY_ANIMAL', 'GOOSE', 1],
                ['SELL', 'WOOL', 1],
            ],
        }
        result, report = order_early_capital(
            m, obs(150, money=300, shed=full), CFG, selected, route(),
        )
        self.assertEqual(result['market'][0][0], 'SELL')
        self.assertEqual(report['capital_execution_gain'], 1)
        self.assertEqual(
            report['candidate_receipts'][0]['executed'], 1,
        )

    def test_active_prefix_membership_is_immutable(self):
        selected = {
            'farmer': ['PASS'],
            'hands': [],
            'market': (
                [['PASS'] for _ in range(10)]
                + [['BUY_LAND'], ['SELL', 'WOOL', 1]]
            ),
        }
        result, report = order_early_capital(
            m, obs(150, money=900, shed={'WOOL': 1}),
            CFG, selected, route(),
        )
        self.assertEqual(result, selected)
        self.assertFalse(report['changed'])
        self.assertEqual(report['reason'], 'no_admitted_capital')

    def test_buy_then_sell_dependency_is_not_broken(self):
        selected = {
            'farmer': ['PASS'],
            'hands': [],
            'market': [
                ['BUY_PRODUCT', 'WHEAT', 1],
                ['BUY_LAND'],
                ['SELL', 'WHEAT', 1],
            ],
        }
        result, report = order_early_capital(
            m, obs(150, money=1000), CFG, selected, route(),
        )
        self.assertEqual(result, selected)
        self.assertEqual(report['reason'], 'execution_guard_rejected')
        reasons = {f['reason'] for f in report['guard_failures']}
        self.assertIn('noncapital_execution_changed', reasons)

    def test_capital_cannot_steal_cash_from_product_purchase(self):
        selected = {
            'farmer': ['PASS'],
            'hands': [],
            'market': [
                ['BUY_PRODUCT', 'WHEAT', 1],
                ['BUY_LAND'],
            ],
        }
        result, report = order_early_capital(
            m, obs(150, money=1000), CFG, selected, route(),
        )
        self.assertEqual(result, selected)
        self.assertEqual(report['reason'], 'execution_guard_rejected')
        before = {
            row['index']: row['executed']
            for row in report['original_receipts']
        }
        after = {
            row['index']: row['executed']
            for row in report['candidate_receipts']
        }
        self.assertEqual(before, {0: 1, 1: 0})
        self.assertEqual(after, {0: 0, 1: 1})

    def test_bound_post_unit_snapshot_drives_replay(self):
        selected = {
            'farmer': ['PASS'],
            'hands': [],
            'market': [['BUY_LAND'], ['SELL', 'WOOL', 1]],
        }
        before = obs(150, money=900, shed={})
        bound = deepcopy(before)
        bound['private']['shed']['WOOL'] = 1
        result, report = order_early_capital(
            m, before, CFG, selected, route(), post_unit=bound,
        )
        self.assertTrue(report['changed'])
        self.assertEqual(report['simulation_source'], 'bound_post_unit_snapshot')
        self.assertEqual(result['market'][0][0], 'SELL')

    def test_computed_unit_replay_includes_drop(self):
        selected = {
            'farmer': ['DROP'],
            'hands': [],
            'market': [['BUY_LAND'], ['SELL', 'WOOL', 1]],
        }
        observation = obs(
            150,
            money=900,
            shed={},
            farmer_inventory={'WOOL': 1},
        )
        result, report = order_early_capital(
            m, observation, CFG, selected, route(),
        )
        self.assertTrue(report['changed'])
        self.assertEqual(report['simulation_source'], 'computed_unit_replay')
        self.assertEqual(result['market'][0][0], 'SELL')

    def test_same_day_seed_and_hire_stay_before_animals(self):
        selected = {
            'farmer': ['NORTH'],
            'hands': [],
            'market': [
                ['SELL', 'WHEAT', 9],
                ['BUY_SEED', 'MELON', 12],
                ['HIRE'],
                ['BUY_ANIMAL', 'COW', 2],
            ],
        }
        plan = route()
        plan[151] = {
            'farmer': ['PLANT', 'MELON'],
            'hands': [],
            'market': [],
        }
        result, _ = order_early_capital(
            m,
            obs(150, money=2643, shed={'WHEAT': 9}),
            CFG,
            selected,
            plan,
        )
        ops = [order[0] for order in result['market']]
        self.assertLess(ops.index('BUY_SEED'), ops.index('BUY_ANIMAL'))
        self.assertLess(ops.index('HIRE'), ops.index('BUY_ANIMAL'))

    def test_cross_turn_land_does_not_drop_today_seeds(self):
        selected = {
            'farmer': ['WEST'],
            'hands': [],
            'market': [
                ['SELL', 'MELON', 12],
                ['BUY_SEED', 'CARROT', 9],
                ['HIRE'],
                ['HIRE'],
            ],
        }
        plan = route()
        plan[265] = {
            'farmer': ['WEST'],
            'hands': [],
            'market': [['BUY_LAND']],
        }
        result, report = order_early_capital(
            m, obs(264, money=1800, unlocked=('NW', 'NE')),
            CFG, selected, plan,
        )
        self.assertEqual(result, selected)
        self.assertEqual(report['reason'], 'no_admitted_capital')

    def test_never_reduces_or_replaces_purchases(self):
        selected = {
            'farmer': ['PASS'],
            'hands': [],
            'market': [
                ['BUY_PRODUCT', 'WHEAT', 8],
                ['BUY_SEED', 'CARROT', 9],
                ['BUY_LAND'],
            ],
        }
        result, report = order_early_capital(
            m, obs(150, money=1200), CFG, selected, route(),
        )
        self.assertEqual(
            sorted(map(repr, result['market'])),
            sorted(map(repr, selected['market'])),
        )
        self.assertEqual(report['reduced'], [])

    def test_no_change_without_a_proved_execution_gain(self):
        selected = {
            'farmer': ['PASS'],
            'hands': [],
            'market': [
                ['BUY_PRODUCT', 'WHEAT', 2],
                ['BUY_LAND'],
                ['BUY_ANIMAL', 'COW', 2],
            ],
        }
        result, report = order_early_capital(
            m, obs(150, money=5000), CFG, selected, route(),
        )
        self.assertEqual(result, selected)
        self.assertEqual(report['reason'], 'execution_guard_rejected')
        self.assertIn(
            'no_capital_execution_gain',
            {failure['reason'] for failure in report['guard_failures']},
        )

    def test_terminal_late_unknown_and_empty_fail_closed(self):
        selected = {
            'farmer': ['PASS'],
            'hands': [],
            'market': [['BUY_LAND'], ['SELL', 'MILK', 1]],
        }
        terminal, terminal_report = order_early_capital(
            m, obs(718), CFG, selected, route(),
        )
        self.assertEqual(terminal, selected)
        self.assertEqual(terminal_report['reason'], 'terminal_window')

        day21, day21_report = order_early_capital(
            m, obs(21 * 24), CFG, selected, route(),
        )
        self.assertEqual(day21, selected)
        self.assertEqual(day21_report['reason'], 'no_admitted_capital')

        invalid = deepcopy(selected)
        invalid['market'] = [['TELEPORT']]
        out, invalid_report = order_early_capital(
            m, obs(1), CFG, invalid, route(),
        )
        self.assertEqual(out, invalid)
        self.assertEqual(invalid_report['reason'], 'malformed_active_order')

        empty = {'farmer': ['PASS'], 'hands': [], 'market': []}
        out, empty_report = order_early_capital(
            m, obs(1), CFG, empty, route(),
        )
        self.assertEqual(out, empty)
        self.assertEqual(empty_report['reason'], 'empty_market')

        malformed_cfg = dict(CFG, turnsPerDay=0)
        out, malformed_report = order_early_capital(
            m, obs(1), malformed_cfg, selected, route(),
        )
        self.assertEqual(out, selected)
        self.assertEqual(malformed_report['reason'], 'malformed_context')

    def test_worker_actions_and_tail_bytes_are_preserved(self):
        selected = {
            'farmer': ['DROP'],
            'hands': [['HARVEST'], ['PASS']],
            'market': [
                ['BUY_LAND'], ['SELL', 'WOOL', 1],
            ] + [['PASS'] for _ in range(9)],
        }
        observation = obs(
            150, money=900, farmer_inventory={'WOOL': 1},
        )
        result, report = order_early_capital(
            m, observation, CFG, selected, route(),
        )
        self.assertTrue(report['changed'])
        self.assertEqual(result['farmer'], selected['farmer'])
        self.assertEqual(result['hands'], selected['hands'])
        self.assertEqual(result['market'][10:], selected['market'][10:])

    def test_receipts_are_deterministic(self):
        selected = {
            'farmer': ['PASS'],
            'hands': [],
            'market': [['BUY_LAND'], ['SELL', 'WOOL', 1]],
        }
        observation = obs(150, money=900, shed={'WOOL': 1})
        first, first_report = order_early_capital(
            m, deepcopy(observation), CFG, deepcopy(selected), deepcopy(route()),
        )
        second, second_report = order_early_capital(
            m, deepcopy(observation), CFG, deepcopy(selected), deepcopy(route()),
        )
        self.assertEqual(first, second)
        self.assertEqual(
            first_report['original_receipt_sha256'],
            second_report['original_receipt_sha256'],
        )
        self.assertEqual(
            first_report['candidate_receipt_sha256'],
            second_report['candidate_receipt_sha256'],
        )

    def test_sale_quote_regression_is_rejected(self):
        selected = {
            'farmer': ['PASS'],
            'hands': [],
            'market': [
                ['BUY_PRODUCT', 'WHEAT', 1],
                ['BUY_LAND'],
                ['SELL', 'WHEAT', 1],
            ],
        }
        result, report = order_early_capital(
            m,
            obs(150, money=1024, shed={'WHEAT': 1},
                inventory={'WHEAT': 10000}),
            CFG,
            selected,
            route(),
        )
        self.assertEqual(result, selected)
        reasons = {failure['reason'] for failure in report['guard_failures']}
        self.assertIn('sale_proceeds_regressed', reasons)

    def test_empty_slots_remain_valid_in_active_prefix(self):
        selected = {
            'farmer': ['PASS'],
            'hands': [],
            'market': [
                ['BUY_LAND'],
                None,
                [],
                ['SELL', 'WOOL', 1],
            ],
        }
        result, report = order_early_capital(
            m, obs(150, money=900, shed={'WOOL': 1}),
            CFG, selected, route(),
        )
        self.assertTrue(report['changed'])
        self.assertEqual(
            sorted(map(repr, result['market'])),
            sorted(map(repr, selected['market'])),
        )
        self.assertEqual(report['capital_execution_gain'], 1)

    def test_payback_table_matches_engine_first_yield(self):
        self.assertEqual(
            PAYBACK_DAYS['GOOSE'],
            m.ANIMALS['GOOSE']['first_yield_day'],
        )
        self.assertEqual(
            PAYBACK_DAYS['COW'],
            m.ANIMALS['COW']['first_yield_day'],
        )
        self.assertEqual(
            PAYBACK_DAYS['SHEEP'],
            m.ANIMALS['SHEEP']['first_yield_day'],
        )
        self.assertEqual(EARLY_DAY_LIMIT, 20)


if __name__ == '__main__':
    unittest.main()
