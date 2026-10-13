# SPDX-License-Identifier: MIT
import unittest
from fractions import Fraction

from linear_bounds import Constraint, Limits, solve, verify_certificate
from rival_feasibility import Interval, RivalLedger, check_column, check_extension, t12_sale_events

TEST_LIMITS = Limits(seconds=1.0, max_combinations=32768, max_rows=8192)


class BoundsTests(unittest.TestCase):
    def base(self, **kwargs):
        return RivalLedger(["WHEAT", "EGG"], 100, as_of_step=5, **kwargs)

    def check(self, base, events, **kwargs):
        return check_extension(base, events, limits=TEST_LIMITS, **kwargs)

    def test_joint_capacity_not_independent_product_caps(self):
        base = self.base()
        events = [dict(kind="sale", step=5, product=p, quantity=q, cash=0)
                  for p, q in [("WHEAT", 60), ("EGG", 60)]]
        result = self.check(base, events, complete=True)
        self.assertFalse(result.keep)
        candidate = base.fork()
        for event in events:
            candidate.event(**event)
        self.assertTrue(verify_certificate(candidate.constraints, result.result.certificate))

    def test_unknown_future_transfer_never_rejected(self):
        events = [dict(kind="sale", step=6, product="WHEAT", quantity=150)]
        result = self.check(self.base(), events)
        self.assertTrue(result.keep)
        self.assertEqual(result.result.reason, "incomplete_continuation")

    def test_same_step_deposit_before_pickup_cannot_be_netted(self):
        base = self.base(shed={"WHEAT": Interval(100, 100), "EGG": Interval(0, 0)},
                         carry={"EGG": Interval(10, 10)})
        deposit = dict(kind="deposit", step=5, product="EGG", quantity=10)
        pickup = dict(kind="pickup", step=5, product="WHEAT", quantity=10)
        self.assertFalse(self.check(base, [deposit, pickup], complete=True).keep)
        self.assertTrue(self.check(base, [pickup, deposit], complete=True).keep)

    def test_carry_is_not_limited_by_shed_capacity(self):
        base = self.base(carry={"EGG": Interval(200, 200)})
        self.assertEqual(base.check(TEST_LIMITS).status, "possible")

    def test_interval_transfer_conserves_stock(self):
        base = self.base(shed={"WHEAT": Interval(0, 0), "EGG": Interval(0, 0)},
                         carry={"EGG": Interval(4, 4)})
        events = [dict(kind="deposit", step=5, product="EGG", quantity=Interval(0, 4)),
                  dict(kind="sale", step=5, product="EGG", quantity=5, cash=1)]
        self.assertFalse(self.check(base, events, complete=True).keep)
        events[-1]["quantity"] = 4
        self.assertTrue(self.check(base, events, complete=True).keep)

    def test_discard_after_partial_deposit(self):
        base = self.base(shed={"WHEAT": Interval(99, 99), "EGG": Interval(0, 0)},
                         carry={"EGG": Interval(10, 10)})
        events = [dict(kind="deposit", step=5, product="EGG", quantity=1),
                  dict(kind="discard", step=5, product="EGG", quantity=9)]
        self.assertTrue(self.check(base, events, complete=True).keep)
        events.append(dict(kind="deposit", step=6, product="EGG", quantity=1))
        self.assertFalse(self.check(base, events, complete=True).keep)

    def test_net_cash_is_not_gross_receipts(self):
        base = self.base(cash=Interval(100, 100))
        events = [dict(kind="sale", step=0, product="EGG", quantity=4, cash=200),
                  dict(kind="expense", step=0, cash=Interval(0, 100)),
                  dict(kind="cash_checkpoint", step=1, cash=250)]
        self.assertTrue(self.check(base, events, complete=True).keep)
        events[1]["cash"] = Interval(0, 40)
        self.assertFalse(self.check(base, events, complete=True).keep)
        events[1]["cash"] = Interval()
        self.assertTrue(self.check(base, events, complete=True).keep)

    def test_income_uncertainty_preserved(self):
        events = [dict(kind="income", step=0, cash=Interval()),
                  dict(kind="cash_checkpoint", step=1, cash=500)]
        self.assertTrue(self.check(self.base(cash=Interval(0, 0)), events, complete=True).keep)

    def test_cross_product_cash_checkpoint(self):
        events = [dict(kind="sale", step=0, product="WHEAT", quantity=2, cash=50),
                  dict(kind="sale", step=0, product="EGG", quantity=3, cash=150),
                  dict(kind="cash_checkpoint", step=1, cash=300)]
        base = self.base(cash=Interval(100, 100))
        self.assertTrue(self.check(base, events, complete=True).keep)
        events[1]["cash"] = 149
        self.assertFalse(self.check(base, events, complete=True).keep)

    def test_inconsistent_facts_widen_to_unknown(self):
        base = self.base(shed={"WHEAT": Interval(60, 60), "EGG": Interval(60, 60)})
        result = self.check(base, [], complete=True)
        self.assertTrue(result.keep)
        self.assertEqual(result.result.reason, "base_infeasible")

    def test_budget_returns_unknown(self):
        result = check_extension(self.base(), [], complete=True, limits=Limits(seconds=0))
        self.assertTrue(result.keep)
        self.assertEqual(result.result.status, "unknown")

    def test_future_cash_is_not_used(self):
        result = self.check(self.base(), [dict(kind="cash_checkpoint", step=6, cash=999)], complete=True)
        self.assertTrue(result.keep)
        self.assertEqual(result.result.reason, "malformed_candidate")

    def test_bad_candidate_is_retained_unknown(self):
        result = self.check(self.base(), [dict(kind="sale", step=0, product="WOOL", quantity=1)], complete=True)
        self.assertTrue(result.keep)
        self.assertEqual(result.result.status, "unknown")

    def test_column_depends_on_own_plan_pricing(self):
        base = self.base(cash=Interval(20, 20), shed={"WHEAT": Interval(0, 0), "EGG": Interval(0, 0)})
        affordable = [dict(kind="buy", step=5, product="WHEAT", quantity=1, cash=19)]
        expensive = [dict(kind="buy", step=5, product="WHEAT", quantity=1, cash=21)]
        result = check_column(base, [affordable, expensive], complete=True, limits=TEST_LIMITS)
        self.assertTrue(result["keep"])
        self.assertTrue(result["conditional"])
        self.assertFalse(check_column(base, [expensive, expensive], complete=True, limits=TEST_LIMITS)["keep"])

    def test_t12_stream_alignment_and_label_preserved(self):
        source = ("day_3_shift_-1_after", ((5, 2), (7, 4)), "after")
        seen = []
        def receipts(stream, index):
            seen.append((stream, index))
            return [99, 191][index]
        events = t12_sale_events("EGG", source, receipts=receipts)
        self.assertEqual([e["cash"] for e in events], [99, 191])
        self.assertEqual([s for s, _ in seen], [source, source])
        self.assertEqual([e["step"] for e in events], [5, 7])

    def test_integer_relaxation_does_not_prune_fractional_witness(self):
        constraints = [Constraint.make({"x": 2}, 1, "upper"),
                       Constraint.make({"x": -2}, -1, "lower")]
        self.assertEqual(solve(constraints, TEST_LIMITS).status, "possible")

    def test_exact_certificate_and_one_sided_variable(self):
        rows = [Constraint.make({"x": 1, "y": 1}, 0, "a"),
                Constraint.make({"x": -1, "y": -1}, -1, "b")]
        result = solve(rows, TEST_LIMITS)
        self.assertEqual(result.status, "infeasible")
        self.assertTrue(verify_certificate(rows, result.certificate))
        self.assertFalse(verify_certificate(rows, {"a": -1, "b": 1}))
        self.assertEqual(solve([rows[0]], TEST_LIMITS).status, "possible")

    def test_reject_inexact_float_input(self):
        with self.assertRaises(TypeError):
            Interval(0.1, 1)
        with self.assertRaises(ValueError):
            Interval(2, 1)


if __name__ == "__main__":
    unittest.main()
