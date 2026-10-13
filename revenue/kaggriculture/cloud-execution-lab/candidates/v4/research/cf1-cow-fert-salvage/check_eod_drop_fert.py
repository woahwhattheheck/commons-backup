# SPDX-License-Identifier: Apache-2.0
"""Full pinned-interpreter checks for the CF1 EOD DROP continuation.

Run with TITAN_ENGINE_DIR=/path/to/checks/reference/engine python -m unittest
-v check_eod_drop_fert. No network, copied game transition, or skipped engine gate.
TITAN_CF1_DROP_SOURCE optionally selects an independently built candidate/mutant.
"""
from __future__ import annotations

import ast
import base64
import copy
import hashlib
import importlib.util
import itertools
import json
import os
from pathlib import Path
import random
import sys
import types
import unittest
import zlib
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
ENGINE_BLOB = '3c202c7ee921da239356789e266b694635103fc4'
ORIGINAL_BLOB = '3f6697c7825ea39b84a00767088eb52f2ba2903f'
ORIGINAL_BYTES = 6486
COUNTS = {'full_engine_pairs': 0}


def git_blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


class Struct(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key) from None

    def __setattr__(self, key, value):
        self[key] = value


def load_engine(root):
    """Load the WHOLE preserved engine and its real upstream seed helper."""
    root = Path(root)
    required = {
        'kaggriculture.py': ENGINE_BLOB,
        'kaggriculture.json': 'b354d06b742fe48402513792253f1a5c29366b20',
        'utils.py': '91c8822ee6201ba4a5a8416c7dbe34f95dd61c87',
    }
    for name, expected in required.items():
        actual = git_blob((root / name).read_bytes())
        if actual != expected:
            raise ValueError(f'{name}: expected {expected}, got {actual}')
    module_ast = ast.parse((root / 'utils.py').read_text())
    helper = next(node for node in module_ast.body if isinstance(node, ast.FunctionDef)
                  and node.name == 'resolve_episode_seed')
    namespace = {'Any': Any, 'Callable': Callable, 'random': random}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), 'upstream_seed_helper', 'exec'), namespace)
    package = types.ModuleType('kaggle_environments')
    utils = types.ModuleType('kaggle_environments.utils')
    utils.resolve_episode_seed = namespace['resolve_episode_seed']
    prior = {key: sys.modules.get(key) for key in ('kaggle_environments', 'kaggle_environments.utils')}
    try:
        sys.modules['kaggle_environments'] = package
        sys.modules['kaggle_environments.utils'] = utils
        spec = importlib.util.spec_from_file_location('kestrel_pinned_engine', root / 'kaggriculture.py')
        engine = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(engine)
    finally:
        for key, value in prior.items():
            if value is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value
    return engine


def load_helper(source=None):
    if git_blob((HERE / 'r04_cow_fert_salvage.py').read_bytes()) != ORIGINAL_BLOB:
        raise ValueError('original CF1 donor identity mismatch')
    source = source or os.environ.get('TITAN_CF1_DROP_SOURCE', str(HERE / 'drop_continuation.py'))
    spec = importlib.util.spec_from_file_location('kestrel_drop_helper', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def normal_state(state):
    state = copy.deepcopy(state)
    for entry in state:
        entry.pop('action', None)  # Inputs differ by definition; all outputs stay checked.
    return state


class DropFertTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = os.environ.get('TITAN_ENGINE_DIR')
        if not root:
            raise RuntimeError('TITAN_ENGINE_DIR is required; no partial-engine/skip fallback')
        cls.engine = load_engine(root)
        cls.helper = load_helper()

    def fixture(self, *, seat=0, actor=0, step=191, position=(4, 4), fed=False,
                cared=False, unfed=0, units=0, carried=None, shed=None, seed=9600803):
        e = self.engine
        cfg = Struct({key: value.get('default') if isinstance(value, dict) else value
                      for key, value in e.specification['configuration'].items()})
        farms = [e._new_farm(10, 3000), e._new_farm(10, 3000)]
        farm = farms[seat]
        farm['farmer'] = [1, 0]
        farm['hands'] = [[i + 1, 1] for i in range(actor)]
        positions = [farm['farmer'], *farm['hands']]
        positions[actor][:] = position
        farm['hires_today'] = actor
        x, y = position
        cow = e._new_animal('COW', 0)
        cow.update(fed_today=fed, cared_today=cared, consecutive_unfed=unfed,
                   yield_units=units, fertilizer_available=True, pending_care_bonus=1)
        farm['tiles'][y][x] = cow
        market = e._new_market()
        town = {'unlocked_shops': ['PIZZA_SHOP', 'YARN_STORE']}
        state = []
        for player in range(2):
            private = e._new_private()
            if player == seat:
                private['inventories'] = [{} for _ in positions]
                private['inventories'][actor] = dict(carried if carried is not None else {'FERTILIZER': 2})
                private['shed'].update(shed or {})
                private['shed']['WOOL'] = private['shed'].get('WOOL', 0) + 1
            action = {'farmer': ['PASS'], 'hands': [], 'market': []}
            if player == seat:
                action['hands'] = [['PASS'] for _ in farm['hands']]
                if actor == 0:
                    action['farmer'] = ['DROP']
                else:
                    action['hands'][actor - 1] = ['DROP']
                action['market'] = [['SELL', 'WOOL', 1]]
            state.append(Struct(observation=Struct(player=player, step=step, day=step // 24,
                          hour=step % 24, farms=farms, private=private, market=market, town=town),
                                action=action, status='ACTIVE', reward=0))
        return state, Struct(configuration=cfg, done=False, info={'seed': seed})

    def proposal(self, state, env, seat=0, enabled=True):
        return self.helper.apply_eod_drop_fert_salvage(
            state[seat].action, state[seat].observation, env.configuration, enabled=enabled)

    def equal_except_one_fert(self, state, env, proposed, seat):
        baseline, candidate = copy.deepcopy(state), copy.deepcopy(state)
        candidate[seat].action = copy.deepcopy(proposed)
        before = copy.deepcopy(state)
        base_env, cand_env = copy.deepcopy(env), copy.deepcopy(env)
        self.engine.interpreter(baseline, base_env)
        self.engine.interpreter(candidate, cand_env)
        base, cand = normal_state(baseline), normal_state(candidate)
        delta = cand[seat].observation.private['shed']['FERTILIZER'] - base[seat].observation.private['shed']['FERTILIZER']
        self.assertEqual(delta, 1)
        cand[seat].observation.private['shed']['FERTILIZER'] -= 1
        self.assertEqual(cand, base)
        self.assertEqual(cand_env, base_env)
        self.assertEqual(state, before)
        COUNTS['full_engine_pairs'] += 1

    def unchanged(self, state, env, seat=0):
        before = copy.deepcopy(state)
        self.assertIs(self.proposal(state, env, seat), state[seat].action)
        self.assertEqual(state, before)

    def test_original_helper_is_byte_exact(self):
        source = (HERE / 'r04_cow_fert_salvage.py').read_bytes()
        self.assertEqual(len(source), ORIGINAL_BYTES)
        self.assertEqual(git_blob(source), ORIGINAL_BLOB)

    def test_off_is_exact_identity_even_for_invalid_input(self):
        for enabled in (False, None, 0, 1, 'yes', [], {}):
            action = {'opaque': object()}
            self.assertIs(self.helper.apply_eod_drop_fert_salvage(action, None, None, enabled=enabled), action)

    def test_full_engine_seat_actor_site_lifecycle_grid(self):
        for seat, actor, site, step, fed, cared, unfed, units in itertools.product(
                (0, 1), (0, 1, 4), ((4, 4), (5, 4), (3, 3)), (47, 191, 695),
                (False, True), (False, True), (0, 1), (0, 6)):
            with self.subTest(seat=seat, actor=actor, site=site, step=step,
                              fed=fed, cared=cared, unfed=unfed, units=units):
                state, env = self.fixture(seat=seat, actor=actor, position=site, step=step,
                                          fed=fed, cared=cared, unfed=unfed, units=units)
                action = self.proposal(state, env, seat)
                self.assertNotEqual(action, state[seat].action)
                self.equal_except_one_fert(state, env, action, seat)

    def test_same_callback_rival_market_does_not_break_certificate(self):
        rivals = ([], [['SELL', 'FERTILIZER', 5]], [['BUY_PRODUCT', 'FERTILIZER', 3]],
                  [['SELL', 'WOOL', 3]], [['BUY_PRODUCT', 'WHEAT', 2], ['HIRE']])
        for seat, orders in itertools.product((0, 1), rivals):
            state, env = self.fixture(seat=seat, carried={'FERTILIZER': 2, 'MILK': 1})
            state[1-seat].action['market'] = copy.deepcopy(orders)
            state[1-seat].observation.private['shed'].update(FERTILIZER=5, WOOL=5)
            self.equal_except_one_fert(state, env, self.proposal(state, env, seat), seat)

    def test_all_authored_harvest_and_collect_capacity_is_reserved(self):
        state, env = self.fixture(actor=1, shed={'MILK': 92})
        state[0].action['farmer'] = ['HARVEST']
        self.unchanged(state, env)
        state[0].observation.private['shed']['MILK'] = 90
        self.equal_except_one_fert(state, env, self.proposal(state, env), 0)

    def test_capacity_displacement_counterexample_is_rejected(self):
        state, env = self.fixture(shed={'MILK': 96})
        farm = state[0].observation.farms[0]
        farm['hands'] = [[3, 3]]
        cow = self.engine._new_animal('COW', 0)
        cow.update(yield_units=2, fed_today=True, cared_today=True)
        farm['tiles'][3][3] = cow
        state[0].observation.private['inventories'].append({})
        state[0].action['hands'] = [['HARVEST']]
        state[0].action['market'] = []
        self.unchanged(state, env)
        forced = copy.deepcopy(state[0].action)
        forced['farmer'] = ['COLLECT_FERTILIZER']
        base, cand = copy.deepcopy(state), copy.deepcopy(state)
        cand[0].action = forced
        self.engine.interpreter(base, copy.deepcopy(env))
        self.engine.interpreter(cand, copy.deepcopy(env))
        self.assertEqual(cand[0].observation.private['shed']['MILK'], base[0].observation.private['shed']['MILK'] - 1)

    def test_all_actor_cargo_not_just_target_counts(self):
        state, env = self.fixture(actor=1)
        state[0].observation.private['inventories'][0]['MILK'] = 97
        self.unchanged(state, env)

    def test_delayed_cargo_sale_is_rejected_with_cash_counterexample(self):
        state, env = self.fixture()
        state[0].action['market'] = [['SELL', 'FERTILIZER', 2]]
        self.unchanged(state, env)
        forced = copy.deepcopy(state[0].action)
        forced['farmer'] = ['COLLECT_FERTILIZER']
        base, cand = copy.deepcopy(state), copy.deepcopy(state)
        cand[0].action = forced
        self.engine.interpreter(base, copy.deepcopy(env))
        self.engine.interpreter(cand, copy.deepcopy(env))
        self.assertGreater(base[0].observation.farms[0]['money'], cand[0].observation.farms[0]['money'])

    def test_empty_cargo_can_collect_before_fert_sale(self):
        state, env = self.fixture(carried={}, shed={'FERTILIZER': 3})
        state[0].action['market'] = [['SELL', 'FERTILIZER', 2]]
        self.equal_except_one_fert(state, env, self.proposal(state, env), 0)

    def test_inert_suffix_is_preserved_and_cannot_veto(self):
        suffixes = ([['SELL', 'FERTILIZER', 2]], [['BUY_PRODUCT', 'WHEAT', 99]],
                    [None, {'opaque': True}, ['HIRE']])
        for suffix in suffixes:
            state, env = self.fixture()
            state[0].action['market'] = [[] for _ in range(10)] + copy.deepcopy(suffix)
            before = copy.deepcopy(state)
            action = self.proposal(state, env)
            self.assertIsNot(action, state[0].action)
            self.assertEqual(action['market'], before[0].action['market'])
            self.equal_except_one_fert(state, env, action, 0)

    def test_active_purchase_veto(self):
        for row in (['HIRE'], ['BUY_PRODUCT', 'WHEAT', 1], ['BUY_ANIMAL', 'COW', 1],
                    ['BUY_SEED', 'WHEAT', 1], ['BUY_LAND']):
            state, env = self.fixture()
            state[0].action['market'] = [row]
            self.unchanged(state, env)

    def test_market_quantities_and_grammar(self):
        for row in (['SELL', 'WOOL', True], ['SELL', 'WOOL', -1], ['SELL', 'WOOL', 1.0],
                    ['SELL', 'WOOL', '2'], ['SELL', 'UNKNOWN', 1], {}, None, ['SELL']):
            state, env = self.fixture()
            state[0].action['market'] = [row]
            self.unchanged(state, env)
        state, env = self.fixture()
        state[0].action['market'] = [[], ['PASS'], ['SELL', 'FERTILIZER', 0]]
        self.equal_except_one_fert(state, env, self.proposal(state, env), 0)

    def test_configuration_and_complete_day_horizon(self):
        for key in self.helper.STANDARD:
            for value in (True, '10', None, self.helper.STANDARD[key] + 1):
                state, env = self.fixture()
                env.configuration[key] = value
                self.unchanged(state, env)
        for step in (-1, 0, 22, 24, 694, 696, 718, 719, 743, True):
            state, env = self.fixture()
            state[0].observation.step = step
            self.unchanged(state, env)

    def test_actual_actor_cardinality(self):
        for mode in ('extra_action', 'missing_action', 'extra_inventory', 'missing_inventory'):
            state, env = self.fixture(actor=1)
            if mode == 'extra_action': state[0].action['hands'].append(['DROP'])
            if mode == 'missing_action': state[0].action['hands'].pop()
            if mode == 'extra_inventory': state[0].observation.private['inventories'].append({})
            if mode == 'missing_inventory': state[0].observation.private['inventories'].pop()
            self.unchanged(state, env)

    def test_colocated_collector_does_not_create_a_false_gain(self):
        state, env = self.fixture(actor=1)
        state[0].observation.farms[0]['farmer'] = [4, 4]
        state[0].action['farmer'] = ['COLLECT_FERTILIZER']
        self.unchanged(state, env)

    def test_parameterized_unit_commands_veto(self):
        for command in (['PICKUP', 'FERTILIZER', 1], ['PLACE', 'FERTILIZER', 1], ['PLANT', 'WHEAT']):
            state, env = self.fixture(actor=1)
            state[0].action['farmer'] = command
            self.unchanged(state, env)

    def test_cow_state_validation(self):
        values = {'animal': ('GOOSE', 'SHEEP', None), 'fertilizer_available': (False, 1),
                  'yield_units': (-1, 7, True, '0'), 'placed_day': (-1, 99),
                  'consecutive_unfed': (-1, 2), 'pending_care_bonus': (-1, None),
                  'fed_today': (1, None), 'cared_today': (1, None), 'kind': ('COOP', None)}
        for field, variants in values.items():
            for value in variants:
                state, env = self.fixture()
                state[0].observation.farms[0]['tiles'][4][4][field] = value
                self.unchanged(state, env)

    def test_inventory_validation_and_aliases(self):
        for value in (-1, True, 1.0, '1', None):
            state, env = self.fixture()
            state[0].observation.private['inventories'][0]['FERTILIZER'] = value
            self.unchanged(state, env)
        state, env = self.fixture(actor=1)
        state[0].observation.private['inventories'][0] = state[0].observation.private['inventories'][1]
        self.unchanged(state, env)
        state, env = self.fixture()
        state[0].observation.private['shed'] = state[0].observation.private['inventories'][0]
        self.unchanged(state, env)

    def test_tile_aliases_veto(self):
        for rival_alias in (False, True):
            state, env = self.fixture()
            farms = state[0].observation.farms
            farms[int(rival_alias)]['tiles'][0][0] = farms[0]['tiles'][4][4]
            self.unchanged(state, env)

    def test_unbounded_other_harvest_veto(self):
        state, env = self.fixture(actor=1)
        state[0].action['farmer'] = ['HARVEST']
        state[0].observation.farms[0]['tiles'][0][1] = {'kind': 'PLANT', 'yield_units': 999}
        self.unchanged(state, env)

    def test_only_one_selected_row_changes_and_inputs_stay_private(self):
        state, env = self.fixture(actor=4)
        before = copy.deepcopy(state)
        action = self.proposal(state, env)
        self.assertEqual(state, before)
        self.assertEqual(action['farmer'], before[0].action['farmer'])
        self.assertEqual(action['hands'][:3], before[0].action['hands'][:3])
        self.assertEqual(action['hands'][3], ['COLLECT_FERTILIZER'])
        self.assertEqual(action['market'], before[0].action['market'])
        action['market'].append(['PASS'])
        self.assertEqual(state, before)

    def test_replay_witnesses_are_supported_by_new_not_original_helper(self):
        envelope = json.loads((HERE / 'DROP-WITNESSES.json').read_text())
        raw = zlib.decompress(base64.b64decode(envelope['data'], validate=True))
        self.assertEqual(hashlib.sha256(raw).hexdigest(), envelope['decoded_sha256'])
        self.assertEqual(len(raw), envelope['decoded_bytes'])
        packet = json.loads(raw)
        self.assertEqual(packet['engine_git_blob'], ENGINE_BLOB)
        self.assertEqual(packet['tapes_git_blob'], 'a43289b9cc5e34a2481fddf652762a7d92f427ef')
        self.assertEqual(len(packet['witnesses']), 2)
        for witness in packet['witnesses']:
            seat = witness['seat']
            observation = copy.deepcopy(witness['obs'])
            action = copy.deepcopy(witness['action'])
            self.assertIs(self.helper.cf1.apply_cow_fert_salvage(action, observation, self.helper.STANDARD, enabled=True), action)
            proposed = self.helper.apply_eod_drop_fert_salvage(action, observation, self.helper.STANDARD, enabled=True)
            self.assertEqual(proposed['hands'][7], ['COLLECT_FERTILIZER'])
            state, env = self.fixture(seat=seat, step=695, seed=witness['seed'])
            for player in range(2):
                state[player].observation.farms = observation['farms']
                state[player].observation.market = observation['market']
                state[player].observation.town = observation['town']
            state[seat].observation.private = observation['private']
            state[seat].action = action
            self.equal_except_one_fert(state, env, proposed, seat)


if __name__ == '__main__':
    unittest.main(verbosity=2)
