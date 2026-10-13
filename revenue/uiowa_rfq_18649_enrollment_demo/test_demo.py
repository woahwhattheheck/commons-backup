"""UIOWA-106 tests. Run normal and with python -O."""

from __future__ import annotations

import hashlib
import importlib.util
import os
import sys
import tempfile
import unittest

try:
    from .canonical import GRANITE_REGISTER_PATH, REGISTER_FIELDS, REGISTER_FIELDS_FROM_023
    from .cli import main as cli_main
    from .demo import materialize
    from .timeline import DemoError, compare_stages, load_stage
except ImportError:
    from canonical import GRANITE_REGISTER_PATH, REGISTER_FIELDS, REGISTER_FIELDS_FROM_023
    from cli import main as cli_main
    from demo import materialize
    from timeline import DemoError, compare_stages, load_stage

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "fixtures")


class DemoTests(unittest.TestCase):
    def test_two_stages_history_preserved(self):
        s1 = load_stage(os.path.join(FIX, "stage1"))
        s2 = load_stage(os.path.join(FIX, "stage2"))
        diff = compare_stages(s1, s2)
        self.assertTrue(diff["history_preserved"])
        self.assertEqual(len(s1["register"]), 3)
        self.assertEqual(len(s2["register"]), 5)
        self.assertEqual(s2["register"][:3], s1["register"])
        self.assertEqual(s2["events"][:2], s1["events"])

    def test_later_evidence_changes_iam_conclusion(self):
        s1 = load_stage(os.path.join(FIX, "stage1"))
        s2 = load_stage(os.path.join(FIX, "stage2"))
        iam1 = next(c for c in s1["conclusions"] if c["group"] == "IAM")
        iam2 = next(c for c in s2["conclusions"] if c["group"] == "IAM")
        ess1 = next(c for c in s1["conclusions"] if c["group"] == "ESS" and c["area"] == "SD")
        ess2 = next(c for c in s2["conclusions"] if c["group"] == "ESS" and c["area"] == "SD")
        self.assertEqual(iam1["status"], "HOLD")
        self.assertEqual(iam2["status"], "supported")
        self.assertEqual(ess1["status"], ess2["status"])
        self.assertEqual(iam1["row_states"], ["HOLD"])
        self.assertEqual(iam2["row_states"][0], "HOLD")  # original row not rewritten
        self.assertIn("SUPPORTING", iam2["row_states"])

    def test_rewrite_refused(self):
        s1 = load_stage(os.path.join(FIX, "stage1"))
        s2 = load_stage(os.path.join(FIX, "stage2"))
        s2["register"][0]["claim"] = "rewritten"
        with self.assertRaises(DemoError):
            compare_stages(s1, s2)

    def test_field_names_match_023(self):
        csv_path = os.path.abspath(
            os.path.join(HERE, os.pardir, "uiowa_rfq_18649_workshare", "methodology", "23-synthetic-evidence-register.csv")
        )
        if os.path.isfile(csv_path):
            with open(csv_path, encoding="utf-8") as fh:
                header = fh.readline().strip().split(",")
            self.assertEqual(header, REGISTER_FIELDS_FROM_023)

    def test_field_names_match_granite_when_present(self):
        path = os.path.abspath(os.path.join(HERE, os.pardir, "uiowa_rfq_18649_evidence_register", "evidence_register.py"))
        if not os.path.isfile(path):
            self.skipTest("granite sibling absent in isolated run")
        spec = importlib.util.spec_from_file_location("uiowa031_er", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        self.assertEqual(mod.REGISTER_FIELDS, REGISTER_FIELDS)
        self.assertEqual(mod.REGISTER_FIELDS_FROM_023, REGISTER_FIELDS_FROM_023)

    def test_required_checks_are_not_assert(self):
        for name in ("timeline.py", "demo.py", "cli.py"):
            with open(os.path.join(HERE, name), encoding="utf-8") as fh:
                src = fh.read()
            self.assertNotRegex(src, r"(?m)^\s*assert ", msg=name)

    def test_cli_fixtures_exit_zero(self):
        self.assertEqual(cli_main(["--fixtures", FIX]), 0)

    def test_cli_overwrite_exit_two(self):
        dest = os.path.join(tempfile.mkdtemp(prefix="uiowa106-"), "out")
        os.mkdir(dest)
        self.assertEqual(cli_main(["--out", dest]), 2)

    def test_cli_materialize_and_compare(self):
        dest = os.path.join(tempfile.mkdtemp(prefix="uiowa106-"), "fresh")
        self.assertEqual(cli_main(["--out", dest]), 0)
        s1 = load_stage(os.path.join(dest, "stage1"))
        s2 = load_stage(os.path.join(dest, "stage2"))
        self.assertTrue(compare_stages(s1, s2)["history_preserved"])
        cal = os.path.join(dest, "stage1", "documents", "ess-registration-calendar-v1.txt")
        with open(cal, "rb") as fh:
            body = fh.read()
        digest = hashlib.sha256(body).hexdigest()
        self.assertEqual(s1["manifest"][0]["sha256"], digest)


if __name__ == "__main__":
    unittest.main()
