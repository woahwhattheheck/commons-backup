"""Exercise the real walkthrough and its negative control."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import input_contract_demo as demo


class DemoTests(unittest.TestCase):
    def test_complete_cases_and_input_preservation(self):
        report = demo.run()
        self.assertEqual(report["cases_checked"], 19)
        self.assertTrue(all(row["input_unchanged"] for row in report["cases"]))
        self.assertEqual(len({row["case"] for row in report["cases"]}), 19)
        self.assertEqual({row["exit"] for row in report["cases"]}, {0, 1, 2})

    def test_optimized_and_foreign_cwd_output_is_identical(self):
        script = str(Path(demo.__file__).resolve())
        with tempfile.TemporaryDirectory() as directory:
            a = subprocess.run([sys.executable, script, "--format", "json"], cwd=directory,
                               capture_output=True, text=True, timeout=20)
            b = subprocess.run([sys.executable, "-O", script, "--format", "json"], cwd=directory,
                               capture_output=True, text=True, timeout=20)
        self.assertEqual((a.returncode, a.stdout, a.stderr), (b.returncode, b.stdout, b.stderr))
        self.assertEqual(a.returncode, 0, a.stderr)
        self.assertEqual(json.loads(a.stdout)["cases_checked"], 19)

    def test_wrong_cli_cannot_produce_a_completed_walkthrough(self):
        def fake_main(_):
            print(json.dumps({"passed": True, "findings": []}))
            return 0
        with patch.object(demo.CLI, "main", side_effect=fake_main):
            with self.assertRaisesRegex(RuntimeError, "threshold_override"):
                demo.run()

    def test_walkthrough_does_not_rewrite_tracked_sources_or_fixtures(self):
        root = Path(demo.__file__).parent
        files = sorted(root.glob("*.py")) + sorted((root / "fixtures").glob("*.json"))
        before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(demo.main([]), 0)
        after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main(verbosity=2)
