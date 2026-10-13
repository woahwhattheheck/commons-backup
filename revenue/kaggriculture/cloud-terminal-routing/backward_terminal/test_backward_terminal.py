# SPDX-License-Identifier: Apache-2.0
"""Focused contracts plus the retained source-bound integration census."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

import backward_terminal as bt
import evaluate_archive as cli


class FakeEngine:
    PRODUCTS = ("CARROT",)

    @staticmethod
    def _new_private():
        return {"shed": {"CARROT": 0}, "seeds": {}, "inventories": [{}]}


class PureContractTests(unittest.TestCase):
    def test_omit_farmer_preserves_market_and_input(self):
        action = {"farmer": ["WATER"], "hands": [["NORTH"]],
                  "market": [["SELL", "CARROT", 2]]}
        original = deepcopy(action)
        changed = bt.omit_unit_action(action, 0)
        self.assertEqual(action, original)
        self.assertEqual(changed["farmer"], ["PASS"])
        self.assertEqual(changed["hands"], original["hands"])
        self.assertEqual(changed["market"], original["market"])

    def test_omit_hand_preserves_slot(self):
        action = {"farmer": ["NORTH"],
                  "hands": [["WEST"], ["FERTILIZE"], ["EAST"]],
                  "market": []}
        changed = bt.omit_unit_action(action, 2)
        self.assertEqual(changed["hands"], [["WEST"], ["PASS"], ["EAST"]])
        with self.assertRaises(bt.RecordError):
            bt.omit_unit_action(action, 4)

    def test_service_occurrences_are_indexed(self):
        action = {"farmer": ["CARE"],
                  "hands": [["PASS"], ["FEED"], ["WATER"], ["FERTILIZE"]],
                  "market": []}
        self.assertEqual(bt.service_occurrences(action),
                         ((0, "CARE"), (2, "FEED"), (3, "WATER"),
                          (4, "FERTILIZE")))

    def test_sale_counts_are_per_successful_unit(self):
        record = {"final_day_receipts": [
            {"step": 718, "player": 0, "op": "SELL", "item": "CARROT", "cash": 12},
            {"step": 718, "player": 0, "op": "SELL", "item": "CARROT", "cash": 11},
            {"step": 718, "player": 1, "op": "SELL", "item": "CARROT", "cash": 10},
            {"step": 718, "player": 1, "op": "BUY_PRODUCT", "item": "CARROT", "cash": -9},
        ]}
        counts = bt.sale_counts(record)
        self.assertEqual(counts[(718, 0, "CARROT")], 2)
        self.assertEqual(counts[(718, 1, "CARROT")], 1)

    def test_delta_hash_is_order_sensitive_and_stable(self):
        one = bt.digest([["shed", [["A", {"before": 0, "after": 1}]]]])
        two = bt.digest([["shed", [["B", {"before": 0, "after": 1}]]]])
        self.assertNotEqual(one, two)
        self.assertEqual(one, bt.digest([["shed", [["A", {"before": 0, "after": 1}]]]]))


class EngineFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = os.environ.get("KAGGRICULTURE_ENGINE")
        if not root:
            raise unittest.SkipTest("KAGGRICULTURE_ENGINE not supplied")
        cls.engine = cli.load_engine(Path(root))

    def make_record(self):
        m = self.engine
        config = {key: value.get("default") if isinstance(value, dict) else value
                  for key, value in m.specification["configuration"].items()}
        config["episodeSteps"] = 720
        seat = 0
        farms = [m._new_farm(10, 0), m._new_farm(10, 0)]
        private = [m._new_private(), m._new_private()]
        x, y = m._default_spawn(10)
        farms[0]["tiles"][y][x] = m._new_plant("CARROT", 27, 24)
        private[0]["inventories"][0] = {"FERTILIZER": 1}
        market = m._new_market()
        town = m._new_town()
        actions = {
            712: [{"farmer": ["FERTILIZE"], "hands": [], "market": []},
                  {"farmer": ["PASS"], "hands": [], "market": []}],
            713: [{"farmer": ["WATER"], "hands": [], "market": []},
                  {"farmer": ["PASS"], "hands": [], "market": []}],
            714: [{"farmer": ["HARVEST"], "hands": [], "market": []},
                  {"farmer": ["PASS"], "hands": [], "market": []}],
            715: [{"farmer": ["DROP"], "hands": [], "market": []},
                  {"farmer": ["PASS"], "hands": [], "market": []}],
            716: [{"farmer": ["PASS"], "hands": [],
                   "market": [["SELL", "CARROT", 8]]},
                  {"farmer": ["PASS"], "hands": [], "market": []}],
            717: [{"farmer": ["PASS"], "hands": [], "market": []},
                  {"farmer": ["PASS"], "hands": [], "market": []}],
            718: [{"farmer": ["PASS"], "hands": [], "market": []},
                  {"farmer": ["PASS"], "hands": [], "market": []}],
        }
        frames = []
        for step in range(712, 719):
            obs = {"step": step, "player": seat, "private": deepcopy(private[seat]),
                   "farms": deepcopy(farms), "market": deepcopy(market),
                   "town": deepcopy(town), "day": step // 24, "hour": step % 24}
            frames.append({"step": step, "observation": obs,
                           "configuration": deepcopy(config),
                           "actions": deepcopy(actions[step])})
            states = []
            for player in (0, 1):
                o = bt.Struct(step=step, player=player, private=private[player],
                              farms=farms, market=market, town=town,
                              day=step // 24, hour=step % 24)
                states.append(bt.Struct(observation=o, action=deepcopy(actions[step][player]),
                                        status="ACTIVE", reward=0.0))
            env = bt.Struct(configuration=bt.Struct(config), done=False, info={"seed": 7})
            m.interpreter(states, env)
            farms = states[0].observation.farms
            market = states[0].observation.market
            town = states[0].observation.town
            private = [states[0].observation.private, states[1].observation.private]
        return {
            "seed": 7, "candidate_seat": seat, "status": "complete",
            "scores": [farms[0]["money"], farms[1]["money"]],
            "arm": "fixture", "opponent": "pass", "final_day": frames,
            "final_day_receipts": [],
            "terminal": {"farms": deepcopy(farms), "private": deepcopy(private)},
        }

    def test_baseline_and_fertilizer_counterfactual(self):
        record = self.make_record()
        baseline = bt.replay_suffix(self.engine, record, 712)
        self.assertEqual(bt.validate_baseline(record, baseline), 7)
        changed = bt.replay_suffix(self.engine, record, 712, omit_unit=0)
        self.assertLess(changed.cash[0], baseline.cash[0])
        self.assertEqual(changed.private["shed"]["FERTILIZER"], 1)

    def test_water_counterfactual_is_worse(self):
        record = self.make_record()
        baseline = bt.replay_suffix(self.engine, record, 713)
        changed = bt.replay_suffix(self.engine, record, 713, omit_unit=0)
        self.assertLess(changed.cash[0], baseline.cash[0])
        self.assertLess(changed.market["inventory"]["CARROT"],
                        baseline.market["inventory"]["CARROT"])

    def test_non_sell_future_market_is_rejected(self):
        record = self.make_record()
        record["final_day"][2]["actions"][1]["market"] = [["HIRE"]]
        with self.assertRaisesRegex(bt.RecordError, "non-SELL"):
            bt.replay_suffix(self.engine, record, 712)

    def test_hidden_end_of_day_boundary_is_rejected(self):
        record = self.make_record()
        for frame in record["final_day"]:
            frame["configuration"]["turnsPerDay"] = 17
        # 713 + 1 = 714 is divisible by 17 * 42.
        with self.assertRaisesRegex(bt.RecordError, "end-of-day"):
            bt.replay_suffix(self.engine, record, 712)

    def test_baseline_tamper_is_detected(self):
        record = self.make_record()
        replay = bt.replay_suffix(self.engine, record, 712)
        record["final_day"][1]["observation"]["farms"][0]["money"] += 1
        with self.assertRaisesRegex(bt.RecordError, "diverges"):
            bt.validate_baseline(record, replay)

    def test_scan_fixture(self):
        record = self.make_record()
        report = bt.scan_records(self.engine, [("fixture.json", record)], first_step=712)
        self.assertEqual(report["candidate_occurrences"], 2)
        self.assertEqual(report["own_cash_effects"]["positive"], 0)
        self.assertEqual(report["own_cash_effects"]["zero"], 0)
        self.assertEqual(report["own_cash_effects"]["negative"], 2)
        self.assertEqual(report["conclusion"], "preserve_all_observed_service_actions")


class RetainedArchiveTests(unittest.TestCase):
    def test_complete_development_census(self):
        archive = os.environ.get("OSPREY_RAW_ARCHIVE")
        engine_root = os.environ.get("KAGGRICULTURE_ENGINE")
        if not archive or not engine_root:
            self.skipTest("retained source archive and official engine not supplied")
        records = cli.read_records(Path(archive))
        report = bt.scan_records(cli.load_engine(Path(engine_root)), records)
        self.assertEqual(report["source_records"], 32)
        self.assertEqual(report["baseline_starts"], 472)
        self.assertEqual(report["baseline_transition_checks"], 5608)
        self.assertEqual(report["baseline_mismatches"], 0)
        self.assertEqual(report["candidate_occurrences"], 1472)
        self.assertEqual(report["distinct_exact_candidates"], 1380)
        self.assertEqual(report["operations"], {"FERTILIZE": 736, "WATER": 736})
        self.assertEqual(report["own_cash_effects"]["positive"], 0)
        self.assertEqual(report["own_cash_effects"]["zero"], 0)
        self.assertEqual(report["own_cash_effects"]["negative"], 1472)
        self.assertEqual(report["operation_ranges"]["FERTILIZE"]["own_cash_min"], -61.0)
        self.assertEqual(report["operation_ranges"]["FERTILIZE"]["own_cash_max"], -27.0)
        self.assertEqual(report["operation_ranges"]["WATER"]["own_cash_min"], -122.0)
        self.assertEqual(report["operation_ranges"]["WATER"]["own_cash_max"], -54.0)
        self.assertEqual(report["conclusion"], "preserve_all_observed_service_actions")


if __name__ == "__main__":
    unittest.main()
