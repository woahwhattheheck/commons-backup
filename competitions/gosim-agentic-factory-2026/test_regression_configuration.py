import unittest

import harness_score as hs
from test_harness_score import policy, run


class RegressionConfigurationTests(unittest.TestCase):
    def test_cross_configuration_best_of_tasks_cannot_mint_pass(self):
        baseline = [
            run(task="a", trial="base-a", harness="baseline-h", model="baseline-m"),
            run(task="b", trial="base-b", harness="baseline-h", model="baseline-m"),
        ]
        candidate = [
            run(task="a", trial="m1-a", harness="candidate-h", model="m1"),
            run(task="b", trial="m1-b", harness="candidate-h", model="m1", passed=0, failed=10),
            run(task="a", trial="m2-a", harness="candidate-h", model="m2", passed=0, failed=10),
            run(task="b", trial="m2-b", harness="candidate-h", model="m2"),
        ]
        gate = hs.compile_report(candidate, policy(), baseline)["regression_gate"]
        self.assertFalse(gate["passed"])
        self.assertEqual(gate["passing_configurations"], [])
        self.assertEqual(
            {(row["harness_revision"], row["model_label"], row["passed"]) for row in gate["configuration_results"]},
            {("candidate-h", "m1", False), ("candidate-h", "m2", False)},
        )
        self.assertEqual(
            gate["failures"],
            [{"task_id": "*", "reason": "NO_CANDIDATE_CONFIGURATION_PASSED"}],
        )

    def test_one_real_candidate_configuration_can_pass(self):
        baseline = [
            run(task="a", trial="base-a", harness="baseline-h", model="baseline-m"),
            run(task="b", trial="base-b", harness="baseline-h", model="baseline-m"),
        ]
        candidate = [
            run(task="a", trial="m1-a", harness="candidate-h", model="m1"),
            run(task="b", trial="m1-b", harness="candidate-h", model="m1"),
            run(task="a", trial="m2-a", harness="candidate-h", model="m2", passed=0, failed=10),
            run(task="b", trial="m2-b", harness="candidate-h", model="m2"),
        ]
        gate = hs.compile_report(candidate, policy(), baseline)["regression_gate"]
        self.assertTrue(gate["passed"])
        self.assertEqual(
            gate["passing_configurations"],
            [{"harness_revision": "candidate-h", "model_label": "m1"}],
        )
        self.assertEqual(gate["failures"], [])

    def test_baseline_must_name_one_concrete_configuration(self):
        baseline = [
            run(task="a", trial="base-a", harness="baseline-h", model="m1"),
            run(task="b", trial="base-b", harness="baseline-h", model="m2"),
        ]
        with self.assertRaisesRegex(hs.ContractError, "baseline must contain exactly one harness/model configuration"):
            hs.compile_report([run(task="a", trial="candidate")], policy(), baseline)


if __name__ == "__main__":
    unittest.main()
