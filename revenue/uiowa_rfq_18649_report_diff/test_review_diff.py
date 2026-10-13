#!/usr/bin/env python3
"""Real parent-compiler integration and regression tests; no mocked report verifier."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import review_diff as diff
from synthetic_demo import AFTER_AT, BEFORE_AT, compile_inputs, example_reports, make_inputs
from workshare_compile import compile_historical
from workshare_contract import authority_root_sha256


class ReportDiffTests(unittest.TestCase):
    def setUp(self):
        self.candidate, self.authority = make_inputs()
        self.before = compile_inputs(self.candidate, self.authority)

    def revised(self, when=AFTER_AT):
        return compile_inputs(self.candidate, self.authority, when)

    def delta(self, when=AFTER_AT):
        return diff.compare_reports(self.before, self.revised(when))

    @staticmethod
    def changed_cells(delta):
        return {(c["group"], c["dimension"]) for c in delta["cell_deltas"] if c["changed"]}

    def source(self, group="ESS", dimension="software"):
        return next(s for s in self.authority["sources"]
                    if s["group"] == group and s["dimension"] == dimension)

    def test_identical_reports_have_twelve_unchanged_cells(self):
        delta = diff.compare_reports(self.before, self.before)
        self.assertEqual(delta["summary"]["cells_total"], 12)
        self.assertEqual(delta["summary"]["cells_changed"], 0)
        self.assertEqual(delta["source_changes"], [])
        self.assertEqual(delta["review_queue"], [])

    def test_content_revision_impacts_exact_cell_without_scoring(self):
        self.source()["source_content_sha256"] = "1" * 64
        delta = self.delta()
        self.assertEqual(self.changed_cells(delta), {("ESS", "software")})
        self.assertEqual(delta["source_changes"][0]["kinds"], ["CONTENT_REVISION"])
        self.assertEqual(delta["summary"]["cells_with_status_change"], 0)
        self.assertNotIn("maturity", delta["cell_deltas"][0])

    def test_generation_only_rebinding_is_not_substantive_change(self):
        self.candidate["authority_generation"] = self.authority["generation"] = "synthetic-g2"
        for source in self.authority["sources"]:
            source["authority_generation"] = "synthetic-g2"
        delta = self.delta()
        self.assertEqual(delta["summary"]["generation_only_rebindings"], 12)
        self.assertEqual(delta["summary"]["source_records_substantively_changed"], 0)
        self.assertEqual(self.changed_cells(delta), set())
        self.assertNotEqual(delta["before"]["evidence_root_sha256"], delta["after"]["evidence_root_sha256"])

    def test_removed_source_leaves_a_visible_missing_evidence_followup(self):
        self.authority["sources"].remove(self.source())
        delta = self.delta()
        row = delta["cell_deltas"][0]
        self.assertEqual(row["after_status"], "HOLD_MISSING_EVIDENCE")
        self.assertEqual(row["removed_source_ids"], ["fictional-ess-software"])
        self.assertEqual(delta["source_changes"][0]["kinds"], ["REMOVED_SOURCE"])
        self.assertIn("missing records do not establish poor practice", delta["review_queue"][0]["questions"][1])

    def test_added_source_and_conflicting_account_are_retained(self):
        added = copy.deepcopy(self.source())
        added.update(source_id="additional-account", maturity=3)
        self.authority["sources"].append(added)
        delta = self.delta()
        self.assertEqual(delta["cell_deltas"][0]["after_status"], "HOLD_CONFLICT")
        self.assertEqual(delta["cell_deltas"][0]["added_source_ids"], ["additional-account"])
        self.assertEqual(delta["source_changes"][0]["kinds"], ["ADDED_SOURCE"])

    def test_reassignment_impacts_both_cells(self):
        self.source()["group"] = "RIS"
        delta = self.delta()
        self.assertEqual(self.changed_cells(delta), {("ESS", "software"), ("RIS", "software")})
        self.assertIn("CELL_REASSIGNMENT", delta["source_changes"][0]["kinds"])

    def test_reference_change_is_not_automatically_called_rename(self):
        self.source()["source_ref"] = "synthetic://a-new-location"
        delta = self.delta()
        self.assertEqual(delta["source_changes"][0]["kinds"], ["REFERENCE_CHANGE"])
        self.assertFalse(delta["interpretation"]["document_rename_inferred"])
        self.assertNotIn("synthetic://a-new-location", json.dumps(delta))

    def test_new_id_same_digest_is_removed_plus_added_not_assumed_identity(self):
        self.source()["source_id"] = "replacement-identity"
        kinds = [row["kinds"] for row in self.delta()["source_changes"]]
        self.assertCountEqual(kinds, [["REMOVED_SOURCE"], ["ADDED_SOURCE"]])

    def test_claim_and_confidence_changes_do_not_imply_content_revision(self):
        self.source().update(claim="PRIVATE TEST PHRASE SHOULD NOT LEAK", confidence_bp=6000)
        delta = self.delta()
        self.assertEqual(delta["source_changes"][0]["kinds"], ["ASSESSMENT_RECORD_CHANGE"])
        self.assertNotIn("PRIVATE TEST PHRASE", json.dumps(delta))
        self.assertEqual(delta["source_changes"][0]["changed_fields"], ["claim", "confidence_bp"])

    def test_observation_metadata_change_is_explicit(self):
        self.source().update(observed_at=AFTER_AT, evidence_kind="interview")
        self.assertEqual(self.delta()["source_changes"][0]["kinds"], ["EVIDENCE_METADATA_CHANGE"])

    def test_clock_only_aging_not_misrepresented_as_evidence_change(self):
        delta = self.delta("2027-02-01T15:00:00Z")
        self.assertEqual(delta["summary"]["cells_with_evaluation_window_effect"], 12)
        self.assertEqual(delta["summary"]["source_records_changed"], 0)
        self.assertEqual(delta["summary"]["cells_with_changed_evidence"], 0)
        self.assertEqual(delta["cell_deltas"][0]["after_status"], "HOLD_STALE_EVIDENCE")

    def test_persistent_missing_evidence_is_not_lost_in_an_empty_diff(self):
        self.authority["sources"].remove(self.source())
        report = self.revised()
        delta = diff.compare_reports(report, report)
        self.assertEqual(delta["summary"]["cells_changed"], 0)
        self.assertEqual(delta["review_queue"][0]["trigger"], "PERSISTENT_HOLD")
        self.assertTrue(delta["cell_deltas"][0]["persistent_hold"])

    def test_conflict_resolution_is_not_claimed_as_maturity_gain(self):
        extra = copy.deepcopy(self.source())
        extra.update(source_id="dissent", maturity=3)
        self.authority["sources"].append(extra)
        self.before = compile_inputs(self.candidate, self.authority)
        self.authority["sources"].remove(extra)
        delta = self.delta()
        self.assertIn("not approval or a validated maturity gain", delta["review_queue"][0]["questions"][-1])
        self.assertFalse(delta["interpretation"]["practice_improvement_inferred"])

    def test_engagement_mismatch_rejected_after_validating_each_report(self):
        self.candidate["engagement"]["prime_candidate"] = self.authority["prime_candidate"] = "Another Fictional Prime"
        for row in self.authority["sources"]:
            row["prime_candidate"] = "Another Fictional Prime"
        with self.assertRaisesRegex(diff.ContractError, "different engagement"):
            self.delta()

    def test_reverse_evaluation_order_rejected(self):
        with self.assertRaisesRegex(diff.ContractError, "evaluated after"):
            diff.compare_reports(self.revised(), self.before)

    def test_mutated_report_receipt_rejected(self):
        bad = copy.deepcopy(self.before)
        bad["receipt_sha256"] = "0" * 64
        with self.assertRaisesRegex(diff.ContractError, "receipt mismatch"):
            diff.compare_reports(self.before, bad)

    def test_rehashed_fabricated_matrix_still_fails_parent_semantics(self):
        bad = copy.deepcopy(self.before)
        bad["assessment_matrix"][0]["source_ids"] = []
        unsigned = {k: v for k, v in bad.items() if k != "receipt_sha256"}
        bad["receipt_sha256"] = diff.digest(unsigned)
        with self.assertRaisesRegex(diff.ContractError, "semantic recompile"):
            diff.compare_reports(self.before, bad)

    def test_historical_report_cannot_be_promoted_through_diff(self):
        historical = compile_historical(self.candidate, self.authority,
                                        authority_root_sha256(self.authority), evaluated_at=BEFORE_AT)
        with self.assertRaisesRegex(diff.ContractError, "UNTRUSTED_INSPECTION"):
            diff.compare_reports(historical, historical)

    def test_synthetic_ui_stub_is_not_a_compiler_report(self):
        with self.assertRaises(diff.ContractError):
            diff.compare_reports(self.before, {"mode": diff.MODE_UNTRUSTED, "assessment_matrix": [None] * 12})

    def test_delta_verification_binds_both_originals(self):
        delta = self.delta()
        self.assertTrue(diff.verify_diff(self.before, self.revised(), delta)["integrity_valid"])
        with self.assertRaisesRegex(diff.ContractError, "verified original"):
            diff.verify_diff(self.before, self.before, delta)

    def test_rehashed_delta_tampering_rejected(self):
        after = self.revised()
        delta = diff.compare_reports(self.before, after)
        delta["interpretation"]["current_evidence_review_authority"] = True
        delta["diff_receipt_sha256"] = diff.digest({k: v for k, v in delta.items() if k != "diff_receipt_sha256"})
        with self.assertRaises(diff.ContractError):
            diff.verify_diff(self.before, after, delta)

    def test_no_input_mutation_or_output_aliasing(self):
        before_copy = copy.deepcopy(self.before)
        after = self.revised()
        delta = diff.compare_reports(self.before, after)
        delta["before"]["status_counts"].clear()
        delta["cell_deltas"][0]["before_reason_codes"].clear()
        self.assertEqual(self.before, before_copy)

    def test_source_input_order_normalizes_to_same_delta(self):
        expected = self.delta()
        self.authority["sources"].reverse()
        self.assertEqual(self.delta(), expected)

    def test_all_external_authority_false_and_no_notes_transfer(self):
        delta = self.delta()
        self.assertTrue(all(value is False for value in delta["external_authority"].values()))
        self.assertFalse(delta["interpretation"]["current_evidence_review_authority"])
        self.assertFalse(delta["interpretation"]["notes_automatically_transferred"])

    def test_markdown_is_from_verified_reports_and_excludes_claims(self):
        self.source()["claim"] = "<script>PRIVATE CLAIM</script>"
        report = self.revised()
        text = diff.render_markdown(self.before, report)
        self.assertNotIn("PRIVATE CLAIM", text)
        self.assertIn(self.before["receipt_sha256"], text)
        self.assertIn(report["receipt_sha256"], text)
        self.assertEqual(sum(line.startswith("| ESS / ") for line in text.splitlines()), 4)

    def test_markdown_escape(self):
        self.assertEqual(diff._escape("<tag>|[link](x)\nnext"), "&lt;tag&gt;\\|\\[link\\]\\(x\\) next")

    def test_demo_expected_revision_impact(self):
        before, after = example_reports()
        delta = diff.compare_reports(before, after)
        self.assertEqual(delta["summary"]["cells_changed"], 6)
        self.assertEqual(delta["summary"]["review_queue_items"], 7)
        self.assertEqual(delta["summary"]["cells_with_status_change"], 3)
        self.assertEqual(delta["summary"]["generation_only_rebindings"], 7)
        self.assertTrue(diff.verify_diff(before, after, delta)["integrity_valid"])


class FileAndCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.before, self.after = example_reports()
        for name, report in (("before.json", self.before), ("after.json", self.after)):
            diff.write_new(self.root / name, diff.canonical_json_bytes(report))

    def run_cli(self, *args):
        return subprocess.run([sys.executable, *(["-O"] if sys.flags.optimize else []),
                               str(Path(diff.__file__).resolve()), *map(str, args)],
                              capture_output=True, text=True, timeout=10)

    def test_cli_compare_verify_and_markdown(self):
        before, after = self.root / "before.json", self.root / "after.json"
        output = self.root / "delta.json"
        result = self.run_cli("compare", before, after, output)
        self.assertEqual(result.returncode, 0, result.stderr)
        verified = self.run_cli("verify", before, after, output)
        self.assertEqual(verified.returncode, 0, verified.stderr)
        self.assertIn("UNTRUSTED_DIFF_INTEGRITY_ONLY", verified.stdout)
        md = self.run_cli("compare", before, after, self.root / "review.md", "--format", "markdown")
        self.assertEqual(md.returncode, 0, md.stderr)

    def test_existing_output_and_inputs_not_overwritten(self):
        target = self.root / "before.json"
        original = target.read_bytes()
        result = self.run_cli("compare", target, self.root / "after.json", target)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(target.read_bytes(), original)

    def test_duplicate_keys_and_nonfinite_json_rejected(self):
        target = self.root / "invalid.json"
        for raw in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}'):
            with self.subTest(raw=raw):
                target.write_text(raw)
                with self.assertRaises(diff.ContractError):
                    diff.load_json(target)

    def test_oversized_and_nonregular_files_rejected(self):
        path = self.root / "big.json"
        path.write_bytes(b" " * (diff.MAX_INPUT_BYTES + 1))
        with self.assertRaises(diff.ContractError):
            diff.load_json(path)
        with self.assertRaises((OSError, diff.ContractError)):
            diff.load_json(self.root)

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "platform lacks no-follow flag")
    def test_final_input_symlink_rejected(self):
        link = self.root / "link.json"
        link.symlink_to(self.root / "before.json")
        with self.assertRaises(OSError):
            diff.load_json(link)

    def test_failed_comparison_publishes_nothing(self):
        malformed = self.root / "invalid.json"
        malformed.write_text('{"mode":"UNTRUSTED_INSPECTION"}')
        out = self.root / "never.json"
        result = self.run_cli("compare", self.root / "before.json", malformed, out)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(out.exists())

    def test_invalid_utf8_is_a_clean_cli_error(self):
        bad = self.root / "invalid.json"
        bad.write_bytes(b"\xff\xfe")
        result = self.run_cli("compare", bad, self.root / "after.json", self.root / "never.json")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)

    def test_output_is_private_on_posix(self):
        if os.name != "posix":
            self.skipTest("POSIX permission bits only")
        self.assertEqual((self.root / "before.json").stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
