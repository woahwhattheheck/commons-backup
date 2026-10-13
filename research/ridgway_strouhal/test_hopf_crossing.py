from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from hopf_crossing import (
    crossing_speed,
    exclude_steady_as_prize_object,
    is_simple_imaginary_crossing,
    linearization,
    truncated_channel_is_prize_domain,
)


class HopfCrossingTests(unittest.TestCase):
    def test_crossing_is_simple_and_transverse(self):
        self.assertTrue(is_simple_imaginary_crossing())
        self.assertGreater(crossing_speed(), 0)
        lam, conj = linearization(47.0)
        self.assertLess(abs(lam.real), 1e-12)
        self.assertLess(abs(lam.imag + conj.imag), 1e-12)

    def test_steady_excluded(self):
        self.assertIs(exclude_steady_as_prize_object(True), False)
        self.assertIs(exclude_steady_as_prize_object(False), True)

    def test_truncation_not_prize_domain(self):
        self.assertIs(truncated_channel_is_prize_domain(), False)

    def test_truth_ledger_refuses_prize_claim(self):
        data = json.loads((HERE / "truth.json").read_text(encoding="utf-8"))
        self.assertIs(data["prize_theorem"], False)
        self.assertIs(data["nonexistence_theorem"], False)
        self.assertIs(data["award_or_payment"], False)
        self.assertIs(data["sponsor_contact"], False)

    def test_readme_records_no_send_without_denial(self):
        text = (HERE / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("not " + "authorized", text)
        self.assertNotIn("not " + "permitted", text)
        self.assertIn("Prize claim / email / submission: NOT DONE", text)
        self.assertIn("This land records no send.", text)


if __name__ == "__main__":
    unittest.main()
