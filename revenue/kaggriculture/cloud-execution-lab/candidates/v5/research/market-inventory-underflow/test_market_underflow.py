# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import json
import subprocess
import sys
import unittest

from verify_market_underflow import run_probe


HERE = Path(__file__).resolve().parent


class MarketInventoryUnderflowTests(unittest.TestCase):
    def test_underflow_crash_hypothesis_is_falsified(self):
        result = run_probe()
        self.assertEqual(result["verdict"], "FALSIFIED")
        self.assertTrue(all(result["checks"].values()))
        self.assertEqual(result["buy_beyond_zero"]["final_inventory"], -1)

    def test_checked_in_receipt_matches_probe(self):
        self.assertEqual(
            run_probe(),
            json.loads((HERE / "RESULTS.json").read_text()),
        )

    def test_cli_emits_same_machine_readable_receipt(self):
        proc = subprocess.run(
            [sys.executable, str(HERE / "verify_market_underflow.py")],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(json.loads(proc.stdout), run_probe())


if __name__ == "__main__":
    unittest.main()
