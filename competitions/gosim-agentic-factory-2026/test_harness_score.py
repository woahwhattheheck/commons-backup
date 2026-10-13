from datetime import datetime, timedelta
import copy
from pathlib import Path
import tempfile
import unittest

import harness_score as hs

HEX_A = "a" * 64
HEX_B = "b" * 64
HEX_C = "c" * 64


def policy(**changes):
    raw = {
        "schema": hs.POLICY_SCHEMA,
        "correctness_floor_micros": 800000,
        "correctness_weight_micros": 800000,
        "token_weight_micros": 100000,
        "time_weight_micros": 100000,
        "token_reference": 1000,
        "time_reference_ms": 10000,
        "max_correctness_drop_micros": 0,
        "max_token_regression_bps": 500,
        "max_time_regression_bps": 500,
    }
    raw.update(changes)
    return raw


def _finish(started: str, wall: int) -> str:
    dt = datetime.fromisoformat(started[:-1] + "+00:00") + timedelta(milliseconds=wall)
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def run(
    task="github-clone",
    trial="t1",
    model="model-a",
    harness="h1",
    total=10,
    passed=10,
    failed=0,
    input_tokens=400,
    output_tokens=300,
    cache_tokens=100,
    wall=5000,
    started="2026-09-13T12:00:00.000Z",
    finished=None,
    task_sha=HEX_A,
    artifact_sha=HEX_B,
    trace_sha=HEX_C,
):
    if finished is None:
        finished = _finish(started, wall)
    return {
        "schema": hs.SCHEMA,
        "task_id": task,
        "trial_id": trial,
        "harness_revision": harness,
        "model_label": model,
        "started_at": started,
        "finished_at": finished,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_tokens": cache_tokens,
        "wall_clock_ms": wall,
        "tests_total": total,
        "tests_passed": passed,
        "tests_failed": failed,
        "task_spec_sha256": task_sha,
        "artifact_manifest_sha256": artifact_sha,
        "trace_sha256": trace_sha,
    }


class ContractTests(unittest.TestCase):
    def test_duplicate_keys_rejected(self):
        with self.assertRaisesRegex(hs.ContractError, "duplicate"):
            hs.load_json_bytes(b'{"a":1,"a":2}')

    def test_nonfinite_json_rejected(self):
        with self.assertRaises(hs.ContractError):
            hs.load_json_bytes(b'{"x":NaN}')

    def test_unknown_run_field_rejected(self):
        item = run()
        item["surprise"] = 1
        with self.assertRaisesRegex(hs.ContractError, "keys"):
            hs.validate_run(item)

    def test_bool_int_trap_rejected(self):
        item = run()
        item["input_tokens"] = True
        with self.assertRaisesRegex(hs.ContractError, "integer"):
            hs.validate_run(item)

    def test_negative_count_rejected(self):
        item = run()
        item["output_tokens"] = -1
        with self.assertRaisesRegex(hs.ContractError, "range"):
            hs.validate_run(item)

    def test_combined_token_overflow_rejected(self):
        item = hs.validate_run(run(input_tokens=hs.MAX_INT, output_tokens=1, cache_tokens=0))
        with self.assertRaisesRegex(hs.ContractError, "combined"):
            hs.metrics_for_run(item, hs.validate_policy(policy()))

    def test_test_total_mismatch_rejected(self):
        with self.assertRaisesRegex(hs.ContractError, "must equal"):
            hs.validate_run(run(total=10, passed=8, failed=1))

    def test_empty_test_suite_rejected(self):
        with self.assertRaisesRegex(hs.ContractError, "range"):
            hs.validate_run(run(total=0, passed=0, failed=0))

    def test_finished_before_started_rejected(self):
        with self.assertRaisesRegex(hs.ContractError, "precedes"):
            hs.validate_run(run(wall=1, finished="2026-09-13T11:59:59.999Z"))

    def test_noncanonical_utc_rejected(self):
        item = run()
        item["started_at"] = "2026-09-13T12:00:00Z"
        with self.assertRaisesRegex(hs.ContractError, "canonical"):
            hs.validate_run(item)

    def test_submillisecond_utc_rejected(self):
        item = run()
        item["started_at"] = "2026-09-13T12:00:00.000001Z"
        with self.assertRaisesRegex(hs.ContractError, "millisecond"):
            hs.validate_run(item)

    def test_wall_clock_must_bind_timestamps(self):
        item = run(wall=1)
        item["wall_clock_ms"] = 2
        with self.assertRaisesRegex(hs.ContractError, "wall_clock_ms"):
            hs.validate_run(item)

    def test_bad_digest_rejected(self):
        with self.assertRaisesRegex(hs.ContractError, "lowercase"):
            hs.validate_run(run(task_sha="A" * 64))

    def test_control_text_rejected(self):
        with self.assertRaisesRegex(hs.ContractError, "control"):
            hs.validate_run(run(model="hello\nworld"))

    def test_policy_unknown_field_rejected(self):
        p = policy()
        p["official_score"] = True
        with self.assertRaisesRegex(hs.ContractError, "policy keys"):
            hs.validate_policy(p)

    def test_policy_bool_trap_rejected(self):
        with self.assertRaisesRegex(hs.ContractError, "integer"):
            hs.validate_policy(policy(token_reference=True))

    def test_weights_must_sum_exactly(self):
        with self.assertRaisesRegex(hs.ContractError, "sum"):
            hs.validate_policy(policy(time_weight_micros=99999))

    def test_identity_reuse_changed_bytes_rejected(self):
        with self.assertRaisesRegex(hs.ContractError, "reused"):
            hs.compile_report([run(), run(input_tokens=401)], policy())

    def test_exact_duplicate_identity_rejected(self):
        a = run()
        with self.assertRaisesRegex(hs.ContractError, "duplicate trial"):
            hs.compile_report([a, copy.deepcopy(a)], policy())

    def test_cross_set_identity_reuse_changed_bytes_rejected(self):
        with self.assertRaisesRegex(hs.ContractError, "across candidate and baseline"):
            hs.compile_report([run(input_tokens=401)], policy(), [run(input_tokens=400)])


class ScoreTests(unittest.TestCase):
    def test_correctness_floor_disables_efficiency(self):
        report = hs.compile_report(
            [run(passed=7, failed=3, input_tokens=1, output_tokens=1, cache_tokens=0, wall=1)],
            policy(),
        )
        metrics = report["entries"][0]["metrics"]
        self.assertFalse(metrics["efficiency_enabled"])
        self.assertEqual(metrics["correctness_micros"], 700000)
        self.assertEqual(metrics["internal_readiness_micros"], 560000)

    def test_full_correctness_gets_efficiency(self):
        metrics = hs.compile_report([run()], policy())["entries"][0]["metrics"]
        self.assertTrue(metrics["efficiency_enabled"])
        self.assertEqual(metrics["correctness_micros"], hs.ONE)
        self.assertEqual(metrics["total_tokens"], 800)
        self.assertGreater(metrics["internal_readiness_micros"], 800000)

    def test_pareto_classification(self):
        runs = [
            run(trial="fast-cheap", input_tokens=200, output_tokens=200, cache_tokens=0, wall=2000),
            run(trial="slow-expensive", input_tokens=500, output_tokens=500, cache_tokens=0, wall=7000),
            run(trial="less-correct", passed=9, failed=1, input_tokens=50, output_tokens=50, cache_tokens=0, wall=1000),
        ]
        flags = {e["run"]["trial_id"]: e["pareto"] for e in hs.compile_report(runs, policy())["entries"]}
        self.assertTrue(flags["fast-cheap"])
        self.assertFalse(flags["slow-expensive"])
        self.assertTrue(flags["less-correct"])

    def test_deterministic_under_reordering(self):
        runs = [
            run(task="b", trial="2", model="m2"),
            run(task="a", trial="1", model="m1", passed=9, failed=1),
            run(task="a", trial="2", model="m1", input_tokens=200),
        ]
        a = hs.compile_report(runs, policy())
        b = hs.compile_report(list(reversed(runs)), policy())
        self.assertEqual(hs.canonical_bytes(a), hs.canonical_bytes(b))
        self.assertEqual(hs.render_markdown(a), hs.render_markdown(b))

    def test_configuration_median_and_worst(self):
        runs = [
            run(task="a", trial="1", input_tokens=100, output_tokens=0, cache_tokens=0, wall=1000),
            run(task="b", trial="2", input_tokens=300, output_tokens=0, cache_tokens=0, wall=3000, passed=8, failed=2),
            run(task="c", trial="3", input_tokens=200, output_tokens=0, cache_tokens=0, wall=2000, passed=9, failed=1),
        ]
        summary = hs.compile_report(runs, policy())["configuration_summaries"][0]
        self.assertEqual(summary["median_correctness_micros"], 900000)
        self.assertEqual(summary["worst_correctness_micros"], 800000)
        self.assertEqual(summary["median_total_tokens"], 200)
        self.assertEqual(summary["worst_total_tokens"], 300)
        self.assertEqual(summary["median_wall_clock_ms"], 2000)
        self.assertEqual(summary["worst_wall_clock_ms"], 3000)

    def test_configuration_identity_cannot_collide_on_separator_text(self):
        runs = [
            run(task="a", trial="1", harness="alpha::beta", model="gamma"),
            run(task="b", trial="2", harness="alpha", model="beta::gamma"),
        ]
        summaries = hs.compile_report(runs, policy())["configuration_summaries"]
        self.assertEqual(len(summaries), 2)
        self.assertEqual(
            {(row["harness_revision"], row["model_label"]) for row in summaries},
            {("alpha::beta", "gamma"), ("alpha", "beta::gamma")},
        )

    def test_markdown_disclaims_official_score(self):
        report = hs.compile_report([run()], policy())
        text = hs.render_markdown(report)
        self.assertIn("not an official GOSIM score", text)
        self.assertIn(report["receipt_sha256"], text)


class RegressionTests(unittest.TestCase):
    def test_correctness_regression_cannot_be_hidden_by_token_savings(self):
        baseline = [run(trial="b", input_tokens=1000, output_tokens=1000, passed=10, failed=0)]
        candidate = [run(trial="c", input_tokens=1, output_tokens=1, passed=9, failed=1)]
        report = hs.compile_report(candidate, policy(), baseline)
        self.assertFalse(report["regression_gate"]["passed"])
        self.assertEqual(report["regression_gate"]["failures"][0]["reason"], "CORRECTNESS_REGRESSION")

    def test_equal_correctness_token_regression(self):
        baseline = [run(trial="b", input_tokens=100, output_tokens=0, cache_tokens=0)]
        candidate = [run(trial="c", input_tokens=106, output_tokens=0, cache_tokens=0)]
        reasons = [x["reason"] for x in hs.compile_report(candidate, policy(max_token_regression_bps=500), baseline)["regression_gate"]["failures"]]
        self.assertIn("TOKEN_REGRESSION_AT_EQUAL_CORRECTNESS", reasons)

    def test_equal_correctness_time_regression(self):
        baseline = [run(trial="b", wall=1000)]
        candidate = [run(trial="c", wall=1060)]
        reasons = [x["reason"] for x in hs.compile_report(candidate, policy(max_time_regression_bps=500), baseline)["regression_gate"]["failures"]]
        self.assertIn("TIME_REGRESSION_AT_EQUAL_CORRECTNESS", reasons)

    def test_missing_baseline_task_fails(self):
        report = hs.compile_report([run(task="b", trial="c")], policy(), [run(task="a", trial="b")])
        self.assertEqual(report["regression_gate"]["failures"], [{"task_id": "a", "reason": "MISSING_CANDIDATE_TASK"}])

    def test_tolerance_can_allow_small_correctness_drop(self):
        baseline = [run(trial="b", total=100, passed=100, failed=0)]
        candidate = [run(trial="c", total=100, passed=99, failed=1)]
        self.assertTrue(hs.compile_report(candidate, policy(max_correctness_drop_micros=10000), baseline)["regression_gate"]["passed"])


class VerificationTests(unittest.TestCase):
    def test_receipt_and_report_tamper_detected(self):
        runs, p = [run()], policy()
        report = hs.compile_report(runs, p)
        self.assertTrue(hs.verify_report(runs, p, report))
        tampered = copy.deepcopy(report)
        tampered["entries"][0]["metrics"]["total_tokens"] += 1
        self.assertFalse(hs.verify_report(runs, p, tampered))

    def test_policy_tamper_detected(self):
        runs, p = [run()], policy()
        report = hs.compile_report(runs, p)
        self.assertFalse(hs.verify_report(runs, policy(token_reference=999), report))

    def test_baseline_tamper_detected(self):
        runs, base, p = [run(trial="c")], [run(trial="b")], policy()
        report = hs.compile_report(runs, p, base)
        self.assertFalse(hs.verify_report(runs, p, report, [run(trial="b", input_tokens=401)]))

    def test_compile_create_exclusive_outputs_and_verify(self):
        runs, p = [run()], policy()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "runs.json").write_bytes(hs.canonical_bytes(runs))
            (root / "policy.json").write_bytes(hs.canonical_bytes(p))
            code = hs.main([
                "compile", "--runs", str(root / "runs.json"), "--policy", str(root / "policy.json"),
                "--output-json", str(root / "report.json"), "--output-md", str(root / "report.md"),
            ])
            self.assertEqual(code, 0)
            self.assertEqual(hs.main([
                "verify", "--runs", str(root / "runs.json"), "--policy", str(root / "policy.json"),
                "--report", str(root / "report.json"),
            ]), 0)
            self.assertEqual(hs.main([
                "compile", "--runs", str(root / "runs.json"), "--policy", str(root / "policy.json"),
                "--output-json", str(root / "report.json"), "--output-md", str(root / "report2.md"),
            ]), 1)

    def test_compile_regression_failure_emits_no_outputs(self):
        baseline, candidate = [run(trial="b")], [run(trial="c", passed=8, failed=2)]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for name, value in (("runs.json", candidate), ("baseline.json", baseline), ("policy.json", policy())):
                (root / name).write_bytes(hs.canonical_bytes(value))
            code = hs.main([
                "compile", "--runs", str(root / "runs.json"), "--baseline", str(root / "baseline.json"),
                "--policy", str(root / "policy.json"), "--output-json", str(root / "report.json"),
                "--output-md", str(root / "report.md"),
            ])
            self.assertEqual(code, 2)
            self.assertFalse((root / "report.json").exists())
            self.assertFalse((root / "report.md").exists())


if __name__ == "__main__":
    unittest.main()
