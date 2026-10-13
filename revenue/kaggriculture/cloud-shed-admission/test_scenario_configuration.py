"""Existing scenario callbacks retain the caller's configuration contract.

This exercises the actual admission consumer, not an alternative wrapper.
No engine is needed: empty scenario families take its defined fallback.
"""
from __future__ import annotations
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import MappingProxyType
import unittest

HERE = Path(__file__).resolve().parent
TARGET = Path(os.environ.get('TITAN_ADMISSION_SOURCE', HERE / 'terminal_admission.py')).resolve()
spec = importlib.util.spec_from_file_location('configuration_admission', TARGET)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class Config(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key) from None


class FalseyConfig(Config):
    def __bool__(self):
        return False


class ConfigurationContractTests(unittest.TestCase):
    def exercise(self, config, observation=None, inspect=None):
        obs = {'step': 718, 'day': 29, 'hour': 22} if observation is None else observation
        selected = {'farmer': ['PASS'], 'hands': [], 'market': []}
        calls = []
        def producer(received, cfg):
            self.assertIs(received, obs)
            self.assertIs(cfg, config)
            calls.append('producer')
            return selected
        def scenarios(received, cfg):
            calls.append('scenario')
            if inspect:
                inspect(received, cfg)
            return []
        agent = module.TerminalAdmissionAgent(producer, None, scenarios)
        action = agent.act(obs, config)
        self.assertEqual(action, selected)
        return agent, calls

    def test_struct_attribute_callback_still_works(self):
        cfg = Config(shedCapacity=3, episodeSteps=720, turnsPerDay=24)
        def check(obs, actual):
            self.assertEqual(actual.shedCapacity, 3)
            self.assertIs(actual, cfg)
        agent, calls = self.exercise(cfg, inspect=check)
        self.assertEqual(calls, ['producer', 'scenario'])
        self.assertEqual(agent.last_report['reason'], 'no_explicit_rival_scenarios')

    def test_dict_callback_receives_original_configuration(self):
        cfg = {'episodeSteps': 720}
        _, calls = self.exercise(cfg, inspect=lambda obs, actual: self.assertIs(actual, cfg))
        self.assertEqual(calls, ['producer', 'scenario'])

    def test_falsey_config_keeps_nondefault_clock(self):
        cfg = FalseyConfig(episodeSteps=50, turnsPerDay=6)
        obs = {'day': 8, 'hour': 0}
        def check(received, actual):
            self.assertIs(actual, cfg)
            self.assertEqual(received['step'], 48)
        agent, calls = self.exercise(cfg, obs, check)
        self.assertEqual(calls, ['producer', 'scenario'])
        self.assertEqual(agent.last_report['reason'], 'no_explicit_rival_scenarios')
        self.assertNotIn('step', obs)

    def test_readonly_mapping_needs_no_copy_protocol(self):
        cfg = MappingProxyType({'episodeSteps': 720})
        _, calls = self.exercise(cfg, inspect=lambda obs, actual: self.assertIs(actual, cfg))
        self.assertEqual(calls, ['producer', 'scenario'])

    def test_none_configuration_supplies_empty_callback_mapping(self):
        def check(obs, actual):
            self.assertEqual(actual, {})
            self.assertIsInstance(actual, dict)
        _, calls = self.exercise(None, inspect=check)
        self.assertEqual(calls, ['producer', 'scenario'])

    def test_derived_clock_uses_supplied_turns_per_day(self):
        cfg = Config(episodeSteps=122, turnsPerDay=10)
        obs = {'day': 12, 'hour': 0}
        def check(received, actual):
            self.assertIs(actual, cfg)
            self.assertEqual(received['step'], 120)
            self.assertIsNot(received, obs)
        _, calls = self.exercise(cfg, obs, check)
        self.assertEqual(calls, ['producer', 'scenario'])
        self.assertNotIn('step', obs)

    def test_nonterminal_does_not_invoke_scenario(self):
        def fail(*args):
            raise AssertionError('nonterminal must not call scenario')
        agent, calls = self.exercise(Config(episodeSteps=720), {'step': 717}, fail)
        self.assertEqual(calls, ['producer'])
        self.assertEqual(agent.last_report['reason'], 'nonterminal')

    def test_parent_exception_is_original_and_single_call(self):
        cfg = Config(episodeSteps=720)
        error = TypeError('producer body sentinel')
        calls = []
        def producer(obs, config):
            self.assertIs(config, cfg)
            calls.append(1)
            raise error
        def scenario(*args):
            self.fail('scenario must not run after parent failure')
        agent = module.TerminalAdmissionAgent(producer, None, scenario)
        with self.assertRaises(TypeError) as caught:
            agent.act({'step': 718}, cfg)
        self.assertIs(caught.exception, error)
        self.assertEqual(calls, [1])

    def test_scenario_exception_is_original_and_not_retried(self):
        cfg = Config(episodeSteps=720)
        error = RuntimeError('scenario body sentinel')
        calls = []
        def producer(*args):
            calls.append('producer')
            return {'farmer': ['PASS'], 'hands': [], 'market': []}
        def scenario(obs, config):
            calls.append('scenario')
            raise error
        agent = module.TerminalAdmissionAgent(producer, None, scenario)
        with self.assertRaises(RuntimeError) as caught:
            agent.act({'step': 718}, cfg)
        self.assertIs(caught.exception, error)
        self.assertEqual(calls, ['producer', 'scenario'])

    def test_explicit_step_is_not_overwritten(self):
        cfg = Config(episodeSteps=720, turnsPerDay=6)
        obs = {'step': 718, 'day': 8, 'hour': 0}
        def check(received, actual):
            self.assertEqual(received['step'], 718)
            self.assertIs(actual, cfg)
        _, calls = self.exercise(cfg, obs, check)
        self.assertEqual(calls, ['producer', 'scenario'])
        self.assertEqual(obs, {'step': 718, 'day': 8, 'hour': 0})


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(ConfigurationContractTests))
    output = os.environ.get('TITAN_CONFIGURATION_REPORT')
    if output:
        data = TARGET.read_bytes()
        Path(output).write_text(json.dumps({
            'source_sha256': hashlib.sha256(data).hexdigest(),
            'source_git_blob': hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest(),
            'test_methods': result.testsRun, 'failures': len(result.failures),
            'errors': len(result.errors), 'skipped': len(result.skipped),
            'success': result.wasSuccessful(), 'full_games': 0}, indent=2) + '\n')
    sys.exit(0 if result.wasSuccessful() else 1)
