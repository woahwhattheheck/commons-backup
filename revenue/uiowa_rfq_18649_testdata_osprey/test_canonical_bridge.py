"""Exercise the actual sibling assessor; no mock is accepted as integration proof."""
from __future__ import annotations

import copy
from datetime import date
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import canonical_bridge as bridge
from fixture_lab import CatalogError, build_bundle, canonical, digest, load_json, write_bundle
from make_example import example

HERE = Path(__file__).resolve().parent
CREATED = "2026-09-19T11:00:00Z"
CUTOFF = "2026-09-19T12:00:00Z"


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "bundle"
        self.catalog = example()
        self.bundle(self.catalog)

    def bundle(self, catalog):
        # Each test uses a fresh directory; the original fixture tree is untouched.
        if self.root.exists():
            self.root = self.root.with_name(self.root.name + "-next")
        write_bundle(build_bundle(catalog, date(2026, 9, 19)), self.root)

    def test_real_assessor_does_not_promote_specifications(self):
        outputs = bridge.run_bridge(self.root, CREATED, CUTOFF)
        report = json.loads(outputs["canonical_report.json"])
        self.assertEqual(report["summary"]["required_cases"], 23)
        self.assertEqual(report["summary"]["cases_with_supported_evidence"], 0)
        self.assertEqual(report["summary"]["cases_with_recorded_failure"], 0)
        self.assertTrue(all(c["status"] == "unknown" for f in report["fixtures"] for c in f["cases"]))
        self.assertEqual(report["summary"]["limitations_by_code"]["RETIRED_FIXTURE"], 1)
        self.assertEqual(report["summary"]["limitations_by_code"]["VERSION_ALIGNMENT"], 1)

    def test_case_conservation_and_unknown_contract(self):
        output = bridge.prepare(self.root, CREATED, CUTOFF)
        summary = output["summary"]
        self.assertEqual(summary["planned_cases"], 28)
        self.assertEqual(summary["mapped_cases"] + summary["unmapped_cases"], 28)
        unmapped = [r for r in output["lineage"] if r["canonical_contract_id"] is None]
        self.assertEqual([r["source_id"] for r in unmapped], ["RIS-FUNDING"])
        self.assertEqual(len(unmapped[0]["cases"]), 5)
        self.assertEqual(unmapped[0]["source_definition"]["target_interface_version"], None)

    def test_original_definitions_retained_without_field_loss(self):
        output = bridge.prepare(self.root, CREATED, CUTOFF)
        got = {r["source_id"]: r["source_definition"] for r in output["lineage"]}
        self.assertEqual(got, {r["id"]: r for r in self.catalog["fixtures"]})

    def test_all_source_pointers_bind_exact_member_bytes(self):
        output = bridge.prepare(self.root, CREATED, CUTOFF)
        for row in output["lineage"]:
            raw = (self.root / row["source_pointer"]).read_bytes()
            self.assertEqual(digest(raw), row["source_member_sha256"])
            self.assertEqual(json.loads(raw)["cases"], row["cases"])

    def test_supplied_refresh_pointer_never_creates_an_event(self):
        cat = bridge.prepare(self.root, CREATED, CUTOFF)["canonical_catalog"]
        self.assertTrue(all(not f["refreshes"] and not f["cleanups"] for f in cat["fixtures"]))
        self.assertTrue(all(not c["runs"] for f in cat["fixtures"] for c in f["cases"]))
        self.assertTrue(all(f["created_at"] == "2026-09-19T11:00:00+00:00" for f in cat["fixtures"]))

    def test_review_interval_is_not_refresh_cadence(self):
        cat = bridge.prepare(self.root, CREATED, CUTOFF)["canonical_catalog"]
        self.assertTrue(all(f["refresh_interval_days"] is None for f in cat["fixtures"]))

    def test_zero_review_interval_stays_zero_in_lineage(self):
        self.catalog["fixtures"][0]["review_interval_days"] = 0
        self.bundle(self.catalog)
        output = bridge.prepare(self.root, CREATED, CUTOFF)
        row = next(r for r in output["lineage"] if r["source_id"] == "ESS-TERM")
        self.assertEqual(row["source_definition"]["review_interval_days"], 0)
        f = next(f for f in output["canonical_catalog"]["fixtures"] if f["id"] == row["canonical_fixture_id"])
        self.assertIsNone(f["refresh_interval_days"])

    def test_no_midpoint_or_range_endpoint_is_substituted(self):
        output = bridge.prepare(self.root, CREATED, CUTOFF)
        self.assertTrue(all(f["maintenance_hours"] is None for f in output["canonical_catalog"]["fixtures"]))
        row = next(r for r in output["lineage"] if r["source_id"] == "IAM-CONTRACTOR")
        self.assertEqual(row["source_definition"]["maintenance_hours"], {"low": 3, "high": 8})

    def test_exact_zero_effort_survives(self):
        self.catalog["fixtures"][0]["maintenance_hours"] = {"low": 0, "high": 0}
        self.bundle(self.catalog)
        output = bridge.prepare(self.root, CREATED, CUTOFF)
        row = next(r for r in output["lineage"] if r["source_id"] == "ESS-TERM")
        f = next(f for f in output["canonical_catalog"]["fixtures"] if f["id"] == row["canonical_fixture_id"])
        self.assertEqual(f["maintenance_hours"], 0)

    def test_version_and_catalog_identity_change_fixture_key(self):
        first = bridge.prepare(self.root, CREATED, CUTOFF)
        keys = {r["source_id"]: r["canonical_fixture_id"] for r in first["lineage"]}
        self.catalog["fixtures"][0]["version"] = "new:version|Δ"
        self.bundle(self.catalog)
        second = bridge.prepare(self.root, CREATED, CUTOFF)
        self.assertNotEqual(keys["ESS-TERM"], next(r for r in second["lineage"] if r["source_id"] == "ESS-TERM")["canonical_fixture_id"])
        self.assertNotEqual(bridge._key("X", "a:b", "c"), bridge._key("X", "a", "b:c"))

    def test_future_creation_is_unknown_not_backdated(self):
        outputs = bridge.run_bridge(self.root, "2026-09-20T12:00:00Z", CUTOFF)
        report = json.loads(outputs["canonical_report.json"])
        self.assertEqual(report["summary"]["limitations_by_code"]["NOT_YET_CREATED"], 5)

    def test_missing_all_targets_is_visible_not_empty_pass(self):
        for item in self.catalog["fixtures"]:
            item["target_interface_version"] = None
        self.bundle(self.catalog)
        with patch.object(bridge, "load_assessor", side_effect=AssertionError("should not load")):
            outputs = bridge.run_bridge(self.root, CREATED, CUTOFF)
        self.assertNotIn("canonical_report.json", outputs)
        mapping = json.loads(outputs["mapping.json"])
        self.assertEqual(mapping["state"], "NO_MAPPED_CONTRACTS")
        self.assertEqual(mapping["summary"]["unmapped_cases"], 28)
        self.assertIsNone(mapping["canonical_source"])

    def test_empty_source_is_not_pass(self):
        self.catalog["fixtures"] = []
        self.bundle(self.catalog)
        outputs = bridge.run_bridge(self.root, CREATED, CUTOFF)
        self.assertEqual(json.loads(outputs["mapping.json"])["state"], "NO_MAPPED_CONTRACTS")

    def test_naive_timestamp_rejected(self):
        with self.assertRaises(CatalogError):
            bridge.prepare(self.root, "2026-09-19T11:00:00", CUTOFF)

    def test_input_byte_tree_unchanged_after_execution(self):
        before = {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        bridge.run_bridge(self.root, CREATED, CUTOFF)
        after = {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_repeat_and_offset_equivalent_runs_match_bytes(self):
        outputs = bridge.run_bridge(self.root, CREATED, CUTOFF)
        self.assertEqual(outputs, bridge.run_bridge(self.root, "2026-09-19T07:00:00-04:00", CUTOFF))

    def test_assessor_binding_matches_executed_source(self):
        module, binding = bridge.load_assessor()
        raw = bridge.canonical_path().read_bytes()
        self.assertEqual(binding["sha256"], digest(raw))
        self.assertEqual(binding["git_blob_sha"], hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest())
        self.assertTrue(callable(module.assess))

    def test_modified_expected_result_cannot_be_imported(self):
        path = self.root / "fixtures/ESS-TERM.json"
        item = load_json(path)
        item["cases"][0]["application_observation"] = {"passed": True}
        path.write_bytes(canonical(item))
        with self.assertRaises(CatalogError): bridge.run_bridge(self.root, CREATED, CUTOFF)

    def test_capture_race_is_not_silently_rebound(self):
        old = bridge.verify_bundle(self.root)
        changed = copy.deepcopy(self.catalog)
        changed["fixtures"][0]["purpose"] = "A changed declared purpose"
        self.bundle(changed)
        with patch.object(bridge, "verify_bundle", return_value=old):
            with self.assertRaisesRegex(CatalogError, "changed during capture"):
                bridge.prepare(self.root, CREATED, CUTOFF)

    def test_bad_canonical_promotion_is_detected(self):
        module, binding = bridge.load_assessor()
        actual_assess = module.assess
        def wrong(catalog, cutoff):
            result = actual_assess(catalog, cutoff)
            result["summary"]["cases_with_supported_evidence"] = 1
            return result
        module.assess = wrong
        with patch.object(bridge, "load_assessor", return_value=(module, binding)):
            with self.assertRaisesRegex(CatalogError, "promoted"):
                bridge.run_bridge(self.root, CREATED, CUTOFF)

    def test_bad_canonical_denominator_is_detected(self):
        module, binding = bridge.load_assessor()
        actual_assess = module.assess
        def wrong(catalog, cutoff):
            result = actual_assess(catalog, cutoff)
            result["summary"]["required_cases"] -= 1
            return result
        module.assess = wrong
        with patch.object(bridge, "load_assessor", return_value=(module, binding)):
            with self.assertRaisesRegex(CatalogError, "lost or duplicated"):
                bridge.run_bridge(self.root, CREATED, CUTOFF)

    def test_cli_normal_optimized_and_double_optimized_match(self):
        reports = []
        for flags in ([], ["-O"], ["-OO"]):
            destination = Path(self.tmp.name) / ("out-" + str(len(reports)))
            result = subprocess.run([sys.executable, *flags, str(HERE / "canonical_bridge.py"),
                str(self.root), "--created-at", CREATED, "--as-of", CUTOFF, "--out", str(destination)],
                text=True, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            reports.append({p.name: p.read_bytes() for p in destination.iterdir()})
        self.assertEqual(reports[0], reports[1])
        self.assertEqual(reports[0], reports[2])

    def test_output_cannot_be_inside_input_bundle(self):
        result = bridge.main([str(self.root), "--created-at", CREATED, "--as-of", CUTOFF,
                              "--out", str(self.root / "changed")])
        self.assertEqual(result, 2)
        self.assertFalse((self.root / "changed").exists())

    def test_existing_output_unchanged(self):
        destination = Path(self.tmp.name) / "occupied"
        destination.mkdir()
        (destination / "keep.txt").write_text("Keep this data")
        result = bridge.main([str(self.root), "--created-at", CREATED, "--as-of", CUTOFF, "--out", str(destination)])
        self.assertEqual(result, 2)
        self.assertEqual([p.name for p in destination.iterdir()], ["keep.txt"])

    def test_original_fixture_cli_rejects_bad_input_under_all_modes(self):
        path = Path(self.tmp.name) / "bad.json"
        path.write_text('{"schema":"bad"}')
        for flags in ([], ["-O"], ["-OO"]):
            result = subprocess.run([sys.executable, *flags, str(HERE / "fixture_lab.py"), "validate", str(path)],
                                    text=True, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
