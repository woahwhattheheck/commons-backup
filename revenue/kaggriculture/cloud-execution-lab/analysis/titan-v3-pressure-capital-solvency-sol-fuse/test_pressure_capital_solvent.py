# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
PRESSURE_DIR = LAB.parent / "cloud-opponent-league" / "lark-responsive"
for root in (LAB, PRESSURE_DIR):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

import mechanics
import early_capital
import sell_priority  # pressure_priority's exact sibling import
import pressure_priority
import pressure_capital_solvent as guard


def load_engine():
    path = LAB / "reference" / "engine" / "kaggriculture.py"
    spec = importlib.util.spec_from_file_location("_sol_fuse_official_engine", path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ENGINE = load_engine()
CONFIG = {
    "boardSize": 10,
    "episodeSteps": 720,
    "turnsPerDay": 24,
    "maxMarketOrdersPerTurn": 10,
    "farmHandCostMult": 1,
    "shedCapacity": 100,
}


def action(market):
    return {"farmer": ["PASS"], "hands": [], "market": deepcopy(market)}


def observation(money=176, *, hires=0, unlocked=("NW", "NE")):
    farm = {
        "money": money,
        "hires_today": hires,
        "unlocked_quadrants": list(unlocked),
        "tiles": [[None] * 10 for _ in range(10)],
        "farmer": [4, 4],
        "hands": [],
    }
    rival = deepcopy(farm)
    rival.update(money=0, unlocked_quadrants=["NW"])
    return {
        "step": 96,
        "player": 0,
        "farms": [farm, rival],
        "private": {"shed": {item: 0 for item in ENGINE.PRODUCTS},
                    "seeds": {}, "inventories": [{}]},
        "market": ENGINE._new_market(),
        "town": {"unlocked_shops": []},
    }


def run_market(own_action):
    market = ENGINE._new_market()
    tiles = [[None if y < 5 else "LOCKED" for _ in range(10)] for y in range(10)]
    farms = [
        {"money": 176, "hires_today": 0, "unlocked_quadrants": ["NW", "NE"],
         "tiles": deepcopy(tiles), "farmer": [4, 4], "hands": []},
        {"money": 0, "hires_today": 0, "unlocked_quadrants": ["NW"],
         "tiles": deepcopy(tiles), "farmer": [4, 4], "hands": []},
    ]
    private = [
        {"shed": {item: 0 for item in ENGINE.PRODUCTS}, "seeds": {}, "inventories": [{}]},
        {"shed": {item: 0 for item in ENGINE.PRODUCTS}, "seeds": {}, "inventories": [{}]},
    ]
    private[0]["shed"].update(CARROT=10, MILK=10)
    private[1]["shed"].update(CARROT=10)
    states = [
        SimpleNamespace(observation=SimpleNamespace(
            market=market, farms=farms, private=private[0]), action=deepcopy(own_action)),
        SimpleNamespace(observation=SimpleNamespace(
            market=market, farms=farms, private=private[1]),
            action=action([["SELL", "CARROT", 10]])),
    ]
    ENGINE._process_market(states, SimpleNamespace(configuration=CONFIG))
    return farms[0]["money"], list(farms[0]["unlocked_quadrants"])


class PressureCapitalContracts(unittest.TestCase):
    def setUp(self):
        self.before = action([
            ["SELL", "CARROT", 10], ["SELL", "MILK", 10], ["BUY_LAND"]])
        self.after = action([
            ["SELL", "MILK", 10], ["SELL", "CARROT", 10], ["BUY_LAND"]])

    def compose(self, before=None, after=None, *, money=176, config=None):
        return guard.preserve_acquisition_solvency(
            mechanics, observation(money), config or CONFIG,
            self.before if before is None else before,
            self.after if after is None else after)

    def test_exact_official_predecessor_is_killed(self):
        obs = observation()
        inherited, report = early_capital.order_early_capital(
            mechanics, obs, CONFIG, self.before, route=[], decisions=[])
        self.assertEqual(inherited, self.before)
        self.assertEqual(report["reason"], "already_ordered")
        scores = tuple(pressure_priority.lot_pressure(
            row, obs["market"], mechanics.market_price)
            for row in inherited["market"][:2])
        self.assertEqual(scores, (22.0, 210.0))
        pressured = pressure_priority.transform(
            inherited, obs, CONFIG, quote=mechanics.market_price)
        self.assertEqual(pressured, self.after)
        self.assertEqual(run_market(inherited), (0, ["NW", "NE", "SW"]))
        self.assertEqual(run_market(pressured), (1988, ["NW", "NE"]))
        repaired, guard_report = self.compose(after=pressured)
        self.assertEqual(repaired, inherited)
        self.assertEqual(guard_report["reason"], "sale_credit_required")
        self.assertEqual(guard_report["certificate"]["cash_shortfall"], 1824)

    def test_sale_only_and_nonexecuted_suffix_keep_pressure(self):
        before = action([["SELL", "CARROT", 1], ["SELL", "MILK", 1]])
        after = action([["SELL", "MILK", 1], ["SELL", "CARROT", 1]])
        returned, report = self.compose(before, after)
        self.assertEqual(returned, after)
        self.assertEqual(report["reason"], "no_downstream_acquisition")
        returned, report = self.compose(config={**CONFIG, "maxMarketOrdersPerTurn": 2})
        self.assertEqual(returned, self.after)
        self.assertEqual(report["reason"], "no_downstream_acquisition")

    def test_starting_cash_certificate_covers_fixed_order_families(self):
        cases = [
            (["BUY_LAND"], 2000, 1999),
            (["HIRE"], 1, 0),
            (["BUY_SEED", "CARROT", 3], 60, 59),
            (["BUY_ANIMAL", "COW", 2], 800, 799),
        ]
        for purchase, safe_cash, short_cash in cases:
            with self.subTest(purchase=purchase):
                before = action([["SELL", "CARROT", 1], ["SELL", "MILK", 1], purchase])
                after = action([["SELL", "MILK", 1], ["SELL", "CARROT", 1], purchase])
                returned, report = self.compose(before, after, money=safe_cash)
                self.assertEqual(returned, after)
                self.assertTrue(report["accepted"])
                returned, report = self.compose(before, after, money=short_cash)
                self.assertEqual(returned, before)
                self.assertEqual(report["reason"], "sale_credit_required")

    def test_fibonacci_hires_and_land_index_advance(self):
        before = action([["SELL", "CARROT", 1], ["SELL", "MILK", 1],
                         ["HIRE"], ["HIRE"], ["HIRE"]])
        after = action([["SELL", "MILK", 1], ["SELL", "CARROT", 1],
                        ["HIRE"], ["HIRE"], ["HIRE"]])
        returned, report = self.compose(before, after, money=4)
        self.assertEqual(returned, after)
        self.assertEqual(report["certificate"]["spent_without_sales"], 4)
        before = action([["SELL", "CARROT", 1], ["SELL", "MILK", 1],
                         ["BUY_LAND"], ["BUY_LAND"]])
        after = action([["SELL", "MILK", 1], ["SELL", "CARROT", 1],
                        ["BUY_LAND"], ["BUY_LAND"]])
        returned, report = self.compose(before, after, money=6000)
        self.assertEqual(returned, after)
        self.assertEqual(report["certificate"]["spent_without_sales"], 6000)

    def test_variable_price_or_contract_drift_fails_closed(self):
        before = action([["SELL", "CARROT", 1], ["SELL", "MILK", 1],
                         ["BUY_PRODUCT", "WHEAT", 1]])
        after = action([["SELL", "MILK", 1], ["SELL", "CARROT", 1],
                        ["BUY_PRODUCT", "WHEAT", 1]])
        returned, report = self.compose(before, after, money=10**9)
        self.assertEqual(returned, before)
        self.assertEqual(report["reason"], "variable_price_purchase")
        changed = deepcopy(self.after)
        changed["market"][0][2] = 11
        self.assertEqual(self.compose(after=changed)[1]["reason"],
                         "executable_multiset_changed")
        changed = deepcopy(self.after)
        changed["farmer"] = ["NORTH"]
        self.assertEqual(self.compose(after=changed)[1]["reason"],
                         "non_market_changed:farmer")

    def test_identity_suffix_integrity_and_immutability(self):
        returned, report = self.compose(after=deepcopy(self.before))
        self.assertEqual(returned, self.before)
        self.assertEqual(report["reason"], "pressure_identity")
        before = action([["SELL", "CARROT", 1], ["SELL", "MILK", 1], ["PASS"]])
        after = action([["SELL", "MILK", 1], ["SELL", "CARROT", 1], []])
        self.assertEqual(self.compose(
            before, after, config={**CONFIG, "maxMarketOrdersPerTurn": 2})[1]["reason"],
            "inactive_suffix_changed")
        frozen = deepcopy((self.before, self.after))
        self.compose(self.before, self.after)
        self.assertEqual((self.before, self.after), frozen)


if __name__ == "__main__":
    unittest.main()
