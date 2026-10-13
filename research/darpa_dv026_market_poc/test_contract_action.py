from __future__ import annotations

import copy
import unittest
from support import *


class ContractActionTests(unittest.TestCase):
    def test_blackbox_action_rejects_capacity_and_observation_transplants(self):
        trader = Trader("buyer", "BUY", 50, 2, 7, "TRUTHFUL", 0)
        obs = "a" * 64
        base = {
            "schema": "darpa-dv026-blackbox-action/v1",
            "order_id": "ord:CONTINUOUS_DOUBLE_AUCTION:buyer",
            "trader_id": "buyer",
            "side": "BUY",
            "price": 50,
            "quantity": 2,
            "action_step": 7,
            "observation_sha256": obs,
        }
        validate_blackbox_action(base, trader, obs, "CONTINUOUS_DOUBLE_AUCTION")
        too_large = copy.deepcopy(base)
        too_large["quantity"] = 3
        with self.assertRaisesRegex(ContractError, "exceeds trader quantity"):
            validate_blackbox_action(too_large, trader, obs, "CONTINUOUS_DOUBLE_AUCTION")
        stale = copy.deepcopy(base)
        stale["observation_sha256"] = "b" * 64
        with self.assertRaisesRegex(ContractError, "digest mismatch"):
            validate_blackbox_action(stale, trader, obs, "CONTINUOUS_DOUBLE_AUCTION")
        transplanted = copy.deepcopy(base)
        transplanted["side"] = "SELL"
        with self.assertRaisesRegex(ContractError, "trader/side transplant"):
            validate_blackbox_action(transplanted, trader, obs, "CONTINUOUS_DOUBLE_AUCTION")
