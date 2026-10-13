"""Real CLI and information-preservation tests for the retained readout."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import rehearse_snapshot as rehearsal
import verify_crosswalk as vc

ROOT = Path(__file__).resolve().parent


class RehearsalTests(unittest.TestCase):
    def setUp(self):
        self.doc = vc.load_strict(ROOT / "crosswalk.json")

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, *(["-O"] if sys.flags.optimize else []), "-B", str(ROOT / "rehearse_snapshot.py"), *args],
            text=True, encoding="utf-8", capture_output=True, timeout=10,
        )

    def test_all_retained_records_and_sources_survive(self):
        result = rehearsal.report_snapshot(self.doc)
        self.assertEqual(result["problems"], self.doc["problems"])
        self.assertEqual(result["source_snapshot"], self.doc["source_snapshot"])

    def test_all_root_fields_reconstruct_the_exact_snapshot(self):
        result = rehearsal.report_snapshot(self.doc)
        reconstructed = {key: result[key] for key in self.doc}
        self.assertEqual(reconstructed, self.doc)
        self.assertEqual(vc.verify(reconstructed), result["snapshot_sha256"])
        cli = self.cli("--format", "json")
        self.assertEqual(cli.returncode, 0, cli.stderr)
        emitted = json.loads(cli.stdout)
        self.assertEqual({key: emitted[key] for key in self.doc}, self.doc)

    def test_scope_is_exact_and_recursively_detached(self):
        before = copy.deepcopy(self.doc)
        result = rehearsal.report_snapshot(self.doc)
        self.assertEqual(result["scope"], self.doc["scope"])
        result["scope"]["expected_problem_numbers"].append(9999)
        result["scope"]["description"] = "changed only in the returned report"
        result["scope"]["parallel_platform_rewards_counted"] = True
        result["scope"]["expected_total_usd"] = 0
        self.assertEqual(self.doc, before)
        self.assertEqual(rehearsal.report_snapshot(self.doc)["scope"], before["scope"])

    def test_summary_matches_actual_records(self):
        self.assertEqual(rehearsal.report_snapshot(self.doc)["summary"], {
            "row_count": 9, "catalog_value_usd": 22000, "parallel_rewards_included": False,
            "formal_present_count": 6, "formal_missing_count": 3,
            "ppl_mapped_count": 8, "historical_active_take_count": 1,
        })

    def test_no_live_check_or_payment_inference(self):
        result = rehearsal.report_snapshot(self.doc)
        self.assertIs(result["live_source_check_performed"], False)
        self.assertEqual(result["snapshot_date"], "2026-09-18")
        text = rehearsal.markdown(result)
        self.assertIn("not money received", text)
        self.assertIn("not performed", text)
        self.assertNotIn("RESEARCH_READY", text)

    def test_asymmetric_reward_and_unknowns_remain(self):
        rows = {r["erdos_number"]: r for r in rehearsal.report_snapshot(self.doc)["problems"]}
        self.assertEqual(rows[625]["reward_scope"], "disproof_maximum")
        self.assertIsNone(rows[64]["ppl_id"])
        self.assertEqual(rows[64]["commons_ownership"]["task_id"], "ERDOS64-N24-PROOF-BACKEND-ZSOL-20260918")
        for n in (625, 687, 1191):
            self.assertIsNone(rows[n]["formal_target"]["theorem"])
            self.assertIsNone(rows[n]["formal_target"]["blob_sha"])

    def test_returned_rows_are_detached_from_source(self):
        before = copy.deepcopy(self.doc)
        result = rehearsal.report_snapshot(self.doc)
        result["problems"][0]["notes"].append("another note")
        result["source_snapshot"]["formal_conjectures_commit"] = "another commit"
        result["limits"].append("another limit")
        self.assertEqual(self.doc, before)
        self.assertEqual(rehearsal.report_snapshot(self.doc)["limits"], list(rehearsal.LIMITS))

    def test_native_verifier_rejects_changed_rehearsal_input(self):
        self.doc["problems"][0]["formal_target"]["theorem"] = "Different.theorem"
        with self.assertRaises(vc.CrosswalkError):
            rehearsal.report_snapshot(self.doc)

    def test_json_cli_matches_native_api_exactly(self):
        result = self.cli("--format", "json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), rehearsal.report_snapshot(self.doc))

    def test_markdown_cli_matches_native_renderer_exactly(self):
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, rehearsal.markdown(rehearsal.report_snapshot(self.doc)))

    def test_cli_repeated_output_is_deterministic(self):
        for fmt in ("json", "markdown"):
            with self.subTest(fmt=fmt):
                first = self.cli("--format", fmt)
                second = self.cli("--format", fmt)
                self.assertEqual(first.returncode, 0, first.stderr)
                self.assertEqual(second.returncode, 0, second.stderr)
                self.assertEqual(first.stdout, second.stdout)

    def test_changed_input_fails_without_partial_report_or_rewrite(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "changed.json"
            self.doc["source_snapshot"]["formal_conjectures_commit"] = "0" * 40
            path.write_text(json.dumps(self.doc), encoding="utf-8")
            before = path.read_bytes()
            result = self.cli("--input", str(path), "--format", "json")
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assertIn("CROSSWALK_ERROR", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual(path.read_bytes(), before)

    def test_missing_input_fails_without_partial_report(self):
        with tempfile.TemporaryDirectory() as td:
            result = self.cli("--input", str(Path(td) / "missing.json"))
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assertNotIn("Traceback", result.stderr)

    def test_duplicate_json_key_fails(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "duplicate.json"
            path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
            result = self.cli("--input", str(path))
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assertIn("duplicate JSON key", result.stderr)

    def test_fixture_and_directory_are_unchanged(self):
        before = {p.name: p.read_bytes() for p in ROOT.iterdir() if p.is_file()}
        self.assertEqual(self.cli("--format", "json").returncode, 0)
        after = {p.name: p.read_bytes() for p in ROOT.iterdir() if p.is_file()}
        self.assertEqual(before, after)

    def test_markdown_contains_each_row_once_in_source_order(self):
        text = rehearsal.markdown(rehearsal.report_snapshot(self.doc))
        rows = [line.split("|")[1].strip() for line in text.splitlines() if line.startswith("| ")][1:]
        self.assertEqual(rows, [str(r["erdos_number"]) for r in self.doc["problems"]])


if __name__ == "__main__":
    unittest.main()
