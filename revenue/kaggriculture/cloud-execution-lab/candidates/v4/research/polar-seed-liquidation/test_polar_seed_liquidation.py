import unittest

from polar_seed_liquidation import (
    ENGINE_BLOB_SHA,
    INTERPRETER_SHA,
    MarketBook,
    SeedCase,
    break_even_extra_yield,
    evaluate,
    naive_incremental,
    revenue,
    scenario_pack,
)


class PolarSeedLiquidationTests(unittest.TestCase):
    def test_sequential_not_quote_times_yield(self):
        book = MarketBook(quote0=10.0, impact=1.0)
        self.assertEqual(revenue(book, 3, 0), 27.0)
        self.assertEqual(naive_incremental(10.0, 3), 30.0)

    def test_committed_output_consumes_the_book_first(self):
        book = MarketBook(quote0=10.0, impact=1.0)
        case = SeedCase(book=book, committed_output=8, extra_yield=3)
        v = evaluate(case)
        self.assertEqual(v.extra_revenue, 3.0)
        self.assertEqual(v.committed_revenue, sum(range(3, 11)))
        self.assertEqual(v.naive_incremental, 30.0)

    def test_sign_flip_fresh_purchase(self):
        book = MarketBook(quote0=10.0, impact=1.0)
        case = SeedCase(
            book=book,
            committed_output=8,
            extra_yield=3,
            buy_seed=1,
            seed_price=6.0,
        )
        v = evaluate(case)
        self.assertTrue(v.sign_flip)
        self.assertEqual(v.naive_incremental, 30.0)
        self.assertEqual(v.net_sequential, 3.0 - 6.0)
        self.assertLess(v.net_sequential, 0)
        self.assertGreater(v.naive_incremental, 0)

    def test_owned_seed_is_sunk(self):
        book = MarketBook(quote0=10.0, impact=1.0)
        owned = SeedCase(
            book=book,
            committed_output=8,
            extra_yield=3,
            owned_seed=1,
            buy_seed=0,
            seed_price=6.0,
        )
        bought = SeedCase(
            book=book,
            committed_output=8,
            extra_yield=3,
            owned_seed=0,
            buy_seed=1,
            seed_price=6.0,
        )
        ov = evaluate(owned)
        bv = evaluate(bought)
        self.assertEqual(ov.purchase_cost, 0.0)
        self.assertEqual(bv.purchase_cost, 6.0)
        self.assertGreater(ov.net_sequential, bv.net_sequential)

    def test_break_even_extra_yield(self):
        book = MarketBook(quote0=10.0, impact=1.0)
        case = SeedCase(
            book=book,
            committed_output=8,
            extra_yield=0,
            buy_seed=1,
            seed_price=3.0,
        )
        be = break_even_extra_yield(case)
        self.assertIsNotNone(be)
        at = evaluate(
            SeedCase(
                book=book,
                committed_output=8,
                extra_yield=be,
                buy_seed=1,
                seed_price=3.0,
            )
        )
        below = evaluate(
            SeedCase(
                book=book,
                committed_output=8,
                extra_yield=max(0, be - 1),
                buy_seed=1,
                seed_price=3.0,
            )
        )
        self.assertGreaterEqual(at.net_sequential, 0)
        if be > 0:
            self.assertLess(below.net_sequential, 0)

    def test_source_pins(self):
        pack = scenario_pack()
        self.assertEqual(pack["interpreter_sha"], INTERPRETER_SHA)
        self.assertEqual(pack["engine_blob_sha"], ENGINE_BLOB_SHA)
        self.assertTrue(pack["sign_flip"]["sign_flip"])
        self.assertEqual(pack["sunk_owned_seed"]["purchase_cost"], 0.0)

    def test_floor_holds(self):
        book = MarketBook(quote0=2.0, impact=1.0, floor=0.0)
        self.assertEqual(revenue(book, 5, 0), 2 + 1 + 0 + 0 + 0)


if __name__ == "__main__":
    unittest.main()
