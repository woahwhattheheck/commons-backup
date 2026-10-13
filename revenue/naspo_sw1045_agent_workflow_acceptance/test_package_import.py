from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


class PackageImportTests(unittest.TestCase):
    def test_package_import_from_repository_root(self):
        repo_root = Path(__file__).resolve().parents[2]
        code = (
            "import revenue.naspo_sw1045_agent_workflow_acceptance as pkg; "
            "assert pkg.compile_trace; assert pkg.verify_receipt"
        )
        completed = subprocess.run(
            [sys.executable, "-c", code],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_module_acceptance_from_repository_root(self):
        repo_root = Path(__file__).resolve().parents[2]
        completed = subprocess.run(
            [sys.executable, "-m", "revenue.naspo_sw1045_agent_workflow_acceptance.acceptance"],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn('"valid": 100', completed.stdout)
        self.assertIn('"hold": 20', completed.stdout)


if __name__ == "__main__":
    unittest.main()
