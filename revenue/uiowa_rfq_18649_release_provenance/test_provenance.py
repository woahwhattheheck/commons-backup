"""Rehearsal and malformed-input tests. No external services are contacted."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import provenance as p
from make_fixtures import ARTIFACT, build


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.packet = build()["complete"]

    def report(self, **kwargs):
        return p.inspect(self.packet, **kwargs)

    def codes(self, report):
        return {check["code"] for check in report["checks"]}

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "provenance.py"), *map(str, args)],
                              capture_output=True, text=True, timeout=10)

    def test_complete_is_linked_not_authenticated(self):
        report = self.report()
        self.assertEqual(report["status"], "LINKED_RECORDS")
        self.assertEqual(report["local_bytes"], "NOT_REQUESTED")
        self.assertIn("no signature", report["limitation"])
        self.assertEqual(sum(c["code"] == "RESOLVED_INPUT" for c in report["checks"]), 2)

    def test_exact_bytes_are_checked_only_when_requested(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "demo-artifact.txt").write_bytes(ARTIFACT)
            report = self.report(artifact_root=Path(folder))
        self.assertEqual(report["status"], "LINKED_RECORDS")
        self.assertTrue(any(c["path"].endswith(".local_bytes") for c in report["checks"]))

    def test_fixture_missing_build_is_precise(self):
        report = p.inspect(build()["missing-build"])
        self.assertEqual(report["status"], "GAPS")
        unknown = [c for c in report["checks"] if c["status"] == "UNKNOWN"]
        self.assertEqual([(c["code"], c["path"]) for c in unknown],
                         [("MISSING_LINK", "deployments/d1.build_id")])
        self.assertIsNone(report["traces"][0]["build_id"])

    def test_fixture_digest_mismatch_does_not_claim_compromise(self):
        report = p.inspect(build()["digest-mismatch"])
        self.assertEqual(report["status"], "CONTRADICTORY_RECORDS")
        failures = [c for c in report["checks"] if c["status"] == "MISMATCH"]
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["path"], "deployments/d1.artifact_digest")
        self.assertIn("not compromise", failures[0]["follow_up"])

    def test_repository_identity_not_just_revision(self):
        self.packet["builds"][0]["observed_repository"] = "https://example.invalid/other"
        self.assertEqual(self.report()["status"], "CONTRADICTORY_RECORDS")

    def test_source_revision_mismatch(self):
        self.packet["builds"][0]["observed_revision"] = "e" * 40
        self.assertEqual(self.report()["status"], "CONTRADICTORY_RECORDS")

    def test_approved_revision_mismatch(self):
        self.packet["sources"][0]["approved_revision"] = "f" * 40
        self.assertEqual(self.report()["status"], "CONTRADICTORY_RECORDS")

    def test_unknown_approval_is_gap(self):
        self.packet["sources"][0]["approval_evidence_id"] = None
        self.assertIn("MISSING_LINK", self.codes(self.report()))
        self.assertEqual(self.report()["status"], "GAPS")

    def test_duplicate_ids_in_each_table_rejected(self):
        for table in ("sources", "builds", "artifacts", "deployments", "evidence"):
            with self.subTest(table=table):
                packet = build()["complete"]
                packet[table].append(copy.deepcopy(packet[table][0]))
                with self.assertRaisesRegex(ValueError, "duplicate record IDs"):
                    p.inspect(packet)

    def test_malformed_digest_rejected(self):
        for digest in ("ABC" * 22, "a" * 63, "a" * 65, 5, True, {}):
            with self.subTest(digest=digest):
                self.packet["artifacts"][0]["sha256"] = digest
                with self.assertRaises(ValueError):
                    self.report()

    def test_unknown_digest_not_zero_filled(self):
        self.packet["artifacts"][0]["sha256"] = None
        self.assertEqual(self.report()["status"], "GAPS")

    def test_blank_and_extra_fields_rejected(self):
        self.packet["evidence"][0]["locator"] = "  \n"
        with self.assertRaises(ValueError):
            self.report()
        self.packet = build()["complete"]
        self.packet["artifacts"][0]["deployment_approved"] = True
        with self.assertRaisesRegex(ValueError, "unexpected"):
            self.report()

    def test_boolean_schema_version_rejected(self):
        self.packet["schema_version"] = True
        with self.assertRaises(ValueError):
            self.report()

    def test_missing_field_is_invalid_but_explicit_null_is_gap(self):
        del self.packet["builds"][0]["builder_id"]
        with self.assertRaises(ValueError):
            self.report()
        self.packet["builds"][0]["builder_id"] = None
        self.assertEqual(self.report()["status"], "GAPS")

    def test_timezone_required(self):
        for value in ("2026-01-12T09:00:00", "2026-13-12T09:00:00Z", "yesterday"):
            self.packet["sources"][0]["approved_at"] = value
            with self.assertRaises(ValueError):
                self.report()

    def test_time_inversion(self):
        self.packet["builds"][0]["finished_at"] = "2026-01-12T08:00:00Z"
        self.assertIn("TIME_INVERSION", self.codes(self.report()))

    def test_equivalent_offset_times(self):
        self.packet["builds"][0]["finished_at"] = "2026-01-12T04:03:00-05:00"
        self.assertEqual(self.report()["status"], "LINKED_RECORDS")

    def test_build_before_approval_permitted_but_deploy_before_approval_not(self):
        self.packet["sources"][0]["approved_at"] = "2026-01-12T09:02:30Z"
        self.assertEqual(self.report()["status"], "LINKED_RECORDS")
        self.packet["sources"][0]["approved_at"] = "2026-01-12T09:04:00Z"
        self.assertEqual(self.report()["status"], "CONTRADICTORY_RECORDS")

    def test_unknown_empty_and_partial_material_inventories(self):
        for coverage in ("partial", "unknown"):
            self.packet["builds"][0]["input_coverage"] = coverage
            self.assertEqual(self.report()["status"], "GAPS")
        self.packet["builds"][0]["input_coverage"] = "declared_complete"
        self.packet["builds"][0]["materials"] = []
        self.assertIn("INPUT_COVERAGE", self.codes(self.report()))

    def test_duplicate_material_and_missing_digest(self):
        self.packet["builds"][0]["materials"].append(copy.deepcopy(self.packet["builds"][0]["materials"][0]))
        self.assertIn("AMBIGUOUS_MATERIAL", self.codes(self.report()))
        self.packet = build()["complete"]
        self.packet["builds"][0]["materials"][0]["sha256"] = None
        self.assertEqual(self.report()["status"], "GAPS")

    def test_interview_is_not_artifact_evidence(self):
        self.packet["evidence"][0]["kind"] = "interview"
        self.assertIn("INTERVIEW_ONLY", self.codes(self.report()))

    def test_synthetic_cannot_become_assessment_findings(self):
        self.packet["data_class"] = "assessment"
        self.assertIn("SYNTHETIC_EVIDENCE", self.codes(self.report()))
        self.assertEqual(self.report()["status"], "GAPS")

    def test_empty_deployment_array_not_pass(self):
        self.packet["deployments"] = []
        self.assertEqual(self.report()["status"], "GAPS")

    def test_independent_deployment_traces_and_early_return(self):
        second = copy.deepcopy(self.packet["deployments"][0])
        second["id"] = "d2"
        self.packet["deployments"][0]["artifact_id"] = "missing"
        self.packet["deployments"].append(second)
        report = self.report()
        self.assertEqual([t["status"] for t in report["traces"]], ["GAPS", "LINKED_RECORDS"])
        self.assertEqual(report["traces"][0]["checks_end"], report["traces"][1]["checks_start"])

    def test_unused_records_are_out_of_semantic_scope(self):
        other = copy.deepcopy(self.packet["builds"][0])
        other.update(id="unused", source_id=None, builder_id=None)
        self.packet["builds"].append(other)
        self.assertEqual(self.report()["status"], "LINKED_RECORDS")
        self.assertIn("unused records are not assessed", self.report()["scope"])

    def test_inspection_does_not_mutate_packet(self):
        original = copy.deepcopy(self.packet)
        self.report()
        self.assertEqual(self.packet, original)

    def test_actual_byte_mismatch(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "demo-artifact.txt").write_text("different bytes", encoding="utf-8")
            report = self.report(artifact_root=Path(folder))
        self.assertEqual(report["status"], "CONTRADICTORY_RECORDS")

    def test_local_unavailable_and_outside_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertIn("ARTIFACT_UNAVAILABLE", self.codes(self.report(artifact_root=Path(folder))))
            for name in ("../outside", "/etc/passwd", "a\\b"):
                self.packet["artifacts"][0]["local_path"] = name
                self.assertIn("OUTSIDE_ARTIFACT_ROOT", self.codes(self.report(artifact_root=Path(folder))))

    def test_symlink_outside_root_not_read(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder, "root")
            root.mkdir()
            outside = Path(folder, "outside")
            outside.write_bytes(ARTIFACT)
            try:
                (root / "demo-artifact.txt").symlink_to(outside)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable on this platform")
            self.assertIn("OUTSIDE_ARTIFACT_ROOT", self.codes(self.report(artifact_root=root)))

    def test_markdown_is_escaped(self):
        self.packet["deployments"][0]["id"] = "pipe|<script>`[link]\nnext"
        text = p.markdown(self.report())
        self.assertNotIn("<script>", text)
        self.assertIn("&#124;", text)
        self.assertIn("&#91;", text)

    def test_checked_in_generated_files_are_reproducible(self):
        self.assertEqual(json.loads((ROOT / "fixtures.json").read_text()), build())
        self.assertEqual(json.loads((ROOT / "packet.schema.json").read_text()), p.schema())
        self.assertEqual((ROOT / "demo-artifact.txt").read_bytes(), ARTIFACT)

    def test_cli_statuses_and_rendering(self):
        for case, status in (("complete", 0), ("missing-build", 1), ("digest-mismatch", 1)):
            result = self.run_cli(ROOT / "fixtures.json", "--case", case)
            self.assertEqual(result.returncode, status, result.stderr)
            self.assertEqual(json.loads(result.stdout)["packet_id"], "SYNTHETIC-057-" + case)
        result = self.run_cli(ROOT / "fixtures.json", "--case", "complete", "--format", "markdown", "--artifact-root", ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith("# Release-record inspection"))
        self.assertEqual(self.run_cli(ROOT / "fixtures.json", "--case", "missing-case").returncode, 2)

    def test_cli_schema(self):
        result = self.run_cli("--schema")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), p.schema())

    def test_duplicate_keys_and_nonfinite_json_and_oversize_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder, "bad.json")
            for text in ('{"a":1,"a":2}', '{"a":NaN}', '{', '"' + 'x' * (4 * 1024 * 1024) + '"'):
                file.write_text(text, encoding="utf-8")
                result = self.run_cli(file)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("Input error:", result.stderr)


if __name__ == "__main__":
    unittest.main()
