import importlib.util
import json
from fractions import Fraction
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("qcover_finite", HERE / "qcover_finite.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class QCoverFiniteTests(unittest.TestCase):
    def test_dedekind_counts_through_five(self):
        self.assertEqual([len(mod.downsets(n)) for n in range(6)], [2, 3, 6, 20, 168, 7581])
        for n in range(6):
            self.assertEqual(len(set(mod.downsets(n))), len(mod.downsets(n)))
            self.assertTrue(all(mod.is_downset(d, n) for d in mod.downsets(n)))

    def test_down_closure_preserves_q_coverability(self):
        # Independent exhaustive arbitrary-family check on B_3.
        n = 3
        for family in range(1 << (1 << n)):
            closure = mod.down_closure(family, n)
            self.assertGreaterEqual(
                mod.product_measure(closure, n, Fraction(2, 5)),
                mod.product_measure(family, n, Fraction(2, 5)),
            )
            for q in (1, 2, 3):
                self.assertEqual(mod.d_q(family, n, q), mod.d_q(closure, n, q))

    def test_q2_sanity_witness_exact(self):
        witness = mod.q2_sanity_witness()
        self.assertEqual(witness["measure_D"], "324/625")
        self.assertEqual(witness["minimum_p_small_cost"], "14/25")
        self.assertEqual(witness["Dq_bitset_hex"], "0xe")

    def test_minimum_cover_matches_independent_generator_family_bruteforce(self):
        # For every up-class on B_3 induced as D^(q), compare the DP result with
        # an independent brute force over all subsets of the 2^N generators.
        n = 3
        p = Fraction(2, 5)
        for d in mod.downsets(n):
            target = mod.d_q(d, n, 2)
            got, _ = mod.minimum_p_small_cover(target, n, p)
            mins = mod.minimal_elements(target, n) if target else ()
            full = (1 << len(mins)) - 1
            generator_rows = []
            for I in range(1 << n):
                cover = 0
                for j, x in enumerate(mins):
                    if I & ~x == 0:
                        cover |= 1 << j
                generator_rows.append((cover, p ** I.bit_count()))
            best = None
            for chosen in range(1 << (1 << n)):
                cover = 0
                cost = Fraction(0)
                for I, (cmask, price) in enumerate(generator_rows):
                    if (chosen >> I) & 1:
                        cover |= cmask
                        cost += price
                if cover == full and (best is None or cost < best):
                    best = cost
            if target == 0:
                best = Fraction(0)
            self.assertEqual(got, best)

    def test_q3_continuum_census_n5_has_no_gap(self):
        result = mod.census(5)
        self.assertEqual(result["downsets_at_max_n"], 7581)
        self.assertEqual(result["census_rows"], 7778)  # 3+6+20+168+7581
        self.assertEqual(result["counts"].get("counterexample", 0), 0)
        self.assertEqual(result["counts"].get("unresolved", 0), 0)
        self.assertEqual(result["counts"]["ineligible"], 5)  # one empty ideal per dimension
        self.assertEqual(result["counts"]["certified"], 7773)

    def test_committed_receipt_regenerates_exactly(self):
        committed = json.loads((HERE / "receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(committed, mod.receipt())


if __name__ == "__main__":
    unittest.main()
