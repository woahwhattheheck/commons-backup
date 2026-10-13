# SPDX-License-Identifier: Apache-2.0
"""Run with PRICESEED_NATIVE_ROOT pointing to the unchanged checked release."""
from collections import Counter
from copy import deepcopy
import json
import os
from pathlib import Path
import random
import unittest

from harness import engine, initial, advance
from seed_budget import SeedBudget, _fixed_cost

ROOT = Path(os.environ.get('PRICESEED_NATIVE_ROOT', '/nonexistent'))
ENGINE, STRUCT = engine(ROOT)
CALLS = Counter()


def fixture(seat=0, money=1000, step=5, hands=0):
    state, env = initial(ENGINE, STRUCT)
    CALLS['initializations'] += 1
    for s in state:
        s.observation.step = step
        s.observation.day = step // 24
        s.observation.hour = step % 24
    farm = state[seat].observation.farms[seat]
    farm['money'] = money
    farm['farmer'] = [4, 4]
    farm['hands'] = [[3 - i, 4] for i in range(hands)]
    farm['hires_today'] = hands
    for row in farm['tiles']:
        for x, tile in enumerate(row):
            if tile != 'LOCKED':
                row[x] = None
    private = state[seat].observation.private
    private['inventories'] = [{} for _ in range(hands + 1)]
    private['seeds'] = {c: 0 for c in ENGINE.CROPS}
    private['seeds']['STRAWBERRY'] = hands + 1
    return state, env


def tick(state, env, action, seat=0, rival=None):
    actions = [None, None]
    actions[seat] = action
    actions[1 - seat] = rival or {'farmer': ['PASS'], 'hands': [], 'market': []}
    step = state[0].observation.step
    advance(ENGINE, state, env, actions, step)
    for s in state:
        s.observation.step = step + 1
    CALLS['transitions'] += 1


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.state, self.env = fixture()
        self.obs = self.state[0].observation
        self.cfg = self.env.configuration
        self.module = SeedBudget()
        self.now = {'farmer': ['PASS'], 'hands': [], 'market': []}
        self.next = {'farmer': ['PLANT', 'STRAWBERRY'], 'hands': [], 'market': [['SELL', 'WOOL', 1]]}
        self.args = dict(episode='a', route='r', source='STRAWBERRY', target='TOMATO',
                         budget=100, reserve=0, max_plants=2, enabled=True)

    def prepare(self, **changes):
        args = {**self.args, **changes}
        return self.module.prepare(self.now, self.obs, self.cfg, self.next, **args)

    def commit(self, action, **changes):
        return self.module.record_returned(action, self.obs, self.cfg,
                                          **{'episode': 'a', 'route': 'r', **changes})

    def ready(self):
        action, report = self.prepare()
        self.assertEqual(report['status'], 'purchase-proposed')
        self.assertTrue(self.commit(action))
        tick(self.state, self.env, action)
        return action

    def apply(self, **changes):
        return self.module.apply(self.next, self.obs, self.cfg,
                                 **{'episode': 'a', 'route': 'r', **changes})

    def test_disabled_identity_and_no_input_mutation(self):
        before = deepcopy((self.now, self.obs, self.cfg, self.next))
        out, r = self.prepare(enabled=False)
        self.assertIs(out, self.now)
        self.assertEqual(r['status'], 'disabled')
        self.assertIsNone(self.module.pending)
        self.assertEqual(before, (self.now, self.obs, self.cfg, self.next))

    def test_full_engine_buy_then_plant_both_seats(self):
        for seat in (0, 1):
            for hands in (0, 1, 2):
                state, env = fixture(seat, hands=hands)
                obs = state[seat].observation
                base = {'farmer': ['PASS'], 'hands': [], 'market': []}
                parent = {'farmer': ['PLANT', 'STRAWBERRY'],
                          'hands': [['PLANT', 'STRAWBERRY'] for _ in range(hands)], 'market': []}
                module = SeedBudget()
                action, r = module.prepare(base, obs, env.configuration, parent,
                    **{**self.args, 'budget': 500, 'max_plants': 3})
                self.assertEqual(r['quantity'], hands + 1)
                self.assertTrue(module.record_returned(action, obs, env.configuration, episode='a', route='r'))
                tick(state, env, action, seat)
                self.assertEqual(obs.private['seeds']['TOMATO'], hands + 1)
                self.assertIsNone(obs.farms[seat]['tiles'][4][4])
                out, r = module.apply(parent, obs, env.configuration, episode='a', route='r')
                self.assertEqual(r['status'], 'plant-proposed')
                tick(state, env, out, seat)
                for x in range(4 - hands, 5):
                    self.assertEqual(obs.farms[seat]['tiles'][4][x]['crop'], 'TOMATO')
                self.assertEqual(obs.private['seeds']['TOMATO'], 0)

    def test_seed_buy_cannot_fund_same_turn_plant(self):
        self.now['farmer'] = ['PLANT', 'TOMATO']
        out, r = self.prepare()
        self.assertEqual(r['quantity'], 1)
        tick(self.state, self.env, out)
        self.assertIsNone(self.obs.farms[0]['tiles'][4][4])
        self.assertEqual(self.obs.private['seeds']['TOMATO'], 1)

    def test_cash_reserves_real_hire_and_seed_cost(self):
        self.now['market'] = [['HIRE'], ['HIRE'], ['BUY_SEED', 'WHEAT', 3]]
        self.obs.farms[0]['money'] = 81
        out, r = self.prepare()
        self.assertIs(out, self.now)
        self.assertEqual(r['incumbent_cost'], 32)
        self.obs.farms[0]['money'] = 82
        out, r = self.prepare()
        self.assertEqual(r['status'], 'purchase-proposed')
        tick(self.state, self.env, out)
        self.assertEqual(self.obs.farms[0]['money'], 0)
        self.assertEqual(len(self.obs.farms[0]['hands']), 2)
        self.assertEqual(self.obs.private['seeds']['WHEAT'], 3)
        self.assertEqual(self.obs.private['seeds']['TOMATO'], 1)

    def test_does_not_count_future_sale_cash(self):
        self.obs.farms[0]['money'] = 49
        self.now['market'] = [['SELL', 'WOOL', 100]]
        self.obs.private['shed']['WOOL'] = 100
        out, r = self.prepare()
        self.assertIs(out, self.now)
        self.assertEqual(r['status'], 'cash-reserved')

    def test_dynamic_buy_is_vetoed_even_with_large_cash(self):
        self.now['market'] = [['BUY_PRODUCT', 'WHEAT', 1]]
        out, r = self.prepare()
        self.assertIs(out, self.now)
        self.assertEqual(r['status'], 'invalid-or-unsupported')

    def test_empty_slot_preserves_raw_prefix_and_dead_tail(self):
        self.cfg.maxMarketOrdersPerTurn = 2
        self.now['market'] = [[], ['SELL', 'WOOL', 1], ['BUY_PRODUCT', 'WHEAT', 10]]
        before = deepcopy(self.now)
        out, r = self.prepare()
        self.assertEqual(out['market'], [['BUY_SEED', 'TOMATO', 1], *before['market'][1:]])
        self.assertEqual(self.now, before)
        self.assertTrue(self.commit(out))

    def test_append_preserves_every_incumbent_slot(self):
        self.now['market'] = [['HIRE'], ['SELL', 'WOOL', 2], ['BUY_SEED', 'WHEAT', 1]]
        before = deepcopy(self.now)
        out, r = self.prepare()
        self.assertEqual(r['status'], 'purchase-proposed')
        self.assertEqual(out['market'][:-1], before['market'])
        self.assertEqual(out['market'][-1], ['BUY_SEED', 'TOMATO', 1])
        self.assertEqual(self.now, before)

    def test_full_cap_fails_and_zero_cap_uses_one(self):
        self.cfg.maxMarketOrdersPerTurn = 0
        self.now['market'] = [['SELL', 'WOOL', 1]]
        out, r = self.prepare()
        self.assertIs(out, self.now)
        self.assertEqual(r['status'], 'no-live-slot')
        self.now['market'] = [[]]
        out, r = self.prepare()
        self.assertEqual(out['market'], [['BUY_SEED', 'TOMATO', 1]])

    def test_budget_ceiling(self):
        out, r = self.prepare(budget=49)
        self.assertIs(out, self.now)
        self.assertEqual(r['status'], 'proposal-over-budget')

    def test_final_return_changes_invalidate_ticket(self):
        for field in ('market', 'farmer', 'hands'):
            out, _ = self.prepare()
            out[field] = [['PASS']] if field == 'hands' else []
            self.assertFalse(self.commit(out))
            self.assertIsNone(self.module.committed)
        out, _ = self.prepare()
        self.cfg.maxMarketOrdersPerTurn = 1
        self.assertFalse(self.commit(out))

    def test_dead_suffix_change_does_not_invalidate(self):
        self.cfg.maxMarketOrdersPerTurn = 1
        out, _ = self.prepare()
        out['market'].append(['BUY_SEED', 'TOMATO', 999])
        self.assertTrue(self.commit(out))

    def test_missing_final_return_cannot_authorize_plant(self):
        out, _ = self.prepare()
        tick(self.state, self.env, out)
        result, r = self.apply()
        self.assertIs(result, self.next)
        self.assertEqual(r['status'], 'no-ticket')

    def test_actual_stock_not_returned_buy_intent(self):
        out, _ = self.prepare()
        self.assertTrue(self.commit(out))
        # Deliberately different actual execution inputs: valid final intent is
        # not itself an observed fill. Admission must still reject on next obs.
        self.obs.farms[0]['money'] = 0
        tick(self.state, self.env, out)
        result, r = self.apply()
        self.assertIs(result, self.next)
        self.assertEqual(r['status'], 'observed-fill-shortfall')

    def test_atomic_ghost_target_demand_is_counted(self):
        self.ready()
        self.next['hands'] = [['PLANT', 'TOMATO']]
        result, r = self.apply()
        self.assertIs(result, self.next)
        self.assertEqual(r['status'], 'observed-fill-shortfall')
        # The real engine proves the missed ghost row blocks the real farmer.
        broken = deepcopy(self.next); broken['farmer'] = ['PLANT', 'TOMATO']
        tick(self.state, self.env, broken)
        self.assertIsNone(self.obs.farms[0]['tiles'][4][4])

    def test_atomic_source_group_not_accidentally_unblocked(self):
        self.ready()
        self.next['hands'] = [['PLANT', 'STRAWBERRY']]
        result, r = self.apply()
        self.assertIs(result, self.next)
        self.assertEqual(r['status'], 'parent-unfunded')

    def test_current_ghost_plant_reserves_target_stock(self):
        self.now['hands'] = [['PLANT', 'TOMATO']]
        self.obs.private['seeds']['TOMATO'] = 1
        out, r = self.prepare()
        self.assertEqual(r['quantity'], 1)

    def test_stale_episode_route_step_seat_consume_once(self):
        for key, value in [('episode', 'other'), ('route', 'other')]:
            self.setUp(); self.ready()
            result, r = self.apply(**{key: value})
            self.assertIs(result, self.next)
            self.assertEqual(r['status'], 'stale-identity')
            self.assertEqual(self.apply()[1]['status'], 'no-ticket')
        self.setUp(); self.ready(); self.obs.step += 1
        self.assertEqual(self.apply()[1]['status'], 'stale-identity')
        self.setUp(); self.ready(); self.obs.player = 1
        self.assertEqual(self.apply()[1]['status'], 'stale-identity')

    def test_parent_change_cancels(self):
        self.ready(); self.next['farmer'] = ['PASS']
        result, r = self.apply()
        self.assertIs(result, self.next)
        self.assertEqual(r['status'], 'parent-plant-changed')
        self.assertEqual(self.apply()[1]['status'], 'no-ticket')

    def test_geometry_locked_occupied_colliding_and_missing(self):
        for case in ('locked', 'occupied', 'collision'):
            self.setUp(); self.ready()
            if case == 'locked': self.obs.farms[0]['tiles'][4][4] = 'LOCKED'
            elif case == 'occupied': self.obs.farms[0]['tiles'][4][4] = ENGINE._new_plant('WHEAT', 0, 24)
            else: self.obs.farms[0]['hands'] = [[4, 4]]
            self.assertEqual(self.apply()[1]['status'], 'plant-site-unavailable')
        self.setUp(); self.next = {'farmer': ['PASS'], 'hands': [['PLANT', 'STRAWBERRY']], 'market': []}
        self.ready()
        self.assertEqual(self.apply()[1]['status'], 'missing-actor')

    def test_transforms_only_selected_plants_market_untouched(self):
        self.ready(); before = deepcopy((self.next, self.obs))
        result, r = self.apply()
        self.assertEqual(r['status'], 'plant-proposed')
        self.assertEqual(result['market'], self.next['market'])
        self.assertEqual(result['farmer'], ['PLANT', 'TOMATO'])
        self.assertEqual((self.next, self.obs), before)
        result['market'][0][2] = 999
        self.assertEqual(self.next['market'][0][2], 1)

    def test_malformed_inputs_fail_closed(self):
        for value in (True, None, '10', -1, 1.0):
            self.cfg.maxMarketOrdersPerTurn = value
            out, r = self.prepare()
            self.assertIs(out, self.now)
            self.assertEqual(r['status'], 'invalid-or-unsupported')
        self.setUp()
        for value in (True, None, float('nan'), float('inf'), -1):
            self.obs.farms[0]['money'] = value
            self.assertIs(self.prepare()[0], self.now)
        self.setUp(); self.obs.private['seeds']['TOMATO'] = True
        self.assertIs(self.prepare()[0], self.now)

    def test_preexisting_target_stock_needs_no_extra_purchase(self):
        self.obs.private['seeds']['TOMATO'] = 1
        out, r = self.prepare()
        self.assertIs(out, self.now)
        self.assertEqual(r['quantity'], 0)
        self.assertTrue(self.commit(out))
        tick(self.state, self.env, out)
        self.assertEqual(self.apply()[1]['status'], 'plant-proposed')

    def test_standard_full_shed_does_not_block_seed_purchase(self):
        self.obs.private['shed'] = {'WOOL': 100}
        self.ready()
        self.assertEqual(self.obs.private['seeds']['TOMATO'], 1)
        self.assertEqual(self.apply()[1]['status'], 'plant-proposed')

    def test_fixed_acquisitions_match_full_engine_both_seats(self):
        rng = random.Random(991)
        for seat in (0, 1):
            for _ in range(60):
                state, env = fixture(seat, money=100000, hands=0)
                obs = state[seat].observation
                obs.farms[seat]['hires_today'] = rng.randrange(12)
                env.configuration.farmHandCostMult = rng.randrange(1, 4)
                market = ([['HIRE']] * rng.randrange(4) +
                          [['BUY_SEED', rng.choice(list(ENGINE.CROPS)), rng.randrange(1, 4)]] +
                          ([['BUY_LAND']] if rng.randrange(2) else []) +
                          [['BUY_ANIMAL', rng.choice(list(ENGINE.ANIMALS)), 1]])
                expected = _fixed_cost(market, obs.farms[seat], env.configuration)
                # Animal purchases share shed capacity. This test starts empty.
                tick(state, env, {'farmer': ['PASS'], 'hands': [], 'market': market}, seat)
                self.assertEqual(100000 - obs.farms[seat]['money'], expected)


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(AdmissionTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({'tests': result.testsRun, 'failures': len(result.failures),
                      'errors': len(result.errors), 'skipped': len(result.skipped),
                      'engine_calls': dict(CALLS)}), flush=True)
    raise SystemExit(not result.wasSuccessful())
