"""Operator-input regressions, ZZ-KESTREL-62D; no replacement scoring policy."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import method

HERE = Path(__file__).resolve().parent


def one(**changes):
    rec = {"recommendation_id": "REC-SYN-A", "effort_days_low": 2,
           "effort_days_high": 4, "effects": {"quality": 1},
           "prerequisites": [], "declared_horizon": None}
    rec.update(changes)
    return {"synthetic": True, "recommendations": [rec]}


class InputShapes(unittest.TestCase):
    def test_invalid_document_shapes(self):
        for doc in (None, [], 0, {"recommendations": {}}, {"recommendations": [None]},
                    {"recommendations": []}, dict(one(), parameters=[])):
            with self.subTest(doc=doc), self.assertRaises(method.MethodError):
                method.Backlog(doc)

    def test_invalid_effort_does_not_become_quick_win(self):
        for value in (True, False, -1, float("nan"), float("inf"), "2", [], {}):
            for field in ("effort_days_low", "effort_days_high"):
                with self.subTest(value=value, field=field), self.assertRaises(method.MethodError):
                    method.Backlog(one(**{field: value}))

    def test_invalid_effects_and_thresholds_are_diagnosed(self):
        for value in (True, -1, float("nan"), float("inf"), "2", [], {}):
            with self.subTest(effect=value), self.assertRaises(method.MethodError):
                method.Backlog(one(effects={"quality": value}))
            with self.subTest(parameter=value), self.assertRaises(method.MethodError):
                method.Backlog(dict(one(), parameters={"quick_win_max_effort_days": value}))

    def test_malformed_references_are_not_iterated_as_text(self):
        for change in ({"prerequisites": "REC-SYN-B"}, {"prerequisites": [None]},
                       {"recommendation_id": []}, {"recommendation_id": " "},
                       {"declared_horizon": []}, {"declared_horizon_reason": True},
                       {"effects": []}):
            with self.subTest(change=change), self.assertRaises(method.MethodError):
                method.Backlog(one(**change))

    def test_zero_and_fractional_estimates_remain_usable(self):
        b = method.Backlog(one(effort_days_low=0, effort_days_high=0.5))
        self.assertEqual(b.results[0]["effort_days_low"], 0)
        self.assertEqual(b.results[0]["proposed_horizon"], "0-90")

    def test_partial_estimate_retains_known_bound(self):
        for lo, hi in ((2, None), (None, 4)):
            with self.subTest(lo=lo, hi=hi):
                b = method.Backlog(one(effort_days_low=lo, effort_days_high=hi))
                row = b.results[0]
                self.assertEqual(row["effort_days_low"], lo if lo is not None else method.UNKNOWN)
                self.assertEqual(row["effort_days_high"], hi if hi is not None else method.UNKNOWN)
                self.assertEqual(row["proposed_horizon"], method.NEEDS_ESTIMATE)
                self.assertIn("REC-SYN-A", b.by_horizon()[method.NEEDS_ESTIMATE])
                self.assertIn("UNKNOWN", method.render(b))

    def test_input_and_declarations_are_not_mutated(self):
        doc = one(declared_horizon="180+", declared_horizon_reason="Human decision")
        saved = copy.deepcopy(doc)
        b = method.Backlog(doc)
        method.render(b)
        self.assertEqual(doc, saved)
        self.assertEqual(b.results[0]["declared_horizon"], "180+")
        self.assertEqual(b.results[0]["declared_horizon_reason"], "Human decision")

    def test_invalid_horizon_does_not_mean_unsized(self):
        for value in ("soon", "", "UNKNOWN"):
            with self.subTest(value=value):
                b = method.Backlog(one(declared_horizon=value))
                self.assertEqual(b.by_horizon()[method.INVALID_HORIZON], ["REC-SYN-A"])
                self.assertEqual(b.by_horizon()[method.NEEDS_ESTIMATE], [])
                self.assertIn("UNKNOWN_HORIZON_VALUE", [v["code"] for v in b.violations])

    def test_sized_unassigned_and_unsized_are_distinct(self):
        doc = one()
        doc["recommendations"].append({"recommendation_id": "REC-SYN-B"})
        b = method.Backlog(doc)
        self.assertEqual(b.by_horizon()[method.UNASSIGNED], ["REC-SYN-A"])
        self.assertEqual(b.by_horizon()[method.NEEDS_ESTIMATE], ["REC-SYN-B"])
        self.assertEqual(sum(map(len, b.by_horizon().values())), 2)

    def test_unsized_dangling_reference_is_visible(self):
        b = method.Backlog(one(effort_days_low=None, effort_days_high=None,
                              prerequisites=["MISSING"]))
        self.assertEqual([v["code"] for v in b.violations], ["DANGLING_PREREQUISITE"])
        self.assertEqual(b.results[0]["proposed_horizon"], method.NEEDS_ESTIMATE)

    def test_declaration_only_dependency_policy_is_preserved(self):
        doc = {"recommendations": [
            one(recommendation_id="A", effort_days_low=60, effort_days_high=90)["recommendations"][0],
            one(recommendation_id="B", prerequisites=["A"])["recommendations"][0],
            one(recommendation_id="C", prerequisites=["B"])["recommendations"][0]]}
        b = method.Backlog(doc)
        self.assertEqual([r["proposed_horizon"] for r in b.results], ["180+", "90-180", "90-180"])
        self.assertIn("not a jointly feasible transitive schedule", method.render(b))

    def test_deep_dependency_paths_do_not_depend_on_recursion_limit(self):
        recs = [{"recommendation_id": str(i), "prerequisites": [str(i+1)] if i < 1049 else []}
                for i in range(1050)]
        b = method.Backlog({"recommendations": recs})
        self.assertEqual(b.violations, [])
        b.by_id["1049"]["prerequisites"] = ["1047"]
        self.assertEqual(b._cycle_from("0"), ["1047", "1048", "1049", "1047"])


class OperatorCli(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "edited.json"
        self.source.write_text(json.dumps(one()), encoding="utf-8")

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(HERE / "method.py"), *args],
                              cwd=self.root, capture_output=True, text=True, timeout=20)

    def test_relative_input_json_is_parseable_and_source_unchanged(self):
        original = self.source.read_bytes()
        p = self.run_cli("--input", "edited.json", "--json")
        self.assertEqual(p.returncode, 0, p.stderr)
        data = json.loads(p.stdout)
        self.assertEqual(data["by_horizon"]["UNASSIGNED"], ["REC-SYN-A"])
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(list(self.root.iterdir()), [self.source])

    def test_repeat_execution_is_byte_identical(self):
        a = self.run_cli("--input", "edited.json", "--json")
        b = self.run_cli("--input", "edited.json", "--json")
        self.assertEqual(a.returncode, 0, a.stderr)
        self.assertEqual((a.stdout, a.stderr), (b.stdout, b.stderr))

    def test_default_backlog_is_independent_of_working_directory(self):
        p = self.run_cli("--check")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("items=9 violations=0 disagreements=2", p.stderr)

    def test_violation_is_exit_one_with_usable_json(self):
        self.source.write_text(json.dumps(one(effort_days_low=None, effort_days_high=None,
                                             prerequisites=["MISSING"])))
        p = self.run_cli("--input", "edited.json", "--json")
        self.assertEqual(p.returncode, 1, p.stderr)
        self.assertEqual(json.loads(p.stdout)["violations"][0]["code"], "DANGLING_PREREQUISITE")

    def test_invalid_json_is_exit_two_without_outputs(self):
        self.source.write_text('{"recommendations":')
        p = self.run_cli("--input", "edited.json", "--outdir", "review")
        self.assertEqual(p.returncode, 2)
        self.assertNotIn("Traceback", p.stderr)
        self.assertFalse((self.root / "review").exists())
        self.assertEqual(p.stdout, "")

    def test_duplicate_keys_are_not_silently_overwritten(self):
        self.source.write_text('{"recommendations": [], "recommendations": []}')
        p = self.run_cli("--input", "edited.json", "--json")
        self.assertEqual(p.returncode, 2)
        self.assertIn("duplicate JSON key", p.stderr)

    def test_nonfinite_json_is_refused(self):
        self.source.write_text(json.dumps(one(effort_days_low=float("nan"))))
        p = self.run_cli("--input", "edited.json", "--json")
        self.assertEqual(p.returncode, 2)
        self.assertIn("non-finite JSON", p.stderr)

    def test_unreadable_and_invalid_utf8_inputs_are_diagnosed(self):
        for name in ("absent.json", "bad-utf8.json"):
            with self.subTest(name=name):
                (self.root / "bad-utf8.json").write_bytes(b"\xff")
                p = self.run_cli("--input", name, "--json")
                self.assertEqual(p.returncode, 2)
                self.assertNotIn("Traceback", p.stderr)

    def test_edited_render_uses_output_directory_not_committed_example(self):
        committed = (HERE / "29-prioritization-method.md").read_bytes()
        p = self.run_cli("--input", "edited.json", "--render", "--outdir", "review")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue((self.root / "review/29-prioritization-method.md").exists())
        self.assertEqual(json.loads((self.root / "review/horizons.json").read_text())["by_horizon"]["UNASSIGNED"], ["REC-SYN-A"])
        self.assertEqual((HERE / "29-prioritization-method.md").read_bytes(), committed)

    def test_edited_render_without_destination_preserves_example(self):
        committed = (HERE / "29-prioritization-method.md").read_bytes()
        p = self.run_cli("--input", "edited.json", "--render")
        self.assertEqual(p.returncode, 2)
        self.assertEqual((HERE / "29-prioritization-method.md").read_bytes(), committed)

    def test_mixed_json_output_flags_are_rejected_before_writing(self):
        p = self.run_cli("--input", "edited.json", "--json", "--outdir", "review")
        self.assertEqual(p.returncode, 2)
        self.assertFalse((self.root / "review").exists())
        self.assertEqual(p.stdout, "")

    def test_input_output_alias_preserves_source(self):
        alias = self.root / "horizons.json"
        alias.write_bytes(self.source.read_bytes())
        original = alias.read_bytes()
        p = self.run_cli("--input", "horizons.json", "--outdir", ".")
        self.assertEqual(p.returncode, 2)
        self.assertEqual(alias.read_bytes(), original)
        self.assertIn("aliases", p.stderr)

    def test_failed_replace_preserves_existing_report(self):
        report = self.root / "report.json"
        report.write_text("previous report")
        with mock.patch.object(method.os, "replace", side_effect=OSError("injected replacement failure")):
            with self.assertRaises(OSError):
                method._write_report(report, "new report", self.source)
        self.assertEqual(report.read_text(), "previous report")
        self.assertEqual(list(self.root.glob(".uiowa029-*")), [])

    def test_hardlink_and_symlink_source_aliases_are_refused(self):
        for link in ("hard", "soft"):
            with self.subTest(link=link):
                path = self.root / link
                if link == "hard":
                    os.link(self.source, path)
                else:
                    path.symlink_to(self.source)
                original = self.source.read_bytes()
                with self.assertRaises(method.MethodError):
                    method._write_report(path, "new report", self.source)
                self.assertEqual(self.source.read_bytes(), original)


if __name__ == "__main__":
    unittest.main(verbosity=2)
