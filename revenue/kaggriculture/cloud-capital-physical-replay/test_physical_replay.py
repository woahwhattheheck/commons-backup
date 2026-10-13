# SPDX-License-Identifier: Apache-2.0
"""Consumer regressions against the existing oracle and actual original controller.

Set TITAN_SOURCE_ROOT, TITAN_ENGINE_DIR, T04_ORACLE, T10_OBSERVATION. These tests
run short conditional continuations, never initialize or replay full games.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import unittest

from check_existing import load
from physical_replay import ReplayLimits, replay_routes

MAIN = "7015cc00acfa4922"
YARN = "dc76e4003029ac51"


class PhysicalReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        names = ("TITAN_SOURCE_ROOT", "TITAN_ENGINE_DIR", "T04_ORACLE", "T10_OBSERVATION")
        if not all(os.environ.get(name) for name in names):
            raise unittest.SkipTest("Set the four documented existing-input paths")
        root = Path(os.environ["TITAN_SOURCE_ROOT"])
        cls.oracle = load(os.environ["T04_ORACLE"], "physical_test_oracle")
        cls.arlene = load(root / "cloud-frontier-policy/next-panel/vendor/arlene.py", "physical_test_arlene")
        evaluator = load(root / "cloud-eval/evaluate.py", "physical_test_eval")
        cls.engine, _ = evaluator.get_engine(os.environ["TITAN_ENGINE_DIR"])
        cls.cfg = {k: v.get("default") if isinstance(v, dict) else v
                   for k, v in cls.engine.specification["configuration"].items()}
        cls.obs = json.loads(Path(os.environ["T10_OBSERVATION"]).read_text())["observation"]

    def setUp(self):
        self.controller = self.arlene.Agent()
        self.scenarios = {"known": self.oracle.Scenario()}

    def run_routes(self, **overrides):
        args = dict(controller=self.controller, route_ids=[MAIN, YARN],
                    observation=self.obs, configuration=self.cfg,
                    engine=self.engine, simulate_bundle=self.oracle.simulate_bundle,
                    scenarios=self.scenarios, end_step=123,
                    limits=ReplayLimits(seconds=5))
        args.update(overrides)
        return replay_routes(**args)

    def test_exact_real_controller_and_oracle_outputs(self):
        report = self.run_routes()
        self.assertTrue(report["complete"])
        for case in report["cases"]:
            parent = deepcopy(self.controller)
            parent.cur = case["offered_route"]
            direct = self.oracle.simulate_bundle(self.engine, self.obs, self.cfg,
                                                 parent.act, end_step=123,
                                                 scenario=self.scenarios["known"], record_actions=True)
            self.assertEqual(case["result"], direct)
            self.assertEqual(len(case["market_rows"]), 3)

    def test_original_controller_and_observation_are_unchanged(self):
        state, obs = deepcopy(self.controller.__dict__), deepcopy(self.obs)
        self.run_routes()
        self.assertEqual(state, self.controller.__dict__)
        self.assertEqual(obs, self.obs)

    def test_independent_scenario_actors(self):
        scenarios = {"a": self.oracle.Scenario(), "b": self.oracle.Scenario()}
        result = self.run_routes(scenarios=scenarios)
        self.assertEqual(len(result["cases"]), 4)
        for index in (0, 2):
            self.assertEqual(result["cases"][index]["result"], result["cases"][index + 1]["result"])

    def test_live_producer_fork_is_rejected_before_call(self):
        state = deepcopy(self.controller.__dict__)
        result = self.run_routes(fork_controller=lambda original: original)
        self.assertFalse(result["complete"])
        self.assertTrue(all(c["cash_gain"] is None for c in result["cases"]))
        self.assertEqual(self.controller.__dict__, state)
        self.assertEqual(result["decisions_executed"], 0)

    def test_budget_is_shared_and_partial_cash_is_not_a_score(self):
        result = self.run_routes(limits=ReplayLimits(seconds=5, decisions=1))
        self.assertFalse(result["complete"])
        self.assertEqual(result["decisions_executed"], 1)
        self.assertEqual(len(result["cases"][0]["market_rows"]), 1)
        self.assertTrue(all(c["cash_gain"] is None for c in result["cases"]))
        self.assertTrue(all(c["reason"] == "budget:decisions" for c in result["cases"]))

    def test_zero_time_makes_no_speculative_calls(self):
        result = self.run_routes(limits=ReplayLimits(seconds=0))
        self.assertEqual(result["decisions_executed"], 0)
        self.assertTrue(all(c["status"] == "incomplete" for c in result["cases"]))

    def test_unknown_route_keeps_other_result_separate(self):
        result = self.run_routes(route_ids=[MAIN, "not-a-route"])
        self.assertEqual(result["cases"][0]["status"], "complete")
        self.assertEqual(result["cases"][1]["status"], "incomplete")
        self.assertFalse(result["complete"])
        self.assertIsNone(result["selection"])

    def test_structurally_incompatible_program_not_forced(self):
        obs = deepcopy(self.obs)
        obs.update(step=227, day=9, hour=11)
        # This intentionally changed clock tests prefix dispatch only. No physical
        # execution is reached and this is not a claimed reached227 observation.
        result = self.run_routes(route_ids=[YARN], observation=obs, end_step=227)
        self.assertEqual(result["cases"][0]["status"], "incompatible")
        self.assertEqual(result["decisions_executed"], 0)

    def test_incomplete_program_is_not_filled_with_pass(self):
        controller = deepcopy(self.controller)
        controller.R[MAIN] = controller.R[MAIN][:122]
        result = self.run_routes(controller=controller, route_ids=[MAIN])
        self.assertEqual(result["cases"][0]["status"], "incomplete")
        self.assertEqual(result["decisions_executed"], 0)

    def test_ordinary_dependency_failure_retains_incomplete(self):
        def broken(*args, **kwargs):
            raise RuntimeError("deliberate dependency failure")
        result = self.run_routes(simulate_bundle=broken)
        self.assertFalse(result["complete"])
        self.assertTrue(all(c["cash_gain"] is None for c in result["cases"]))
        self.assertIn("RuntimeError", result["cases"][0]["reason"])

    def test_external_cancellation_propagates(self):
        class Cancelled(BaseException):
            pass
        def cancelled(*args, **kwargs):
            raise Cancelled()
        with self.assertRaises(Cancelled):
            self.run_routes(simulate_bundle=cancelled)

    def test_missing_scenarios_and_duplicate_offers_are_explicit(self):
        with self.assertRaises(ValueError):
            self.run_routes(scenarios={})
        with self.assertRaises(ValueError):
            self.run_routes(route_ids=[MAIN, MAIN])

    def test_end_must_be_executable(self):
        with self.assertRaises(ValueError):
            self.run_routes(end_step=120)
        with self.assertRaises(ValueError):
            self.run_routes(end_step=719)

    def test_queue_receipts_include_actual_hires_not_just_dynamic_quotes(self):
        result = self.run_routes(route_ids=[MAIN], end_step=121)
        row = result["cases"][0]["market_rows"][0]
        self.assertEqual(row["orders"], [["HIRE"], ["HIRE"]])
        self.assertEqual(row["hires_after"] - row["hires_before"], 2)
        self.assertEqual(row["cash_delta"], -8.0)
        self.assertEqual(row["cash_after"], 90.0)

    def test_nominal_unaffordable_orders_are_not_recorded_as_paid(self):
        obs = deepcopy(self.obs)
        obs["farms"][int(obs["player"])]["money"] = 3.0
        result = self.run_routes(observation=obs, route_ids=[MAIN], end_step=121)
        row = result["cases"][0]["market_rows"][0]
        self.assertEqual(row["orders"], [["HIRE"], ["HIRE"]])
        self.assertEqual(row["hires_after"] - row["hires_before"], 1)
        self.assertEqual(row["cash_delta"], -3.0)
        self.assertEqual(row["cash_after"], 0.0)


if __name__ == "__main__":
    unittest.main()
