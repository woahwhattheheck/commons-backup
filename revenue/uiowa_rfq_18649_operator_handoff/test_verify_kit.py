#!/usr/bin/env python3
"""Tests for the handoff verifier.

The thing under test is a claim-checker, so most of these tests are adversarial:
they build a component that lies, or breaks, or hangs, or is simply absent, and
assert the verifier refuses to call it WORKING.

Run:  python3 -m unittest test_verify_kit
"""

import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import verify_kit  # noqa: E402
import render_guide  # noqa: E402

FIXTURE_ROOT = os.path.join(HERE, "fixtures", "minikit")
FIXTURE_MANIFEST = os.path.join(HERE, "fixtures", "minikit_manifest.json")
REAL_MANIFEST = os.path.join(HERE, "kit_manifest.json")
UNKNOWNS = os.path.join(HERE, "university_inputs.csv")


def status_of(report, lane):
    for r in report["components"]:
        if r["component"] == lane:
            return r
    raise AssertionError("component %s not in report" % lane)


def write_lane(root, name, files):
    d = os.path.join(root, name)
    os.makedirs(d, exist_ok=True)
    for rel, body in files.items():
        p = os.path.join(d, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(body)
    return d


def manifest_for(lanes):
    return {
        "manifest_version": "test", "lane_prefix": "uiowa_rfq_18649_",
        "phases": [{"id": "p1", "order": 1, "title": "t", "purpose": "p", "operator_does": [],
                    "components": [{"lane": ln, "role": "r"} for ln in lanes]}],
    }


class FixtureGroundTruth(unittest.TestCase):
    """The classifier is checked against a fixture whose answers are known."""

    @classmethod
    def setUpClass(cls):
        with open(FIXTURE_MANIFEST, encoding="utf-8") as fh:
            cls.manifest = json.load(fh)
        cls.report = verify_kit.survey(FIXTURE_ROOT, cls.manifest, timeout=30)

    def test_passing_component_earns_working(self):
        r = status_of(self.report, "uiowa_rfq_18649_alpha")
        self.assertEqual(r["status"], verify_kit.WORKING)
        self.assertGreaterEqual(r["tests_ran"], 2)

    def test_failing_component_is_draft_despite_readme_claiming_success(self):
        readme = os.path.join(FIXTURE_ROOT, "uiowa_rfq_18649_bravo", "README.md")
        with open(readme, encoding="utf-8") as fh:
            text = fh.read()
        # The fixture's README asserts it works. The verifier must disagree.
        self.assertIn("production ready", text.lower())
        r = status_of(self.report, "uiowa_rfq_18649_bravo")
        self.assertEqual(r["status"], verify_kit.DRAFT)
        self.assertIn("did not pass", r["reason"])

    def test_document_only_component_is_draft_not_missing(self):
        r = status_of(self.report, "uiowa_rfq_18649_charlie")
        self.assertEqual(r["status"], verify_kit.DRAFT)
        self.assertEqual(r["kind"], "document")

    def test_unbuilt_component_is_missing(self):
        r = status_of(self.report, "uiowa_rfq_18649_delta")
        self.assertEqual(r["status"], verify_kit.MISSING)
        self.assertFalse(r["present"])

    def test_lane_absent_from_manifest_is_reported_not_dropped(self):
        r = status_of(self.report, "uiowa_rfq_18649_echo")
        self.assertEqual(r["status"], verify_kit.UNMAPPED)
        self.assertEqual(r["phase"], "unassigned")

    def test_counts_match_rows(self):
        c = self.report["counts"]
        self.assertEqual(sum(c.values()), len(self.report["components"]))


class HostileInputs(unittest.TestCase):
    """Each of these is a way a component can look fine and not be fine."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="vk_hostile_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_test_file_that_collects_zero_tests_is_not_working(self):
        # A module named test_*.py with no TestCase in it exits 0 under unittest
        # and prints "Ran 0 tests ... OK". That silent green must not be a pass.
        write_lane(self.tmp, "uiowa_rfq_18649_hollow", {
            "test_nothing.py": "VALUE = 1\n",
            "README.md": "# hollow\n",
        })
        rep = verify_kit.survey(self.tmp, manifest_for(["uiowa_rfq_18649_hollow"]), timeout=30)
        r = status_of(rep, "uiowa_rfq_18649_hollow")
        self.assertEqual(r["status"], verify_kit.DRAFT)
        self.assertEqual(r["tests_ran"], 0)
        self.assertIn("no tests were collected", r["reason"])

    def test_missing_dependency_is_named_not_swallowed(self):
        write_lane(self.tmp, "uiowa_rfq_18649_needsdep", {
            "test_dep.py": ("import unittest\nimport totally_not_installed_pkg\n\n"
                            "class T(unittest.TestCase):\n    def test_x(self):\n"
                            "        self.assertTrue(True)\n"),
            "requirements.txt": "totally_not_installed_pkg>=1\n",
        })
        rep = verify_kit.survey(self.tmp, manifest_for(["uiowa_rfq_18649_needsdep"]), timeout=30)
        r = status_of(rep, "uiowa_rfq_18649_needsdep")
        self.assertEqual(r["status"], verify_kit.DRAFT)
        self.assertIn("totally_not_installed_pkg", r["reason"])
        self.assertIn("missing dependency", r["reason"])

    def test_hanging_check_times_out_and_stays_draft(self):
        write_lane(self.tmp, "uiowa_rfq_18649_hang", {
            "test_slow.py": ("import time\nimport unittest\n\n"
                             "class T(unittest.TestCase):\n    def test_slow(self):\n"
                             "        time.sleep(30)\n"),
        })
        rep = verify_kit.survey(self.tmp, manifest_for(["uiowa_rfq_18649_hang"]), timeout=2)
        r = status_of(rep, "uiowa_rfq_18649_hang")
        self.assertEqual(r["status"], verify_kit.DRAFT)
        self.assertTrue(any(run["timed_out"] for run in r["runs"]))
        self.assertIn("timeout", r["reason"])

    def test_survey_of_nonexistent_root_does_not_crash_and_reports_missing(self):
        gone = os.path.join(self.tmp, "no_such_dir")
        rep = verify_kit.survey(gone, manifest_for(["uiowa_rfq_18649_anything"]), timeout=5)
        r = status_of(rep, "uiowa_rfq_18649_anything")
        self.assertEqual(r["status"], verify_kit.MISSING)
        self.assertEqual(rep["counts"][verify_kit.WORKING], 0)

    def test_empty_lane_directory_is_draft_with_zero_files(self):
        os.makedirs(os.path.join(self.tmp, "uiowa_rfq_18649_empty"))
        rep = verify_kit.survey(self.tmp, manifest_for(["uiowa_rfq_18649_empty"]), timeout=5)
        r = status_of(rep, "uiowa_rfq_18649_empty")
        self.assertEqual(r["status"], verify_kit.DRAFT)
        self.assertEqual(r["inventory"]["files"], 0)

    def test_no_exec_mode_never_awards_working(self):
        rep = verify_kit.survey(FIXTURE_ROOT, manifest_for(["uiowa_rfq_18649_alpha"]),
                                timeout=10, execute=False)
        r = status_of(rep, "uiowa_rfq_18649_alpha")
        self.assertEqual(r["status"], verify_kit.DRAFT)
        self.assertIn("not executed", r["reason"])

    def test_source_lane_is_not_modified_by_a_test_with_side_effects(self):
        # Other seats own their directories. A test that writes next to itself must
        # write into the throwaway copy, never into the original.
        lane = write_lane(self.tmp, "uiowa_rfq_18649_writer", {
            "test_writes.py": (
                "import os\nimport unittest\n\n"
                "class T(unittest.TestCase):\n    def test_w(self):\n"
                "        p = os.path.join(os.path.dirname(os.path.abspath(__file__)),"
                " 'side_effect.txt')\n"
                "        open(p, 'w').write('x')\n"
                "        self.assertTrue(os.path.exists(p))\n"),
        })
        before = sorted(os.listdir(lane))
        rep = verify_kit.survey(self.tmp, manifest_for(["uiowa_rfq_18649_writer"]), timeout=30)
        self.assertEqual(status_of(rep, "uiowa_rfq_18649_writer")["status"], verify_kit.WORKING)
        self.assertEqual(sorted(os.listdir(lane)), before)
        self.assertFalse(os.path.exists(os.path.join(lane, "side_effect.txt")))

    def test_a_deliberately_broken_fixture_does_not_condemn_its_parent(self):
        # This lane itself ships a fixture component built to fail. If fixture
        # directories were collected as the parent's own checks, every kit that
        # carries a negative fixture would report itself broken.
        write_lane(self.tmp, "uiowa_rfq_18649_haskit", {
            "test_real.py": ("import unittest\n\nclass T(unittest.TestCase):\n"
                             "    def test_ok(self):\n        self.assertTrue(True)\n"),
            "fixtures/broken/test_bad.py": ("import unittest\n\nclass T(unittest.TestCase):\n"
                                            "    def test_fail(self):\n        self.fail('on purpose')\n"),
        })
        rep = verify_kit.survey(self.tmp, manifest_for(["uiowa_rfq_18649_haskit"]), timeout=30)
        r = status_of(rep, "uiowa_rfq_18649_haskit")
        self.assertEqual(r["status"], verify_kit.WORKING)
        self.assertEqual(r["check_files"], ["test_real.py"])
        # the fixture file is still counted in the inventory, just not run as a check
        self.assertGreaterEqual(r["inventory"]["py_files"], 2)

    def test_explicit_repo_root_overrides_the_parent_of_survey_root(self):
        # A survey root assembled elsewhere (e.g. a merged view) must still be able
        # to give a component runner the real repository root.
        write_lane(self.tmp, "uiowa_rfq_18649_echoesrepo", {
            "go.py": ("import sys\nprint('repo=' + sys.argv[1])\n"),
        })
        man = manifest_for(["uiowa_rfq_18649_echoesrepo"])
        man["phases"][0]["components"][0]["runner"] = {"cmd": ["python3", "go.py", "{REPO}"],
                                                       "note": "t"}
        rep = verify_kit.survey(self.tmp, man, timeout=30, repo_root="/explicit/root")
        r = status_of(rep, "uiowa_rfq_18649_echoesrepo")
        self.assertEqual(r["status"], verify_kit.WORKING)
        self.assertIn("repo=/explicit/root", r["runs"][0]["output_tail"])

    def test_runner_that_fails_does_not_earn_working(self):
        write_lane(self.tmp, "uiowa_rfq_18649_badrunner", {
            "go.py": "import sys\nsys.exit(3)\n",
        })
        man = manifest_for(["uiowa_rfq_18649_badrunner"])
        man["phases"][0]["components"][0]["runner"] = {"cmd": ["python3", "go.py"], "note": "t"}
        rep = verify_kit.survey(self.tmp, man, timeout=30)
        r = status_of(rep, "uiowa_rfq_18649_badrunner")
        self.assertEqual(r["status"], verify_kit.DRAFT)
        self.assertIn("did not succeed", r["reason"])

    def test_runner_that_exits_zero_without_output_does_not_earn_working(self):
        write_lane(self.tmp, "uiowa_rfq_18649_silent", {"go.py": "pass\n"})
        man = manifest_for(["uiowa_rfq_18649_silent"])
        man["phases"][0]["components"][0]["runner"] = {"cmd": ["python3", "go.py"], "note": "t"}
        rep = verify_kit.survey(self.tmp, man, timeout=30)
        self.assertEqual(status_of(rep, "uiowa_rfq_18649_silent")["status"], verify_kit.DRAFT)


class Outputs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(FIXTURE_MANIFEST, encoding="utf-8") as fh:
            cls.manifest = json.load(fh)
        cls.report = verify_kit.survey(FIXTURE_ROOT, cls.manifest, timeout=30)
        cls.tmp = tempfile.mkdtemp(prefix="vk_out_")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_csv_has_a_row_per_component_and_a_status_column(self):
        p = os.path.join(self.tmp, "s.csv")
        verify_kit.write_csv(self.report, p)
        with open(p, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(len(rows), len(self.report["components"]))
        self.assertTrue(all(r["status"] in
                            (verify_kit.WORKING, verify_kit.DRAFT, verify_kit.MISSING,
                             verify_kit.UNMAPPED) for r in rows))

    def test_markdown_log_quotes_real_command_output(self):
        p = os.path.join(self.tmp, "s.md")
        verify_kit.write_md(self.report, p)
        with open(p, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("uiowa_rfq_18649_alpha — WORKING", text)
        self.assertIn("Ran 2 tests", text)      # verbatim output of the real run
        self.assertIn("FAILED", text)           # bravo's real failure is not hidden

    def test_cli_runs_end_to_end(self):
        out = os.path.join(self.tmp, "cli.json")
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, "verify_kit.py"),
             "--root", FIXTURE_ROOT, "--manifest", FIXTURE_MANIFEST,
             "--timeout", "30", "--out-json", out],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(proc.returncode, 0, proc.stdout.decode())
        self.assertTrue(os.path.exists(out))
        self.assertIn(b"WORKING", proc.stdout)


class HandoffIntegrity(unittest.TestCase):
    """Guardrails on the handoff's own claims."""

    def test_every_university_input_is_unknown(self):
        with open(UNKNOWNS, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.assertGreater(len(rows), 10)
        for r in rows:
            self.assertEqual(r["status"], "UNKNOWN",
                             "%s was given a status other than UNKNOWN" % r["input_id"])
            self.assertTrue(r["blocks_component"].startswith("uiowa_rfq_18649_"))

    def test_unknown_register_carries_no_score_column(self):
        # An UNKNOWN must never be quietly turned into a number.
        with open(UNKNOWNS, encoding="utf-8") as fh:
            header = next(csv.reader(fh))
        for banned in ("score", "rating", "maturity", "percentile", "grade"):
            self.assertFalse(any(banned in h.lower() for h in header),
                             "register must not carry a %s column" % banned)

    def test_real_manifest_lanes_are_uniquely_named_and_prefixed(self):
        with open(REAL_MANIFEST, encoding="utf-8") as fh:
            man = json.load(fh)
        lanes = [c["lane"] for p in man["phases"] for c in p["components"]]
        for ln in lanes:
            self.assertTrue(ln.startswith("uiowa_rfq_18649_"), ln)
        # A lane may legitimately serve two phases, but a phase must not list one twice.
        for p in man["phases"]:
            inner = [c["lane"] for c in p["components"]]
            self.assertEqual(len(inner), len(set(inner)), "duplicate lane in phase %s" % p["id"])

    def test_rendered_guide_never_calls_a_missing_component_working(self):
        with open(REAL_MANIFEST, encoding="utf-8") as fh:
            man = json.load(fh)
        with open(UNKNOWNS, encoding="utf-8") as fh:
            unknowns = list(csv.DictReader(fh))
        report = verify_kit.survey(FIXTURE_ROOT, self._fixture_shaped(man), timeout=30)
        text = render_guide.render(man, report, unknowns)
        for r in report["components"]:
            if r["status"] == verify_kit.MISSING:
                line = [ln for ln in text.splitlines() if "`%s`" % r["component"] in ln]
                self.assertTrue(line, "missing component absent from guide: %s" % r["component"])
                self.assertFalse(any("**WORKING**" in ln for ln in line))
        self.assertIn("UNKNOWN", text)
        self.assertIn("not a maturity rating", text)

    @staticmethod
    def _fixture_shaped(real_manifest):
        # Render against the fixture survey so the test needs no live lane tree.
        man = json.loads(json.dumps(real_manifest))
        man["lane_prefix"] = "uiowa_rfq_18649_"
        return man


if __name__ == "__main__":
    unittest.main()
