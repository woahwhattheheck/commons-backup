import unittest

import harness_score as hs
from test_harness_score import HEX_A, HEX_B, policy, run


class TaskGenerationRegressionTests(unittest.TestCase):
    def test_same_task_name_different_spec_is_generation_mismatch(self):
        baseline = [run(task="x", trial="base", task_sha=HEX_A)]
        candidate = [
            run(
                task="x",
                trial="candidate",
                task_sha=HEX_B,
                input_tokens=1,
                output_tokens=1,
                cache_tokens=0,
                wall=1,
            )
        ]
        gate = hs.compile_report(candidate, policy(), baseline)["regression_gate"]
        self.assertFalse(gate["passed"])
        self.assertEqual(
            gate["failures"],
            [{"task_id": "x", "reason": "TASK_GENERATION_MISMATCH"}],
        )

    def test_same_task_spec_different_test_cardinality_is_generation_mismatch(self):
        baseline = [run(task="x", trial="base", total=10, passed=10, failed=0)]
        candidate = [run(task="x", trial="candidate", total=20, passed=20, failed=0)]
        gate = hs.compile_report(candidate, policy(), baseline)["regression_gate"]
        self.assertEqual(
            gate["failures"],
            [{"task_id": "x", "reason": "TASK_GENERATION_MISMATCH"}],
        )

    def test_ambiguous_task_generation_within_candidate_rejected(self):
        candidate = [
            run(task="x", trial="one", task_sha=HEX_A),
            run(task="x", trial="two", task_sha=HEX_B),
        ]
        with self.assertRaisesRegex(hs.ContractError, "multiple task generations"):
            hs.compile_report(
                candidate,
                policy(),
                [run(task="x", trial="base", task_sha=HEX_A)],
            )

    def test_baseline_free_pareto_rejects_different_task_specs(self):
        candidate = [
            run(task="x", trial="one", task_sha=HEX_A),
            run(task="x", trial="two", task_sha=HEX_B),
        ]
        with self.assertRaisesRegex(hs.ContractError, "multiple task generations"):
            hs.compile_report(candidate, policy())

    def test_baseline_free_pareto_rejects_different_test_cardinality(self):
        candidate = [
            run(task="x", trial="one", total=10, passed=10, failed=0, task_sha=HEX_A),
            run(task="x", trial="two", total=20, passed=20, failed=0, task_sha=HEX_A),
        ]
        with self.assertRaisesRegex(hs.ContractError, "multiple task generations"):
            hs.compile_report(candidate, policy())


if __name__ == "__main__":
    unittest.main()
