# SPDX-License-Identifier: Apache-2.0
"""Native-parser parity for inherited malformed-quantity terminal orders.

Run with the existing pinned engine/consumer paths; this suite runs no games.
No input downloads, source writes, scenario inference, or policy promotion.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

import terminal_input_cases as cases

DEPS = None
PRODUCER = None
COUNTS = {"producer_market_cells": 0, "reference_terminal_transitions": 0,
          "unit_snapshots": 0, "consumer_calls": 0}
WITNESSES = []
INVALID_JSON_QUANTITIES = [None, "not-an-int", "", [], {}]
OPERATIONS = [("SELL", "CARROT"), ("BUY_SEED", "CARROT"),
              ("BUY_PRODUCT", "WHEAT"), ("BUY_ANIMAL", "SHEEP")]


def source_identity(path):
    data = Path(path).read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "git_blob": hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()}


def load_producer(path):
    spec = importlib.util.spec_from_file_location("_terminal_noop_producer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture(position=0, *, quantity="not-an-int", operation="BUY_SEED", item="CARROT"):
    farm = {"money": 100000, "tiles": [[None for _ in range(10)] for _ in range(10)],
            "farmer": [4, 4], "hands": [], "unlocked_quadrants": ["NW"], "hires_today": 0}
    farms = [deepcopy(farm), deepcopy(farm)]
    farms[position]["money"] += 33
    market = {"inventory": {p: 10000 for p in DEPS.engine.PRODUCTS}, "prices": {}}
    DEPS.engine._refresh_prices(market)
    cfg = dict(episodeSteps=720, boardSize=10, turnsPerDay=24, shedCapacity=100,
               maxMarketOrdersPerTurn=10, farmHandCostMult=1)
    obs = {"step": 718, "player": position, "farms": farms, "market": market,
           "day": 29, "hour": 22, "town": {"unlocked_shops": []},
           "private": {"shed": {"WHEAT": 2, "MILK": 2}, "seeds": {}, "inventories": [{}]}}
    action = {"farmer": ["PASS"], "hands": [],
              "market": [[], ["SELL", "WHEAT", 2], ["SELL", "MILK", 2]] +
                        [[] for _ in range(6)] + [[operation, item, deepcopy(quantity)]],
              "caller_metadata": {"retained": True}}
    scenarios = [
        {"id": "wheat17", "shed": {"WHEAT": 17}, "market": [["SELL", "WHEAT", 17], []],
         "origin": "retained constructed PORT pattern; not a game input"},
        {"id": "milk2-wheat3", "shed": {"MILK": 2, "WHEAT": 3},
         "market": [["SELL", "MILK", 2], ["SELL", "WHEAT", 3]],
         "origin": "retained constructed PORT pattern; not a game input"},
    ]
    return obs, cfg, action, scenarios


def snapshot(obs, cfg, action):
    COUNTS["unit_snapshots"] += 1
    return cases.own_unit_snapshot(DEPS.engine, obs, cfg, action)


def build(obs, cfg, action, scenarios, *, post=None, **kwargs):
    if post is None:
        post = snapshot(obs, cfg, action)
    packet = PRODUCER.build_terminal_inputs(DEPS.engine, obs, cfg, action,
        post_unit_observation=post, scenarios=scenarios, **kwargs)
    COUNTS["producer_market_cells"] += packet["native_market_calls"]
    return packet


def native_receipt(obs, cfg, action, scenario):
    state, env = cases.make_state(obs, cfg, action, scenario)
    DEPS.engine.interpreter(state, env)
    COUNTS["reference_terminal_transitions"] += 1
    if [s.status for s in state] != ["DONE", "DONE"]:
        raise AssertionError("Expected a completed native terminal transition")
    position = obs["player"]
    return {"own_cash": state[position].reward, "rival_cash": state[1-position].reward,
            "own_private": deepcopy(state[position].observation.private)}


class NativeNoopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if DEPS is None or PRODUCER is None:
            raise unittest.SkipTest("Supply the pinned engine and actual consumer paths via this file's CLI")

    def test_native_ignored_quantities_are_accepted_by_queue_preflight(self):
        for operation, item in OPERATIONS:
            for quantity in INVALID_JSON_QUANTITIES:
                with self.subTest(operation=operation, quantity=quantity):
                    queue = [[operation, item, deepcopy(quantity)]]
                    self.assertIsNone(DEPS.engine._parse_order(queue[0]))
                    before = deepcopy(queue)
                    PRODUCER._queue_ok(queue, 10)
                    self.assertEqual(queue, before)

    def test_whole_tables_match_native_cash_for_all_ignored_quantity_types(self):
        for position in (0, 1):
            for operation, item in OPERATIONS:
                for quantity in INVALID_JSON_QUANTITIES:
                    with self.subTest(position=position, operation=operation, quantity=quantity):
                        obs, cfg, action, scenarios = fixture(position, quantity=quantity,
                                                              operation=operation, item=item)
                        packet = build(obs, cfg, action, scenarios)
                        self.assertTrue(packet["complete"])
                        by_id = {s["id"]: s for s in scenarios}
                        for row in packet["document"]["receipts"]:
                            self.assertTrue(row["done"])
                            actual = native_receipt(obs, cfg, row["own_action"], by_id[row["scenario"]])
                            self.assertEqual([row["own_cash"], row["rival_cash"]],
                                             [actual["own_cash"], actual["rival_cash"]])
                            self.assertEqual(row["own_seeds_after"], actual["own_private"]["seeds"])
                        if operation != "SELL":
                            self.assertTrue(all(p["action"]["market"][9] == action["market"][9]
                                                for p in packet["plans"]))

    def test_ignored_seed_order_no_longer_suppresses_existing_winning_choice(self):
        for position in (0, 1):
            with self.subTest(position=position):
                obs, cfg, action, scenarios = fixture(position)
                before = deepcopy((obs, cfg, action, scenarios))
                packet = build(obs, cfg, action, scenarios)
                output, actor = cases.choose(DEPS, obs, cfg, action, packet)
                COUNTS["consumer_calls"] += 1
                self.assertNotEqual(output, action)
                self.assertEqual(output["market"][9], action["market"][9])
                self.assertEqual(output["farmer"], action["farmer"])
                self.assertEqual(output["caller_metadata"], action["caller_metadata"])
                self.assertEqual(actor.draws, 1)
                self.assertEqual(actor.last_objective["value"], "1")
                selected_rows = [native_receipt(obs, cfg, output, s) for s in scenarios]
                self.assertTrue(all(r["own_cash"] > r["rival_cash"] for r in selected_rows))
                baseline_rows = [native_receipt(obs, cfg, action, s) for s in scenarios]
                self.assertTrue(any(r["own_cash"] < r["rival_cash"] for r in baseline_rows))
                self.assertEqual((obs, cfg, action, scenarios), before)
                WITNESSES.append({"player": position, "selected_action": action,
                    "output_action": output, "baseline_native": baseline_rows,
                    "chosen_native": selected_rows, "draws": actor.draws,
                    "objective_value": actor.last_objective["value"],
                    "scope": "Constructed terminal case, not a reached or full-game win"})

    def test_unknown_list_and_mapping_opcodes_match_native_noops(self):
        for opcode in ([], {}, ["SELL"], {"op": "SELL"}):
            with self.subTest(opcode=opcode):
                order = [deepcopy(opcode), "WHEAT", 2]
                self.assertIsNone(DEPS.engine._parse_order(order))
                PRODUCER._queue_ok([order], 10)

    def test_unknown_opcode_keeps_its_slot_in_complete_native_tables(self):
        for position in (0, 1):
            for opcode in ([], {}):
                with self.subTest(position=position, opcode=opcode):
                    obs, cfg, action, scenarios = fixture(position)
                    action["market"][9] = [deepcopy(opcode), "WHEAT", 2]
                    packet = build(obs, cfg, action, scenarios)
                    self.assertTrue(packet["complete"])
                    by_id = {s["id"]: s for s in scenarios}
                    for row in packet["document"]["receipts"]:
                        self.assertEqual(row["own_action"]["market"][9], action["market"][9])
                        actual = native_receipt(obs, cfg, row["own_action"], by_id[row["scenario"]])
                        self.assertEqual([row["own_cash"], row["rival_cash"]],
                                         [actual["own_cash"], actual["rival_cash"]])

    def test_current_units_are_not_replayed(self):
        obs, cfg, action, scenarios = fixture()
        obs["private"]["shed"] = {}
        obs["private"]["inventories"] = [{"WHEAT": 2, "MILK": 2}]
        action["farmer"] = ["DROP"]
        post = snapshot(obs, cfg, action)
        with patch.object(DEPS.engine, "_apply_unit_action", side_effect=AssertionError("duplicate units")):
            packet = build(obs, cfg, action, scenarios, post=post)
        self.assertTrue(packet["complete"])
        self.assertEqual(packet["fallback_action"], action)
        self.assertEqual(obs["private"]["shed"], {})

    def test_unchanged_valid_quantity_coercions_match_native(self):
        for quantity in (2, "2", " 2 ", 2.75, True):
            with self.subTest(quantity=quantity):
                obs, cfg, action, scenarios = fixture(quantity=quantity)
                self.assertEqual(DEPS.engine._parse_order(action["market"][9])["remaining"], int(quantity))
                packet = build(obs, cfg, action, scenarios[:1], max_plans=1)
                row = packet["document"]["receipts"][0]
                actual = native_receipt(obs, cfg, action, scenarios[0])
                self.assertEqual(row["own_cash"], actual["own_cash"])
                self.assertEqual(row["own_seeds_after"], actual["own_private"]["seeds"])

    def test_native_overflow_still_stops_before_market_calls(self):
        for quantity in (float("inf"), float("-inf")):
            with self.subTest(quantity=quantity):
                obs, cfg, action, scenarios = fixture(quantity=quantity)
                with self.assertRaises(OverflowError):
                    DEPS.engine._parse_order(action["market"][9])
                post = snapshot(obs, cfg, action)
                with patch.object(DEPS.engine, "_process_market", side_effect=AssertionError("native overflow call")):
                    with self.assertRaisesRegex(ValueError, "Unsupported noninteger"):
                        build(obs, cfg, action, scenarios, post=post)

    def test_quantity_work_bounds_are_preserved(self):
        for count in (1001, -1001):
            with self.subTest(count=count), self.assertRaisesRegex(ValueError, "bounded consumer"):
                PRODUCER._queue_ok([["SELL", "WHEAT", count]], 10)
        PRODUCER._queue_ok([["SELL", "WHEAT", 1000], ["SELL", "WHEAT", -1000]], 10)

    def test_incomplete_table_preserves_full_fallback(self):
        obs, cfg, action, scenarios = fixture()
        packet = build(obs, cfg, action, scenarios, max_cells=1)
        self.assertFalse(packet["complete"])
        self.assertEqual(packet["native_market_calls"], 1)
        output, actor = cases.choose(DEPS, obs, cfg, action, packet)
        COUNTS["consumer_calls"] += 1
        self.assertEqual(output, action)
        self.assertEqual(actor.draws, 0)

    def test_expired_deadline_does_not_call_native_market(self):
        obs, cfg, action, scenarios = fixture()
        post = snapshot(obs, cfg, action)
        with patch.object(DEPS.engine, "_process_market", side_effect=AssertionError("expired call")):
            packet = build(obs, cfg, action, scenarios, post=post, deadline=time.perf_counter() - 1)
        self.assertEqual(packet["status"], "deadline")
        self.assertEqual(packet["native_market_calls"], 0)
        self.assertFalse(packet["complete"])

    def test_inactive_malformed_tail_is_preserved(self):
        obs, cfg, action, scenarios = fixture()
        cfg["maxMarketOrdersPerTurn"] = 3
        packet = build(obs, cfg, action, scenarios)
        self.assertTrue(packet["complete"])
        self.assertTrue(all(p["action"]["market"][3:] == action["market"][3:] for p in packet["plans"]))

    def test_nonfinite_json_receipts_are_still_unavailable(self):
        obs, cfg, action, scenarios = fixture(quantity=float("nan"))
        # Native ignores NaN, but result documents deliberately require finite JSON.
        with self.assertRaises(ValueError):
            build(obs, cfg, action, scenarios)


def main(argv=None):
    global DEPS, PRODUCER
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--producer-file", type=Path, default=Path(__file__).with_name("terminal_inputs.py"))
    parser.add_argument("--loader", type=Path, required=True)
    parser.add_argument("--engine-dir", type=Path, required=True)
    parser.add_argument("--consumers", type=Path, required=True)
    parser.add_argument("--core-file", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    DEPS = cases.dependencies(args.loader, args.engine_dir, args.consumers, args.core_file)
    PRODUCER = load_producer(args.producer_file)
    log = io.StringIO()
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(NativeNoopTests))
    report = {"schema": "titan.terminal-order-noops.tests.v1", "tests": result.testsRun,
              "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
              "success": result.wasSuccessful(), "counts": COUNTS, "witnesses": WITNESSES,
              "sources": {"producer": source_identity(args.producer_file), "tests": source_identity(__file__),
                          "engine": source_identity(args.engine_dir / "kaggriculture.py"),
                          "score": source_identity(args.consumers / "score_endgame.py"),
                          "weighted": source_identity(args.consumers / "weighted_selector.py"),
                          "selector": source_identity(args.consumers / "selector.py"),
                          "utility": source_identity(args.consumers / "terminal_utility.py"),
                          "solver": source_identity(args.core_file)},
              "full_games": 0, "new_game_seeds": 0, "log": log.getvalue()}
    with args.report.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
        handle.write("\n")
    print(log.getvalue(), end="")
    print(json.dumps({k: report[k] for k in ("success", "tests", "failures", "errors", "skipped", "counts")}, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
