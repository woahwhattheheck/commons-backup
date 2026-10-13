# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import json
import subprocess
import sys
import unittest

from verify_cross_farm_boundary import run_probe


HERE = Path(__file__).resolve().parent


class CrossFarmOwnershipBoundaryTests(unittest.TestCase):
    def test_pinned_official_engine_falsifies_cross_farm_mutation(self):
        result = run_probe()
        self.assertEqual(result["verdict"], "FALSIFIED")
        self.assertTrue(all(result["checks"].values()))
        self.assertFalse(result["runtime_change"])
        self.assertFalse(result["policy_change"])

    def test_checked_in_receipt_matches_live_probe(self):
        expected = json.loads((HERE / "RESULTS.json").read_text())
        self.assertEqual(run_probe(), expected)

    def test_cli_is_machine_readable_and_successful(self):
        proc = subprocess.run(
            [sys.executable, str(HERE / "verify_cross_farm_boundary.py")],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(json.loads(proc.stdout), run_probe())


if __name__ == "__main__":
    unittest.main()
