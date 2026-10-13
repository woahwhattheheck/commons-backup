# SPDX-License-Identifier: Apache-2.0
"""Regression coverage for the frozen-SELL single-pass receipt candidate."""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import random
import sys
import unittest

HERE = Path(__file__).resolve().parent
EXECUTION = HERE.parent / "cloud-execution-lab"
sys.path.insert(0, str(EXECUTION))
try:
    spec = importlib.util.spec_from_file_location("reed_hotpath_scheduler", EXECUTION / "scheduler.py")
    scheduler = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(scheduler)
finally:
    sys.path.pop(0)

from candidate import single_pass_receipts


def old_single(obj, inv, quantity):
    cash = scheduler.receipt_math.sale_receipts(
        [{"step": 0, "quantity": quantity, "product": obj.item}],
        lambda _p, _t: inv,
        lambda _p, i: obj.quote(int(i)),
        0,
    )
    for _ in range(quantity):
        if obj.quote(inv) > 1:
            inv += 1
        else:
            break
    return int(cash), inv


class CandidateMarketPath(scheduler.MarketPath):
    def _single(self, inv, quantity):
        return single_pass_receipts(self, inv, quantity, fallback=lambda i, q: old_single(self, i, q))


class ReferenceMarketPath(scheduler.MarketPath):
    def _single(self, inv, quantity):
        return old_single(self, inv, quantity)


def model(cls, item="WOOL", inv=10000, params=None, now=600, end=608):
    return cls(item, inv, params, ["YARN_STORE", "BAKERY"], {}, now, end)


def outcome(fn, *args):
    try:
        return ("return", fn(*args))
    except BaseException as exc:
        return ("error", type(exc).__name__, str(exc))


class SinglePassReceiptTests(unittest.TestCase):
    def test_actual_price_curves(self):
        configs = [
            None,
            scheduler.m._resolve_market_params({p: {"I0": 0, "T": 100, "base": 37} for p in scheduler.m.PRODUCTS}),
            scheduler.m._resolve_market_params({
                p: {"I0": 200, "T": 15, "base": 113, "below_func": "linear", "above_func": "sq", "above_target": 1.6}
                for p in scheduler.m.PRODUCTS
            }),
        ]
        for item in scheduler.m.PRODUCTS:
            for params in configs:
                old = model(ReferenceMarketPath, item, params=params)
                new = model(CandidateMarketPath, item, params=params)
                for inventory in (-500, -1, 0, 1, 14, 15, 99, 100, 198, 200, 202, 1000, 9800, 9999, 10000, 10010, 10105, 10200, 10500, 12000, 20000):
                    for qty in (0, 1, 2, 7, 19, 40, 100):
                        self.assertEqual(old._single(inventory, qty), new._single(inventory, qty), (item, inventory, qty))

    def test_numeric_fallback_and_errors(self):
        old, new = model(ReferenceMarketPath), model(CandidateMarketPath)
        for inv in (-2**54, -2**53, 2**53 - 3, 2**53, 2**54, 10000.0, 10000.75, True, "10000", None, float("nan"), float("inf")):
            for qty in (-1, 0, 1, 3, 1.0, 1.5, True, "1", None):
                self.assertEqual(outcome(old._single, inv, qty), outcome(new._single, inv, qty), (inv, qty))

    def test_float_accumulation_and_floor_precision(self):
        for fn in (
            lambda i: 0.5,
            lambda i: 1,
            lambda i: 1.25,
            lambda i: 2**54 + 1,
            lambda i: 2**54 - i * 2,
            lambda i: float("nan"),
            lambda i: float("inf"),
        ):
            old, new = model(ReferenceMarketPath), model(CandidateMarketPath)
            old.quote = fn
            new.quote = fn
            for qty in (0, 1, 3, 13, 100):
                self.assertEqual(outcome(old._single, 10000, qty), outcome(new._single, 10000, qty))
        for first in (0.5, 1.25, 2, 2**53 - 4, 2**53 - 1, 2**53, 2**54):
            old, new = model(ReferenceMarketPath), model(CandidateMarketPath)
            old.quote = lambda inv, first=first: first if inv == 0 else 1
            new.quote = lambda inv, first=first: first if inv == 0 else 1
            for qty in (1, 2, 3, 7, 19, 100):
                self.assertEqual(outcome(old._single, 0, qty), outcome(new._single, 0, qty), (first, qty))

    def test_quote_work_is_not_duplicated(self):
        calls = [0, 0]
        for index, cls in enumerate((ReferenceMarketPath, CandidateMarketPath)):
            policy = model(cls)
            def quote(inv, index=index):
                calls[index] += 1
                return 10 if inv < 10000 else 1
            policy.quote = quote
            self.assertEqual(policy._single(9990, 40), (130, 10000))
        self.assertEqual(calls, [51, 11])
        calls = [0, 0]
        for index, cls in enumerate((ReferenceMarketPath, CandidateMarketPath)):
            policy = model(cls)
            def quote(inv, index=index):
                calls[index] += 1
                return 100
            policy.quote = quote
            policy._single(10000, 40)
        self.assertEqual(calls, [80, 40])

    def test_joint_and_score_parity(self):
        plans = [(), ((600, 0),), ((600, 12),), ((600, 3), (604, 9)), ((604, 5), (608, 7)), ((600, 4), (600, 2), (607, 10))]
        rivals = [0, 7, ((601, 3), (607, 8)), ((600, 2), (600, 7), (608, 3))]
        for item in ("CARROT", "WOOL", "MILK", "FERTILIZER"):
            for inv in (9800, 10000, 10200, 12000):
                old, new = model(ReferenceMarketPath, item, inv), model(CandidateMarketPath, item, inv)
                for own in (0, 1, 6, 21):
                    for rival_qty in (0, 1, 7, 24):
                        for alignment in ("paired", "after", "before"):
                            self.assertEqual(old._joint(inv, own, rival_qty, alignment), new._joint(inv, own, rival_qty, alignment))
                for plan in plans:
                    for rival in rivals:
                        for alignment in ("paired", "after", "before"):
                            for terminal in (False, True):
                                self.assertEqual(old.score(plan, 12, rival, alignment, terminal), new.score(plan, 12, rival, alignment, terminal))

    def test_full_optimizer_and_capacity_order(self):
        rng = random.Random(4809)
        for index in range(60):
            qty = rng.randrange(1, 23)
            now = 600 if index % 2 else 710
            dates = [now, now + 1, now + 4, now + 8]
            reference = ((now, qty // 2), (now + 4, qty - qty // 2))
            args = dict(
                item=rng.choice(scheduler.PRODUCTS), quantity=qty, inventory=rng.randrange(9800, 10400), params=None,
                shops=["YARN_STORE", "BAKERY"], config={}, now=now, dates=dates, reference=reference,
                rival_quantity=rng.randrange(0, 25), minimum_now=index % 3, last=718,
            )
            outputs, checks = [], []
            for cls in (ReferenceMarketPath, CandidateMarketPath):
                original = scheduler.MarketPath
                calls = []
                def feasible(plan):
                    calls.append(plan)
                    return sum(q for t, q in plan if t <= now + 1) >= index % 4
                scheduler.MarketPath = cls
                try:
                    outputs.append(scheduler.optimize_lot(**copy.deepcopy(args), capacity_ok=feasible))
                finally:
                    scheduler.MarketPath = original
                checks.append(calls)
            self.assertEqual(outputs[0], outputs[1], index)
            self.assertEqual(checks[0], checks[1], index)

    def test_baseexception_identity(self):
        class Stop(BaseException):
            pass
        for cls in (ReferenceMarketPath, CandidateMarketPath):
            obj = model(cls)
            error = Stop("controlled cancellation")
            def quote(inv):
                raise error
            obj.quote = quote
            with self.assertRaises(Stop) as caught:
                obj._single(10000, 4)
            self.assertIs(caught.exception, error)


if __name__ == "__main__":
    unittest.main(verbosity=2)
