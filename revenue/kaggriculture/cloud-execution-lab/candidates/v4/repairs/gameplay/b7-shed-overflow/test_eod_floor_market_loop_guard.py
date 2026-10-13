#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import unittest

import eod_floor_replacement as mod


def floor_market():
    return {
        "inventory": {item: 1_000_000 for item in mod.PRODUCTS},
        "prices": {item: 1 for item in mod.PRODUCTS},
    }


def floor_price(_item, _stock, _params=None):
    return 1


def case(*, capacity: int, shed_units: int, carried_units: int, market_rows=None):
    observation = {
        "step": 23,
        "player": 0,
        "farms": [{"money": 1000.0, "hands": []}],
        "private": {
            "shed": {"EGG": shed_units},
            "inventories": [{"EGG": carried_units}],
        },
        "market": floor_market(),
    }
    action = {
        "farmer": ["PASS"],
        "hands": [],
        "market": [] if market_rows is None else market_rows,
    }
    configuration = {
        "turnsPerDay": 24,
        "shedCapacity": capacity,
        "maxMarketOrdersPerTurn": 10,
    }
    return mod.analyze(
        observation,
        action,
        configuration,
        market_price_fn=floor_price,
    )


class MarketLoopExecutionCap(unittest.TestCase):
    def test_candidate_100000_units_fails_closed(self):
        # Official _process_market increments idx_esc before checking >=100_000,
        # so one row can commit at most 99,999 units. Certifying 100,000 would
        # overstate cash by one and falsely claim zero EOD discard.
        decision = case(capacity=100_000, shed_units=100_000, carried_units=100_000)
        self.assertFalse(decision["admit"])
        self.assertEqual(decision["reason"], "market_unit_loop_guard")

    def test_99999_unit_boundary_remains_admissible(self):
        decision = case(capacity=99_999, shed_units=99_999, carried_units=99_999)
        self.assertTrue(decision["admit"])
        self.assertEqual(decision["proposal"], ["SELL", "EGG", 99_999])
        self.assertEqual(decision["cash_gain"], 99_999)

    def test_prefix_request_100000_fails_before_projection(self):
        # A huge prefix SELL is also truncated by the engine. The helper must
        # not project it as fully executed and reason from an impossible shed.
        decision = case(
            capacity=200_000,
            shed_units=200_000,
            carried_units=100_000,
            market_rows=[["SELL", "EGG", 100_000]],
        )
        self.assertFalse(decision["admit"])
        self.assertEqual(decision["reason"], "market_prefix_or_slot")


if __name__ == "__main__":
    unittest.main()
