# SPDX-License-Identifier: Apache-2.0
"""Native-finalizer and official-engine wiring controls, NOT sellby15 economics."""
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(os.environ['TITAN_NATIVE_ROOT']).resolve()
REF = Path(os.environ['TITAN_REFERENCE_ROOT']).resolve()
sys.path.insert(0, str(ROOT))
from native_sale_window import NativeSaleWindow, validate_market_only, digest, verify_native


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


EVALUATOR = load(REF / 'evaluator/evaluate.py', '_sale_window_official_evaluator')
ENGINE, ENGINE_HASHES = EVALUATOR.get_engine(REF / 'engine', loader=REF / 'evaluator/loader.py')


def game(seed=17, seat=0):
    S = EVALUATOR.Struct
    cfg = S({k: v.get('default') if isinstance(v, dict) else v
             for k, v in ENGINE.specification['configuration'].items()})
    cfg.seed = seed
    env = S(configuration=cfg, done=False, info={})
    state = [S(observation=S(), action={}, status='ACTIVE', reward=0) for _ in range(2)]
    ENGINE.interpreter(state, env)
    for s in state:
        s.observation.step = 348
    return state, env, deepcopy(state[seat].observation)


def identity(obs, cfg, action):
    return action


def sell_fixture(obs, cfg, action):
    action['market'].append(['SELL', 'MELON', 3])
    return action


def evil_units(obs, cfg, action):
    action['farmer'] = ['DIG']
    return action


def mutate_detached(obs, cfg, action):
    obs['private']['shed']['MELON'] = 0
    cfg['shedCapacity'] = 1
    action['market'].append(['SELL', 'MELON', 3])
    return action


def ordinary_error(obs, cfg, action):
    raise ValueError('synthetic callback fault')


def base_error(obs, cfg, action):
    raise KeyboardInterrupt('synthetic interruption')


class History:
    def __init__(self):
        self.actions = []
        self.diagnostics = {}

    def remember(self, obs, cfg, action, post):
        self.actions.append(deepcopy(action))


class NativeWiringTests(unittest.TestCase):
    def setUp(self):
        self.main = load(ROOT / 'main.py', '_sale_window_test_main')
        self.state, self.env, self.obs = game()
        self.cfg = dict(self.env.configuration)
        self.action = {'farmer': ['PASS'], 'hands': [], 'market': []}
        self.history = History()
        self.inst = None
        self.trials = []

    def tearDown(self):
        for trial in self.trials:
            self.main._INSTANCE = None
            if self.main._new_instance is trial._factory:
                trial.close()

    def trial(self, policy=identity, pressure=False, mode='completed', fallback=False):
        trial = NativeSaleWindow(self.main, policy, enabled=True, label='SYNTHETIC wiring control')
        self.trials.append(trial)
        def driver(obs, cfg):
            instance = self.main._new_instance(ROOT, {'seed': False, 'funding': False,
                                                     'market_pressure': pressure})
            self.inst = self.main._INSTANCE = instance
            instance.diagnostics = {'status': mode}
            instance.history = self.history
            instance._selected_snapshot = lambda obs, returned=None: deepcopy(obs)
            result = instance._finish_production(obs, self.action, cfg)
            if fallback:
                instance.diagnostics = {'status': 'deadline_fallback', 'fallback_stage': 'synthetic_after_hook'}
                return self.action
            return result
        trial._native_agent = driver  # White-box finalizer fixture, explicitly not a full game.
        return trial

    def test_disabled_returns_exact_native_callable_without_binding(self):
        factory = self.main._new_instance
        trial = NativeSaleWindow(self.main, enabled=False)
        self.assertIs(trial.agent, self.main.agent)
        self.assertIs(self.main._new_instance, factory)
        self.assertEqual(trial.rows, [])

    def test_real_source_binding_and_policy_file_hash(self):
        trial = self.trial()
        self.assertEqual(trial.native_binding, verify_native(self.main))
        self.assertEqual(trial.policy_binding['source_sha256'], hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        self.assertEqual(trial.policy_binding['entrypoint'], 'identity')

    def test_identity_is_exact_object_and_receipt(self):
        trial = self.trial()
        returned = trial.agent(self.obs, self.cfg)
        self.assertIs(returned, self.action)
        self.assertEqual(self.history.actions, [self.action])
        self.assertTrue(trial.rows[-1]['accepted'])
        self.assertFalse(trial.rows[-1]['accepted_prefix_changed'])
        self.assertTrue(trial.rows[-1]['returned_matches_proposal'])
        self.assertIsNone(trial.rows[-1]['fills'])

    def test_proposal_commits_to_real_native_receipt_owner(self):
        trial = self.trial(sell_fixture)
        before = deepcopy((self.obs, self.cfg, self.action))
        returned = trial.agent(self.obs, self.cfg)
        self.assertEqual(returned['market'], [['SELL', 'MELON', 3]])
        self.assertEqual(self.history.actions, [returned])
        self.assertEqual((self.obs, self.cfg, self.action), before)
        row = trial.rows[-1]
        self.assertEqual(row['callbacks'], 1)
        self.assertTrue(row['accepted_prefix_changed'])
        self.assertTrue(row['returned_prefix_changed'])
        self.assertTrue(row['returned_matches_proposal'])
        self.assertEqual(row['economic_verdict'], 'not_measured')

    def test_final_pressure_runs_before_hook_and_receipts_after(self):
        self.action['market'] = [[], ['SELL', 'STRAWBERRY', 2]]
        trial = self.trial(sell_fixture, pressure=True)
        returned = trial.agent(self.obs, self.cfg)
        self.assertTrue(self.inst.diagnostics['market_pressure']['enabled'])
        self.assertEqual(returned['market'][-1], ['SELL', 'MELON', 3])
        self.assertEqual(self.history.actions, [returned])
        self.assertTrue(trial.rows[-1]['returned_matches_proposal'])

    def test_fallback_never_starts_optional_callback(self):
        trial = self.trial(sell_fixture, mode='deadline_fallback')
        returned = trial.agent(self.obs, self.cfg)
        self.assertIs(returned, self.action)
        self.assertEqual(trial.rows[-1]['callbacks'], 0)
        self.assertEqual(self.history.actions, [returned])

    def test_proposed_change_is_not_reported_as_returned_change_after_fallback(self):
        trial = self.trial(sell_fixture, fallback=True)
        returned = trial.agent(self.obs, self.cfg)
        row = trial.rows[-1]
        self.assertIs(returned, self.action)
        self.assertTrue(row['accepted_prefix_changed'])
        self.assertFalse(row['returned_prefix_changed'])
        self.assertFalse(row['returned_matches_proposal'])
        self.assertEqual(row['native_status'], 'deadline_fallback')

    def test_callback_cannot_mutate_caller_owned_observation_or_configuration(self):
        trial = self.trial(mutate_detached)
        before = deepcopy((self.obs, self.cfg, self.action))
        trial.agent(self.obs, self.cfg)
        self.assertEqual((self.obs, self.cfg, self.action), before)

    def test_unit_change_fails_closed_and_is_an_error_not_no_op_evidence(self):
        trial = self.trial(evil_units)
        returned = trial.agent(self.obs, self.cfg)
        self.assertIs(returned, self.action)
        self.assertFalse(trial.rows[-1]['accepted'])
        self.assertIn('Non-market', trial.rows[-1]['error'])
        self.assertEqual(self.history.actions, [returned])

    def test_ordinary_error_is_visible(self):
        trial = self.trial(ordinary_error)
        self.assertIs(trial.agent(self.obs, self.cfg), self.action)
        self.assertIn('synthetic callback fault', trial.rows[-1]['error'])
        self.assertFalse(trial.rows[-1]['proposal_returned'])

    def test_base_exception_is_not_swallowed_or_claimed_returned(self):
        trial = self.trial(base_error)
        with self.assertRaises(KeyboardInterrupt):
            trial.agent(self.obs, self.cfg)
        self.assertFalse(trial.rows[-1]['returned'])
        self.assertEqual(trial.rows[-1]['raised'], 'KeyboardInterrupt')
        self.assertEqual(self.history.actions, [])

    def test_repeated_step_new_episode_has_separate_call_identity(self):
        trial = self.trial(sell_fixture)
        trial.agent(self.obs, self.cfg)
        trial.agent(self.obs, self.cfg)
        self.assertEqual([r['call'] for r in trial.rows], [0, 1])
        self.assertEqual([r['callbacks'] for r in trial.rows], [1, 1])

    def test_duplicate_binding_and_live_instance_are_rejected(self):
        trial = self.trial()
        with self.assertRaises(ValueError):
            NativeSaleWindow(self.main, identity, enabled=True)
        trial.agent(self.obs, self.cfg)
        with self.assertRaises(ValueError):
            NativeSaleWindow(self.main, identity, enabled=True)

    def test_unbind_never_overwrites_peer_factory(self):
        trial = self.trial()
        self.main._new_instance = lambda *args: None
        with self.assertRaises(RuntimeError):
            trial.close()
        self.main._new_instance = trial._factory

    def test_full_official_transition_matches_direct_returned_action_both_seats(self):
        # This proves the wiring, not a policy advantage. Candidate state is a
        # constructed legal stock/step fixture; no natural-game claim is made.
        for seat in (0, 1):
            self.main._INSTANCE = None
            if self.trials:
                self.trials[-1].close()
            self.state, self.env, self.obs = game(seat=seat)
            self.state[seat].observation.private['shed']['MELON'] = 3
            self.obs = deepcopy(self.state[seat].observation)
            trial = self.trial(sell_fixture)
            returned = trial.agent(self.obs, self.cfg)
            direct = deepcopy(self.action)
            direct['market'] = [['SELL', 'MELON', 3]]
            left, right = deepcopy(self.state), deepcopy(self.state)
            left[seat].action = returned
            right[seat].action = direct
            for arm in (left, right):
                arm[1-seat].action = {'farmer': ['PASS'], 'hands': [], 'market': []}
            ENGINE.interpreter(left, deepcopy(self.env))
            ENGINE.interpreter(right, deepcopy(self.env))
            self.assertEqual(left, right)
            self.assertEqual(left[seat].observation.private['shed']['MELON'], 0)
            self.assertGreater(left[0].observation.farms[seat]['money'],
                               self.state[0].observation.farms[seat]['money'])


class QueueOwnershipTests(unittest.TestCase):
    def action(self, rows):
        return {'farmer': ['PASS'], 'hands': [['CARE']], 'market': deepcopy(rows)}

    def valid(self, before, after, cap=10):
        validate_market_only(self.action(before), self.action(after),
                             {'maxMarketOrdersPerTurn': cap}, {'MELON', 'STRAWBERRY'})

    def invalid(self, before, after, cap=10):
        with self.assertRaises(ValueError):
            self.valid(before, after, cap)

    def test_empty_slot_and_target_rows_can_change_without_shifting_positions(self):
        self.valid([[], ['SELL', 'MELON', 5]], [['SELL', 'STRAWBERRY', 2], []])
        self.valid([['SELL', 'MELON', 5]], [['SELL', 'MELON', 1]])

    def test_economic_prefix_keeps_exact_rows_including_target_sale(self):
        before = [['SELL', 'MELON', 5], ['HIRE'], []]
        self.valid(before, before[:-1] + [['SELL', 'MELON', 1]])
        self.invalid(before, [['SELL', 'MELON', 4], ['HIRE'], []])

    def test_inputs_and_unrelated_goods_are_immutable(self):
        for item in ('WHEAT', 'FERTILIZER', 'CARROT', 'TOMATO', 'EGG'):
            self.invalid([['SELL', item, 3]], [['SELL', item, 2]])
        self.invalid([], [['BUY_PRODUCT', 'MELON', 1]])

    def test_raw_cap_cannot_be_bypassed_by_compression_or_suffix_edits(self):
        self.invalid([[], ['SELL', 'MELON', 2]], [['SELL', 'MELON', 2]], 1)
        self.invalid([[], ['SELL', 'MELON', 2]], [[], ['SELL', 'MELON', 3]], 1)
        self.invalid([[]], [[], ['SELL', 'MELON', 3]], 1)
        self.valid([[], ['SELL', 'MELON', 2]], [['SELL', 'MELON', 1], ['SELL', 'MELON', 2]], 1)

    def test_strict_integer_quantity_and_unknown_row_barriers(self):
        for q in (True, -1, 1.5, '2', float('inf')):
            self.invalid([], [['SELL', 'MELON', q]])
        self.invalid([[], ['UNKNOWN']], [['SELL', 'MELON', 1], ['UNKNOWN']])

    def test_zero_cap_and_non_market_metadata(self):
        self.valid([['SELL', 'MELON', 2]], [['SELL', 'MELON', 2]], 0)
        self.valid([], [['SELL', 'MELON', 2]], 0)
        self.invalid([[]], [[], ['SELL', 'MELON', 2]], 0)
        before = self.action([])
        after = deepcopy(before); after['userdata'] = 'new'
        with self.assertRaises(ValueError):
            validate_market_only(before, after, {}, {'MELON'})


if __name__ == '__main__':
    unittest.main(verbosity=2)
