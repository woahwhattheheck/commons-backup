"""Actual PR9997 parent/terminal-admission boundary; no existing suite rerun.

Set TITAN_INTEGRATED_ROOT to the verified integrated-selected-v1 extraction
and TITAN_REPO_ROOT/TITAN_ENGINE_DIR to the existing source and engine caches.
Constructed observations test invocation and clock shape, not policy strength.
"""
from __future__ import annotations
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get('TITAN_REPO_ROOT', HERE.parents[2]))
INTEGRATED = Path(os.environ['TITAN_INTEGRATED_ROOT']).resolve()
ENGINE = Path(os.environ['TITAN_ENGINE_DIR']).resolve()
expected = 'c2ad172e4a0603c64c275cf798a14cf7edefcb4317393e51fd27124d47ca1f74'
if hashlib.sha256((INTEGRATED/'integrated_selected.py').read_bytes()).hexdigest() != expected:
    raise ValueError('This integration check requires the exact PR9997 source')
sys.path.insert(0, str(INTEGRATED))
import integrated_selected
from market_primitives import make_primitives
from terminal_admission import TerminalAdmissionAgent, RivalScenario, optimize_terminal_admission
spec = importlib.util.spec_from_file_location('admission_join_eval', ROOT/'revenue/kaggriculture/cloud-eval/evaluate.py')
ev = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ev
spec.loader.exec_module(ev)
engine, engine_hashes = ev.get_engine(ENGINE)
S = ev.Struct


def initial(player=0, step=0):
    cfg = S({k:v.get('default') if isinstance(v, dict) else v
             for k,v in engine.specification['configuration'].items()})
    cfg.seed = 1  # Engine initialization only; no scored game is run here.
    env = S(configuration=cfg, done=False, info={})
    states = [S(observation=S(), action={}, status='ACTIVE', reward=0) for _ in range(2)]
    engine.interpreter(states, env)
    obs = copy.deepcopy(states[player].observation)
    obs['step'] = step
    obs['day'], obs['hour'] = divmod(step, cfg.turnsPerDay)
    return obs, cfg


class IntegratedConsumerTests(unittest.TestCase):
    def joined(self, observation, config, *, omit_step=False, none_config=False):
        """Two fresh identical source parents; each is invoked once, independently."""
        left, right = integrated_selected.make_agent(), integrated_selected.make_agent()
        calls = {'producer':0, 'scenario':0}
        original = left.production.act
        def producer_call(*args, **kwargs):
            calls['producer'] += 1
            return original(*args, **kwargs)
        left.production.act = producer_call
        scenarios = [RivalScenario('idle', {}, [], 'explicit uncalibrated no-sale hypothesis')]
        def scenario_model(obs, cfg):
            calls['scenario'] += 1
            return scenarios
        wrapped = TerminalAdmissionAgent(left.act, make_primitives(integrated_selected.m),
            scenario_model, max_states=16, max_candidates=16, time_budget_s=1)
        obs = copy.deepcopy(observation)
        if omit_step:
            del obs['step']
        supplied_config = None if none_config else config
        expected = right.act(copy.deepcopy(obs), supplied_config)
        actual = wrapped.act(copy.deepcopy(obs), supplied_config)
        self.assertEqual(calls['producer'], 1)
        return actual, expected, wrapped, calls, scenarios

    def test_initial_actual_parent_both_positions(self):
        for player in (0, 1):
            with self.subTest(player=player):
                actual, expected, wrapper, calls, _ = self.joined(*initial(player))
                self.assertEqual(actual, expected)
                self.assertEqual(calls['scenario'], 0)
                self.assertEqual(wrapper.last_report['reason'], 'nonterminal')

    def test_initial_day_hour_clock_matches_integrated_contract(self):
        for player in (0, 1):
            with self.subTest(player=player):
                actual, expected, _, calls, _ = self.joined(*initial(player), omit_step=True)
                self.assertEqual(actual, expected)
                self.assertEqual(calls['scenario'], 0)

    def test_optional_configuration_matches_integrated_contract(self):
        for omit in (False, True):
            with self.subTest(omit_step=omit):
                actual, expected, _, calls, _ = self.joined(*initial(), omit_step=omit, none_config=True)
                self.assertEqual(actual, expected)
                self.assertEqual(calls['scenario'], 0)

    def test_constructed_terminal_actual_parent_and_offline_primitives(self):
        # Fresh actor + constructed last-turn input: interface, not reached-state evidence.
        for player in (0, 1):
            with self.subTest(player=player):
                obs, cfg = initial(player, 718)
                actual, expected, wrapper, calls, scenarios = self.joined(obs, cfg)
                control, report = optimize_terminal_admission(engine, obs, cfg, expected,
                    scenarios, max_states=16, max_candidates=16, time_budget_s=1)
                self.assertEqual(actual, control)
                self.assertEqual(calls['scenario'], 1)
                self.assertEqual(wrapper.last_report['reason'], report['reason'])

    def test_terminal_derived_clock_and_none_config(self):
        obs, cfg = initial(0, 718)
        regular = self.joined(obs, cfg)
        derived = self.joined(obs, cfg, omit_step=True, none_config=True)
        self.assertEqual(derived[0], regular[0])
        self.assertEqual(derived[3]['scenario'], 1)
        self.assertEqual(derived[2].last_report['reason'], regular[2].last_report['reason'])

    def test_parent_body_failure_is_not_retried(self):
        parent = integrated_selected.make_agent()
        calls = []
        def failing(*args):
            calls.append(1)
            raise TypeError('retained actual-parent production failure')
        parent.production.act = failing
        def unexpected(*args):
            raise AssertionError('scenario must not run after producer failure')
        wrapped = TerminalAdmissionAgent(parent.act, make_primitives(integrated_selected.m), unexpected)
        with self.assertRaisesRegex(TypeError, 'retained actual-parent production failure'):
            wrapped.act(*initial())
        self.assertEqual(len(calls), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
