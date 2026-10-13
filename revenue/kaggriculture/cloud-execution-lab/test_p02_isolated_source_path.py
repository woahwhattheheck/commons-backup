# SPDX-License-Identifier: Apache-2.0
"""Isolated official-panel workers must resolve archive source siblings.

GitHub Actions run 34393177945 (titan-p02-live-integration, SHA
484781ad2c2f9a04c76d284b2cec324288f86dc3) failed every scheduled game at
step 0:

    ModuleNotFoundError: No module named 'observed_clone'

The process-isolated evaluator copies a stripped environment into each
worker and only inserts the lab directory. scheduler.py imports
observed_clone by bare name; build_integrated.source_files maps that
module to cloud-runtime-pulse. test_e07_hosted_source_path covers the
unittest PYTHONPATH; this contract covers the stripped worker env used
by run_p02_live_panel.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import run_p02_live_panel as panel

LAB = Path(__file__).resolve().parent
PULSE = LAB.parent / "cloud-runtime-pulse"
QUICKSTEP = LAB.parent / "cloud-quickstep"


def _stripped(pythonpath=None, probe="import scheduler"):
    with tempfile.TemporaryDirectory(prefix="kag-eval-agent-") as tmp:
        env = {
            "PATH": os.defpath,
            "HOME": tmp,
            "LANG": "C.UTF-8",
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        if pythonpath is not None:
            env["PYTHONPATH"] = pythonpath
        script = f"import sys\nsys.path.insert(0, {str(LAB)!r})\n{probe}"
        return subprocess.run(
            [sys.executable, "-B", "-c", script],
            cwd=tmp, env=env, capture_output=True, text=True,
        )


class IsolatedP02SourcePathContracts(unittest.TestCase):
    def test_lab_only_stripped_env_cannot_import_scheduler(self):
        result = _stripped(pythonpath=None)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("observed_clone", result.stderr)

    def test_source_pythonpath_includes_pulse_and_quickstep(self):
        pythonpath = panel.isolated_source_pythonpath(LAB)
        parts = [Path(item) for item in pythonpath.split(os.pathsep)]
        self.assertIn(LAB.resolve(), parts)
        self.assertIn(PULSE.resolve(), parts)
        self.assertIn(QUICKSTEP.resolve(), parts)

    def test_stripped_env_with_source_pythonpath_imports_agents(self):
        pythonpath = panel.isolated_source_pythonpath(LAB)
        result = _stripped(pythonpath=pythonpath, probe=panel.ISOLATED_IMPORT_PROBE)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_evaluator_patch_forwards_isolated_pythonpath(self):
        source = LAB / "reference/evaluator/evaluate.py"
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "evaluate-p02.py"
            panel.patch_evaluator(source, target)
            text = target.read_text(encoding="utf-8")
            self.assertIn('env["TITAN_P02_TRACE_DIR"]', text)
            self.assertIn('os.environ.get("TITAN_P02_PYTHONPATH")', text)
            self.assertIn('env["PYTHONPATH"] = os.environ["TITAN_P02_PYTHONPATH"]', text)

    def test_assert_isolated_source_imports_accepts_complete_path(self):
        panel.assert_isolated_source_imports(
            LAB, panel.isolated_source_pythonpath(LAB))


if __name__ == "__main__":
    unittest.main()
