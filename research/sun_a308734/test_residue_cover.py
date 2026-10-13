from __future__ import annotations

import unittest
from math import gcd, prod

from .oracle import find_fixed_menu_witness
from .residue_cover import (
    NEXT_PRIME_FAILURE_MODULUS,
    NEXT_PRIME_FAILURE_PRIMES,
    NEXT_PRIME_FAILURE_RESIDUE,
    OBSTRUCTION_MODULUS,
    OBSTRUCTION_PRIMES,
    PAIR_MENU,
    SEED_FAILURE_MODULUS,
    SEED_FAILURE_PRIMES,
    SEED_FAILURE_RESIDUE,
    SEED_MENU,
    choose_low_obstruction_free,
    cover_trace,
    menu_totals,
    uniform_cover_holds,
    verify_failure_residue,
)


class ResidueCoverTests(unittest.TestCase):
    def test_menu_is_exact_and_tiny(self) -> None:
        self.assertEqual(
            menu_totals(),
            (2, 5, 8, 10, 13, 17, 20, 25, 26, 29, 32, 34, 37, 40, 41, 52, 61, 65, 73, 85),
        )
        self.assertEqual(len(set(menu_totals())), len(PAIR_MENU))
        self.assertLessEqual(max(menu_totals()), 85)
        for pair in PAIR_MENU:
            self.assertEqual(pair.total, pair.left + pair.right)
            self.assertEqual(pair.left, (2**pair.a * 3**pair.b) ** 2)
            self.assertEqual(pair.right, (2**pair.c * 5**pair.d) ** 2)

    def test_exact_eight_prime_dynamic_program(self) -> None:
        trace = cover_trace()
        self.assertTrue(uniform_cover_holds())
        self.assertEqual(OBSTRUCTION_MODULUS, 6_324_430_497)
        self.assertEqual(
            [step.reachable_masks for step in trace],
            [3, 21, 181, 1507, 10746, 61553, 202209, 508812],
        )
        self.assertEqual(
            [step.minimum_survivors for step in trace],
            [10, 7, 6, 5, 4, 3, 2, 1],
        )
        self.assertFalse(any(step.zero_mask_reachable for step in trace))

    def test_independent_full_enumeration_first_five_primes(self) -> None:
        primes = OBSTRUCTION_PRIMES[:5]
        modulus = prod(primes)
        self.assertEqual(modulus, 100_947)
        for n in range(modulus):
            self.assertTrue(any(gcd(n - pair.total, modulus) == 1 for pair in PAIR_MENU))

    def test_constructive_choice_rechecks_certificate(self) -> None:
        for n in range(-100, 10_001):
            pair = choose_low_obstruction_free(n)
            self.assertEqual(gcd(n - pair.total, OBSTRUCTION_MODULUS), 1)

    def test_seed_menu_boundary_is_real(self) -> None:
        self.assertEqual(SEED_FAILURE_PRIMES, (3, 7, 11, 19, 23, 31, 43))
        self.assertEqual(SEED_FAILURE_MODULUS, 134_562_351)
        rows = verify_failure_residue(
            SEED_FAILURE_RESIDUE, SEED_FAILURE_MODULUS, SEED_MENU
        )
        self.assertEqual(SEED_FAILURE_RESIDUE, 99_162_274)
        self.assertTrue(all(common > 1 for _, common in rows))

    def test_final_menu_boundary_at_59_is_real(self) -> None:
        self.assertEqual(NEXT_PRIME_FAILURE_PRIMES[-1], 59)
        self.assertEqual(NEXT_PRIME_FAILURE_MODULUS, 373_141_399_323)
        rows = verify_failure_residue(
            NEXT_PRIME_FAILURE_RESIDUE,
            NEXT_PRIME_FAILURE_MODULUS,
            PAIR_MENU,
        )
        self.assertEqual(NEXT_PRIME_FAILURE_RESIDUE, 41_144_806_933)
        self.assertTrue(all(common > 1 for _, common in rows))

    def test_fixed_menu_oracle_constructs_exact_witnesses(self) -> None:
        for n in (2, 3, 5, 27, 65, 85, 110, 10_000):
            witness = find_fixed_menu_witness(n)
            self.assertIsNotNone(witness, n)
            assert witness is not None
            witness.verify(n)
        self.assertIsNone(find_fixed_menu_witness(1))


if __name__ == "__main__":
    unittest.main()
