"""Public-clock lifecycle checks for ALDER's existing input-budget entrypoint.

These tests isolate module-level actor construction. They do not execute the
policy economics, engine, games, or seed panels.
"""
import importlib.util
from pathlib import Path
import sys
import types
import unittest

CANDIDATE = Path(__file__).with_name('candidate.py')


class FakeTimer:
    expired = object()
    def __init__(self, *args): pass
    def __enter__(self): return self
    def __exit__(self, *args): return False


class FakeParent:
    DECISIONS = []
    _noop = staticmethod(lambda *args: False)


class FakeScheduler(types.ModuleType):
    m = object()
    parent = FakeParent()
    post_units = staticmethod(lambda *args: ({}, {}))


class FakeBudget:
    def __init__(self, *args):
        self.last = types.SimpleNamespace()


class StubAgent:
    def __init__(self, serial):
        self.serial = serial
        self.calls = []
    def act(self, observation, configuration=None):
        self.calls.append((dict(observation), configuration))
        return {'serial': self.serial}


class PublicClockTests(unittest.TestCase):
    def load(self):
        counter = {'n': 0}
        runtime = types.ModuleType('titan_runtime')
        runtime.TitanAgent = lambda: None
        runtime.deadline = types.SimpleNamespace(
            _DeadlineTimer=FakeTimer, DeadlineExceeded=Exception)
        budget = types.ModuleType('input_budget')
        budget.FinalInputBudget = FakeBudget
        scheduler = FakeScheduler('scheduler')
        previous = {name: sys.modules.get(name)
                    for name in ('titan_runtime', 'input_budget', 'scheduler')}
        sys.modules.update(titan_runtime=runtime, input_budget=budget, scheduler=scheduler)
        try:
            spec = importlib.util.spec_from_file_location('input_budget_candidate_under_test', CANDIDATE)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        finally:
            for name, value in previous.items():
                if value is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = value

        def make_agent(**kwargs):
            counter['n'] += 1
            return StubAgent(counter['n'])
        module.make_agent = make_agent
        return module, counter

    def test_sparse_zero_resets_existing_actor(self):
        module, counter = self.load()
        self.assertEqual(module.agent({'day': 0, 'hour': 1}, {}), {'serial': 1})
        self.assertEqual(module.agent({'day': 0, 'hour': 0}, {}), {'serial': 2})
        self.assertEqual(counter['n'], 2)

    def test_sparse_nonzero_reuses_actor(self):
        module, counter = self.load()
        module.agent({'day': 0, 'hour': 1}, {})
        module.agent({'day': 1, 'hour': 0}, {})
        self.assertEqual(counter['n'], 1)

    def test_explicit_zero_precedes_day_hour(self):
        module, counter = self.load()
        module.agent({'day': 0, 'hour': 1}, {})
        module.agent({'step': 0, 'day': 3, 'hour': 2}, {})
        self.assertEqual(counter['n'], 2)

    def test_explicit_nonzero_precedes_sparse_zero(self):
        module, counter = self.load()
        module.agent({'day': 0, 'hour': 1}, {})
        module.agent({'step': 7, 'day': 0, 'hour': 0}, {})
        self.assertEqual(counter['n'], 1)

    def test_null_step_uses_public_clock(self):
        module, counter = self.load()
        module.agent({'step': None, 'day': 0, 'hour': 1}, {})
        module.agent({'step': None, 'day': 0, 'hour': 0}, {})
        self.assertEqual(counter['n'], 2)

    def test_configuration_none_uses_default_period(self):
        module, _ = self.load()
        self.assertEqual(module._absolute_step({'day': 1, 'hour': 2}, None), 26)

    def test_custom_turns_per_day(self):
        module, _ = self.load()
        self.assertEqual(module._absolute_step(
            {'day': 2, 'hour': 3}, {'turnsPerDay': 10}), 23)

    def test_inputs_are_not_mutated(self):
        module, _ = self.load()
        observation = {'step': None, 'day': 0, 'hour': 1}
        configuration = {'turnsPerDay': 12}
        before = (dict(observation), dict(configuration))
        module.agent(observation, configuration)
        self.assertEqual((observation, configuration), before)


if __name__ == '__main__':
    unittest.main()
