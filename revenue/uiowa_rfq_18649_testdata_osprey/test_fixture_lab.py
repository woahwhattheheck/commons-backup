"""Regression tests for the offline fixture lab, not target applications."""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from fixture_lab import (BOUNDARY, CatalogError, assess_catalog, build_bundle, canonical,
                         digest, generate_cases, load_json, render_review,
                         validate_catalog, verify_bundle, write_bundle)
from make_example import example

HERE = Path(__file__).resolve().parent
CUT = date(2026, 9, 19)


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = example()

    def change(self, key, value):
        self.catalog["fixtures"][0][key] = value
        return self.catalog

    def test_unpaired_surrogate_is_a_controlled_catalog_error(self):
        self.catalog["fixtures"][0]["purpose"] = "\ud800"
        with self.assertRaises(CatalogError):
            validate_catalog(self.catalog)

    def test_excessive_json_nesting_is_a_controlled_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested.json"
            path.write_text("[" * 2500 + "0" + "]" * 2500)
            with self.assertRaises(CatalogError): load_json(path)

    def test_json_depth_boundary_is_deterministic(self):
        from fixture_lab import MAX_JSON_DEPTH
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested.json"
            path.write_text("[" * MAX_JSON_DEPTH + "0" + "]" * MAX_JSON_DEPTH)
            self.assertIsInstance(load_json(path), list)
            path.write_text("[" * (MAX_JSON_DEPTH+1) + "0" + "]" * (MAX_JSON_DEPTH+1))
            with self.assertRaises(CatalogError): load_json(path)

    def test_canonical_catalog_size_limit(self):
        from unittest.mock import patch
        with patch("fixture_lab.MAX_BYTES", 32):
            with self.assertRaises(CatalogError): validate_catalog(self.catalog)

    def test_valid_catalog(self):
        self.assertIs(validate_catalog(self.catalog), self.catalog)

    def test_empty_catalog_is_unassessed_not_passed(self):
        self.catalog["fixtures"] = []
        report = assess_catalog(self.catalog, CUT)
        self.assertEqual(report["summary"]["assessment_state"], "NOT_ASSESSED")

    def test_synthetic_must_be_literal_true(self):
        for value in [1, "true", False, None]:
            with self.subTest(value=value):
                self.catalog["synthetic"] = value
                with self.assertRaises(CatalogError):
                    validate_catalog(self.catalog)

    def test_duplicate_id(self):
        self.catalog["fixtures"].append(copy.deepcopy(self.catalog["fixtures"][0]))
        with self.assertRaises(CatalogError):
            validate_catalog(self.catalog)

    def test_unknown_field_is_not_silently_ignored(self):
        with self.assertRaises(CatalogError):
            validate_catalog(self.change("last_refresh", "2026-09-10"))

    def test_missing_field(self):
        del self.catalog["fixtures"][0]["parameters"]
        with self.assertRaises(CatalogError):
            validate_catalog(self.catalog)

    def test_stable_identifier_validation(self):
        for bad in ["../escape", "a/b", "", " space", "A"*81, 1, "a\\b"]:
            with self.subTest(bad=bad), self.assertRaises(CatalogError):
                validate_catalog(self.change("id", bad))

    def test_invalid_group_and_generator_types(self):
        for field in ("group", "generator"):
            for bad in ([], {}, True, "invalid"):
                with self.subTest(field=field, bad=bad):
                    cat = example(); cat["fixtures"][0][field] = bad
                    with self.assertRaises(CatalogError):
                        validate_catalog(cat)

    def test_interval_and_cleanup_reject_bool_negative_fraction(self):
        for field in ("review_interval_days", "cleanup_after_days"):
            for bad in (True, -1, 0.5, "14", 36501):
                cat = example(); cat["fixtures"][0][field] = bad
                with self.subTest(field=field, bad=bad), self.assertRaises(CatalogError):
                    validate_catalog(cat)

    def test_invalid_date_formats(self):
        for bad in ("2026-02-30", "20260910", "2026-9-10", "2026-09-10T00:00:00Z"):
            with self.subTest(bad=bad), self.assertRaises(CatalogError):
                validate_catalog(self.change("last_refreshed", bad))

    def test_null_date_and_owner_allowed_as_unknown(self):
        self.change("last_refreshed", None); self.change("owner_role", None)
        validate_catalog(self.catalog)

    def test_refresh_cannot_follow_retirement(self):
        with self.assertRaises(CatalogError):
            validate_catalog(self.change("retired_on", "2026-09-01"))

    def test_empty_or_duplicate_boundary_list(self):
        for bad in ([], ["before", "before"], ["nonexistent"], [["before"]]):
            with self.subTest(bad=bad), self.assertRaises(CatalogError):
                validate_catalog(self.change("required_boundaries", bad))

    def test_effort_is_an_ordered_nonnegative_integer_range(self):
        for bad in ({"low": 6, "high": 5}, {"low": True, "high": 5}, {"low": -1, "high": 5}, {"low": 2}):
            with self.subTest(bad=bad), self.assertRaises(CatalogError):
                validate_catalog(self.change("maintenance_hours", bad))

    def test_timezone_required(self):
        self.catalog["fixtures"][0]["parameters"]["start"] = "2026-01-01T00:00:00"
        with self.assertRaises(CatalogError):
            validate_catalog(self.catalog)

    def test_invalid_or_reversed_interval(self):
        for start, end in [("bad", "2026-01-01T00:00:00Z"),
                           ("2026-10-02T00:00:00Z", "2026-10-01T00:00:00Z"),
                           ("2026-10-01T00:00:00Z", "2026-10-01T00:00:00Z")]:
            self.catalog["fixtures"][0]["parameters"] = {"start": start, "end": end}
            with self.subTest(start=start), self.assertRaises(CatalogError):
                validate_catalog(self.catalog)

    def test_one_microsecond_window_cannot_claim_interior_coverage(self):
        self.change("parameters", {"start": "2026-01-01T00:00:00.000000Z", "end": "2026-01-01T00:00:00.000001Z"})
        with self.assertRaises(CatalogError): validate_catalog(self.catalog)
        self.change("required_boundaries", ["at_start", "at_end"])
        validate_catalog(self.catalog)

    def test_extreme_timestamp_requires_only_representable_boundaries(self):
        self.change("parameters", {"start": "0001-01-01T00:00:00+00:00", "end": "0001-01-02T00:00:00+00:00"})
        with self.assertRaises(CatalogError): validate_catalog(self.catalog)
        self.change("required_boundaries", ["at_start", "at_end"])
        validate_catalog(self.catalog)
        self.assertEqual(len(generate_cases(self.catalog["fixtures"][0])), 2)

    def test_unrepresentable_timezone_shift_is_controlled_error(self):
        self.change("parameters", {"start": "0001-01-01T00:00:00+01:00", "end": "0001-01-02T00:00:00Z"})
        with self.assertRaises(CatalogError): validate_catalog(self.catalog)

    def test_directory_input_is_controlled_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(CatalogError): load_json(Path(tmp))

    def test_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.json"; path.write_text('{"a":1,"a":2}')
            with self.assertRaises(CatalogError): load_json(path)

    def test_nonfinite_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.json"; path.write_text('{"a":NaN}')
            with self.assertRaises(CatalogError): load_json(path)

    def test_invalid_encoding_and_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.json"
            for raw in [b'\xff', b'{']:
                path.write_bytes(raw)
                with self.assertRaises(CatalogError): load_json(path)


class AssessmentTests(unittest.TestCase):
    def setUp(self): self.catalog = example()

    def codes(self, fixture):
        return {f["code"] for f in assess_catalog(self.catalog, CUT)["findings"] if f["fixture_id"] == fixture}

    def test_expected_followups(self):
        self.assertEqual(self.codes("ESS-TERM"), set())
        self.assertTrue({"OWNER_UNKNOWN", "INTERFACE_REVIEW_REQUIRED", "REVIEW_OVERDUE", "REFRESH_EVIDENCE_UNKNOWN", "BOUNDARY_PLAN_PARTIAL"} <= self.codes("ESS-LEGACY"))

    def test_unknown_target_is_not_mismatch(self):
        self.assertEqual(self.codes("RIS-FUNDING"), {"TARGET_VERSION_UNKNOWN"})

    def test_missing_refresh_is_not_overdue(self):
        codes = self.codes("IAM-UNKNOWN")
        self.assertIn("REFRESH_DATE_UNKNOWN", codes)
        self.assertNotIn("REVIEW_OVERDUE", codes)

    def test_retired_does_not_have_active_refresh_overdue(self):
        codes = self.codes("RIS-RETIRED")
        self.assertIn("CLEANUP_UNVERIFIED", codes)
        self.assertNotIn("REVIEW_OVERDUE", codes)

    def test_cleanup_reference_is_only_supplied_metadata(self):
        self.catalog["fixtures"][3]["cleanup_evidence"] = "FICTIONAL-CLEANUP-001"
        self.assertNotIn("CLEANUP_UNVERIFIED", self.codes("RIS-RETIRED"))
        self.assertIn("supplied pointer, not a verified artifact", render_review(assess_catalog(self.catalog, CUT)))

    def test_review_due_exact_boundary_is_not_overdue(self):
        self.catalog["fixtures"][0]["last_refreshed"] = "2026-09-05"
        self.assertNotIn("REVIEW_OVERDUE", self.codes("ESS-TERM"))
        self.catalog["fixtures"][0]["last_refreshed"] = "2026-09-04"
        self.assertIn("REVIEW_OVERDUE", self.codes("ESS-TERM"))

    def test_future_refresh_is_not_fresh(self):
        self.catalog["fixtures"][0]["last_refreshed"] = "2026-09-20"
        self.assertIn("FUTURE_REFRESH_RECORD", self.codes("ESS-TERM"))

    def test_future_retirement_remains_active(self):
        self.catalog["fixtures"][0]["retired_on"] = "2026-09-20"
        row = next(r for r in assess_catalog(self.catalog, CUT)["fixtures"] if r["id"] == "ESS-TERM")
        self.assertEqual(row["lifecycle"], "active")

    def test_cleanup_on_active_fixture_is_inconsistent(self):
        self.catalog["fixtures"][0]["cleanup_evidence"] = "FICTIONAL-CLEANUP"
        self.assertIn("CLEANUP_RECORD_WITHOUT_EFFECTIVE_RETIREMENT", self.codes("ESS-TERM"))

    def test_application_coverage_is_never_inferred(self):
        report = assess_catalog(self.catalog, CUT)
        self.assertTrue(all(r["executed_application_cases"] is None for r in report["fixtures"]))
        self.assertEqual(report["summary"]["assessment_state"], "REVIEW_INPUT_ONLY")

    def test_markdown_escapes_active_markup(self):
        report = assess_catalog(self.catalog, CUT)
        report["findings"][0]["follow_up"] = '<script>x</script>|\nline'
        rendered = render_review(report)
        self.assertNotIn('<script>', rendered)
        self.assertIn('&lt;script&gt;x&lt;/script&gt;\\| line', rendered)


class FixtureTests(unittest.TestCase):
    def test_temporal_boundary_oracles_for_every_generator(self):
        for item in example()["fixtures"]:
            item["required_boundaries"] = list(BOUNDARY)
            cases = generate_cases(item)
            self.assertEqual([c["boundary"] for c in cases], list(BOUNDARY))
            field = {"term_window": "term_active", "funding_window": "funding_period_active", "role_transition": "effective_roles"}[item["generator"]]
            self.assertEqual([bool(c["reference_expectation"][field]) for c in cases], [False, True, True, False, False])

    def test_partial_coverage_generates_only_requested_boundaries(self):
        self.assertEqual(len(generate_cases(example()["fixtures"][1])), 3)

    def test_no_application_observations_are_fabricated(self):
        for item in example()["fixtures"]:
            for case in generate_cases(item):
                self.assertIsNone(case["application_observation"])
                self.assertIs(case["synthetic"], True)

    def test_case_ids_unique_across_groups(self):
        ids = [c["case_id"] for i in example()["fixtures"] for c in generate_cases(i)]
        self.assertEqual(len(ids), len(set(ids)))

    def test_offsets_represent_equal_instants(self):
        item = example()["fixtures"][0]
        one = generate_cases(item)
        item["parameters"] = {"start": "2026-10-01T05:00:00Z", "end": "2026-10-02T05:00:00Z"}
        self.assertEqual(one, generate_cases(item))

    def test_randomized_windows_preserve_half_open_contract(self):
        import random
        from datetime import datetime, timedelta, timezone
        rng = random.Random(0x86C1)
        for _ in range(250):
            item = copy.deepcopy(example()["fixtures"][0])
            start = datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=rng.randint(0, 10000000))
            end = start + timedelta(microseconds=rng.randint(2, 86400000000))
            item["parameters"] = {"start": start.isoformat(), "end": end.isoformat()}
            cases = generate_cases(item)
            self.assertEqual([c["reference_expectation"]["term_active"] for c in cases], [False, True, True, False, False])
            inside = datetime.fromisoformat(cases[2]["inputs"]["at"])
            self.assertLess(start, inside); self.assertLess(inside, end)

    def test_expired_role_removal_is_explicit(self):
        cases = generate_cases(example()["fixtures"][4])
        self.assertTrue(cases[3]["reference_expectation"]["stale_previous_role_must_not_persist"])
        self.assertEqual(cases[3]["reference_expectation"]["effective_roles"], [])


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "bundle"
        self.catalog = example()
        self.files = build_bundle(self.catalog, CUT)
        write_bundle(self.files, self.root)

    def test_bundle_verifies_and_reports_boundary(self):
        report = verify_bundle(self.root)
        self.assertEqual(report["state"], "REPRODUCIBLE_SYNTHETIC_BUNDLE")
        self.assertEqual(report["files"], 9)
        self.assertIn("not executed", report["notice"])

    def test_repeat_generation_byte_identical(self):
        self.assertEqual(self.files, build_bundle(self.catalog, CUT))

    def test_catalog_item_order_does_not_change_bundle(self):
        self.catalog["fixtures"].reverse()
        self.assertEqual(self.files, build_bundle(self.catalog, CUT))

    def test_existing_destination_not_overwritten(self):
        with self.assertRaises(CatalogError): write_bundle(self.files, self.root)
        self.assertEqual((self.root / "manifest.json").read_bytes(), self.files["manifest.json"])

    def test_modified_fixture_detected(self):
        path = self.root / "fixtures/ESS-TERM.json"
        path.write_bytes(path.read_bytes().replace(b'"term_active": true', b'"term_active": null', 1))
        with self.assertRaises(CatalogError): verify_bundle(self.root)

    def test_rehashed_altered_expectation_still_rejected(self):
        path = self.root / "fixtures/ESS-TERM.json"
        data = load_json(path); data["cases"][0]["reference_expectation"]["term_active"] = True
        payload = canonical(data); path.write_bytes(payload)
        manifest_path = self.root / "manifest.json"; manifest = load_json(manifest_path)
        for record in manifest["files"]:
            if record["path"] == "fixtures/ESS-TERM.json":
                record["bytes"] = len(payload); record["sha256"] = digest(payload)
        manifest_path.write_bytes(canonical(manifest))
        with self.assertRaisesRegex(CatalogError, "reproducible"):
            verify_bundle(self.root)

    def test_missing_member(self):
        (self.root / "review.json").unlink()
        with self.assertRaises(CatalogError): verify_bundle(self.root)

    def test_unlisted_extra_member(self):
        (self.root / "unexpected.txt").write_text("extra")
        with self.assertRaises(CatalogError): verify_bundle(self.root)

    def test_empty_manifest_members_cannot_bypass_regeneration(self):
        path = self.root / "manifest.json"; manifest = load_json(path); manifest["files"] = []
        path.write_bytes(canonical(manifest))
        with self.assertRaises(CatalogError): verify_bundle(self.root)

    def test_path_traversal_and_noncanonical_path_rejected(self):
        path = self.root / "manifest.json"; original = load_json(path)
        for bad in ("../outside", "/tmp/outside", "fixtures/../review.json", "./review.json", "fixtures\\outside"):
            manifest = copy.deepcopy(original); manifest["files"][0]["path"] = bad
            path.write_bytes(canonical(manifest))
            with self.subTest(bad=bad), self.assertRaises(CatalogError): verify_bundle(self.root)

    def test_symlink_fixture_rejected(self):
        target = self.root / "fixtures/ESS-TERM.json"; outside = self.root.parent / "copy.json"
        outside.write_bytes(target.read_bytes()); target.unlink(); target.symlink_to(outside)
        with self.assertRaises(CatalogError): verify_bundle(self.root)

    def test_symlink_manifest_rejected(self):
        target = self.root / "manifest.json"; outside = self.root.parent / "manifest-copy.json"
        outside.write_bytes(target.read_bytes()); target.unlink(); target.symlink_to(outside)
        with self.assertRaises(CatalogError): verify_bundle(self.root)

    def test_duplicate_manifest_path_rejected(self):
        path = self.root / "manifest.json"; manifest = load_json(path)
        manifest["files"].append(copy.deepcopy(manifest["files"][0])); path.write_bytes(canonical(manifest))
        with self.assertRaises(CatalogError): verify_bundle(self.root)

    def test_wrong_generator_version_rejected(self):
        path = self.root / "manifest.json"; manifest = load_json(path); manifest["generator_version"] = "9.9.9"
        path.write_bytes(canonical(manifest))
        with self.assertRaises(CatalogError): verify_bundle(self.root)

    def test_unknown_manifest_field_rejected(self):
        path = self.root / "manifest.json"; manifest = load_json(path); manifest["approved"] = True
        path.write_bytes(canonical(manifest))
        with self.assertRaises(CatalogError): verify_bundle(self.root)


class CLITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "catalog.json"; self.path.write_bytes(canonical(example()))

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(HERE / "fixture_lab.py"), *map(str, args)],
                              capture_output=True, text=True, timeout=15)

    def test_cli_unpaired_surrogate_has_no_traceback(self):
        cat = example(); cat["fixtures"][0]["purpose"] = "\ud800"
        self.path.write_text(json.dumps(cat))
        result = self.run_cli("validate", self.path)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)

    def test_cli_validate(self):
        result = self.run_cli("validate", self.path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["fixtures"], 6)

    def test_cli_markdown(self):
        result = self.run_cli("assess", self.path, "--as-of", "2026-09-19", "--format", "markdown")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OWNER_UNKNOWN", result.stdout)

    def test_cli_complete_bundle_flow(self):
        out = self.path.parent / "generated"
        made = self.run_cli("generate", self.path, "--as-of", "2026-09-19", "--out", out)
        checked = self.run_cli("verify-bundle", out)
        self.assertEqual(made.returncode, 0, made.stderr)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertEqual(made.stdout, checked.stdout)

    def test_cli_invalid_date_is_structured_error(self):
        result = self.run_cli("assess", self.path, "--as-of", "2026-02-31")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)

    def test_cli_missing_input_is_structured_error(self):
        result = self.run_cli("validate", self.path.parent / "missing")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)

    def test_cli_requires_cutoff(self):
        result = self.run_cli("assess", self.path)
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__": unittest.main()
