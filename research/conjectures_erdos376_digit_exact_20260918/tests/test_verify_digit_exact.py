import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import verify_digit_exact as v


class DigitExactTests(unittest.TestCase):
    def test_known_witnesses(self):
        expected = [0, 1, 10, 756, 757, 3160, 3186, 3187, 3250, 7560, 7561, 7651, 20007]
        self.assertEqual(v.witness_values(1_000_000), expected)

    def test_known_nonwitnesses(self):
        for n in [2, 3, 4, 5, 6, 7, 8, 9, 11, 755, 758, 20008]:
            self.assertFalse(v.digit_good_357(n), n)

    def test_generic_prefix_equivalence_small_grid(self):
        for p in v.PRIMES:
            for n in range(10_000):
                self.assertEqual(v.digit_good_base(n, p), v.prefix_no_carry(n, p), (p, n))

    def test_exact_central_binomial_equivalence_small_grid(self):
        for n in range(512):
            self.assertEqual(v.digit_good_357(n), v.central_binom_coprime_105(n), n)

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            v.digit_good_base(-1, 3)
        with self.assertRaises(ValueError):
            v.digit_good_base(0, 1)
        with self.assertRaises(ValueError):
            v.prefix_no_carry(-1, 3)

    def test_full_report_deterministic(self):
        report = v.build_report()
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["generic_cases"], 600_003)
        self.assertEqual(report["arithmetic_cases"], 4097)
        self.assertEqual(report["witness_count"], 13)
        self.assertEqual(
            report["witness_list_sha256"],
            "bcf682f1acff4a7ef6804d09f470075824a5149ae61804b8476bc0597166f6c3",
        )

    def test_cli_compact_json(self):
        cp = subprocess.run(
            [sys.executable, str(ROOT / "verify_digit_exact.py"), "--compact"],
            check=True, capture_output=True, text=True,
        )
        report = json.loads(cp.stdout)
        self.assertEqual(report["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
