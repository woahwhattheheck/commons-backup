from __future__ import annotations

import unittest
from support import *


class MarketPocTests(unittest.TestCase):
    def test_market_observes_irrational_bid_instead_of_censoring_it(self):
        buyer = Trader("buyer", "BUY", 50, 1, 1, "TRUTHFUL", 0)
        seller = Trader("seller", "SELL", 70, 1, 2, "TRUTHFUL", 0)
        obs_b = "a" * 64
        obs_s = "b" * 64
        buy = validate_blackbox_action(
            {
                "schema": "darpa-dv026-blackbox-action/v1",
                "order_id": "ord:CONTINUOUS_DOUBLE_AUCTION:buyer",
                "trader_id": "buyer",
                "side": "BUY",
                "price": 100,
                "quantity": 1,
                "action_step": 1,
                "observation_sha256": obs_b,
            },
            buyer,
            obs_b,
            "CONTINUOUS_DOUBLE_AUCTION",
        )
        sell = validate_blackbox_action(
            {
                "schema": "darpa-dv026-blackbox-action/v1",
                "order_id": "ord:CONTINUOUS_DOUBLE_AUCTION:seller",
                "trader_id": "seller",
                "side": "SELL",
                "price": 1,
                "quantity": 1,
                "action_step": 2,
                "observation_sha256": obs_s,
            },
            seller,
            obs_s,
            "CONTINUOUS_DOUBLE_AUCTION",
        )
        fills = run_continuous([buy, sell], {"buyer": buyer, "seller": seller})
        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0].surplus, -20)
