import json
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

import exact_values as ev


class Erdos153ExactValueTests(unittest.TestCase):
    def test_sidon_definition_examples(self):
        self.assertTrue(ev.is_sidon((0, 1, 4, 9, 11)))
        self.assertFalse(ev.is_sidon((0, 1, 2)))  # 0+2 = 1+1

    def test_sumset_size_for_sidon(self):
        for case in ev.CASES:
            self.assertEqual(len(ev.sumset(case.witness)), case.n * (case.n + 1) // 2)

    def test_witness_energies(self):
        expected = {5: Fraction(14, 5), 6: Fraction(74, 21), 7: Fraction(9, 2)}
        for case in ev.CASES:
            self.assertEqual(ev.gap_energy(case.witness), expected[case.n])

    def test_cutoffs_are_exact_integer_thresholds(self):
        for case in ev.CASES:
            self.assertTrue(ev.cutoff_holds(case))
            self.assertTrue(ev.cutoff_is_minimal(case))

    def test_exhaustive_scans_close_all_finite_premises(self):
        receipt = ev.make_receipt()
        for row in receipt["results"]:
            self.assertEqual(row["subsets_checked"], row["expected_subsets"])
            self.assertTrue(row["finite_lower_bound_holds"])
            self.assertTrue(row["witness_realizes_value"])
            self.assertTrue(row["finite_premises_establish_exact_value_via_published_f_eq_of_search"])

    def test_expected_scan_counts_and_minima(self):
        expected = {
            5: (1287, 22, [14, 5], 8),
            6: (38760, 80, [74, 21], 6),
            7: (2035800, 760, [9, 2], 30),
        }
        for row in ev.make_receipt()["results"]:
            subsets, sidon, minimum, minimizers = expected[row["n"]]
            self.assertEqual(row["subsets_checked"], subsets)
            self.assertEqual(row["sidon_subsets"], sidon)
            self.assertEqual(row["minimum_in_window"], minimum)
            self.assertEqual(len(row["minimizers_in_window"]), minimizers)

    def test_receipt_digest_roundtrip(self):
        receipt = ev.make_receipt()
        ev.validate_receipt(receipt)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "receipt.json"
            p.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
            loaded = json.loads(p.read_text())
            ev.validate_receipt(loaded)


if __name__ == "__main__":
    unittest.main()
