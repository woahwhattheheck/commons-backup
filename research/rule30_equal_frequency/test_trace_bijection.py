from __future__ import annotations

import itertools
import unittest

from research.rule30_equal_frequency.trace_bijection import (
    center_trace,
    deepest_bit_flip,
    lone_seed_trace,
    reconstruct_left_prefix,
    rule30,
)


class Rule30TraceBijectionTests(unittest.TestCase):
    def test_rule_is_left_permutive(self):
        for center, right in itertools.product((0, 1), repeat=2):
            with self.subTest(center=center, right=right):
                self.assertNotEqual(
                    rule30(0, center, right),
                    rule30(1, center, right),
                )

    def test_deepest_new_bit_leaves_earlier_trace_fixed_and_flips_new_bit(self):
        for depth in range(1, 8):
            for right in itertools.product((0, 1), repeat=depth + 1):
                for closer in itertools.product((0, 1), repeat=depth - 1):
                    zero, one = deepest_bit_flip(right, closer)
                    self.assertEqual(zero[:-1], one[:-1])
                    self.assertEqual(zero[-1] ^ one[-1], 1)

    def test_exhaustive_bijection_for_all_right_prefixes_through_horizon_six(self):
        for horizon in range(1, 7):
            expected = 1 << horizon
            for right in itertools.product((0, 1), repeat=horizon + 1):
                seen = {}
                for left in itertools.product((0, 1), repeat=horizon):
                    trace = center_trace(right, left)
                    self.assertNotIn(trace, seen)
                    seen[trace] = left
                    self.assertEqual(reconstruct_left_prefix(right, trace), left)
                self.assertEqual(len(seen), expected)

    def test_every_target_trace_has_unique_constructive_preimage(self):
        right = (1, 0, 1, 1, 0, 1, 0, 0)
        horizon = len(right) - 1
        for target in itertools.product((0, 1), repeat=horizon):
            left = reconstruct_left_prefix(right, target)
            self.assertEqual(center_trace(right, left), target)

    def test_lone_seed_is_one_specific_zero_left_preimage_not_an_ensemble_average(self):
        horizon = 32
        trace = lone_seed_trace(horizon)
        right = (1,) + (0,) * horizon
        recovered = reconstruct_left_prefix(right, trace[1:])
        self.assertEqual(recovered, (0,) * horizon)
        # The finite prefix need not be exactly balanced; no ensemble
        # statement is silently promoted to the lone-seed limit claim.
        self.assertEqual(sum(trace[1:]), 17)
        self.assertEqual(len(trace[1:]), 32)

    def test_invalid_bits_and_short_right_prefix_fail_closed(self):
        with self.assertRaises(ValueError):
            rule30(2, 0, 0)
        with self.assertRaises(ValueError):
            center_trace((1,), (0,))
        with self.assertRaises(ValueError):
            reconstruct_left_prefix((1, 0), (0, 2))
        with self.assertRaises(ValueError):
            lone_seed_trace(-1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
