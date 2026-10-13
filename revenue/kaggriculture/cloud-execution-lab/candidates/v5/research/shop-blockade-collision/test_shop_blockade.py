# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import json
import subprocess
import sys
import unittest

from verify_shop_blockade import run_probe


HERE = Path(__file__).resolve().parent


class ShopBlockadeCollisionTests(unittest.TestCase):
    def test_blockade_is_falsified_for_buys_and_sells_in_both_seats(self):
        result = run_probe()
        self.assertEqual(result["verdict"], "FALSIFIED")
        self.assertTrue(all(result["checks"].values()))
        self.assertEqual([row["seat"] for row in result["buy_runs"]], [0, 1])
        self.assertEqual([row["seat"] for row in result["sell_runs"]], [0, 1])

    def test_checked_in_receipt_matches_probe(self):
        self.assertEqual(
            run_probe(),
            json.loads((HERE / "RESULTS.json").read_text()),
        )

    def test_cli_emits_same_machine_readable_receipt(self):
        proc = subprocess.run(
            [sys.executable, str(HERE / "verify_shop_blockade.py")],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(json.loads(proc.stdout), run_probe())


if __name__ == "__main__":
    unittest.main()
