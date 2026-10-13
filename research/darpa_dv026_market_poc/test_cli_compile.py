from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from support import *


class CliCompileTests(unittest.TestCase):
    def test_cli_compile_verify_and_create_exclusive(self):
        with tempfile.TemporaryDirectory() as td:
            result_path = Path(td) / "result.json"
            md_path = Path(td) / "result.md"
            cmd = [sys.executable, str(HERE / "cli.py"), "compile", "--scenario", str(HERE / "scenario_good.json"), "--json-out", str(result_path), "--markdown-out", str(md_path)]
            run = subprocess.run(cmd, check=False, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn(STATUS_READY, run.stdout)
            verify = subprocess.run([sys.executable, str(HERE / "cli.py"), "verify", "--scenario", str(HERE / "scenario_good.json"), "--result", str(result_path)], check=False, capture_output=True, text=True)
            self.assertEqual(verify.returncode, 0, verify.stderr)
            self.assertEqual(verify.stdout.strip(), '{"valid":true}')
            rerun = subprocess.run(cmd, check=False, capture_output=True, text=True)
            self.assertNotEqual(rerun.returncode, 0)
            self.assertIn("refuse existing output", rerun.stderr)
