from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from support import *


class CliSymlinkTests(unittest.TestCase):
    def test_cli_rejects_symlink_input_and_output(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            input_link = td / "scenario.json"
            input_link.symlink_to(HERE / "scenario_good.json")
            result_path = td / "result.json"
            md_path = td / "result.md"
            run = subprocess.run([sys.executable, str(HERE / "cli.py"), "compile", "--scenario", str(input_link), "--json-out", str(result_path), "--markdown-out", str(md_path)], check=False, capture_output=True, text=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertIn("ordinary regular file", run.stderr)

            out_target = td / "target"
            out_target.write_text("sentinel")
            result_link = td / "out.json"
            result_link.symlink_to(out_target)
            run2 = subprocess.run([sys.executable, str(HERE / "cli.py"), "compile", "--scenario", str(HERE / "scenario_good.json"), "--json-out", str(result_link), "--markdown-out", str(md_path)], check=False, capture_output=True, text=True)
            self.assertNotEqual(run2.returncode, 0)
            self.assertEqual(out_target.read_text(), "sentinel")
