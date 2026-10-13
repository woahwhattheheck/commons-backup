import importlib.util
from fractions import Fraction as Q
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("jet_obstruction", ROOT / "jet_obstruction.py")
jo = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(jo)


class JetObstructionTests(unittest.TestCase):
    def test_generic_reference_star_is_full_rank(self):
        t1, t2, s = (Q(1), Q(0)), (Q(0), Q(1)), (Q(1), Q(1))
        matrix = jo.strong_constraint_matrix(t1, t2, s)
        self.assertEqual(jo.rank(matrix), 8)
        self.assertEqual(jo.determinant(matrix), jo.predicted_strong_determinant(t1, t2, s))
        self.assertNotEqual(jo.determinant(matrix), 0)

    def test_non_axis_aligned_stars_match_closed_form(self):
        for t1, t2, s in [
            ((Q(2), Q(1)), (Q(-1), Q(3)), (Q(1), Q(2))),
            ((Q(1), Q(2)), (Q(3), Q(-1)), (Q(2), Q(3))),
        ]:
            self.assertEqual(
                jo.determinant(jo.strong_constraint_matrix(t1, t2, s)),
                jo.predicted_strong_determinant(t1, t2, s),
            )

    def test_degenerate_star_loses_constraint(self):
        t1, t2, s = (Q(1), Q(0)), (Q(0), Q(1)), (Q(2), Q(0))
        self.assertEqual(jo.predicted_strong_determinant(t1, t2, s), 0)
        self.assertLess(jo.rank(jo.strong_constraint_matrix(t1, t2, s)), 8)

    def test_weak_boundary_has_four_jet_dofs(self):
        self.assertEqual(jo.rank(jo.weak_constraint_matrix((Q(2), Q(3)))), 4)

    def test_manufactured_boundary_gradient_norm(self):
        for x, y in [(Q(1), Q(0)), (Q(0), Q(1)), (Q(3, 5), Q(4, 5))]:
            gradient = jo.manufactured_gradient(x, y)
            self.assertEqual(jo.frobenius_sq(gradient), 4)
            self.assertEqual(gradient[0][0] + gradient[1][1], 0)

    def test_full_certificate(self):
        certificate = jo.certificate()
        self.assertEqual(certificate["strong_nullity"], 0)
        self.assertEqual(certificate["weak_nullity"], 4)


if __name__ == "__main__":
    unittest.main()
