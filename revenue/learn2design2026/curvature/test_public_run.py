"""Pure history-contract tests; these do not execute organizer physics."""
import unittest
import numpy as np
from public_run import feasible_statistics, json_arrays
from benchmark import constructor_adapter, verify_sources
from synthetic import _Algorithm


class PublicHistoryTests(unittest.TestCase):
    def test_feasible_nonminimum_lane_is_retained(self):
        result = feasible_statistics([np.array([1., 4.]), np.array([2., 3.])],
                                     [np.array([0., 4.]), np.array([1., 3.])],
                                     [np.array([False, True]), np.array([False, True])], 2, 4)
        self.assertEqual(result['best_raw_objective_loss'], 1.)
        self.assertEqual(result['best_feasible_objective_loss'], 3.)
        self.assertEqual(result['best_feasible_sensitivity_loss'], 3.)
        self.assertEqual(result['feasible_finite_evaluations'], 2)
        self.assertIsNone(result['official_score'])

    def test_numpy_outer_history_is_supported(self):
        result = feasible_statistics(np.array([[1., 2.]]), np.array([[1., 2.]]),
                                     np.array([[False, True]]), 2, 2)
        self.assertEqual(result['best_feasible_objective_loss'], 2.)

    def test_no_feasible_point_remains_none(self):
        result = feasible_statistics([[1., 2.]], [[1., 2.]], [[False, False]], 2, 2)
        self.assertFalse(result['has_feasible_point'])
        self.assertIsNone(result['best_feasible_objective_loss'])
        self.assertIsNone(result['best_feasible_sensitivity_loss'])

    def test_nonfinite_feasible_point_does_not_win(self):
        result = feasible_statistics([[np.nan, 2.]], [[1., 2.]], [[True, True]], 2, 2)
        self.assertEqual(result['best_feasible_sensitivity_loss'], 2.)
        self.assertEqual(result['feasible_finite_evaluations'], 1)

    def test_missing_or_misaligned_aux_fails(self):
        for losses, sensitivity, flags in [([[1., 2.]], [], []), ([], [], []),
                                           ([[1., 2.]], [[1., 2.]], [[True, True], [True, True]])]:
            with self.subTest(flags=flags), self.assertRaises(ValueError):
                feasible_statistics(losses, sensitivity, flags, 2, 2)

    def test_reduced_histories_fail(self):
        with self.assertRaisesRegex(ValueError, 'full batch'):
            feasible_statistics([1.], [1.], [True], 2, 2)

    def test_nonboolean_feasibility_fails(self):
        for flags in [[1, 0], [None, True], ['true', 'false']]:
            with self.subTest(flags=flags), self.assertRaises(ValueError):
                feasible_statistics([[1., 2.]], [[1., 2.]], [flags], 2, 2)

    def test_wrong_evaluation_count_fails(self):
        with self.assertRaises(ValueError):
            feasible_statistics([[1., 2.]], [[1., 2.]], [[True, True]], 2, 4)

    def test_json_conversion_preserves_missing_and_booleans(self):
        self.assertEqual(json_arrays([[1., np.nan, np.inf, -np.inf]]), [[1., None, None, None]])
        self.assertEqual(json_arrays([np.array([True, False])]), [[True, False]])

    def test_frozen_source_pins_match_bytes(self):
        self.assertEqual(len(verify_sources()), 2)

    def test_constructor_adapter_preserves_methods(self):
        class Legacy(_Algorithm):
            algorithm_str = 'legacy'
            def optimize(self):
                return 7
        adapted = constructor_adapter(Legacy)
        self.assertIs(adapted.optimize, Legacy.optimize)
        self.assertEqual(adapted().optimize(), 7)

    def test_unexpected_abstract_gap_is_not_silenced(self):
        from abc import abstractmethod
        class Broken(_Algorithm):
            @abstractmethod
            def other(self):
                pass
        with self.assertRaises(ValueError):
            constructor_adapter(Broken)


if __name__ == '__main__':
    unittest.main()
