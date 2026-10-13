import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import core
from test_core import job, jobs_capture, run_capture, step


class CliTests(unittest.TestCase):
    def write_json(self, path, value): path.write_text(json.dumps(value), encoding="utf-8")

    def test_compile_verify_create_exclusive(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td); run = root/"run.json"; jobs = root/"jobs.json"; receipt = root/"receipt.json"; verification = root/"verify.json"
            self.write_json(run, run_capture()); self.write_json(jobs, jobs_capture([job(steps=[step()])]))
            cmd = [sys.executable, str(HERE/"cli.py"), "compile", "--case", str(run), str(jobs), "--out", str(receipt)]
            first = subprocess.run(cmd, capture_output=True, text=True); self.assertEqual(first.returncode, 0, first.stderr)
            second = subprocess.run(cmd, capture_output=True, text=True); self.assertEqual(second.returncode, 2)
            verify = subprocess.run([sys.executable, str(HERE/"cli.py"), "verify", "--receipt", str(receipt), "--case", str(run), str(jobs), "--out", str(verification)], capture_output=True, text=True)
            self.assertEqual(verify.returncode, 0, verify.stderr); self.assertTrue(json.loads(verification.read_text())["valid"])

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_symlink_input_fails_closed_without_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td); real = root/"real.json"; link = root/"link.json"; jobs = root/"jobs.json"; out = root/"out.json"
            self.write_json(real, run_capture()); self.write_json(jobs, jobs_capture([job(steps=[step()])]))
            os.symlink(real, link)
            result = subprocess.run([sys.executable, str(HERE/"cli.py"), "compile", "--case", str(link), str(jobs), "--out", str(out)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2); self.assertFalse(out.exists())

    def test_live_queued_shape_projection_is_pending_not_green_or_red(self):
        run = run_capture(34944258971, repo="woahwhattheheck/commons", head="4b52d0529fcf5d658267b06144b0da153275a562", status="queued", conclusion=None)
        jobs = jobs_capture([job(104299817981, name="guard", status="queued", conclusion=None, runner_id=0)], run_id=34944258971, repo="woahwhattheheck/commons", head="4b52d0529fcf5d658267b06144b0da153275a562")
        row = core.classify_case(run, jobs)
        self.assertEqual(row["classification"], "PENDING_EXECUTION"); self.assertFalse(row["github_actions_green"]); self.assertFalse(row["source_regression_proven"])


if __name__ == "__main__": unittest.main(verbosity=2)
