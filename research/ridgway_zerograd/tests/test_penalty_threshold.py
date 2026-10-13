import importlib.util
from fractions import Fraction
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("penalty_threshold", ROOT / "penalty_threshold.py")
pt = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pt)


class PenaltyThresholdTests(unittest.TestCase):
    def test_basis_dimension_matches_complete_div_free_pk_space(self):
        for k in range(1, 6):
            self.assertEqual(len(pt.stream_basis(k)), (k + 1) * (k + 4) // 2)

    def test_basis_is_pointwise_divergence_free(self):
        for k in range(1, 6):
            for vx, vy in pt.stream_basis(k):
                self.assertEqual(pt._add(pt._diff(vx, 0), pt._diff(vy, 1)), {})

    def test_exact_matrices_are_symmetric_rationals(self):
        for k in range(1, 4):
            for matrix in pt.assemble(k):
                self.assertTrue(
                    all(
                        matrix[i][j] == matrix[j][i]
                        for i in range(len(matrix))
                        for j in range(len(matrix))
                    )
                )
                self.assertTrue(all(isinstance(x, Fraction) for row in matrix for x in row))

    def test_quartic_threshold_regression(self):
        edge, diameter, *_ = pt.threshold(4)
        self.assertAlmostEqual(edge, 21.64389840489578, places=9)
        self.assertAlmostEqual(diameter, 30.60909466682901, places=9)

    def test_reference_mu100_exceeds_local_diameter_threshold(self):
        _, diameter, *_ = pt.threshold(4)
        self.assertGreater(100.0, diameter)

    def test_threshold_has_expected_sign_change(self):
        edge, _, a0, boundary, norm = pt.threshold(4)
        self.assertLess(pt.normalized_min_eig(a0, boundary, norm, 0.99 * edge), 0)
        self.assertGreater(pt.normalized_min_eig(a0, boundary, norm, 1.01 * edge), 0)

    def test_threshold_increases_over_degrees_one_to_five(self):
        values = [pt.threshold(k)[0] for k in range(1, 6)]
        self.assertTrue(all(left < right for left, right in zip(values, values[1:])))

    def test_global_penalty_conversion_is_two_scale(self):
        edge, *_ = pt.threshold(4)
        self.assertAlmostEqual(pt.global_mu_requirement(edge, 1.0), edge)
        self.assertAlmostEqual(pt.global_mu_requirement(edge, 5.0), 5.0 * edge)
        with self.assertRaises(ValueError):
            pt.global_mu_requirement(edge, 0.0)


if __name__ == "__main__":
    unittest.main()
