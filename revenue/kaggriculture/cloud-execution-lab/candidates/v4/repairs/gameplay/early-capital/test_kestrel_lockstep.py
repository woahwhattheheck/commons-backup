# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import importlib.util
import sys
import unittest

from kestrel_lockstep import (
    OFFICIAL_ENGINE_GIT_BLOB,
    order_early_capital_lockstep,
    rival_lockstep_certificate,
    verify_current_bindings,
)


class FakeMechanics:
    @staticmethod
    def market_price(item, inventory, params=None):
        bases = {"MILK": 500, "WOOL": 400, "CARROT": 300,
                 "WHEAT": 100, "FERTILIZER": 100}
        return max(1, bases.get(item, 250) - max(0, inventory - 10000))


def observation(*products):
    names = set(products) | {"MILK", "WOOL", "CARROT", "WHEAT", "FERTILIZER"}
    inv = {name: 10000 for name in names}
    return {
        "market": {
            "inventory": inv,
            "prices": {name: FakeMechanics.market_price(name, inv[name]) for name in names},
            "params": None,
        }
    }


def action(market):
    return {"farmer": ["PASS"], "hands": [], "market": deepcopy(market)}


def proposal(rows):
    def run(mechanics, obs, cfg, selected, route, decisions=()):
        out = deepcopy(selected)
        out["market"] = deepcopy(rows)
        return out, {
            "changed": out != selected,
            "reason": "ordered" if out != selected else "already_ordered",
            "revision": "v6-commit-real-capital",
            "capital_certificate_reason": "certified",
        }
    return run


CFG = {"maxMarketOrdersPerTurn": 10, "shedCapacity": 100}


class KestrelCurrentV4Contracts(unittest.TestCase):
    def test_disabled_is_exact_parent_identity(self):
        selected = action([["BUY_LAND"], ["SELL", "MILK", 1]])
        out, report = order_early_capital_lockstep(
            FakeMechanics, observation("MILK"), CFG, selected, [], enabled=False,
            base_order=proposal([["SELL", "MILK", 1], ["BUY_LAND"]]))
        self.assertIs(out, selected)
        self.assertEqual(report["reason"], "disabled")

    def test_current_buy_product_sacrifice_shape_is_rejected(self):
        selected = action([["SELL", "WOOL", 10], ["BUY_PRODUCT", "WHEAT", 2], ["BUY_LAND"]])
        candidate = [["SELL", "WOOL", 10], ["BUY_LAND"], ["BUY_PRODUCT", "WHEAT", 2]]
        out, report = order_early_capital_lockstep(
            FakeMechanics, observation("WOOL", "WHEAT"), CFG, selected, [], enabled=True,
            base_order=proposal(candidate))
        self.assertIs(out, selected)
        self.assertIn("unsupported_active_op:BUY_PRODUCT",
                      report["lockstep_certificate"]["barriers"])

    def test_sale_only_single_capital_can_be_certified(self):
        selected = action([["BUY_LAND"], ["SELL", "MILK", 3]])
        candidate = action([["SELL", "MILK", 3], ["BUY_LAND"]])
        ok, report = rival_lockstep_certificate(
            FakeMechanics, observation("MILK"), CFG, selected, candidate)
        self.assertTrue(ok, report)
        self.assertEqual(report["capital"]["candidate_index"], 1)

    def test_certified_wrapper_returns_candidate(self):
        selected = action([["BUY_LAND"], ["SELL", "MILK", 3]])
        rows = [["SELL", "MILK", 3], ["BUY_LAND"]]
        out, report = order_early_capital_lockstep(
            FakeMechanics, observation("MILK"), CFG, selected, [], enabled=True,
            base_order=proposal(rows))
        self.assertEqual(out["market"], rows)
        self.assertIsNot(out, selected)
        self.assertEqual(report["reason"], "rival_lockstep_nonregression_proved")

    def test_rival_buyable_sale_is_rejected(self):
        selected = action([["BUY_LAND"], ["SELL", "WHEAT", 2]])
        candidate = action([["SELL", "WHEAT", 2], ["BUY_LAND"]])
        ok, report = rival_lockstep_certificate(
            FakeMechanics, observation("WHEAT"), CFG, selected, candidate)
        self.assertFalse(ok)
        self.assertIn("rival_buyable_sale:WHEAT", report["barriers"])

    def test_requested_sale_units_cannot_move_later(self):
        selected = action([["SELL", "MILK", 10], ["SELL", "MILK", 1], ["BUY_LAND"]])
        candidate = action([["SELL", "MILK", 1], ["SELL", "MILK", 10], ["BUY_LAND"]])
        ok, report = rival_lockstep_certificate(
            FakeMechanics, observation("MILK"), CFG, selected, candidate)
        self.assertFalse(ok)
        self.assertIn("sale_units_moved_later", report["barriers"])

    def test_inactive_tail_is_exact_parent_owned(self):
        cfg = {"maxMarketOrdersPerTurn": 2, "shedCapacity": 100}
        selected = action([["BUY_LAND"], ["SELL", "MILK", 1], ["PASS"]])
        candidate = action([["SELL", "MILK", 1], ["BUY_LAND"], ["SELL", "WOOL", 1]])
        ok, report = rival_lockstep_certificate(
            FakeMechanics, observation("MILK", "WOOL"), cfg, selected, candidate)
        self.assertFalse(ok)
        self.assertIn("inactive_tail_changed", report["barriers"])

    def test_capital_must_be_last_effectful_candidate_row(self):
        selected = action([["SELL", "MILK", 1], ["SELL", "WOOL", 1], ["BUY_LAND"]])
        candidate = action([["SELL", "MILK", 1], ["BUY_LAND"], ["SELL", "WOOL", 1]])
        ok, report = rival_lockstep_certificate(
            FakeMechanics, observation("MILK", "WOOL"), CFG, selected, candidate)
        self.assertFalse(ok)
        self.assertIn("effectful_order_after_capital", report["barriers"])

    def test_exactly_one_capital_order(self):
        selected = action([["BUY_LAND"], ["BUY_ANIMAL", "COW", 1], ["SELL", "MILK", 1]])
        candidate = action([["SELL", "MILK", 1], ["BUY_LAND"], ["BUY_ANIMAL", "COW", 1]])
        ok, report = rival_lockstep_certificate(
            FakeMechanics, observation("MILK"), CFG, selected, candidate)
        self.assertFalse(ok)
        self.assertIn("requires_exactly_one_capital_order", report["barriers"])

    def test_non_market_mutation_rejected(self):
        selected = action([["BUY_LAND"], ["SELL", "MILK", 1]])
        candidate = action([["SELL", "MILK", 1], ["BUY_LAND"]])
        candidate["farmer"] = ["NORTH"]
        ok, report = rival_lockstep_certificate(
            FakeMechanics, observation("MILK"), CFG, selected, candidate)
        self.assertFalse(ok)
        self.assertIn("non_market_mutation", report["barriers"])

    def test_bool_configuration_poison_fails_closed(self):
        selected = action([["BUY_LAND"], ["SELL", "MILK", 1]])
        candidate = action([["SELL", "MILK", 1], ["BUY_LAND"]])
        ok, report = rival_lockstep_certificate(
            FakeMechanics, observation("MILK"), {"maxMarketOrdersPerTurn": True}, selected, candidate)
        self.assertFalse(ok)
        self.assertIn("invalid_maxMarketOrdersPerTurn", report["barriers"])

    def test_changed_candidate_requires_canonical_v6_base_report(self):
        selected = action([["BUY_LAND"], ["SELL", "MILK", 1]])
        rows = [["SELL", "MILK", 1], ["BUY_LAND"]]
        def spoof(mechanics, obs, cfg, selected, route, decisions=()):
            out = deepcopy(selected)
            out["market"] = deepcopy(rows)
            return out, {"changed": True, "reason": "ordered"}
        out, report = order_early_capital_lockstep(
            FakeMechanics, observation("MILK"), CFG, selected, [], enabled=True,
            base_order=spoof)
        self.assertIs(out, selected)
        self.assertEqual(report["reason"], "canonical_base_unproven")

    def test_checkout_exact_current_predecessor_and_bindings(self):
        here = Path(__file__).resolve()
        cloud = None
        for parent in [here.parent, *here.parents]:
            candidate = parent / "revenue/kaggriculture/cloud-execution-lab"
            if (candidate / "early_capital.py").is_file():
                cloud = candidate
                break
        if cloud is None:
            self.skipTest("repository cloud-execution-lab checkout unavailable")
        receipt = verify_current_bindings(cloud)
        self.assertTrue(receipt["ok"], receipt)

        source = cloud / "candidates/v4/repairs/gameplay/early-capital/early_capital.py"
        spec = importlib.util.spec_from_file_location("canonical_v4_early_capital", source)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        current = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(current)
        old_path = list(sys.path)
        sys.path.insert(0, str(cloud))
        try:
            import mechanics as mechanics
        finally:
            sys.path[:] = old_path
        self.assertEqual(OFFICIAL_ENGINE_GIT_BLOB,
                         receipt["observed"]["reference/engine/kaggriculture.py"])

        products = list(mechanics.PRODUCTS)
        stock = {p: 0 for p in products}
        own = {"money": 5000, "unlocked_quadrants": ["NW"], "hires_today": 0,
               "tiles": [[None] * 10 for _ in range(10)], "farmer": (4, 4), "hands": []}
        rival = deepcopy(own)
        obs = {
            "step": 150, "day": 6, "hour": 6, "player": 0,
            "farms": [own, rival],
            "private": {"shed": stock, "inventories": [{}], "seeds": {}},
            "market": {"inventory": {p: 10000 for p in products},
                       "prices": {p: mechanics.market_price(p, 10000, None) for p in products},
                       "params": None},
        }
        cfg = {"episodeSteps": 720, "turnsPerDay": 24, "farmHandCostMult": 1,
               "maxMarketOrdersPerTurn": 10, "shedCapacity": 100, "boardSize": 10}
        selected = {"farmer": ["PASS"], "hands": [],
                    "market": [["BUY_PRODUCT", "WHEAT", 2], ["BUY_LAND"]]}
        route = [{"farmer": ["PASS"], "hands": [], "market": []} for _ in range(720)]
        base, base_report = current.order_early_capital(
            mechanics, obs, cfg, selected, route, ((226, "x", 1, "t"),))
        self.assertTrue(base_report["changed"])
        ops = [row[0] for row in base["market"]]
        self.assertLess(ops.index("BUY_LAND"), ops.index("BUY_PRODUCT"))

        guarded, guarded_report = order_early_capital_lockstep(
            mechanics, obs, cfg, selected, route, ((226, "x", 1, "t"),),
            enabled=True, base_order=current.order_early_capital)
        self.assertIs(guarded, selected)
        self.assertIn("unsupported_active_op:BUY_PRODUCT",
                      guarded_report["lockstep_certificate"]["barriers"])


if __name__ == "__main__":
    unittest.main()
