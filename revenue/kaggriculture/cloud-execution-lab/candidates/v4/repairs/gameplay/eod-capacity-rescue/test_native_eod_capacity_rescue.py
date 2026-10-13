# SPDX-License-Identifier: Apache-2.0
"""Source-pinned native projection + official full-interpreter differential gate.

TITAN_RUNTIME_ROOT=/path/to/production python test_native_eod_capacity_rescue.py
Repeat with python -O. Uses existing offline engine/evaluator bytes; no downloads.
"""
from __future__ import annotations

import copy
from collections import Counter
import hashlib
import importlib.util
import itertools
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from native_eod_capacity_rescue import apply_native_eod_capacity_rescue as rescue

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ['TITAN_RUNTIME_ROOT']) if 'TITAN_RUNTIME_ROOT' in os.environ else next(
    (p for p in HERE.parents if (p / 'scheduler.py').is_file()), HERE)
PINS = {'scheduler.py': 'a483b24dd72b580d7d8811636b54d2d44f391575',
        'mechanics.py': '044a4f9c0a4a44dde10ada57563238bcaf82075d'}
COUNTS = Counter()


def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def passed(n=0):
    return {'farmer': ['PASS'], 'hands': [['PASS'] for _ in range(n)], 'market': []}


class NativeEOD(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for name, expected in PINS.items():
            actual = blob((ROOT / name).read_bytes())
            if actual != expected:
                raise ValueError(f'{name}: expected {expected}; got {actual}')
        sys.path.insert(0, str(ROOT))
        spec = importlib.util.spec_from_file_location('native_eod_eval', ROOT / 'checks/reference/evaluator/evaluate.py')
        cls.ev = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.ev)
        cls.engine, cls.hashes = cls.ev.get_engine(ROOT / 'checks/reference/engine',
                                                  ROOT / 'checks/reference/evaluator/loader.py')
        import scheduler
        cls.scheduler = scheduler
        for module, filename in ((scheduler, 'scheduler.py'), (scheduler.m, 'mechanics.py')):
            if blob(Path(module.__file__).read_bytes()) != PINS[filename]:
                raise ValueError('Imported module does not match source pin')

    def fixture(self, seat=0, product='MILK', shed=100, cargo=(5,), step=23, floor=False):
        E, S = self.engine, self.ev.Struct
        cfg = S({k: v.get('default') if isinstance(v, dict) else v
                 for k, v in E.specification['configuration'].items()})
        cfg.weedSpawnChance = 0
        farms = [E._new_farm(10, 10000), E._new_farm(10, 10000)]
        farms[seat]['hands'] = [[0, i + 1] for i in range(len(cargo) - 1)]
        farms[seat]['farmer'] = [0, 0]
        market = E._new_market()
        if floor:
            market['inventory'][product] = 100000
        E._refresh_prices(market)
        state = []
        for player in range(2):
            private = E._new_private()
            if player == seat:
                private['shed'][product] = shed
                private['inventories'] = [{product: n} if n else {} for n in cargo]
            state.append(S(observation=S(player=player, step=step, day=step // 24,
                                         hour=step % 24, farms=farms, private=private,
                                         market=market, town={'unlocked_shops': []}),
                           action=passed(len(cargo) - 1 if player == seat else 0),
                           status='ACTIVE', reward=0))
        return state, S(configuration=cfg, done=False, info={'seed': 7712345})

    def pair(self, state, env, seat, *, expect=True):
        original = copy.deepcopy(state)
        action = state[seat].action
        result, info = rescue(action, state[seat].observation, env.configuration, enabled=True)
        self.assertEqual(state, original, 'candidate mutated input')
        self.assertEqual(info['changed'], expect, info)
        COUNTS['candidates'] += 1
        if not expect:
            self.assertIs(result, action)
            return info, None, None
        self.assertIsNot(result, action)
        self.assertEqual(result['farmer'], action['farmer'])
        self.assertEqual(result['hands'], action['hands'])
        self.assertEqual(result['market'][:-1], action['market'])
        self.assertEqual(result['market'][-1], ['SELL', info['product'], info['rescued_units']])
        parent, candidate = copy.deepcopy(state), copy.deepcopy(state)
        candidate[seat].action = result
        self.engine.interpreter(parent, copy.deepcopy(env))
        self.engine.interpreter(candidate, copy.deepcopy(env))
        COUNTS['full_interpreter_pairs'] += 1
        self.assertEqual(parent[seat].observation.private, candidate[seat].observation.private)
        pf = copy.deepcopy(parent[0].observation.farms)
        cf = copy.deepcopy(candidate[0].observation.farms)
        gain = cf[seat].pop('money') - pf[seat].pop('money')
        # Rival money is allowed to respond to changed public supply.
        cf[1-seat].pop('money'); pf[1-seat].pop('money')
        self.assertEqual(cf, pf)
        self.assertGreaterEqual(gain, info['rescued_units'])
        self.assertEqual(candidate[seat].observation.private['inventories'], [{}])
        self.assertEqual(candidate[0].observation.town, parent[0].observation.town)
        COUNTS['rescued_units'] += info['rescued_units']
        return info, parent, candidate

    def test_01_off_identity_no_projection(self):
        state, env = self.fixture()
        with patch.object(self.scheduler, 'post_units', side_effect=AssertionError('OFF projected')):
            result, info = rescue(state[0].action, state[0].observation, env.configuration)
        self.assertIs(result, state[0].action)
        self.assertEqual(info, {'changed': False, 'reason': 'disabled'})
        result, _ = rescue(None, None, None)
        self.assertIsNone(result)

    def test_02_all_products_both_seats_capacity_quote_grid(self):
        for seat, item, total, cargo, floor in itertools.product(
                (0, 1), self.engine.PRODUCTS, (85, 95, 100), (1, 6, 17), (False, True)):
            with self.subTest(seat=seat, item=item, total=total, cargo=cargo, floor=floor):
                state, env = self.fixture(seat, item, total, (cargo,), floor=floor)
                self.pair(state, env, seat, expect=total + cargo > 100)

    def test_03_harvest_created_overflow_real_actor_order(self):
        for seat, first in itertools.product((0, 1), (0, 1)):
            state, env = self.fixture(seat, 'WHEAT', 100, (0, 0), step=71)
            farm = state[0].observation.farms[seat]
            farm['farmer'] = farm['hands'][0] = [0, 0]
            plant = self.engine._new_plant('WHEAT', 0, 24)
            plant['yield_units'] = 5
            farm['tiles'][0][0] = plant
            actions = [['HARVEST'], ['HARVEST']] if first == 0 else [['WATER'], ['HARVEST']]
            state[seat].action.update(farmer=actions[0], hands=[actions[1]])
            self.assertEqual(sum(sum(x.values()) for x in state[seat].observation.private['inventories']), 0)
            info, _, _ = self.pair(state, env, seat)
            self.assertEqual(info['rescued_units'], 5 + first)
            # A pre-unit cargo calculation sees zero and misses the opportunity.
            self.assertLessEqual(sum(state[seat].observation.private['shed'].values()) - 100, 0)

    def test_04_drop_already_discarded_must_not_sell(self):
        for seat in (0, 1):
            state, env = self.fixture(seat)
            state[0].observation.farms[seat]['farmer'] = [4, 4]
            state[seat].action['farmer'] = ['DROP']
            self.pair(state, env, seat, expect=False)
            # The predecessor's neutral-op veto is correct here; do not remove it
            # without a matching post-unit projection.
            self.engine.interpreter(state, env)
            self.assertEqual(state[seat].observation.private['shed']['MILK'], 100)

    def test_05_place_partial_still_rescues_remaining_cargo(self):
        for seat in (0, 1):
            state, env = self.fixture(seat, shed=97, cargo=(8,))
            state[0].observation.farms[seat]['farmer'] = [4, 4]
            state[seat].action['farmer'] = ['PLACE', 'MILK', 2]
            info, _, _ = self.pair(state, env, seat)
            self.assertEqual(info['rescued_units'], 5)
            self.assertEqual(info['post_unit_shed_total'], 99)

    def test_06_feed_and_fertilize_use_post_consumption_quantity(self):
        for seat, op in itertools.product((0, 1), ('FEED', 'FERTILIZE')):
            product = 'WHEAT' if op == 'FEED' else 'FERTILIZER'
            state, env = self.fixture(seat, product, 100, (5,))
            farm = state[0].observation.farms[seat]
            farm['tiles'][0][0] = self.engine._new_animal('COW', 0) if op == 'FEED' else self.engine._new_plant('WHEAT', 0, 24)
            state[seat].action['farmer'] = [op]
            info, _, _ = self.pair(state, env, seat)
            self.assertEqual(info['rescued_units'], 4)

    def test_07_collect_fertilizer_creates_overflow(self):
        for seat in (0, 1):
            state, env = self.fixture(seat, 'FERTILIZER', 100, (0,))
            tile = self.engine._new_animal('COW', 0)
            tile['fertilizer_available'] = True
            state[0].observation.farms[seat]['tiles'][0][0] = tile
            state[seat].action['farmer'] = ['COLLECT_FERTILIZER']
            info, _, _ = self.pair(state, env, seat)
            self.assertEqual(info['rescued_units'], 1)

    def test_08_multiple_inventories_and_mixed_shed_identity(self):
        for seat, count in itertools.product((0, 1), (1, 2, 4)):
            state, env = self.fixture(seat, 'MILK', 20, (9,) * count)
            state[seat].observation.private['shed']['WHEAT'] = 80
            info, _, _ = self.pair(state, env, seat, expect=count * 9 <= 20)
            if info['changed']:
                self.assertEqual(info['rescued_units'], count * 9)

    def test_09_mixed_or_unknown_cargo_fail_closed(self):
        for seat, item in itertools.product((0, 1), ('EGG', 'COW', '???')):
            state, env = self.fixture(seat)
            state[seat].observation.private['inventories'][0][item] = 1
            if item == 'EGG':
                # Fund either possible set-iteration choice so a broken mixed-
                # cargo guard cannot hide behind insufficient same-item stock.
                state[seat].observation.private['shed'].update(MILK=50, EGG=50)
            self.pair(state, env, seat, expect=False)

    def test_10_market_rows_budget_and_stock_changes(self):
        for rows in ([['SELL', 'EGG', 0]], [['BUY_PRODUCT', 'EGG', 1]],
                     [['BUY_ANIMAL', 'COW', 1]], [['???']], [[[]]],
                     [None], [[]] * 10, [[]] * 11):
            state, env = self.fixture()
            state[0].action['market'] = rows
            self.pair(state, env, 0, expect=False)
        state, env = self.fixture()
        state[0].action['market'] = [[]] * 9
        info, _, _ = self.pair(state, env, 0)
        self.assertEqual(info['rescued_units'], 5)

    def test_11_hire_land_seed_market_prefix_and_metadata(self):
        for seat in (0, 1):
            state, env = self.fixture(seat)
            state[seat].action['market'] = [['HIRE'], ['BUY_LAND', 'NE'], ['BUY_SEED', 'WHEAT', 2]]
            state[seat].action['debug'] = {'trace': ['retain']}
            info, _, _ = self.pair(state, env, seat)
            self.assertEqual(info['rescued_units'], 5)

    def test_12_terminal_day_and_non_eod(self):
        for step in (0, 22, 24, 694, 696, 718, 719, -1, True):
            state, env = self.fixture(step=step)
            self.pair(state, env, 0, expect=False)
        state, env = self.fixture(step=695)
        self.pair(state, env, 0)

    def test_13_standard_configuration_guard(self):
        for key, value in (('shedCapacity', 101), ('maxMarketOrdersPerTurn', 12),
                           ('turnsPerDay', 12), ('episodeSteps', 719),
                           ('boardSize', 8), ('townShopSellInterval', 23),
                           ('townCenterSellInterval', 23), ('shedCapacity', True)):
            state, env = self.fixture()
            env.configuration[key] = value
            self.pair(state, env, 0, expect=False)

    def test_14_schema_fail_closed(self):
        mutations = [lambda o, a: o.update(player=True), lambda o, a: o.update(player=2),
                     lambda o, a: o['farms'].append({}),
                     lambda o, a: o['farms'][0].update(farmer=[0, '0']),
                     lambda o, a: o['farms'][0].update(money=float('inf')),
                     lambda o, a: o['private']['inventories'][0].update(MILK=True),
                     lambda o, a: o['private']['shed'].update(MILK=-1),
                     lambda o, a: o['market']['prices'].update(MILK=True),
                     lambda o, a: a.update(farmer=[[]]),
                     lambda o, a: a.update(hands=None),
                     lambda o, a: a.update(farmer=['PICKUP', 'MILK', '3'])]
        for mutate in mutations:
            state, env = self.fixture()
            mutate(state[0].observation, state[0].action)
            self.pair(state, env, 0, expect=False)

    def test_15_projection_errors_fail_closed_not_deadlines(self):
        state, env = self.fixture()
        with patch.object(self.scheduler, 'post_units', side_effect=ValueError('bad state')):
            self.pair(state, env, 0, expect=False)
        class DeadlineExceeded(Exception):
            pass
        with patch.object(self.scheduler, 'post_units', side_effect=DeadlineExceeded()):
            with self.assertRaises(DeadlineExceeded):
                rescue(state[0].action, state[0].observation, env.configuration, enabled=True)

    def test_16_actual_atomic_plant_projection(self):
        for seat, seeds in itertools.product((0, 1), (1, 2)):
            state, env = self.fixture(seat, 'MILK', 100, (2, 3))
            state[seat].observation.private['seeds']['WHEAT'] = seeds
            state[seat].action.update(farmer=['PLANT', 'WHEAT'], hands=[['PLANT', 'WHEAT']])
            info, parent, candidate = self.pair(state, env, seat)
            self.assertEqual(info['rescued_units'], 5)
            self.assertEqual(parent[seat].observation.private['seeds']['WHEAT'], seeds if seeds == 1 else 0)

    def test_17_rival_order_streams_not_a_public_state_theorem(self):
        for seat, op, floor in itertools.product((0, 1), ('BUY_PRODUCT', 'SELL'), (False, True)):
            state, env = self.fixture(seat, floor=floor)
            state[1-seat].observation.private['shed']['MILK'] = 20
            state[1-seat].action['market'] = [[op, 'MILK', 7]]
            self.pair(state, env, seat)

    def test_18_floor_pass_rival_exact_public_state_and_margin(self):
        for seat in (0, 1):
            state, env = self.fixture(seat, floor=True)
            info, parent, candidate = self.pair(state, env, seat)
            self.assertEqual(parent[0].observation.market, candidate[0].observation.market)
            self.assertEqual(candidate[0].observation.farms[seat]['money'] - parent[0].observation.farms[seat]['money'], 5)
            self.assertEqual(info['rescued_units'], 5)


    def test_19_omitted_and_extra_actor_commands_exact_engine(self):
        for seat in (0, 1):
            state, env = self.fixture(seat, cargo=(0, 5))
            state[seat].action['hands'] = []
            info, _, _ = self.pair(state, env, seat)
            self.assertEqual(info['rescued_units'], 5)
            state, env = self.fixture(seat)
            state[seat].action['hands'] = [['HARVEST']]
            info, _, _ = self.pair(state, env, seat)
            self.assertEqual(info['rescued_units'], 5)
            # Ghost PLANT still counts in atomic demand even though no actor
            # can execute it. The real farmer must NOT plant the single seed.
            state, env = self.fixture(seat)
            state[seat].observation.private['seeds']['WHEAT'] = 1
            state[seat].action.update(farmer=['PLANT', 'WHEAT'], hands=[['PLANT', 'WHEAT']])
            _, parent, _ = self.pair(state, env, seat)
            self.assertEqual(parent[seat].observation.private['seeds']['WHEAT'], 1)


if __name__ == '__main__':
    outcome = unittest.main(verbosity=2, exit=False)
    print(json.dumps({'counts': dict(COUNTS), 'runtime_pins': PINS}, sort_keys=True))
    sys.exit(0 if outcome.result.wasSuccessful() else 1)
