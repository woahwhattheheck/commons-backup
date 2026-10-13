from fractions import Fraction
from math import isqrt
import unittest

try:
    from .asymptotic import (
        PowerLogRuntime,
        RelationToLinear,
        spiky_linear_runtime,
        target_mismatch_witness,
    )
    from .rule30 import (
        binary_mod,
        center_bit,
        center_prefix,
        eventually_periodic_predictor,
        rule150_center_closed_form,
    )
except ImportError:  # direct execution
    from asymptotic import (
        PowerLogRuntime,
        RelationToLinear,
        spiky_linear_runtime,
        target_mismatch_witness,
    )
    from rule30 import (
        binary_mod,
        center_bit,
        center_prefix,
        eventually_periodic_predictor,
        rule150_center_closed_form,
    )


class AsymptoticContractTests(unittest.TestCase):
    def test_target_mismatch_linear_witness(self):
        witness = target_mismatch_witness()
        self.assertEqual(witness.relation_to_linear(), RelationToLinear.LINEAR_SCALE)
        self.assertFalse(witness.is_prose_shortcut())
        self.assertTrue(witness.is_displayed_predicate_counterexample())

    def test_three_way_target_separators(self):
        # A vs B: not-o(n) does not imply Omega(n).
        for k in range(2, 12):
            power = 1 << k
            self.assertEqual(spiky_linear_runtime(power), power)
            non_power = power + 1
            self.assertEqual(spiky_linear_runtime(non_power), isqrt(non_power))

        # B vs C: not-O(n) does not imply Omega(n).  This second witness is
        # quadratic on powers of two and sqrt-scale elsewhere.
        def q(n):
            return n * n if n > 0 and (n & (n - 1)) == 0 else isqrt(n)

        for k in range(2, 12):
            power = 1 << k
            self.assertEqual(q(power), power * power)
            non_power = power + 1
            self.assertEqual(q(non_power), isqrt(non_power))

        huge_power = 1 << 2048
        huge_non_power = huge_power + 1
        self.assertEqual(q(huge_power), huge_power * huge_power)
        self.assertEqual(q(huge_non_power), isqrt(huge_non_power))

    def test_canonical_growth_families(self):
        cases = [
            (PowerLogRuntime(Fraction(0), 1), RelationToLinear.SUBLINEAR),
            (PowerLogRuntime(Fraction(1, 2), 0), RelationToLinear.SUBLINEAR),
            (PowerLogRuntime(Fraction(1), -1), RelationToLinear.SUBLINEAR),
            (PowerLogRuntime(Fraction(1), 0), RelationToLinear.LINEAR_SCALE),
            (PowerLogRuntime(Fraction(1), 1), RelationToLinear.SUPERLINEAR),
            (PowerLogRuntime(Fraction(2), 0), RelationToLinear.SUPERLINEAR),
        ]
        for family, expected in cases:
            with self.subTest(family=family):
                self.assertEqual(family.relation_to_linear(), expected)

    def test_spiky_linear_family_is_not_empirically_smoothed_away(self):
        for k in range(1, 17):
            n = 1 << k
            self.assertEqual(spiky_linear_runtime(n), n)
        self.assertLess(spiky_linear_runtime((1 << 16) - 1), (1 << 16) - 1)

        # This helper is an exact theorem witness, so it must not depend on
        # float conversion or precision at large integer magnitudes.
        huge_non_power = 10**1000 + 12345
        self.assertEqual(spiky_linear_runtime(huge_non_power), isqrt(huge_non_power))
        huge_power = 1 << 4096
        self.assertEqual(spiky_linear_runtime(huge_power), huge_power)


class OracleAndLemmaTests(unittest.TestCase):
    def test_rule30_known_center_prefix(self):
        expected = (1, 1, 0, 1, 1, 1, 0, 0, 1, 1, 0, 0, 0, 1)
        self.assertEqual(center_prefix(30, len(expected) - 1), expected)

    def test_rule150_center_is_constant(self):
        for n in range(96):
            self.assertEqual(center_bit(150, n), 1)
            self.assertEqual(rule150_center_closed_form(n), 1)

    def test_binary_mod_matches_python(self):
        for modulus in range(1, 20):
            for n in range(0, 500):
                self.assertEqual(binary_mod(n, modulus), n % modulus)

    def test_periodic_predictor(self):
        prefix = (1, 0, 0)
        period = (1, 1, 0, 1)
        direct = prefix + period * 40
        for n in range(len(direct)):
            self.assertEqual(eventually_periodic_predictor(n, prefix, period), direct[n])

    def test_hostile_inputs(self):
        with self.assertRaises(ValueError):
            center_bit(30, -1)
        with self.assertRaises(ValueError):
            center_bit(256, 0)
        with self.assertRaises(ValueError):
            binary_mod(3, 0)
        with self.assertRaises(ValueError):
            eventually_periodic_predictor(0, (), ())


if __name__ == "__main__":
    unittest.main()
