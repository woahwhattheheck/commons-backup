# SPDX-License-Identifier: Apache-2.0
"""Recursive declared-event prefix tests over the existing T04 consumer."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import os
from pathlib import Path
import random
import unittest

import physical_replay as replay
from test_prefix_reuse import Controller


@dataclass
class Scenario:
    market_deltas: dict = field(default_factory=dict)
    new_shops: dict = field(default_factory=dict)
    new_weeds: dict = field(default_factory=dict)
    label: str = "constructed"


class PrefixTreePlanTests(unittest.TestCase):
    def six(self):
        scenarios = {"none": Scenario(label="none")}
        for visible in (288, 360, 432, 504, 576):
            scenarios[str(visible)] = Scenario(
                new_shops={visible - 1: ("YARN_STORE",)}, label=str(visible))
        return scenarios

    def test_six_arrival_tree_exact_segments(self):
        plan = replay._event_prefix_paths(self.six(), 226, 718)
        self.assertEqual(plan["root_stop"], 286)
        self.assertEqual(plan["branch_steps"], (287, 359, 431, 503, 575))
        self.assertEqual((plan["max_depth"], plan["nodes"]), (6, 11))
        expected = {
            "none": [(226, 286), (287, 358), (359, 430),
                     (431, 502), (503, 574), (575, 718)],
            "288": [(226, 286), (287, 718)],
            "360": [(226, 286), (287, 358), (359, 718)],
            "432": [(226, 286), (287, 358), (359, 430), (431, 718)],
            "504": [(226, 286), (287, 358), (359, 430),
                    (431, 502), (503, 718)],
            "576": [(226, 286), (287, 358), (359, 430),
                    (431, 502), (503, 574), (575, 718)],
        }
        self.assertEqual({key: [(node.start_step, node.end_step) for node in path]
                          for key, path in plan["paths"].items()}, expected)

    def test_diverged_worlds_never_remerge(self):
        scenarios = {
            "left": Scenario(new_shops={5: ("BAKERY",), 7: ("YARN_STORE",)}),
            "right": Scenario(new_shops={5: ("PIZZA_SHOP",), 7: ("YARN_STORE",)}),
        }
        plan = replay._event_prefix_paths(scenarios, 2, 9)
        self.assertEqual(plan["branch_steps"], (5,))
        self.assertFalse(any(set(node.scenario_ids) == {"left", "right"}
                             for path in plan["paths"].values()
                             for node in path if node.start_step >= 5))

    def test_identical_mechanics_share_terminal_node_despite_labels(self):
        plan = replay._event_prefix_paths(
            {"a": Scenario(label="a"), "b": Scenario(label="b")}, 2, 9)
        self.assertEqual(plan["branch_steps"], ())
        self.assertEqual(plan["paths"]["a"], plan["paths"]["b"])
        self.assertEqual((plan["paths"]["a"][0].start_step,
                          plan["paths"]["a"][0].end_step), (2, 9))

    def test_current_step_split_has_no_global_node(self):
        plan = replay._event_prefix_paths(
            {"a": Scenario(), "b": Scenario(market_deltas={2: {"MILK": 1}})}, 2, 9)
        self.assertEqual(plan["root_stop"], 1)
        self.assertEqual(plan["branch_steps"], (2,))
        self.assertTrue(all(path[0].start_step == 2 for path in plan["paths"].values()))

    def test_unknown_shapes_retain_ordinary_path(self):
        self.assertIsNone(replay._event_prefix_paths({"a": {}, "b": {}}, 2, 9))
        @dataclass
        class Extended(Scenario):
            extra: int = 1
        self.assertIsNone(replay._event_prefix_paths(
            {"a": Extended(), "b": Extended()}, 2, 9))


@unittest.skipUnless(os.environ.get("OSPREY_RILL_EVIDENCE"),
                     "Set OSPREY_RILL_EVIDENCE to the retained RILL evidence root")
class NativePrefixTreeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from check_prefix_reuse import setup
        cls.c = setup(Path(os.environ["OSPREY_RILL_EVIDENCE"]))

    def setUp(self):
        self.obs = deepcopy(self.c.obs)
        self.obs.update(step=22, day=0, hour=22)
        self.cfg = deepcopy(self.c.cfg)
        self.cfg["episodeSteps"] = 80
        self.actor = Controller(switch=23)
        self.scenarios = {
            "none": self.c.oracle.Scenario(label="none"),
            "at24": self.c.oracle.Scenario(new_shops={24: ("YARN_STORE",)}, label="at24"),
            "at36": self.c.oracle.Scenario(new_shops={36: ("YARN_STORE",)}, label="at36"),
            "at48": self.c.oracle.Scenario(new_shops={48: ("YARN_STORE",)}, label="at48"),
            "at60": self.c.oracle.Scenario(new_shops={60: ("YARN_STORE",)}, label="at60"),
        }

    def execute(self, reuse, *, scenarios=None, player=0, fork=deepcopy, decisions=5000):
        obs = deepcopy(self.obs)
        obs["player"] = player
        return replay.replay_routes(
            self.actor, ("main", "other"), obs, self.cfg,
            self.c.engine, self.c.oracle.simulate_bundle,
            scenarios=self.scenarios if scenarios is None else scenarios,
            end_step=70, fork_controller=fork,
            limits=replay.ReplayLimits(seconds=30, decisions=decisions),
            reuse_scenario_prefixes=reuse)

    def test_nested_outputs_equal_independent_execution(self):
        independent = self.execute(False)
        nested = self.execute(True)
        self.assertTrue(independent["complete"] and nested["complete"])
        self.assertEqual(nested["cases"], independent["cases"])
        self.assertEqual(independent["decisions_executed"], 490)
        self.assertEqual(nested["decisions_executed"], 330)
        self.assertEqual(nested["prefix_reuse"]["reused_decisions"], 160)
        self.assertEqual(nested["prefix_reuse"]["branch_steps"], [24, 36, 48, 60])
        self.assertEqual(nested["prefix_reuse"]["prefixes_computed"], 8)

    def test_second_seat_equal(self):
        self.assertEqual(self.execute(True, player=1)["cases"], self.execute(False, player=1)["cases"])

    def test_scenario_order_changes_no_case_or_work_total(self):
        forward = self.execute(True)
        reversed_scenarios = dict(reversed(tuple(self.scenarios.items())))
        backward = self.execute(True, scenarios=reversed_scenarios)
        by_key = lambda report: {(case["offered_route"], case["scenario_id"]): case
                                 for case in report["cases"]}
        self.assertEqual(by_key(forward), by_key(backward))
        self.assertEqual(forward["decisions_executed"], backward["decisions_executed"])
        self.assertEqual(forward["prefix_reuse"]["reused_decisions"],
                         backward["prefix_reuse"]["reused_decisions"])

    def test_actor_local_rng_is_in_every_nested_checkpoint(self):
        class LocalRng(Controller):
            def __init__(self):
                super().__init__(switch=23)
                self.rng = random.Random(919)
            def act(self, view):
                action = super().act(view)
                action["market"][0][2] = self.rng.randrange(5)
                return action
        self.actor = LocalRng()
        state = self.actor.rng.getstate()
        self.assertEqual(self.execute(True)["cases"], self.execute(False)["cases"])
        self.assertEqual(self.actor.rng.getstate(), state)
        self.assertEqual(self.actor.calls, 0)

    def test_deep_checkpoint_cancellation_propagates(self):
        calls = [0]
        def fork(actor):
            calls[0] += 1
            if calls[0] == 3:
                raise KeyboardInterrupt("nested checkpoint cancellation")
            return deepcopy(actor)
        with self.assertRaisesRegex(KeyboardInterrupt, "nested checkpoint cancellation"):
            self.execute(True, fork=fork)
        self.assertEqual(self.actor.calls, 0)

    def test_deep_checkpoint_identity_is_rejected(self):
        calls = [0]
        held = [None]
        def fork(actor):
            calls[0] += 1
            if calls[0] == 3:
                return actor
            held[0] = deepcopy(actor)
            return held[0]
        report = self.execute(True, fork=fork)
        self.assertFalse(report["complete"])
        self.assertIn("not independent", report["cases"][0]["reason"])
        self.assertTrue(all(case["cash_gain"] is None for case in report["cases"][:1]))

    def test_result_rows_are_independent_after_nested_reuse(self):
        report = self.execute(True)
        before = deepcopy(report["cases"][0])
        report["cases"][-1]["result"]["actions"][22]["market"][0][2] = 999
        report["cases"][-1]["market_rows"][0]["cash_after"] = -1
        self.assertEqual(report["cases"][0], before)

    def test_shared_decision_budget_stops_without_partial_score(self):
        report = self.execute(True, decisions=55)
        self.assertFalse(report["complete"])
        self.assertEqual(report["decisions_executed"], 55)
        self.assertEqual(report["cases"][0]["status"], "complete")
        self.assertIsNotNone(report["cases"][0]["cash_gain"])
        self.assertTrue(all(case["cash_gain"] is None for case in report["cases"][1:]))

    def test_extended_scenario_schema_falls_back_to_independent(self):
        @dataclass(frozen=True)
        class Extended(type(next(iter(self.scenarios.values())))):
            extra: int = 1
        scenarios = {
            "a": Extended(label="a"),
            "b": Extended(new_shops={24: ("YARN_STORE",)}, label="b"),
        }
        ordinary = self.execute(False, scenarios=scenarios)
        fallback = self.execute(True, scenarios=scenarios)
        self.assertEqual(fallback["cases"], ordinary["cases"])
        self.assertEqual(fallback["decisions_executed"], ordinary["decisions_executed"])
        self.assertEqual(fallback["prefix_reuse"]["strategy"], "ordinary_unsupported_schema")


if __name__ == "__main__":
    unittest.main()
