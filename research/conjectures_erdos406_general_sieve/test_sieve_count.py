import json
import pathlib
import subprocess
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import sieve_count as s


class SieveCountTests(unittest.TestCase):
    def test_period_and_modulus(self):
        self.assertEqual(s.period(1), 2)
        self.assertEqual(s.period(5), 162)
        self.assertEqual(s.modulus(5), 243)

    def test_fixed_digits(self):
        self.assertEqual(s.ternary_digits_fixed(0, 4), (0, 0, 0, 0))
        self.assertEqual(s.ternary_digits_fixed(1 + 2 * 3 + 3**2, 3), (1, 2, 1))

    def test_digit_residue_count(self):
        for m in range(1, 9):
            vals = s.expected_digit_residues(m)
            self.assertEqual(len(vals), 2**m)
            self.assertTrue(all(s.is_digit_residue(v, m) for v in vals))

    def test_lift_congruence(self):
        for m in range(1, 11):
            self.assertEqual(s.primitive_root_lift_residue(m), 1 + 3**m)

    def test_v3_identity(self):
        for m in range(1, 10):
            self.assertEqual(s.v3(2 ** s.period(m) - 1), m)

    def test_full_order_and_survivors(self):
        for m in range(1, 10):
            row = s.check_depth(m)
            self.assertEqual(row.unit_image_count, row.period)
            self.assertEqual(row.survivor_count, 2**m)

    def test_existing_contribution_control_m5(self):
        row = s.check_depth(5)
        self.assertEqual(row.period, 162)
        self.assertEqual(row.survivor_count, 32)

    def test_receipt_is_deterministic(self):
        a = s.build_receipt(9)
        b = s.build_receipt(9)
        self.assertEqual(a, b)
        self.assertEqual(len(a["payload_sha256"]), 64)

    def test_cli_round_trip(self):
        out = subprocess.check_output(
            [sys.executable, str(HERE / "sieve_count.py"), "--max-m", "6"],
            text=True,
        )
        data = json.loads(out)
        self.assertEqual(data["payload"]["max_m"], 6)
        self.assertEqual(data["payload"]["rows"][-1]["survivor_count"], 64)


if __name__ == "__main__":
    unittest.main()
