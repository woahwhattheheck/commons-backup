# SPDX-License-Identifier: Apache-2.0
"""Reopened S8 acceptance; real pinned interpreter, no legacy runtime imports.

S8_NATIVE_ROOT must identify the unpacked b567 native artifact. No network fetch.
S8_MODULE optionally selects a generated helper (used by semantic fault controls).
"""
from __future__ import annotations
import copy
import hashlib
import importlib.util
import os
from pathlib import Path
import random
import sys
import types
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import compose_reopened_s8 as composer

PINS = {
    'checks/reference/engine/kaggriculture.py': '3c202c7ee921da239356789e266b694635103fc4',
    'checks/reference/engine/kaggriculture.json': 'b354d06b742fe48402513792253f1a5c29366b20',
    'checks/reference/engine/utils.py': '91c8822ee6201ba4a5a8416c7dbe34f95dd61c87',
    'checks/reference/evaluator/loader.py': '23948e10cfc3d32f46c9abb1321b0d8fc8db21d5',
}


def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


native = Path(os.environ['S8_NATIVE_ROOT']) if 'S8_NATIVE_ROOT' in os.environ else HERE.parents[4]
for rel, expected in PINS.items():
    data = (native / rel).read_bytes()  # Missing/changed inputs fail before imports.
    if blob(data) != expected:
        raise ValueError(f'input mismatch: {rel}')
loader = load(native / 'checks/reference/evaluator/loader.py', 's8_pinned_loader')
engine, _engine_hashes = loader.get_engine(native / 'checks/reference/engine')
Struct = loader.Struct
DONOR = (HERE / 's8_egg_care.py').read_bytes()
generated = composer.compose(DONOR)
if os.environ.get('S8_MODULE'):
    lane = load(Path(os.environ['S8_MODULE']), 's8_external_candidate')
else:
    lane = types.ModuleType('s8_generated_candidate')
    exec(compile(generated, 'generated_reopened_s8.py', 'exec'), lane.__dict__)
donor = types.ModuleType('s8_original_donor')
exec(compile(DONOR, 'original_s8.py', 'exec'), donor.__dict__)
CALLS = 0
INITIALIZATIONS = 0
TRANSITIONS = 0


def action(row='COLLECT_FERTILIZER', market=None):
    return {'farmer': [row], 'hands': [], 'market': [] if market is None else market}


def world(seat=0, *, full=False, egg=115, fert=100, day=10, units=0, stock=6):
    cfg = Struct({k: v.get('default') if isinstance(v, dict) else v
                  for k, v in engine.specification['configuration'].items()})
    cfg.update(seed=991, weedSpawnChance=0,
               marketParams={'EGG': {'base': egg}, 'FERTILIZER': {'base': fert}})
    env = Struct(configuration=cfg, done=False, info={})
    state = [Struct(observation=Struct(), action={}, status='ACTIVE', reward=0)
             for _ in range(2)]
    transition(state, env, None)
    farm = state[seat].observation.farms[seat]
    tile = engine._new_animal('GOOSE', 0)
    tile.update(yield_units=units, fed_today=True, fertilizer_available=True)
    farm['tiles'][4][4] = tile
    farm['farmer'] = [4, 4]
    priv = state[seat].observation.private
    priv['shed'].update(FERTILIZER=stock, WHEAT=10, MILK=100-stock-10 if full else 0)
    priv['inventories'] = [{}]
    for s in state:
        s.observation.update(step=day*24+23, day=day, hour=23)
    return state, env


def transition(state, env, step, own=None, seat=0, rival=None):
    global CALLS, INITIALIZATIONS, TRANSITIONS
    if step is not None:
        for i, s in enumerate(state):
            s.observation.step = step
            s.action = (own if i == seat else rival) or action('PASS')
    CALLS += 1
    INITIALIZATIONS += int(step is None)
    TRANSITIONS += int(step is not None)
    return engine.interpreter(state, env)


def obs(state, seat=0):
    return copy.deepcopy(state[seat].observation)


def goose(state, seat=0):
    return state[seat].observation.farms[seat]['tiles'][4][4]


def apply(state, env, parent=None, seat=0, mode='spread_or_discard'):
    return lane.apply_egg_care(obs(state, seat), parent or action(), env.configuration,
                               enabled=True, price_mode=mode)


def continuation(state, env, seat, start=263, *, feed=True):
    # Same observable continuation policy for both arms. No further CARE.
    # Liquidate FERT/MILK, feed once, realize next-cycle EGG by HARVEST/DROP/SELL.
    for step in range(start+1, start+29):
        offset = step-start
        private = state[seat].observation.private
        if offset == 1:
            a = {'farmer': ['PICKUP', 'WHEAT', 1] if feed else ['PASS'], 'hands': [],
                 'market': [['SELL', item, private['shed'].get(item, 0)]
                            for item in ('FERTILIZER', 'MILK')]}
        elif offset == 2:
            a = action('FEED' if feed else 'PASS')
        elif offset == 25:
            a = action('HARVEST')
        elif offset == 26:
            a = action('DROP')
        elif offset == 27:
            a = action('PASS', [['SELL', 'EGG', private['shed'].get('EGG', 0)]])
        else:
            a = action('PASS')
        transition(state, env, step, a, seat)
    return state[seat].observation.farms[seat]['money']


class ReopenedS8(unittest.TestCase):
    def tearDown(self):
        lane.telemetry.clear()

    def test_donor_byte_identity_and_drift_rejected(self):
        self.assertEqual(blob(DONOR), composer.DONOR_BLOB)
        self.assertEqual(composer.compose(DONOR), generated)
        with self.assertRaises(ValueError):
            composer.compose(DONOR + b'\n')

    def test_ships_disabled_same_key(self):
        state, env = world()
        a = action()
        self.assertEqual(lane.KEY, 'r04_s8_egg_care')
        self.assertIs(lane.apply_egg_care(obs(state), a, env.configuration), a)

    def test_positive_small_spread_reopens_earlier_quote(self):
        state, env = world(egg=115, fert=100)
        a = action()
        self.assertIs(donor.apply_egg_care(obs(state), a, env.configuration, enabled=True), a)
        self.assertEqual(apply(state, env)['farmer'], ['CARE'])
        self.assertEqual(lane.telemetry['spread_activations'], 1)

    def test_equal_or_negative_spread_does_not_spend_fertilizer(self):
        for egg in (50, 100):
            state, env = world(egg=egg)
            a = action()
            self.assertIs(apply(state, env, a), a)

    def test_certified_discard_reopens_low_quote_without_buffer(self):
        for seat in (0, 1):
            state, env = world(seat, full=True, egg=50, stock=0)
            self.assertEqual(apply(state, env, seat=seat)['farmer'], ['CARE'])
        self.assertEqual(lane.telemetry['discard_activations'], 2)
        self.assertEqual(lane.telemetry['fertilizer_units_foregone'], 0)

    def test_discard_requires_full_lower_bound(self):
        state, env = world(full=True, egg=50)
        a = action()
        state[0].observation.private['shed']['MILK'] -= 1
        self.assertFalse(lane.discarded_fertilizer(obs(state), a, env.configuration))
        self.assertIs(apply(state, env, a), a)

    def test_live_sell_room_veto(self):
        state, env = world(full=True, egg=50)
        a = action(market=[['SELL', 'MILK', 1]])
        self.assertFalse(lane.discarded_fertilizer(obs(state), a, env.configuration))
        self.assertIs(apply(state, env, a), a)

    def test_unfillable_sell_is_conservatively_subtracted(self):
        state, env = world(full=True, egg=50)
        a = action(market=[['SELL', 'WOOL', 1]])
        self.assertIs(apply(state, env, a), a)

    def test_buy_never_invents_full_shed(self):
        state, env = world(egg=50)
        a = action(market=[['BUY_PRODUCT', 'MILK', 1000]])
        self.assertFalse(lane.discarded_fertilizer(obs(state), a, env.configuration))
        self.assertIs(apply(state, env, a), a)

    def test_dead_sell_suffix_does_not_veto_or_compact(self):
        state, env = world(full=True, egg=50)
        env.configuration.maxMarketOrdersPerTurn = 1
        a = action(market=[[], ['SELL', 'MILK', 1]])
        self.assertEqual(apply(state, env, a)['farmer'], ['CARE'])
        self.assertEqual(a['market'], [[], ['SELL', 'MILK', 1]])

    def test_malformed_live_rows_block_but_dead_rows_are_irrelevant(self):
        for bad in (None, 8, ['UNKNOWN'], ['SELL', 'MILK', True], ['SELL', 'MILK', -1]):
            state, env = world(full=True, egg=50)
            env.configuration.maxMarketOrdersPerTurn = 1
            a = action(market=[bad])
            self.assertIs(apply(state, env, a), a)
            b = action(market=[[], bad])
            self.assertEqual(apply(state, env, b)['farmer'], ['CARE'])

    def test_pickup_blocks_discard_certificate(self):
        state, env = world(full=True, egg=50)
        farm = state[0].observation.farms[0]
        farm['hands'] = [[4, 3]]
        a = action(); a['hands'] = [['PICKUP', 'WHEAT', 1]]
        self.assertIs(apply(state, env, a), a)

    def test_original_harvest_priority_unchanged(self):
        state, env = world(full=True, egg=200)
        a = action('HARVEST')
        self.assertIs(apply(state, env, a), a)

    def test_original_no_harvest_cap_bound_preserved(self):
        for held in (2, 3, 4):
            state, env = world(units=held, full=True, egg=200)
            a = action()
            self.assertIs(apply(state, env, a), a)

    def test_unfed_cared_unavailable_and_pending_block(self):
        for field, value in (('fed_today', False), ('cared_today', True),
                             ('fertilizer_available', False), ('pending_care_bonus', 1)):
            state, env = world(full=True, egg=200)
            goose(state)[field] = value
            a = action()
            self.assertIs(apply(state, env, a), a)

    def test_final_day_and_hour_block(self):
        for step in (28*24+23, 29*24+23, 10*24+22):
            state, env = world(full=True, egg=200)
            for s in state: s.observation.step = step
            a = action()
            self.assertIs(apply(state, env, a), a)

    def test_immature_block(self):
        state, env = world(day=1, full=True, egg=200)
        a = action()
        self.assertIs(apply(state, env, a), a)

    def test_stacked_active_actor_block(self):
        state, env = world(full=True, egg=200)
        state[0].observation.farms[0]['hands'] = [[4, 4]]
        a = action(); a['hands'] = [['HARVEST']]
        self.assertIs(apply(state, env, a), a)

    def test_future_config_and_bool_types_fail_closed(self):
        for key, value in (('turnsPerDay', 12), ('episodeSteps', 721), ('turnsPerDay', True)):
            state, env = world(full=True, egg=200)
            env.configuration[key] = value
            a = action()
            self.assertIs(apply(state, env, a), a)
        for value in (True, -1, 0.5):
            state, env = world(full=True, egg=50)
            state[0].observation.private['shed']['MILK'] = value
            a = action()
            self.assertIs(apply(state, env, a), a)

    def test_modes_and_low_buffer(self):
        state, env = world(egg=115)
        a = action()
        self.assertIs(apply(state, env, a, mode='donor'), a)
        self.assertIs(apply(state, env, a, mode='discard'), a)
        self.assertEqual(apply(state, env, a, mode='spread')['farmer'], ['CARE'])
        state[0].observation.private['shed']['FERTILIZER'] = 3
        self.assertIs(apply(state, env, a, mode='spread'), a)
        with self.assertRaises(ValueError):
            apply(state, env, a, mode='typo')

    def test_invalid_price_cannot_certify(self):
        for value in (True, 0, -1, 2.5, None):
            state, env = world(full=True)
            state[0].observation.market['prices']['EGG'] = value
            a = action()
            self.assertIs(apply(state, env, a), a)

    def test_input_mutation_and_result_alias_separation(self):
        state, env = world(full=True, egg=50)
        o = obs(state); a = action(); before = copy.deepcopy((o, a))
        out = lane.apply_egg_care(o, a, env.configuration, enabled=True)
        self.assertEqual((o, a), before)
        self.assertIsNot(out, a)
        out['farmer'].append('x'); out['market'].append(['PASS'])
        self.assertEqual((o, a), before)

    def test_original_donor_mode_action_equivalence(self):
        rng = random.Random(667)
        for _ in range(160):
            state, env = world(egg=rng.randrange(50, 220), units=rng.randrange(5),
                               day=rng.randrange(30), stock=rng.randrange(9))
            tile = goose(state)
            tile['fed_today'] = rng.choice((True, False))
            tile['pending_care_bonus'] = rng.randrange(2)
            a = action()
            expected = donor.apply_egg_care(obs(state), a, env.configuration, enabled=True)
            actual = apply(state, env, a, mode='donor')
            self.assertEqual(actual, expected)
            self.assertEqual(actual is a, expected is a)

    def test_actual_first_eod_discard_state_equivalence(self):
        rng = random.Random(722)
        for seat in (0, 1):
            for _ in range(40):
                state, env = world(seat, full=True, egg=50, units=rng.randrange(2), stock=rng.randrange(11))
                private = state[seat].observation.private
                # Multiple item ordering variants, all must discard when full.
                items = [('EGG', rng.randrange(5)), ('FERTILIZER', rng.randrange(5)), ('WHEAT', rng.randrange(5))]
                rng.shuffle(items); private['inventories'] = [dict(items)]
                a = action(); out = apply(state, env, a, seat)
                self.assertEqual(out['farmer'], ['CARE'])
                baseline, baseline_env = copy.deepcopy((state, env))
                candidate, candidate_env = copy.deepcopy((state, env))
                rival = action('PASS', [['BUY_PRODUCT', 'EGG', rng.randrange(4)]])
                transition(baseline, baseline_env, 263, a, seat, rival)
                transition(candidate, candidate_env, 263, out, seat, rival)
                self.assertEqual(goose(candidate, seat)['pending_care_bonus'], 1)
                self.assertEqual(goose(baseline, seat)['pending_care_bonus'], 0)
                goose(candidate, seat)['pending_care_bonus'] = 0
                # Returned actions intentionally differ; all observed state and env agree.
                for s in candidate: s.action = {}
                for s in baseline: s.action = {}
                self.assertEqual(candidate, baseline)
                self.assertEqual(candidate_env, baseline_env)

    def test_actual_discard_survives_nonremoving_orders_and_dead_suffix(self):
        markets = ([['HIRE']], [['BUY_LAND']], [['BUY_PRODUCT', 'MILK', 50]],
                   [['BUY_ANIMAL', 'GOOSE', 1]], [['BUY_SEED', 'WHEAT', 1]],
                   [[], ['SELL', 'MILK', 100]], [['SELL', 'FERTILIZER', 0]])
        for seat in (0, 1):
            for market in markets:
                state, env = world(seat, full=True, egg=50)
                env.configuration.maxMarketOrdersPerTurn = 1
                a = action(market=copy.deepcopy(market)); out = apply(state, env, a, seat)
                self.assertEqual(out['farmer'], ['CARE'])
                baseline, e1 = copy.deepcopy((state, env)); candidate, e2 = copy.deepcopy((state, env))
                transition(baseline, e1, 263, a, seat)
                transition(candidate, e2, 263, out, seat)
                goose(candidate, seat)['pending_care_bonus'] = 0
                for s in baseline: s.action = {}
                for s in candidate: s.action = {}
                self.assertEqual(candidate, baseline)
                self.assertEqual(e2, e1)

    def test_actual_independent_workers_and_ordered_inventory_disposal(self):
        for seat in (0, 1):
            state, env = world(seat, full=True, egg=50)
            farm = state[seat].observation.farms[seat]
            farm['hands'] = [[3, 4], [2, 4]]
            for x in (3, 2):
                farm['tiles'][4][x] = copy.deepcopy(goose(state, seat))
            state[seat].observation.private['inventories'] = [
                {'EGG': 2}, {'FERTILIZER': 7, 'WHEAT': 3}, {'WHEAT': 9, 'EGG': 1}]
            a = action(); a['hands'] = [['COLLECT_FERTILIZER'], ['COLLECT_FERTILIZER']]
            out = apply(state, env, a, seat)
            self.assertEqual(out['hands'], [['CARE'], ['CARE']])
            baseline, e1 = copy.deepcopy((state, env)); candidate, e2 = copy.deepcopy((state, env))
            transition(baseline, e1, 263, a, seat)
            transition(candidate, e2, 263, out, seat)
            for x in (2, 3, 4):
                ct = candidate[seat].observation.farms[seat]['tiles'][4][x]
                bt = baseline[seat].observation.farms[seat]['tiles'][4][x]
                self.assertEqual(ct['pending_care_bonus'], 1)
                self.assertEqual(bt['pending_care_bonus'], 0)
                ct['pending_care_bonus'] = 0
            for s in baseline: s.action = {}
            for s in candidate: s.action = {}
            self.assertEqual(candidate, baseline)
            self.assertEqual(e2, e1)

    def test_actual_pickup_can_make_collection_fill(self):
        for seat in (0, 1):
            state, env = world(seat, full=True, egg=50)
            farm = state[seat].observation.farms[seat]
            farm['hands'] = [[4, 4]]
            state[seat].observation.private['inventories'] = [{}, {}]
            a = action(); a['hands'] = [['PICKUP', 'WHEAT', 1]]
            self.assertFalse(lane.discarded_fertilizer(obs(state, seat), a, env.configuration))
            baseline, e1 = copy.deepcopy((state, env)); candidate, e2 = copy.deepcopy((state, env))
            transition(baseline, e1, 263, a, seat)
            changed = copy.deepcopy(a); changed['farmer'] = ['CARE']
            transition(candidate, e2, 263, changed, seat)
            # Farmer inventory is deposited before hand inventory: pickup opens
            # a real slot, baseline fertilizer wins it, candidate returns wheat.
            bs = baseline[seat].observation.private['shed']
            cs = candidate[seat].observation.private['shed']
            self.assertEqual(bs['FERTILIZER'], cs['FERTILIZER'] + 1)
            self.assertEqual(cs['WHEAT'], bs['WHEAT'] + 1)

    def test_actual_live_sell_creates_real_fertilizer_loss(self):
        for seat in (0, 1):
            state, env = world(seat, full=True, egg=50)
            a = action(market=[['SELL', 'MILK', 1]])
            self.assertIs(apply(state, env, a, seat), a)
            baseline, e1 = copy.deepcopy((state, env)); candidate, e2 = copy.deepcopy((state, env))
            transition(baseline, e1, 263, a, seat)
            changed = copy.deepcopy(a); changed['farmer'] = ['CARE']
            transition(candidate, e2, 263, changed, seat)
            self.assertEqual(baseline[seat].observation.private['shed']['FERTILIZER'],
                             candidate[seat].observation.private['shed']['FERTILIZER'] + 1)

    def test_actual_realized_discard_and_spread_controls(self):
        for seat in (0, 1):
            for full, egg in ((True, 50), (False, 115)):
                state, env = world(seat, full=full, egg=egg)
                a = action(); out = apply(state, env, a, seat)
                self.assertEqual(out['farmer'], ['CARE'])
                baseline, e1 = copy.deepcopy((state, env)); candidate, e2 = copy.deepcopy((state, env))
                transition(baseline, e1, 263, a, seat)
                transition(candidate, e2, 263, out, seat)
                b_cash = continuation(baseline, e1, seat)
                c_cash = continuation(candidate, e2, seat)
                self.assertGreater(c_cash, b_cash)
                self.assertEqual(goose(candidate, seat)['yield_units'], 0)
                self.assertEqual(candidate[seat].observation.private['shed']['EGG'], 0)

    def test_actual_unfed_future_loses_bonus_not_free_profit(self):
        for seat in (0, 1):
            state, env = world(seat, full=True, egg=50)
            a = action(); out = apply(state, env, a, seat)
            baseline, e1 = copy.deepcopy((state, env)); candidate, e2 = copy.deepcopy((state, env))
            transition(baseline, e1, 263, a, seat)
            transition(candidate, e2, 263, out, seat)
            b_cash = continuation(baseline, e1, seat, feed=False)
            c_cash = continuation(candidate, e2, seat, feed=False)
            self.assertEqual(c_cash, b_cash)
            self.assertEqual(goose(candidate, seat)['pending_care_bonus'], 0)


if __name__ == '__main__':
    program = unittest.main(exit=False, verbosity=2)
    print('FULL_INTERPRETER_CALLS=' + str(CALLS), 'INITIALIZATIONS=' + str(INITIALIZATIONS),
          'ACTION_TRANSITIONS=' + str(TRANSITIONS), flush=True)
    raise SystemExit(0 if program.result.wasSuccessful() else 1)
