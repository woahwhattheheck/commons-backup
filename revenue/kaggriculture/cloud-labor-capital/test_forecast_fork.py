"""Explicit forecast forks over the actual pinned engine, with no new games.

Set T10_SOURCEPACK to the retained source pack. T10_COMPOSITION_SOURCE may point
at an exact saved copy of the existing KEEL composition.py for isolated replay.
"""
import copy
import importlib.util
import os
from pathlib import Path
import sys
import unittest

import labor_capital as labor
from test_engine import ENGINE, PASS, Script, observation


class NestedParent:
    """Mutable controller state; a shallow copy is deliberately insufficient."""
    def __init__(self, actions=None, fail_step=None):
        self.state = {"steps": [], "calls": 0}
        self.actions = copy.deepcopy(actions or {})
        self.fail_step = fail_step
        self.engine = ENGINE  # Shared code is not deepcopy-able controller data.

    def __copy__(self):
        raise AssertionError("an explicit factory must replace the Arlene copy")

    def act(self, obs):
        self.state["steps"].append(obs["step"])
        self.state["calls"] += 1
        if obs["step"] == self.fail_step:
            raise RuntimeError("forecast failure")
        return copy.deepcopy(self.actions.get(obs["step"], PASS))

    def fork(self):
        clone = NestedParent(self.actions, self.fail_step)
        clone.state = copy.deepcopy(self.state)
        return clone


def load_file(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class ForecastForkTests(unittest.TestCase):
    def test_explicit_factory_owns_nested_mutable_state(self):
        obs = observation(20)
        parent = NestedParent({20: dict(PASS, market=[["BUY_SEED", "CARROT", 1]])})
        first = parent.act(obs)
        saved = copy.deepcopy((obs, parent.state, first))
        forks = []
        def factory():
            fork = parent.fork()
            forks.append(fork)
            return fork.act
        result = labor.project_shift(ENGINE, obs, parent, first, fork_parent=factory)
        self.assertEqual(result.estimated_cash, 80)
        self.assertEqual(forks[0].state["steps"], [20, 21, 22, 23])
        self.assertEqual((obs, parent.state, first), saved)
        self.assertEqual(len(forks), 1)
        self.assertIs(forks[0].engine, parent.engine)

    def test_each_projection_receives_a_fresh_continuation(self):
        obs = observation(21)
        parent = NestedParent()
        first = parent.act(obs)
        forks = []
        def factory():
            fork = parent.fork()
            forks.append(fork)
            return fork.act
        a = labor.project_shift(ENGINE, obs, parent, first, fork_parent=factory)
        b = labor.project_shift(ENGINE, obs, parent, first, fork_parent=factory)
        self.assertEqual(a, b)
        self.assertIsNot(forks[0].state, forks[1].state)
        self.assertEqual([p.state["steps"] for p in forks], [[21, 22, 23]] * 2)
        self.assertEqual(parent.state["steps"], [21])

    def test_hiring_agent_calls_current_parent_once_and_forks_every_arm(self):
        obs = observation(22)
        parent = NestedParent({22: dict(PASS, market=[["HIRE"], ["HIRE"]])})
        forks = []
        def factory():
            fork = parent.fork()
            forks.append(fork)
            return fork.act
        actor = labor.HiringAgent(parent, ENGINE, fork_parent=factory)
        action = actor.act(obs)
        self.assertEqual(parent.state, {"steps": [22], "calls": 1})
        self.assertEqual(len(forks), 3)  # Control and two suffix omissions.
        self.assertTrue(all(f.state["steps"] == [22, 23] for f in forks))
        self.assertEqual(actor.last_decision["selected"], "omit_hire_suffix_2")
        self.assertEqual(action["market"], [labor.NO_ORDER, labor.NO_ORDER])
        self.assertEqual(obs.farms[0]["money"], 100)

    def test_no_alternatives_do_not_request_a_forecast(self):
        parent = NestedParent()
        def forbidden():
            raise AssertionError("factory must not run without alternatives")
        actor = labor.HiringAgent(parent, ENGINE, fork_parent=forbidden)
        self.assertEqual(actor.act(observation(22)), PASS)
        self.assertEqual(parent.state["calls"], 1)

    def test_noncallable_factory_rejected_before_current_parent_call(self):
        parent = NestedParent()
        with self.assertRaisesRegex(TypeError, "zero-argument"):
            labor.HiringAgent(parent, ENGINE, fork_parent=object())
        self.assertEqual(parent.state["calls"], 0)

    def test_direct_projection_rejects_noncallable_factory(self):
        with self.assertRaisesRegex(TypeError, "zero-argument"):
            labor.project_shift(ENGINE, observation(22), NestedParent(), PASS,
                                fork_parent=object())

    def test_returned_value_must_be_an_observation_callable(self):
        obs = observation(22)
        before = copy.deepcopy(obs)
        with self.assertRaisesRegex(TypeError, "observation callable"):
            labor.project_shift(ENGINE, obs, NestedParent(), PASS,
                                fork_parent=lambda: None)
        self.assertEqual(obs, before)

    def test_factory_error_is_not_silently_replaced_by_shallow_copy(self):
        def broken():
            raise LookupError("factory failed")
        parent = NestedParent()
        with self.assertRaisesRegex(LookupError, "factory failed"):
            labor.project_shift(ENGINE, observation(22), parent, PASS,
                                fork_parent=broken)
        self.assertEqual(parent.state["calls"], 0)

    def test_forecast_error_does_not_mutate_live_parent_or_inputs(self):
        obs = observation(21)
        parent = NestedParent(fail_step=22)
        first = parent.act(obs)
        saved = copy.deepcopy((obs, parent.state, first))
        with self.assertRaisesRegex(RuntimeError, "forecast failure"):
            labor.project_shift(ENGINE, obs, parent, first,
                                fork_parent=lambda: parent.fork().act)
        self.assertEqual((obs, parent.state, first), saved)

    def test_final_decision_uses_selected_action_without_a_second_call(self):
        parent = NestedParent(fail_step=718)
        obs = observation(718)
        first = dict(PASS, market=[["BUY_SEED", "CARROT", 1]])
        result = labor.project_shift(ENGINE, obs, parent, first,
                                     fork_parent=lambda: parent.fork().act)
        self.assertEqual(result.estimated_cash, 80)
        self.assertEqual(parent.state["calls"], 0)

    def test_explicit_callable_preserves_cash_trough_and_complete_endpoint(self):
        for seat in (0, 1):
            with self.subTest(seat=seat):
                obs = observation(716, seat=seat)
                obs.private["shed"]["EGG"] = 2
                first = dict(PASS, market=[["BUY_SEED", "CARROT", 1], ["SELL", "EGG", 2]])
                plan = {717: dict(PASS, market=[["BUY_SEED", "WHEAT", 1]])}
                expected = labor.project_shift(ENGINE, obs, Script(plan), first)
                parent = NestedParent(plan)
                actual = labor.project_shift(ENGINE, obs, parent, first,
                                              fork_parent=lambda: parent.fork().act)
                self.assertEqual(actual, expected)
                self.assertEqual(actual.minimum_cash, 80)
                self.assertEqual(actual.estimated_cash, 169)

    def test_factory_can_return_a_plain_function(self):
        calls = []
        def factory():
            def act(obs):
                calls.append(obs["step"])
                return dict(PASS, market=[["BUY_SEED", "WHEAT", 1]])
            return act
        result = labor.project_shift(ENGINE, observation(21), object(), PASS,
                                     fork_parent=factory)
        self.assertEqual(calls, [22, 23])
        self.assertEqual(result.estimated_cash, 80)

    def test_custom_factory_leaves_engine_functions_unchanged(self):
        functions = {name: getattr(ENGINE, name) for name in
                     ("_process_market", "_apply_unit_action", "interpreter")}
        parent = NestedParent()
        labor.project_shift(ENGINE, observation(20), parent, PASS,
                            fork_parent=lambda: parent.fork().act)
        for name, function in functions.items():
            self.assertIs(getattr(ENGINE, name), function)

    def test_keel_existing_factory_contract_composes_directly(self):
        default = Path(__file__).resolve().parents[1] / "cloud-service-labor-composition/composition.py"
        path = Path(os.environ.get("T10_COMPOSITION_SOURCE", str(default)))
        composition = load_file(path, "t10_existing_keel_fork")
        base = Path(os.environ["T10_SOURCEPACK"]) / "commons/revenue/kaggriculture"
        arlene = load_file(base / "cloud-frontier-policy/next-panel/vendor/arlene.py",
                           "t10_existing_arlene_fork")
        owner = composition.Composition(arlene, labor, None, ENGINE,
                                        service=False, labor=False)
        obs = observation(22)
        selected = owner.act(obs)
        state = copy.deepcopy(owner.base.__dict__)
        expected = labor.project_shift(ENGINE, obs, owner.base, selected)
        actual = labor.project_shift(ENGINE, obs, owner, selected,
                                     fork_parent=owner.fork_parent)
        self.assertEqual(actual, expected)
        self.assertEqual(owner.parent_calls, 1)
        self.assertEqual(owner.calls, 1)
        self.assertEqual(owner.forks, 1)
        self.assertEqual(owner.base.__dict__, state)


if __name__ == "__main__":
    unittest.main()
