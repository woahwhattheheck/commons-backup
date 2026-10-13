"""Independent regression review for UIOWA-076 source projection and missing context.

Loads the actual sibling analyzer without changing sys.path or generic module
bindings. The actual generator runs in a fresh interpreter, including -O when
this test process is optimized. All input data is the author's fictional case.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("uiowa076_trace_review_subject", HERE / "ai_coding.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load the sibling analyzer")
a = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(a)


def python_command() -> list[str]:
    return [sys.executable] + (["-O"] * sys.flags.optimize)


class SourceTraceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture_tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.fixture_tmp.cleanup)
        cls.fixture_dir = Path(cls.fixture_tmp.name)
        command = python_command() + [str(HERE / "rehearse.py"), "--out", str(cls.fixture_dir / "case")]
        result = subprocess.run(command, capture_output=True, text=True, timeout=20)
        if result.returncode:
            raise RuntimeError(result.stderr)
        cls.input_path = cls.fixture_dir / "case/synthetic/changes.json"
        cls.root = cls.input_path.parent
        cls.original = json.loads(cls.input_path.read_text(encoding="utf-8"))

    def setUp(self):
        self.data = copy.deepcopy(self.original)

    def change(self, cid="ESS-A"):
        return next(c for c in self.data["changes"] if c["id"] == cid)

    def report(self):
        return a.analyze(self.data, self.root)

    def row(self, cid="ESS-A"):
        return next(c for c in self.report()["changes"] if c["id"] == cid)

    def pair(self):
        return next(p for p in self.report()["comparisons"] if p["pair_id"] == "PAIR-ESS")

    def test_original_worked_results_are_unchanged(self):
        comparisons = {p["pair_id"]: p for p in self.report()["comparisons"]}
        for pid, author, lifecycle, faults in [("PAIR-ESS", "-67", "-70", 0), ("PAIR-RIS", "-45", "90", 2)]:
            with self.subTest(pair=pid):
                p = comparisons[pid]
                self.assertTrue(p["comparable"])
                self.assertEqual((p["author_delta_minutes"], p["lifecycle_delta_minutes"], p["faults_delta"]),
                                 (author, lifecycle, faults))
        self.assertFalse(comparisons["PAIR-IAM"]["comparable"])
        self.assertEqual(len(self.report()["evidence"]), 77)

    def test_unknown_context_is_not_a_match_for_each_dimension(self):
        for field in a.CONTEXT:
            for value in (None, "UNKNOWN", "unknown", " UnKnOwN "):
                for arms in (("ESS-A",), ("ESS-M",), ("ESS-A", "ESS-M")):
                    with self.subTest(field=field, value=value, arms=arms):
                        self.data = copy.deepcopy(self.original)
                        for cid in arms:
                            self.change(cid)["context"][field] = value
                        p = self.pair()
                        self.assertFalse(p["comparable"])
                        for cid in arms:
                            mode = self.change(cid)["mode"]
                            self.assertIn(f"{mode}_{field}_unknown", p["reasons"])
                            self.assertEqual(self.row(cid)["context"][field], value)
                        for key in ("author_delta_minutes", "delivery_effort_delta_minutes", "lifecycle_delta_minutes", "faults_delta"):
                            self.assertIsNone(p[key])

    def test_unknown_context_does_not_erase_known_per_change_amounts(self):
        self.change()["context"]["stack"] = None
        r = self.row()
        self.assertEqual(r["lifecycle_effort_minutes"], "80")
        self.assertEqual(r["comparable_faults"], 0)
        self.assertFalse(self.pair()["comparable"])

    def test_no_guessing_missing_context_from_other_words(self):
        for value in ("unknown-runtime-v2", "N/A", "not-collected", "?", "bounded"):
            with self.subTest(value=value):
                self.data = copy.deepcopy(self.original)
                for cid in ("ESS-A", "ESS-M"):
                    self.change(cid)["context"]["stack"] = value
                self.assertTrue(self.pair()["comparable"])

    def test_bad_context_shapes_remain_input_errors(self):
        for field in a.CONTEXT:
            for value in (False, 0, [], {}, "", " \t "):
                with self.subTest(field=field, value=value):
                    self.data = copy.deepcopy(self.original)
                    self.change()["context"][field] = value
                    with self.assertRaises(a.InputError):
                        self.report()

    def test_known_context_mismatch_retains_existing_reason(self):
        self.change()["context"]["criticality"] = "different"
        self.assertIn("criticality_mismatch", self.pair()["reasons"])
        self.assertFalse(self.pair()["comparable"])

    def test_source_trace_preserves_dates_and_acceptance_edges(self):
        trace = self.row()["source_trace"]
        c = self.change()
        self.assertEqual(trace["started_at"], c["started_at"])
        self.assertEqual(trace["accepted_at"], c["accepted_at"])
        self.assertEqual(trace["acceptance_evidence_ids"], c["acceptance_evidence_ids"])
        self.assertEqual(trace["followup"], c["followup"])

    def test_source_trace_preserves_stage_coverage_and_allocations(self):
        trace = self.row()["source_trace"]
        self.assertEqual(trace["coverage"], self.change()["coverage"])
        self.assertEqual(trace["effort"], sorted(self.change()["effort"], key=lambda e: e["id"]))

    def test_change_of_acceptance_edge_is_visible(self):
        before = self.report()
        self.change()["acceptance_evidence_ids"] = ["EV-RIS-A-ACCEPT"]
        after = self.report()
        self.assertNotEqual(before, after)
        self.assertNotEqual(a.markdown(before), a.markdown(after))
        self.assertEqual(self.row()["source_trace"]["acceptance_evidence_ids"], ["EV-RIS-A-ACCEPT"])
        self.assertEqual(before["evidence"], after["evidence"])
        self.assertEqual(before["comparisons"], after["comparisons"])

    def test_change_of_followup_edge_is_visible(self):
        before = self.report()
        self.change()["followup"]["evidence_ids"] = ["EV-RIS-A-FOLLOWUP"]
        after = self.report()
        self.assertNotEqual(before, after)
        self.assertNotEqual(a.markdown(before), a.markdown(after))
        self.assertEqual(self.row()["source_trace"]["followup"]["evidence_ids"], ["EV-RIS-A-FOLLOWUP"])

    def test_change_of_coverage_basis_is_visible(self):
        before = self.report()
        self.change()["coverage"]["author"]["basis"] = "New coverage qualification for a human assessor."
        after = self.report()
        self.assertNotEqual(before, after)
        self.assertIn("New coverage qualification", a.markdown(after))

    def test_change_of_allocation_id_is_visible(self):
        before = self.report()
        self.change()["effort"][0]["id"] = "ESS-A-reallocated-understanding"
        after = self.report()
        self.assertNotEqual(before, after)
        self.assertIn("ESS-A-reallocated-understanding", a.markdown(after))

    def test_window_shift_changes_trace_not_equal_duration_arithmetic(self):
        before = self.report()
        c = self.change()
        c.update(started_at="2026-08-02T09:00:00Z", accepted_at="2026-08-02T10:30:00Z")
        c["followup"]["observed_through"] = "2026-09-01T10:30:00Z"
        after = self.report()
        self.assertNotEqual(before, after)
        self.assertEqual(before["comparisons"], after["comparisons"])
        self.assertEqual(self.row()["wall_delivery_minutes"], "90")
        self.assertIn("2026-09-01T10:30:00Z", a.markdown(after))

    def test_incomplete_observations_keep_unknowns_and_source_edges(self):
        c = self.change("IAM-A")
        trace = self.row("IAM-A")["source_trace"]
        self.assertIsNone(trace["accepted_at"])
        self.assertIsNone(trace["followup"]["observed_through"])
        self.assertIsNone(trace["followup"]["reported_faults"])
        self.assertEqual(trace["acceptance_evidence_ids"], [])
        self.assertEqual(trace["followup"]["evidence_ids"], c["followup"]["evidence_ids"])
        self.assertTrue(any(e["minutes"] is None for e in trace["effort"]))

    def test_report_is_detached_from_caller_mutation(self):
        report = self.report()
        frozen = json.dumps(report, sort_keys=True)
        c = self.change()
        c["context"]["stack"] = "changed-after-analysis"
        c["acceptance_evidence_ids"].clear()
        c["followup"]["evidence_ids"].clear()
        c["coverage"]["author"]["basis"] = "changed"
        c["coverage"]["author"]["evidence_ids"].clear()
        c["effort"][0]["minutes"] = "999"
        c["effort"][0]["evidence_ids"].clear()
        c["practices"]["verification"]["evidence_ids"].clear()
        self.assertEqual(json.dumps(report, sort_keys=True), frozen)

    def test_analysis_does_not_mutate_input(self):
        before = copy.deepcopy(self.data)
        self.report()
        self.assertEqual(before, self.data)

    def test_decimal_input_trace_is_json_serializable(self):
        self.change()["effort"][0]["minutes"] = Decimal("0.123456")
        report = self.report()
        decoded = json.loads(json.dumps(report))
        r = next(x for x in decoded["changes"] if x["id"] == "ESS-A")
        e = next(x for x in r["source_trace"]["effort"] if x["stage"] == "understand")
        self.assertEqual(e["minutes"], "0.123456")

    def test_record_and_allocation_order_is_not_semantic_churn(self):
        before = self.report()
        self.data["changes"].reverse()
        self.data["evidence"].reverse()
        for c in self.data["changes"]:
            c["effort"].reverse()
        self.assertEqual(before, self.report())

    def test_rendered_trace_escapes_coverage_markup(self):
        self.change()["coverage"]["author"]["basis"] = "<element>basis</element>|next\nline"
        output = a.markdown(self.report())
        self.assertNotIn("<element>", output)
        self.assertIn("&lt;element&gt;basis&lt;/element&gt;&#124;next<br>line", output)

    def test_trace_links_resolve_to_retained_registry_ids(self):
        report = self.report()
        ids = {e["id"] for e in report["evidence"]}
        for row in report["changes"]:
            trace = row["source_trace"]
            lists = [trace["acceptance_evidence_ids"], trace["followup"]["evidence_ids"]]
            lists.extend(e["evidence_ids"] for e in trace["coverage"].values())
            lists.extend(e["evidence_ids"] for e in trace["effort"])
            for refs in lists:
                self.assertTrue(set(refs) <= ids)

    def test_cli_and_api_outputs_agree_in_actual_interpreter_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "cli"
            command = python_command() + [str(HERE / "ai_coding.py"), str(self.input_path), "--out", str(out)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads((out / "report.json").read_text(encoding="utf-8")), self.report())
            self.assertEqual((out / "report.md").read_text(encoding="utf-8"), a.markdown(self.report()))
            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            for name, digest in manifest.items():
                self.assertEqual(digest, hashlib.sha256((out / name).read_bytes()).hexdigest())

    def test_rehearsal_two_independent_locations_have_identical_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            second = Path(tmp) / "second-case"
            result = subprocess.run(python_command() + [str(HERE / "rehearse.py"), "--out", str(second)],
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            first = self.fixture_dir / "case"
            first_files = {str(p.relative_to(first)): p.read_bytes() for p in first.rglob("*") if p.is_file()}
            second_files = {str(p.relative_to(second)): p.read_bytes() for p in second.rglob("*") if p.is_file()}
            self.assertEqual(first_files, second_files)


if __name__ == "__main__":
    unittest.main()
