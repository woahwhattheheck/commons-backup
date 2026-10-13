# SPDX-License-Identifier: Apache-2.0
"""Additional controls for AXLE-SCALE's single lockstep-scale research package.

Run: TITAN_ENGINE=/path/kaggriculture.py python [-O] -m unittest -v test_lockstep_quote_controls
These are synthetic market callbacks, not an agent or a game-strength result.
"""
from __future__ import annotations

import copy
import os
from pathlib import Path
import unittest

import lockstep_scale as l

RUNNER_BLOB = "9eebd953931635e23e000cfeb27772421abe4688"


def market_outcome(engine, rows, *, item="FERTILIZER", inventory=10000,
                   held=(0, 0), money=(10**9, 10**9), other_cargo=(0, 0)):
    """Fixture only: use the owner's loader/state and real engine market calls."""
    if any(held[i] + other_cargo[i] > 100 for i in (0, 1)):
        raise ValueError("Controls require capacity-valid initial sheds")
    state, env = l.make_state(engine, item, inventory, held)
    for i in (0, 1):
        state[i].action = {"market": copy.deepcopy(rows[i])}
        state[0].observation.farms[i]["money"] = money[i]
        if other_cargo[i]:
            state[i].observation.private["shed"]["CARROT"] = other_cargo[i]
    engine._process_market(state, env)
    return {
        "cash_delta": [f["money"] - money[i]
                       for i, f in enumerate(state[0].observation.farms)],
        "final_sheds": [copy.deepcopy(s.observation.private["shed"]) for s in state],
        "final_inventory": state[0].observation.market["inventory"][item],
    }


def cycle(item="FERTILIZER", quantity=100):
    return [["BUY_PRODUCT", item, quantity], ["SELL", item, quantity]]


class LockstepQuoteControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = l.load_engine(Path(os.environ.get("TITAN_ENGINE", "kaggriculture.py")))

    def test_exact_runner_custody(self):
        self.assertEqual(l.git_blob(Path(l.__file__).read_bytes()), RUNNER_BLOB)

    def test_real_buy_capacity_not_requested_volume(self):
        orders = [["BUY_PRODUCT", "WHEAT", 1000]]
        r = market_outcome(self.engine, (orders, orders), item="WHEAT")
        self.assertEqual([s["WHEAT"] for s in r["final_sheds"]], [100, 100])
        self.assertEqual(r["cash_delta"], [-3445, -3445])
        self.assertEqual(r["final_inventory"], 9800)

    def test_other_cargo_reserves_real_capacity(self):
        r = market_outcome(self.engine, ([["BUY_PRODUCT", "WHEAT", 50]], []),
                           item="WHEAT", other_cargo=(99, 0))
        self.assertEqual(r["final_sheds"][0]["WHEAT"], 1)
        self.assertEqual(r["final_sheds"][0]["CARROT"], 99)
        self.assertEqual(r["cash_delta"], [-26, 0])

    def test_post_buy_quote_must_be_affordable(self):
        orders = [["BUY_PRODUCT", "WHEAT", 1]]
        r = market_outcome(self.engine, (orders, orders), item="WHEAT", money=(25, 26))
        self.assertEqual(r["cash_delta"], [0, -26])
        self.assertEqual([s["WHEAT"] for s in r["final_sheds"]], [0, 1])
        self.assertEqual(r["final_inventory"], 9999)

    def test_failed_buy_does_not_cancel_later_sell_row(self):
        r = market_outcome(self.engine, (cycle(), []), held=(100, 0))
        self.assertEqual(r["final_sheds"][0]["FERTILIZER"], 0)
        self.assertGreater(r["cash_delta"][0], 0)
        self.assertEqual(r["final_inventory"], 10100)

    def test_isolated_roundtrips_zero_in_both_buyable_products(self):
        for item in ("WHEAT", "FERTILIZER"):
            with self.subTest(item=item):
                r = market_outcome(self.engine, (cycle(item), []), item=item)
                self.assertEqual(r["cash_delta"], [0, 0])
                self.assertEqual(r["final_inventory"], 10000)
                self.assertEqual(r["final_sheds"][0][item], 0)

    def test_aligned_fertilizer_roundtrips_not_universally_zero(self):
        r = market_outcome(self.engine, (cycle(), cycle()))
        self.assertEqual(r["cash_delta"], [20, 20])
        self.assertEqual(r["final_inventory"], 10000)
        self.assertEqual([s["FERTILIZER"] for s in r["final_sheds"]], [0, 0])

    def test_aligned_wheat_is_not_fertilizer(self):
        r = market_outcome(self.engine, (cycle("WHEAT"), cycle("WHEAT")), item="WHEAT")
        self.assertEqual(r["cash_delta"], [0, 0])
        self.assertEqual(r["final_inventory"], 10000)

    def test_five_cycles_use_ten_rows_and_require_partner(self):
        both = market_outcome(self.engine, (cycle() * 5, cycle() * 5))
        alone = market_outcome(self.engine, (cycle() * 5, []))
        self.assertEqual(both["cash_delta"], [100, 100])
        self.assertEqual(alone["cash_delta"], [0, 0])
        self.assertEqual(both["final_inventory"], 10000)
        self.assertEqual([s["FERTILIZER"] for s in both["final_sheds"]], [0, 0])

    def test_sixth_cycle_is_outside_executable_raw_prefix(self):
        five = market_outcome(self.engine, (cycle() * 5, cycle() * 5))
        six = market_outcome(self.engine, (cycle() * 6, cycle() * 6))
        self.assertEqual(five, six)

    def test_quantity_thousand_cannot_scale_roundtrip_fills(self):
        hundred = market_outcome(self.engine, (cycle(), cycle()))
        thousand = market_outcome(self.engine, (cycle(quantity=1000), cycle(quantity=1000)))
        self.assertEqual(hundred, thousand)

    def test_one_row_lag_transfers_value_not_physical_seat(self):
        orders = (cycle(), [[]] + cycle())
        a = market_outcome(self.engine, orders)
        b = market_outcome(self.engine, orders[::-1])
        self.assertEqual(a["cash_delta"], [990, -990])
        self.assertEqual(b["cash_delta"], [-990, 990])
        self.assertEqual(a["final_inventory"], 10000)
        self.assertEqual(b["final_inventory"], 10000)

    def test_floor_roundtrips_have_no_batch_gain(self):
        r = market_outcome(self.engine, (cycle(), cycle()), inventory=11000)
        self.assertEqual(r["cash_delta"], [0, 0])
        # $1 SELLs do not restore the 200 units taken from public inventory.
        self.assertEqual(r["final_inventory"], 10800)

    def test_unrelated_product_roundtrip_does_not_create_alignment(self):
        r = market_outcome(self.engine, (cycle(), cycle("WHEAT")))
        self.assertEqual(r["cash_delta"], [0, 0])
        self.assertEqual(r["final_inventory"], 10000)

    def test_ignored_tuple_preserves_later_row_position(self):
        sale = ["SELL", "WHEAT", 50]
        r = l.execute(self.engine, "WHEAT", 9899, (50, 50),
                      ([sale], [("SELL", "WHEAT", 50), sale]))
        self.assertEqual(r["cash"], [1685, 1494])
        self.assertEqual(r["sold"], [50, 50])

    def test_control_fixture_rejects_impossible_capacity(self):
        with self.assertRaisesRegex(ValueError, "capacity-valid"):
            market_outcome(self.engine, ([], []), held=(100, 0), other_cargo=(1, 0))

    def test_fixture_does_not_mutate_caller_orders(self):
        rows = (cycle(), [[]] + cycle())
        before = copy.deepcopy(rows)
        market_outcome(self.engine, rows)
        self.assertEqual(rows, before)


if __name__ == "__main__":
    unittest.main()
