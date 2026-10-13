# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import r04_feed_prebuy as lane
import r04_full_router as r04


def _tile_grid():
    tiles = [[None for _ in range(10)] for _ in range(10)]
    tiles[4][6] = {
        "animal": "GOOSE",
        "fed_today": False,
        "consecutive_unfed": 1,
    }
    return tiles


def _observation():
    return {
        "step": 39,
        "player": 0,
        "farms": [{
            "money": 5000.0,
            "farmer": [4, 4],
            "hands": [],
            "tiles": _tile_grid(),
        }],
        "private": {
            "shed": {"WHEAT": 0},
            "inventories": [{}],
        },
        "market": {
            "inventory": {"WHEAT": 10000},
            "prices": {
                "WHEAT": 30,
                "EGG": 100,
                "MILK": 100,
                "WOOL": 100,
                "FERTILIZER": 10,
                "CARROT": 50,
                "TOMATO": 50,
                "STRAWBERRY": 50,
                "MELON": 50,
            }
        },
    }


def _action():
    return {"farmer": ["PASS"], "hands": [], "market": []}


def _standard_config():
    return {
        "episodeSteps": 720,
        "boardSize": 10,
        "turnsPerDay": 24,
        "shedCapacity": 100,
        "maxMarketOrdersPerTurn": 10,
        "marketParams": {},
    }


class FeedPrebuyFutureCashTests(unittest.TestCase):
    def setUp(self):
        self.old_policy = r04._POLICY
        self.tape = [
            {"farmer": ["PASS"], "hands": [], "market": []}
            for _ in range(719)
        ]
        state = SimpleNamespace(
            plan=0,
            last_step=39,
            day=1,
            queues={},
            v217_used=0,
            v217_task=None,
        )
        r04._POLICY = SimpleNamespace(players={0: state}, tapes=[self.tape])

    def tearDown(self):
        r04._POLICY = self.old_policy

    def _apply(self, parent):
        return lane.apply_feed_prebuy(
            _observation(), parent, configuration=_standard_config(), enabled=True)

    def test_remaining_day_cash_spenders_are_hard_barriers(self):
        spend_rows = (
            ["HIRE"],
            ["BUY_LAND"],
            ["BUY_PRODUCT", "FERTILIZER", 1],
            ["BUY_SEED", "WHEAT", 1],
            ["BUY_ANIMAL", "GOOSE", 1],
        )
        for row in spend_rows:
            with self.subTest(row=row):
                self.tape[40]["market"] = [row]
                parent = _action()
                self.assertIs(self._apply(parent), parent)
                self.tape[40]["market"] = []

    def test_later_buy_land_starvation_witness_fails_closed(self):
        # F2's flat $1k reserve must not be allowed to fund the rescue by
        # stealing cash from a literal purchase already authored for h16+.
        self.tape[47]["market"] = [["BUY_LAND"]]
        parent = _action()
        self.assertIs(self._apply(parent), parent)

    def test_next_day_purchase_does_not_block_hour15_prebuy(self):
        self.tape[48]["market"] = [["BUY_LAND"]]
        out = self._apply(_action())
        self.assertEqual(out["market"], [["BUY_PRODUCT", "WHEAT", 2]])

    def test_future_sell_is_not_a_cash_spend_barrier(self):
        self.tape[40]["market"] = [["SELL", "CARROT", 1]]
        out = self._apply(_action())
        self.assertEqual(out["market"], [["BUY_PRODUCT", "WHEAT", 2]])

    def test_malformed_future_market_rows_fail_closed(self):
        for row in ({"verb": "BUY_LAND"}, [], None, "", 0, False):
            with self.subTest(row=row):
                self.tape[40]["market"] = [row]
                parent = _action()
                self.assertIs(self._apply(parent), parent)
                self.tape[40]["market"] = []


if __name__ == "__main__":
    unittest.main()