"""Executable UIOWA-076 contract and semantic regression suite (stdlib only)."""
from __future__ import annotations
import contextlib
import copy
import importlib.util
import io
import hashlib
import json
import runpy
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from pathlib import Path

def _load_sibling(name):
    """Keep aggregate discovery independent of generic sys.modules entries."""
    path = Path(__file__).resolve().with_name(name + ".py")
    spec = importlib.util.spec_from_file_location("_uiowa076_test_" + name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load test dependency: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


a = _load_sibling("ai_coding")
rehearse = _load_sibling("rehearse")


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.input = rehearse.build_fixture(self.base / "packet")
        self.root = self.input.parent
        self.data = json.loads(self.input.read_text(encoding="utf-8"))

    def run_data(self):
        return a.analyze(self.data, self.root)

    def change(self, cid="ESS-A"):
        return next(c for c in self.data["changes"] if c["id"] == cid)

    def result(self, cid="ESS-A"):
        return next(c for c in self.run_data()["changes"] if c["id"] == cid)

    def pair(self, pid="PAIR-ESS"):
        return next(p for p in self.run_data()["comparisons"] if p["pair_id"] == pid)

    def reject(self, pattern):
        with self.assertRaisesRegex(a.InputError, pattern):
            self.run_data()

    def test_aggregate_import_ignores_generic_cached_modules(self):
        unrelated = {name: types.ModuleType(name) for name in ("ai_coding", "rehearse")}
        original_path = list(sys.path)
        with patch.dict(sys.modules, unrelated):
            namespace = runpy.run_path(str(Path(__file__).resolve()), run_name="aggregate_076_probe")
            self.assertIsNot(namespace["a"], unrelated["ai_coding"])
            self.assertIsNot(namespace["rehearse"], unrelated["rehearse"])
            self.assertTrue(callable(namespace["rehearse"].build_fixture))
            self.assertEqual(Path(namespace["a"].__file__).resolve(), Path(a.__file__).resolve())
            self.assertIs(sys.modules["ai_coding"], unrelated["ai_coding"])
            self.assertIs(sys.modules["rehearse"], unrelated["rehearse"])
        self.assertEqual(sys.path, original_path)

    def test_imported_rehearsal_uses_its_own_analyzer(self):
        unrelated = types.ModuleType("ai_coding")
        out = self.base / "embedded-rehearsal"
        original_path = list(sys.path)
        stream = io.StringIO()
        with patch.dict(sys.modules, {"ai_coding": unrelated}), contextlib.redirect_stdout(stream):
            self.assertEqual(rehearse.main(["--out", str(out)]), 0)
            self.assertIs(sys.modules["ai_coding"], unrelated)
        self.assertEqual(sys.path, original_path)
        self.assertIn("comparable=2 sources=77", stream.getvalue())
        self.assertTrue((out / "reports/report.json").is_file())

    def test_package_mode_rehearsal_from_repository_root(self):
        root = Path(__file__).resolve().parents[2]
        out = self.base / "package-rehearsal"
        run = subprocess.run([sys.executable, "-m", "revenue.uiowa_rfq_18649_ai_coding.rehearse",
                              "--out", str(out)], cwd=root, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("comparable=2 sources=77", run.stdout)

    def test_missing_sibling_fails_before_creating_packet(self):
        isolated = self.base / "isolated"
        isolated.mkdir()
        script = isolated / "rehearse.py"
        script.write_bytes(Path(rehearse.__file__).read_bytes())
        out = self.base / "missing-analyzer-packet"
        run = subprocess.run([sys.executable, str(script), "--out", str(out)],
                             cwd=isolated, capture_output=True, text=True)
        self.assertEqual(run.returncode, 2)
        self.assertIn("REHEARSAL ERROR", run.stderr)
        self.assertFalse(out.exists())

    def test_worked_contrasts(self):
        report = self.run_data()
        self.assertEqual(len(report["evidence"]), 77)
        ess, iam, ris = report["comparisons"]
        self.assertEqual((ess["author_delta_minutes"], ess["lifecycle_delta_minutes"], ess["faults_delta"]), ("-67", "-70", 0))
        self.assertEqual((ris["author_delta_minutes"], ris["lifecycle_delta_minutes"], ris["faults_delta"]), ("-45", "90", 2))
        self.assertFalse(iam["comparable"])
        self.assertIsNone(iam["lifecycle_delta_minutes"])

    def test_complete_and_recorded_effort_are_distinct(self):
        row = self.result("IAM-A")
        self.assertEqual(row["recorded_effort_minutes"], "34")
        self.assertIsNone(row["delivery_effort_minutes"])
        self.assertIsNone(row["lifecycle_effort_minutes"])
        self.assertIsNone(row["comparable_faults"])

    def test_wall_clock_is_not_person_effort(self):
        row = self.result("RIS-A")
        self.assertEqual(row["wall_delivery_minutes"], "90")
        self.assertEqual(row["delivery_effort_minutes"], "170")

    def test_decimal_addition_is_exact(self):
        logs = self.change()["effort"]
        logs[0]["minutes"] = "0.1"
        extra = copy.deepcopy(logs[0]); extra.update(id="ESS-A-extra", minutes="0.2")
        logs.append(extra)
        self.assertEqual(self.result()["stages"]["understand"]["complete_minutes"], "0.3")

    def test_unknown_is_not_zero(self):
        self.change()["effort"][0]["minutes"] = None
        row = self.result()
        self.assertIsNone(row["lifecycle_effort_minutes"])
        self.assertEqual(row["stages"]["understand"]["recorded_minutes"], "0")
        self.assertIn("missing_effort_amount", row["stages"]["understand"]["reasons"])

    def test_empty_stage_requires_supported_complete_coverage_for_zero(self):
        c = self.change(); c["effort"] = [e for e in c["effort"] if e["stage"] != "repair"]
        self.assertEqual(self.result()["stages"]["repair"]["complete_minutes"], "0")
        c["coverage"]["repair"]["state"] = "unknown"
        self.assertIsNone(self.result()["stages"]["repair"]["complete_minutes"])

    def test_coverage_without_evidence_is_incomplete(self):
        self.change()["coverage"]["author"]["evidence_ids"] = []
        self.assertIsNone(self.result()["stages"]["author"]["complete_minutes"])
        self.assertFalse(self.pair()["comparable"])

    def test_interview_statement_not_promoted_to_demonstration(self):
        p = self.result("IAM-A")["practices"]["understanding"]
        self.assertEqual((p["claimed_state"], p["effective_state"], p["support"]), ("demonstrated", "stated", "statement_only"))

    def test_unsupported_gap_is_unknown_not_failed(self):
        p = self.change()["practices"]["verification"]
        p.update(state="gap", evidence_ids=[])
        self.assertEqual(self.result()["practices"]["verification"]["effective_state"], "unknown")

    def test_incomplete_followup_preserves_reported_faults_not_comparability(self):
        self.change()["followup"]["observed_through"] = "2026-08-20T10:30:00Z"
        row = self.result()
        self.assertEqual(row["reported_faults"], 0)
        self.assertIsNone(row["comparable_faults"])
        self.assertIsNone(row["lifecycle_effort_minutes"])
        self.assertEqual(row["delivery_effort_minutes"], "75")

    def test_longer_observation_window_cannot_pose_as_thirty_days(self):
        self.change()["followup"]["observed_through"] = "2026-09-05T10:30:00Z"
        self.assertFalse(self.result()["followup_window_exact"])
        self.assertFalse(self.pair()["comparable"])

    def test_unknown_fault_count_never_becomes_zero(self):
        self.change()["followup"]["reported_faults"] = None
        self.assertFalse(self.pair()["comparable"])
        self.assertIsNone(self.pair()["faults_delta"])

    def test_context_difference_suppresses_all_contrasts(self):
        self.change()["context"]["stack"] = "different-runtime"
        pair = self.pair()
        self.assertIn("stack_mismatch", pair["reasons"])
        self.assertIsNone(pair["author_delta_minutes"])

    def test_missing_comparison_arm_is_visible(self):
        self.data["changes"] = [self.change()]
        self.assertEqual(self.pair()["reasons"], ["missing_comparison_arm"])

    def test_duplicate_mode_is_not_silently_selected(self):
        self.change("ESS-M")["mode"] = "assisted"
        self.reject("duplicate comparison mode")

    def test_duplicate_allocation_is_rejected(self):
        self.change()["effort"].append(copy.deepcopy(self.change()["effort"][0]))
        self.reject("duplicate effort ID")

    def test_duplicate_change_is_rejected(self):
        self.change("ESS-M")["id"] = "ESS-A"
        self.reject("duplicate change ID")

    def test_unresolved_and_duplicate_evidence_references(self):
        c = self.change(); original = c["acceptance_evidence_ids"][:]
        for values, pattern in [(["NOT-FOUND"], "unresolved"), (original*2, "duplicate evidence")]:
            with self.subTest(values=values):
                c["acceptance_evidence_ids"] = values
                self.reject(pattern)

    def test_bad_effort_quantities_fail_as_input_errors(self):
        for value in [True, -1, "NaN", "Infinity", "0.0000001", "1000000001", [], {}, ""]:
            with self.subTest(value=value):
                self.change()["effort"][0]["minutes"] = value
                self.reject("decimal|nonnegative|magnitude")

    def test_malformed_enum_is_input_error_not_type_error(self):
        self.change()["group"] = []
        self.reject("unknown group")

    def test_chronology_and_timezone_are_validated(self):
        for value in ["2026-07-31T10:00:00Z", "2027-01-01T00:00:00Z", "2026-08-01T10:30:00", "", False]:
            with self.subTest(value=value):
                self.change()["accepted_at"] = value
                self.reject("chronology|timezone|blank|timestamp")

    def test_equivalent_offsets_produce_equal_duration(self):
        self.change()["accepted_at"] = "2026-08-01T06:30:00-04:00"
        self.assertEqual(self.result()["wall_delivery_minutes"], "90")
        self.assertTrue(self.result()["followup_window_exact"])

    def test_future_source_observation_is_rejected(self):
        self.data["evidence"][0]["observed_at"] = "2027-01-01T00:00:00Z"
        self.reject("future evidence")

    def test_source_tamper_is_not_a_new_finding(self):
        path = self.root / self.data["evidence"][0]["path"]
        path.write_text(path.read_text(encoding="utf-8")+"changed\n", encoding="utf-8")
        self.reject("digest mismatch")

    def test_invalid_locators_fail(self):
        for start, end in [(0, 1), (2, 1), (1, 100000), (True, 2)]:
            with self.subTest(start=start, end=end):
                self.data["evidence"][0].update(start_line=start, end_line=end)
                self.reject("invalid line locator")

    def test_missing_and_external_source_paths_fail(self):
        for value, pattern in [("sources/absent.md", "missing"), ("../../external.md", "escapes"), ("/external.md", "relative")]:
            with self.subTest(path=value):
                self.data["evidence"][0]["path"] = value
                self.reject(pattern)

    def test_symlink_escape_fails(self):
        outside = self.base / "outside.md"; outside.write_text("not part of packet")
        link = self.root / "sources" / "escape.md"
        try:
            link.symlink_to(outside)
        except OSError:
            self.skipTest("symlink privilege unavailable")
        self.data["evidence"][0]["path"] = "sources/escape.md"
        self.reject("escapes")

    def test_unicode_source_path_and_exact_excerpt(self):
        old = self.root / "sources/change_histories.md"
        new = old.with_name("hístories-研究.md"); old.rename(new)
        for ev in self.data["evidence"]:
            ev["path"] = "sources/" + new.name
        report = self.run_data()
        ev = report["evidence"][0]
        self.assertEqual(ev["excerpt"], "\n".join(new.read_text(encoding="utf-8").splitlines()[ev["start_line"]-1:ev["end_line"]]))

    def test_duplicate_keys_and_nonfinite_json_fail(self):
        for text in ['{"x":1,"x":2}', '{"x":NaN}']:
            self.input.write_text(text)
            with self.assertRaises(a.InputError):
                a.load_report(self.input)

    def test_unknown_schema_and_real_data_flag_fail(self):
        self.data["synthetic"] = False
        self.reject("explicit synthetic")
        self.data["synthetic"] = True; self.data["schema_version"] = "2.0"
        self.reject("unsupported schema")

    def test_deterministic_outputs_and_manifest(self):
        report = self.run_data()
        for name in ["one", "two"]:
            a.write_outputs(report, self.base/name)
        for p in (self.base/"one").iterdir():
            self.assertEqual(p.read_bytes(), (self.base/"two"/p.name).read_bytes())
        manifest = json.loads((self.base/"one/manifest.json").read_text(encoding="utf-8"))
        for name, digest in manifest.items():
            self.assertEqual(digest, hashlib.sha256((self.base/"one"/name).read_bytes()).hexdigest())

    def test_input_order_does_not_change_assessments(self):
        expected = self.run_data()
        self.data["changes"].reverse(); self.data["evidence"].reverse()
        self.assertEqual(expected, self.run_data())

    def test_cli_success_and_failed_input_no_output(self):
        script = Path(a.__file__)
        out = self.base/"cli"
        result = subprocess.run([sys.executable, str(script), str(self.input), "--out", str(out)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("comparable=2 sources=77", result.stdout)
        self.input.write_text("{malformed")
        badout = self.base/"badout"
        result = subprocess.run([sys.executable, str(script), str(self.input), "--out", str(badout)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(badout.exists())

    def test_rehearsal_never_resets_existing_files(self):
        sentinel = self.base/"sentinel"; sentinel.write_text("keep me")
        with self.assertRaisesRegex(ValueError, "empty"):
            rehearse.build_fixture(self.base)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep me")

    def test_input_source_alias_is_not_overwritten(self):
        renamed = self.root/"report.json"
        self.input.rename(renamed)
        original = renamed.read_bytes()
        self.assertEqual(a.main([str(renamed), "--out", str(self.root)]), 2)
        self.assertEqual(renamed.read_bytes(), original)

    def test_untrusted_markup_is_escaped(self):
        self.change()["practices"]["verification"]["rationale"] = '<script>bad</script>|cell\nnext'
        rendered = a.markdown(self.run_data())
        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertIn("&#124;cell<br>next", rendered)


if __name__ == "__main__":
    unittest.main()
