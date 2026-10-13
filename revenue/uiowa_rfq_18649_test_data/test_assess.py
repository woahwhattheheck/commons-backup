"""Offline regression, temporal-boundary, malformed-input and CLI tests."""
from copy import deepcopy
from contextlib import redirect_stdout, redirect_stderr
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


assessor = load("uiowa047_assessor", ROOT / "assess.py")
example = load("uiowa047_example", ROOT / "example.py")


class AssessmentTests(unittest.TestCase):
    def setUp(self):
        self.data = example.minimal_catalog()
        self.f = self.data["fixtures"][0]
        self.case = self.f["cases"][0]

    def report(self, clock=example.AS_OF):
        return assessor.assess(self.data, clock)

    def codes(self):
        return {n["code"] for n in self.report()["limitations"]}

    def support(self):
        return self.report()["summary"]["cases_with_supported_evidence"]

    def test_complete_evidence(self):
        self.assertEqual(self.support(), 1)
        self.assertEqual(self.codes(), set())

    def test_recipe_alone_is_not_demonstration(self):
        self.f["refreshes"] = []
        self.assertEqual(self.support(), 0)
        self.assertIn("REFRESH_NOT_DEMONSTRATED", self.codes())

    def test_null_refresh_receipt(self):
        self.f["refreshes"][0]["evidence_ref"] = None
        self.assertEqual(self.support(), 0)

    def test_version_alignment(self):
        self.f["contract_version"] = "v2"
        self.assertEqual(self.support(), 0)
        self.assertIn("VERSION_ALIGNMENT", self.codes())

    def test_unknown_fixture_version(self):
        self.f["fixture_version"] = None
        self.assertEqual(self.support(), 0)

    def test_old_fixture_run(self):
        self.case["runs"][0]["fixture_version"] = "fixture-0"
        self.assertEqual(self.support(), 0)

    def test_old_contract_run(self):
        self.case["runs"][0]["contract_version"] = "v2"
        self.assertEqual(self.support(), 0)

    def test_failed_run_supersedes_pass(self):
        self.case["runs"].append(example.event("2026-09-18T13:00:00Z", "failed"))
        self.assertEqual(self.support(), 0)
        self.assertIn("CASE_FAILURE_RECORDED", self.codes())

    def test_failed_refresh_supersedes_success(self):
        self.f["refreshes"].append(example.event("2026-09-18T13:00:00Z", "failed"))
        self.assertEqual(self.support(), 0)

    def test_unbacked_latest_run_does_not_resurrect_earlier_pass(self):
        self.case["runs"].append(example.event("2026-09-18T13:00:00Z", evidence_ref=None))
        self.assertEqual(self.support(), 0)

    def test_future_failure_excluded(self):
        self.case["runs"].append(example.event("2026-09-20T13:00:00Z", "failed"))
        self.assertEqual(self.support(), 1)

    def test_event_at_cutoff_included(self):
        self.case["runs"].append(example.event(example.AS_OF, "failed"))
        self.assertEqual(self.support(), 0)

    def test_freshness_boundary(self):
        self.f["refresh_interval_days"] = 2
        self.assertEqual(self.support(), 1)
        report = self.report("2026-09-19T12:00:01Z")
        self.assertEqual(report["summary"]["cases_with_supported_evidence"], 0)
        self.assertIn("REFRESH_OVERDUE", {n["code"] for n in report["limitations"]})

    def test_refresh_cadence_unknown(self):
        self.f["refresh_interval_days"] = None
        self.assertEqual(self.support(), 0)

    def test_pre_refresh_run_not_reused(self):
        self.f["refreshes"].append(example.event("2026-09-18T13:00:00Z"))
        self.assertEqual(self.support(), 0)

    def test_equal_refresh_and_run_time_does_not_prove_order(self):
        self.case["runs"][0]["at"] = self.f["refreshes"][0]["at"]
        self.assertEqual(self.support(), 0)

    def test_unknown_owner_and_effort_not_a_coverage_score(self):
        self.f.update(owner=None, maintenance_hours=None)
        self.assertEqual(self.support(), 1)
        self.assertTrue({"OWNER_UNKNOWN", "EFFORT_UNKNOWN"} <= self.codes())

    def test_missing_specification(self):
        self.data["contracts"][0]["required_cases"].append("unicode-student-key")
        self.assertEqual(self.report()["summary"]["cases_without_specification"], 1)

    def test_no_fixtures_preserves_denominator(self):
        self.data["fixtures"] = []
        self.assertEqual(self.report()["summary"]["required_cases"], 1)
        self.assertEqual(self.report()["summary"]["cases_without_specification"], 1)

    def test_retired_fixture_not_current_coverage(self):
        self.f["state"] = "retired"
        self.assertEqual(self.support(), 0)
        self.assertIn("RETIRED_FIXTURE", self.codes())

    def test_active_after_cleanup(self):
        self.f["cleanups"] = [{"at": "2026-09-18T13:00:00Z", "outcome": "succeeded", "evidence_ref": "SYN-CLEAN"}]
        self.assertEqual(self.support(), 0)
        self.assertIn("ACTIVE_AFTER_CLEANUP", self.codes())

    def test_recreation_after_cleanup(self):
        self.f["cleanups"] = [{"at": "2026-09-16T13:00:00Z", "outcome": "succeeded", "evidence_ref": "SYN-CLEAN"}]
        self.assertEqual(self.support(), 1)
        self.assertNotIn("ACTIVE_AFTER_CLEANUP", self.codes())

    def test_old_cleanup_does_not_clear_recreated_fixture_due_date(self):
        self.f["cleanups"] = [{"at": "2026-09-16T13:00:00Z", "outcome": "succeeded", "evidence_ref": "SYN-CLEAN"}]
        self.f["cleanup_due_at"] = "2026-09-18T13:00:00Z"
        self.assertIn("CLEANUP_NOT_DEMONSTRATED", self.codes())

    def test_failed_cleanup_does_not_count_as_completed(self):
        self.f["cleanups"] = [{"at": "2026-09-18T13:00:00Z", "outcome": "failed", "evidence_ref": "SYN-CLEAN-FAIL"}]
        self.f["cleanup_due_at"] = "2026-09-18T12:00:00Z"
        self.assertIn("CLEANUP_NOT_DEMONSTRATED", self.codes())

    def test_cleanup_exact_due_time_not_overdue(self):
        self.f["cleanup_due_at"] = example.AS_OF
        self.assertNotIn("CLEANUP_NOT_DEMONSTRATED", self.codes())

    def test_timezone_offsets_compare_as_instants(self):
        self.case["runs"][0]["at"] = "2026-09-18T08:00:00-04:00"
        self.assertEqual(self.support(), 1)
        self.assertEqual(self.report("2026-09-19T08:00:00-04:00")["summary"], self.report()["summary"])

    def test_parallel_pass_does_not_hide_other_fixture_failure(self):
        second = deepcopy(self.f)
        second["id"] = "SYN-ESS-02"
        second["cases"][0]["runs"][0]["outcome"] = "failed"
        self.data["fixtures"].append(second)
        row = self.report()["coverage"][0]
        self.assertEqual(row["supported_by"], ["SYN-ESS-01"])
        self.assertEqual(row["failure_recorded_by"], ["SYN-ESS-02"])

    def test_assessment_is_pure(self):
        before = deepcopy(self.data)
        self.report()
        self.assertEqual(before, self.data)

    def test_event_order_independent(self):
        self.case["runs"].append(example.event("2026-09-18T13:00:00Z", "failed"))
        before = self.report()
        self.case["runs"].reverse()
        after = self.report()
        for key in ("summary", "coverage", "fixtures", "limitations"):
            self.assertEqual(before[key], after[key])

    def test_missing_origin_requires_metadata_context(self):
        self.data["context"] = "assessment-metadata"
        self.f["origin"] = "unknown"
        self.assertIn("ORIGIN_REVIEW", self.codes())

    def test_markdown_escapes_untrusted_fields(self):
        self.f["owner"] = '<script>|\n[open](file:///nope)'
        self.f["maintenance_hours"] = None
        rendered = assessor.markdown(self.report())
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("[open]", rendered)
        self.assertIn("&#124;", rendered)

    def test_example_expected_results(self):
        report = assessor.assess(example.catalog(), example.AS_OF)
        self.assertEqual(report["summary"]["fixtures"], 4)
        self.assertEqual(report["summary"]["required_cases"], 8)
        self.assertEqual(report["summary"]["cases_with_supported_evidence"], 3)
        self.assertEqual(report["summary"]["cases_without_specification"], 1)
        self.assertEqual(report["summary"]["cases_with_recorded_failure"], 1)
        self.assertEqual({c["group"] for c in report["coverage"]}, {"ESS", "RIS", "IAM"})

    def test_validation_bad_scalars(self):
        for field, values in {"maintenance_hours": [True, -1, float("nan"), float("inf"), "2"],
                              "refresh_interval_days": [True, 0, -1, 2.5, "7"],
                              "state": [None, [], "deleted"], "origin": [[], None, "real"],
                              "owner": [[], {}, ""], "cases": [None, {}]}.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    data = example.minimal_catalog()
                    data["fixtures"][0][field] = value
                    with self.assertRaises(assessor.InputError):
                        assessor.assess(data, example.AS_OF)

    def test_validation_temporal_and_references(self):
        mutations = [lambda d: d["fixtures"][0].update(created_at="2026-09-02"),
                     lambda d: d["fixtures"][0].update(created_at="2026-09-02T08:00:00"),
                     lambda d: d["fixtures"][0].update(contract_id="missing"),
                     lambda d: d["fixtures"][0].update(cleanup_due_at="2025-01-01T00:00:00Z"),
                     lambda d: d["fixtures"][0]["refreshes"][0].update(at="2025-01-01T00:00:00Z"),
                     lambda d: d["fixtures"][0]["cases"][0].update(id="not-required"),
                     lambda d: d["fixtures"].append(deepcopy(d["fixtures"][0])),
                     lambda d: d["contracts"].append(deepcopy(d["contracts"][0])),
                     lambda d: d["fixtures"][0]["cases"].append(deepcopy(d["fixtures"][0]["cases"][0])),
                     lambda d: d["fixtures"][0]["refreshes"].append(deepcopy(d["fixtures"][0]["refreshes"][0])),
                     lambda d: d["contracts"][0]["required_cases"].append("late-withdrawal"),
                     lambda d: d.update(schema_version=True), lambda d: d.update(extra="typo"),
                     lambda d: d["fixtures"][0].update(origin="production-derived")]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                data = example.minimal_catalog()
                mutate(data)
                with self.assertRaises(assessor.InputError):
                    assessor.assess(data, example.AS_OF)

    def test_duplicate_json_keys(self):
        with self.assertRaises(assessor.InputError):
            json.loads('{"x":1,"x":2}', object_pairs_hook=assessor._object)

    def test_timezone_equivalent_duplicate_events_rejected(self):
        self.f["refreshes"].append(example.event("2026-09-17T08:00:00-04:00"))
        with self.assertRaises(assessor.InputError):
            self.report()

    def test_future_events_are_counted(self):
        self.case["runs"].append(example.event("2026-09-20T13:00:00Z", "failed"))
        self.assertEqual(self.report()["fixtures"][0]["excluded_future_events"], 1)

    def test_current_row_state_is_not_inferred_from_future_creation(self):
        self.f.update(created_at="2026-09-20T12:00:00Z", refreshes=[])
        self.case["runs"] = []
        self.assertEqual(self.support(), 0)
        self.assertIn("NOT_YET_CREATED", self.codes())

    def test_large_integer_effort_does_not_crash(self):
        self.f["maintenance_hours"] = 10 ** 400
        self.assertEqual(self.support(), 1)

    def test_cli_valid_and_error_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "catalog.json", Path(directory) / "report.json"
            source.write_text(json.dumps(self.data), encoding="utf-8")
            self.assertEqual(assessor.main([str(source), "--as-of", example.AS_OF, "--output", str(output)]), 0)
            self.assertEqual(json.loads(output.read_text())["summary"]["fixtures"], 1)
            with redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(assessor.main([str(source), "--as-of", example.AS_OF, "--format", "markdown"]), 0)
            self.assertIn("Test-data readiness evidence", stdout.getvalue())
            with redirect_stderr(io.StringIO()):
                self.assertEqual(assessor.main([str(source), "--as-of", example.AS_OF, "--output", str(source)]), 2)
                source.write_text("{broken", encoding="utf-8")
                self.assertEqual(assessor.main([str(source), "--as-of", example.AS_OF]), 2)
                self.assertEqual(assessor.main([str(source) + "-missing", "--as-of", example.AS_OF]), 2)


if __name__ == "__main__":
    unittest.main()
