# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import json
import subprocess
import sys
import unittest

from verify_double_harvest import run_probe


HERE = Path(__file__).resolve().parent


class DoubleHarvestSequencingTests(unittest.TestCase):
    def test_pinned_engine_falsifies_duplication_for_every_actor_priority(self):
        result = run_probe()
        self.assertEqual(result["verdict"], "FALSIFIED")
        self.assertTrue(all(result["checks"].values()))
        self.assertEqual([run["total_carrots"] for run in result["runs"]], [3, 3, 3])

    def test_checked_in_receipt_matches_probe(self):
        self.assertEqual(
            run_probe(),
            json.loads((HERE / "RESULTS.json").read_text()),
        )

    def test_cli_emits_same_machine_readable_receipt(self):
        proc = subprocess.run(
            [sys.executable, str(HERE / "verify_double_harvest.py")],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(json.loads(proc.stdout), run_probe())


if __name__ == "__main__":
    unittest.main()
