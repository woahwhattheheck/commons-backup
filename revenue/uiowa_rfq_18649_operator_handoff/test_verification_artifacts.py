"""Executable regression coverage for the existing verifier's stable artifacts.

All component data are fictional. No real University records or live services.
"""
import copy
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import verification_artifacts as artifacts
import verify_kit
import render_guide


def make_fixture(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    components = {
        "demo_pass": {"test_good.py": '''import os, sys, unittest
class T(unittest.TestCase):
    def test_one(self):
        print("work=" + os.getcwd())
        print("optimization=" + str(sys.flags.optimize))
        self.assertEqual(1 + 1, 2)
    def test_two(self):
        self.assertTrue(True)
'''},
        "demo_fail": {"test_bad.py": '''import unittest
class T(unittest.TestCase):
    def test_bad(self):
        self.fail("SYNTHETIC diagnostic: latency=2.750s on 2026-11-22")
'''},
        "demo_hollow": {"test_empty.py": "VALUE = 1\n"},
        "demo_runner": {"run.py": '''import os, sys
print("work=" + os.getcwd())
for item in sys.argv[1:]:
    print("input=" + item)
print("measurement=2.750s; records=19; date=2026-11-22")
'''},
        "demo_doc": {"README.md": "# FICTIONAL rehearsal\nThis is not proof of execution.\n"},
        "demo_unmapped": {"README.md": "Not yet mapped.\n"},
    }
    for component, files in components.items():
        directory = root / component
        directory.mkdir()
        for name, text in files.items():
            (directory / name).write_text(text, encoding="utf-8")
    mapped = [{"lane": name, "role": "fictional test component"}
              for name in components if name != "demo_unmapped"]
    mapped.append({"lane": "demo_missing", "role": "not supplied"})
    next(item for item in mapped if item["lane"] == "demo_runner")["runner"] = {
        "cmd": ["python3", "run.py", "{ROOT}", "{REPO}", "{OUT}/result.json"]}
    return {"manifest_version": "synthetic-v1", "lane_prefix": "demo_",
            "phases": [{"id": "rehearsal", "order": 1, "title": "Fictional rehearsal",
                        "purpose": "Fictional verifier regression only", "operator_does": [],
                        "components": mapped}]}


def row(report, name):
    return next(item for item in report["components"] if item["component"] == name)


def dump_views(report, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    artifacts.write_json(report, str(destination / "status.json"))
    verify_kit.write_csv(report, str(destination / "status.csv"))
    verify_kit.write_md(report, str(destination / "verification.md"))
    return {name: (destination / name).read_bytes()
            for name in ("status.json", "status.csv", "verification.md")}


class Normalization(unittest.TestCase):
    def test_known_roots_are_longest_first(self):
        text = '"/tmp/repo/revenue/a.txt" /tmp/repo/README.md'
        self.assertEqual(artifacts.normalize_output(text, [("REPO", "/tmp/repo"),
                                                          ("ROOT", "/tmp/repo/revenue")]),
                         '"{ROOT}/a.txt" {REPO}/README.md')

    def test_sibling_and_embedded_paths_are_not_scrubbed(self):
        text = "/tmp/kit-other/a /other/tmp/kit/a"
        self.assertEqual(artifacts.normalize_output(text, [("ROOT", "/tmp/kit")]), text)

    def test_root_slash_and_unrelated_temp_paths_remain(self):
        text = "/tmp/application-data/file.json"
        self.assertEqual(artifacts.normalize_output(text, [("ROOT", "/")]), text)

    def test_only_exact_unittest_summary_timing_is_removed(self):
        text = "Ran 2 tests in 0.123s\nlatency=0.123s\nstarted 2026-11-22\nRan 1 test in 1.000s"
        output = artifacts.normalize_output(text, [])
        self.assertEqual(output.count("timing in raw run metadata"), 2)
        self.assertIn("latency=0.123s\nstarted 2026-11-22", output)

    def test_similar_application_statement_survives(self):
        text = "application: Ran 2 tests in 0.123s\nRan 2 tests in 0.123s (budget exceeded)"
        self.assertEqual(artifacts.normalize_output(text, []), text)

    def test_normalization_precedes_tail_truncation(self):
        a = ("prefix=" + "/tmp/short" + "/x " ) * 150
        b = ("prefix=" + "/tmp/a-much-longer-known-copy" + "/x ") * 150
        first = artifacts.capture_output(a, "cmd", [("WORK", "/tmp/short")])
        second = artifacts.capture_output(b, "cmd", [("WORK", "/tmp/a-much-longer-known-copy")])
        self.assertEqual(first["semantic_output_tail"], second["semantic_output_tail"])
        self.assertEqual(first["semantic_output_sha256"], second["semantic_output_sha256"])
        self.assertNotEqual(first["output_sha256"], second["output_sha256"])
        self.assertEqual(first["output_full"], a)

    def test_changed_diagnostic_before_tail_changes_digest(self):
        a = artifacts.capture_output("ERROR A\n" + "z" * 1500, "cmd", [])
        b = artifacts.capture_output("ERROR B\n" + "z" * 1500, "cmd", [])
        self.assertEqual(a["semantic_output_tail"], b["semantic_output_tail"])
        self.assertNotEqual(a["semantic_output_sha256"], b["semantic_output_sha256"])

    def test_canonical_digest_is_independent_of_dictionary_order(self):
        self.assertEqual(artifacts.canonical_digest({"a": 1, "b": 2}),
                         artifacts.canonical_digest({"b": 2, "a": 1}))


class ActualExecutions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="verifier-regression-")
        cls.home = Path(cls.temp.name)
        cls.root_a = cls.home / "short" / "revenue"
        cls.root_b = cls.home / "much-longer-relocated-checkout" / "revenue"
        cls.manifest = make_fixture(cls.root_a)
        make_fixture(cls.root_b)
        cls.before = artifacts.tree_digest(str(cls.root_a))
        cls.a = verify_kit.survey(str(cls.root_a), cls.manifest, timeout=10,
                                 repo_root=str(cls.root_a.parent))
        cls.b = verify_kit.survey(str(cls.root_b), cls.manifest, timeout=10,
                                 repo_root=str(cls.root_b.parent))
        cls.views_a = dump_views(cls.a, cls.home / "outputs-a")
        cls.views_b = dump_views(cls.b, cls.home / "outputs-b")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_three_artifacts_are_byte_identical_across_relocated_roots(self):
        self.assertEqual(self.views_a, self.views_b)

    def test_raw_records_retain_different_paths_and_timing(self):
        run_a = row(self.a, "demo_runner")["runs"][0]
        run_b = row(self.b, "demo_runner")["runs"][0]
        self.assertIn(str(self.root_a), run_a["command"])
        self.assertIn(str(self.root_b), run_b["output_full"])
        self.assertNotEqual(run_a["command"], run_b["command"])
        self.assertIn("duration_s", run_a)
        self.assertIn("generated_at_utc", self.a)
        self.assertEqual(run_a["argv"][0], sys.executable)
        self.assertIn("verify_kit_", run_a["cwd"])

    def test_semantic_projection_is_pure_and_idempotent(self):
        before = copy.deepcopy(self.a)
        semantic = artifacts.semantic_report(self.a)
        self.assertEqual(self.a, before)
        self.assertEqual(artifacts.semantic_report(semantic), semantic)
        self.assertNotIn("generated_at_utc", semantic)
        for component in semantic["components"]:
            for run in component["runs"]:
                self.assertNotIn("duration_s", run)
                self.assertNotIn("output_full", run)
                self.assertNotIn("argv", run)
                self.assertNotIn("cwd", run)

    def test_real_diagnostics_remain_visible(self):
        text = self.views_a["verification.md"].decode()
        self.assertIn("SYNTHETIC diagnostic: latency=2.750s on 2026-11-22", text)
        self.assertIn("FAILED", text)
        self.assertIn("measurement=2.750s; records=19; date=2026-11-22", text)
        self.assertIn("normalized observation", text)

    def test_expected_statuses_are_preserved(self):
        expected = {"demo_pass": "WORKING", "demo_fail": "DRAFT", "demo_hollow": "DRAFT",
                    "demo_runner": "WORKING", "demo_doc": "DRAFT", "demo_missing": "MISSING",
                    "demo_unmapped": "UNMAPPED"}
        self.assertEqual({item["component"]: item["status"] for item in self.a["components"]}, expected)
        self.assertEqual(row(self.a, "demo_pass")["tests_ran"], 2)
        self.assertEqual(row(self.a, "demo_hollow")["tests_ran"], 0)

    def test_no_source_file_changed_after_execution(self):
        self.assertEqual(self.before, artifacts.tree_digest(str(self.root_a)))

    def test_changed_source_and_failure_change_stable_artifacts(self):
        root = self.home / "changed" / "revenue"
        manifest = make_fixture(root)
        test = root / "demo_fail" / "test_bad.py"
        test.write_text(test.read_text().replace("latency=2.750s", "latency=3.125s"))
        changed = verify_kit.survey(str(root), manifest, timeout=10, repo_root=str(root.parent))
        self.assertNotEqual(row(changed, "demo_fail")["source_sha256"],
                            row(self.a, "demo_fail")["source_sha256"])
        self.assertIn("latency=3.125s", dump_views(changed, self.home / "changed-out")["verification.md"].decode())

    def test_no_exec_remains_unproven(self):
        result = verify_kit.survey(str(self.root_a), self.manifest, execute=False)
        self.assertFalse(result["executed_checks"])
        self.assertNotIn("WORKING", [item["status"] for item in result["components"]])
        artifacts.semantic_report(result)

    def test_legacy_truncated_run_cannot_claim_reproducibility(self):
        legacy = copy.deepcopy(self.a)
        del row(legacy, "demo_pass")["runs"][0]["semantic_output_tail"]
        with self.assertRaisesRegex(ValueError, "legacy run"):
            artifacts.semantic_report(legacy)

    def test_manifest_content_changes_binding(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["phases"][0]["components"][0]["role"] = "changed role"
        result = verify_kit.survey(str(self.root_a), manifest, execute=False)
        self.assertNotEqual(self.a["manifest_sha256"], result["manifest_sha256"])

    def test_optimization_is_propagated_to_actual_child(self):
        run = row(self.a, "demo_pass")["runs"][0]
        self.assertEqual(run["python_optimization"], sys.flags.optimize)
        self.assertIn("optimization=" + str(sys.flags.optimize), run["output_full"])
        if sys.flags.optimize:
            self.assertEqual(run["argv"][1], "-" + "O" * sys.flags.optimize)
            self.assertIn("python3 -" + "O" * sys.flags.optimize, run["command"])

    def test_source_binding_includes_fixture_content_but_excludes_caches(self):
        root = self.home / "digest-only"
        root.mkdir()
        (root / "fixture.txt").write_text("first")
        first = artifacts.tree_digest(str(root))
        (root / "__pycache__").mkdir()
        (root / "__pycache__" / "ignore.pyc").write_bytes(b"noise")
        self.assertEqual(first, artifacts.tree_digest(str(root)))
        (root / "fixture.txt").write_text("second")
        self.assertNotEqual(first, artifacts.tree_digest(str(root)))

    def test_cli_emits_stable_and_raw_records_separately(self):
        manifest_path = self.home / "fixture-manifest.json"
        manifest_path.write_text(json.dumps(self.manifest))
        output = self.home / "cli"
        output.mkdir()
        command = [sys.executable] + (["-O"] if sys.flags.optimize else []) + [
            str(HERE / "verify_kit.py"), "--root", str(self.root_a),
            "--manifest", str(manifest_path), "--out-json", str(output / "stable.json"),
            "--out-run-json", str(output / "raw.json"), "--out-csv", str(output / "stable.csv"),
            "--out-md", str(output / "stable.md"), "--timeout", "10", "--quiet"]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=20)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        stable = json.loads((output / "stable.json").read_text())
        raw = json.loads((output / "raw.json").read_text())
        self.assertEqual(stable, artifacts.semantic_report(raw))
        self.assertIn(str(self.root_a), (output / "raw.json").read_text())
        self.assertNotIn(str(self.root_a), (output / "stable.json").read_text())
        self.assertNotIn("verify_kit_out_", (output / "stable.csv").read_text())

    def test_cli_refuses_raw_and_stable_destination_collision(self):
        destination = str(self.home / "must-not-be-overwritten.json")
        with self.assertRaises(SystemExit) as caught:
            verify_kit.main(["--out-json", destination, "--out-run-json", destination])
        self.assertEqual(caught.exception.code, 2)
        self.assertFalse(Path(destination).exists())

    def test_timeout_is_retained_in_semantic_output(self):
        root = self.home / "timeout"
        root.mkdir()
        (root / "test_timeout.py").write_text("import time\ntime.sleep(5)\n")
        run = verify_kit.run_one_check(str(root), "test_timeout.py", 0.1)
        self.assertTrue(run["timed_out"])
        self.assertIsNone(run["exit_code"])
        self.assertEqual(run["tests_ran"], 0)
        self.assertEqual(run["semantic_output_sha256"], hashlib.sha256(b"").hexdigest())

    def test_guide_renderer_accepts_both_raw_and_semantic_records(self):
        raw_guide = render_guide.render(self.manifest, self.a, [])
        self.assertIn(self.a["generated_at_utc"], raw_guide)
        semantic_guide = render_guide.render(self.manifest, artifacts.semantic_report(self.a), [])
        self.assertIn("normalized observation format", semantic_guide)
        self.assertIn("separate --out-run-json record", semantic_guide)
        self.assertNotIn(self.a["generated_at_utc"], semantic_guide)

    def test_normalized_guide_also_matches_across_locations(self):
        a = render_guide.render(self.manifest, artifacts.semantic_report(self.a), [])
        b = render_guide.render(self.manifest, artifacts.semantic_report(self.b), [])
        self.assertEqual(a, b)
        self.assertIn("not a maturity rating", a)

    def test_csv_counts_and_reasons_are_not_reinvented(self):
        rows = list(csv.DictReader(self.views_a["status.csv"].decode().splitlines()))
        self.assertEqual(len(rows), len(self.a["components"]))
        self.assertEqual(sum(self.a["counts"].values()), len(rows))
        self.assertTrue(all(item["status"] in {"WORKING", "DRAFT", "MISSING", "UNMAPPED"}
                            for item in rows))
        self.assertIn("{OUT}", next(item for item in rows if item["component"] == "demo_runner")["reason"])


if __name__ == "__main__":
    unittest.main()
