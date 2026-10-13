# SPDX-License-Identifier: Apache-2.0
"""Differential contracts against the checked-in official Kaggriculture engine."""
from __future__ import annotations

import hashlib
import importlib.util
import os
import pathlib
import sys
import types
import unittest

HERE = pathlib.Path(__file__).resolve().parent
ENGINE_PATH = HERE.parent / "cloud-execution-lab" / "reference" / "engine" / "kaggriculture.py"
ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"

# The engine imports only this helper from the Kaggle package at module load.
# The capacity primitives under test do not call it, so a minimal module keeps
# the proof hermetic on runners that do not preinstall kaggle-environments.
try:
    import kaggle_environments.utils  # type: ignore[import-not-found]  # noqa: F401
except ModuleNotFoundError:
    package = types.ModuleType("kaggle_environments")
    utils = types.ModuleType("kaggle_environments.utils")
    utils.resolve_episode_seed = lambda env: 0
    package.utils = utils
    sys.modules["kaggle_environments"] = package
    sys.modules["kaggle_environments.utils"] = utils

ENGINE_SPEC = importlib.util.spec_from_file_location("w08_pinned_engine", ENGINE_PATH)
if ENGINE_SPEC is None or ENGINE_SPEC.loader is None:
    raise RuntimeError(f"cannot load pinned engine: {ENGINE_PATH}")
ENGINE = importlib.util.module_from_spec(ENGINE_SPEC)
ENGINE_SPEC.loader.exec_module(ENGINE)

LEDGER_SPEC = importlib.util.spec_from_file_location("w08_capacity_ledger_parity", HERE / "capacity_ledger.py")
if LEDGER_SPEC is None or LEDGER_SPEC.loader is None:
    raise RuntimeError("cannot load capacity ledger")
LEDGER = importlib.util.module_from_spec(LEDGER_SPEC)
LEDGER_SPEC.loader.exec_module(LEDGER)


def event(event_id: str, step: int, phase: str, op: str, **kwargs):
    payload = {"id": event_id, "step": step, "phase": phase, "op": op, **kwargs}
    if op == "PLACE" and payload.get("destination") is None:
        payload["destination"] = "shed"
    return payload


def positive(mapping):
    return {key: value for key, value in mapping.items() if value > 0}


def actual_state(shed, inventories):
    farm = ENGINE._new_farm(10, 1_000_000)
    private = ENGINE._new_private()
    private["shed"].update(shed)
    private["inventories"] = [dict(inventory) for inventory in inventories]
    farm["hands"] = [list(farm["farmer"]) for _ in inventories[1:]]
    return farm, private


def ledger_carried(result, count):
    return [result["final"]["carried"].get(str(actor), {}) for actor in range(count)]


class OfficialEngineParityTests(unittest.TestCase):
    def test_official_engine_blob_is_exactly_pinned(self):
        if os.environ.get("W08_ALLOW_ENGINE_STUB") == "1":
            self.skipTest("local primitive stub; hosted CI pins the full engine blob")
        payload = ENGINE_PATH.read_bytes()
        git_blob = hashlib.sha1(
            f"blob {len(payload)}\0".encode("ascii") + payload,
            usedforsecurity=False,
        ).hexdigest()
        self.assertEqual(git_blob, ENGINE_GIT_BLOB)

    def test_drop_and_place_match_official_engine_exhaustively(self):
        cases = 0
        for capacity in range(1, 7):
            for initial in range(capacity + 1):
                for wheat in range(4):
                    for milk in range(4):
                        carried = {"WHEAT": wheat, "MILK": milk}
                        farm, private = actual_state({"EGG": initial}, [carried])
                        before_total = initial + wheat + milk
                        ENGINE._apply_unit_action(
                            farm, private, 0, ["DROP"], 10, 0, 24,
                            shed_capacity=capacity,
                        )
                        result = LEDGER.simulate_capacity(
                            capacity=capacity,
                            initial_shed={"EGG": initial},
                            initial_carried={0: carried},
                            events=[event("drop", 0, "unit", "DROP", actor=0)],
                        )
                        self.assertEqual(result["final"]["shed"], positive(private["shed"]))
                        self.assertEqual(ledger_carried(result, 1), [positive(private["inventories"][0])])
                        actual_discard = before_total - sum(private["shed"].values()) - sum(private["inventories"][0].values())
                        self.assertEqual(result["summary"]["discarded_total"], actual_discard)
                        cases += 1

                for carried_quantity in range(5):
                    for requested in range(6):
                        carried = {"MILK": carried_quantity}
                        farm, private = actual_state({"EGG": initial}, [carried])
                        ENGINE._apply_unit_action(
                            farm, private, 0, ["PLACE", "MILK", requested],
                            10, 0, 24, shed_capacity=capacity,
                        )
                        result = LEDGER.simulate_capacity(
                            capacity=capacity,
                            initial_shed={"EGG": initial},
                            initial_carried={0: carried},
                            events=[event("place", 0, "unit", "PLACE", actor=0,
                                          item="MILK", quantity=requested)],
                        )
                        self.assertEqual(result["final"]["shed"], positive(private["shed"]))
                        self.assertEqual(ledger_carried(result, 1), [positive(private["inventories"][0])])
                        self.assertEqual(result["summary"]["discarded_total"], 0)
                        cases += 1
        self.assertEqual(cases, 1242)

    def test_pickup_matches_official_engine_exhaustively(self):
        cases = 0
        for capacity in range(1, 7):
            for available in range(capacity + 1):
                for requested in range(6):
                    farm, private = actual_state({"WHEAT": available}, [{}])
                    ENGINE._apply_unit_action(
                        farm, private, 0, ["PICKUP", "WHEAT", requested],
                        10, 0, 24, shed_capacity=capacity,
                    )
                    result = LEDGER.simulate_capacity(
                        capacity=capacity,
                        initial_shed={"WHEAT": available},
                        initial_carried={0: {}},
                        events=[event("pickup", 0, "unit", "PICKUP", actor=0,
                                      item="WHEAT", quantity=requested)],
                    )
                    self.assertEqual(result["final"]["shed"], positive(private["shed"]))
                    self.assertEqual(ledger_carried(result, 1), [positive(private["inventories"][0])])
                    cases += 1
        self.assertEqual(cases, 162)

    def test_market_buys_and_sales_match_official_engine_exhaustively(self):
        cases = 0
        for capacity in range(1, 7):
            for occupied in range(capacity + 1):
                for requested in range(6):
                    for op, item in (("BUY_PRODUCT", "WHEAT"), ("BUY_ANIMAL", "COW")):
                        farm, private = actual_state({"EGG": occupied}, [{}])
                        market = {"inventory": {product: 10_000 for product in ENGINE.PRODUCTS}}
                        realized = 0
                        for _ in range(requested):
                            if not ENGINE._commit_unit(op, item, 1, farm, private,
                                                       market, capacity):
                                break
                            realized += 1
                        result = LEDGER.simulate_capacity(
                            capacity=capacity,
                            initial_shed={"EGG": occupied},
                            initial_carried={},
                            events=[event("buy", 0, "market", op,
                                          item=item, quantity=requested)],
                        )
                        self.assertEqual(result["receipts"][0]["realized"], realized)
                        self.assertEqual(result["final"]["shed"], positive(private["shed"]))
                        cases += 1

        for available in range(7):
            for requested in range(7):
                farm, private = actual_state({"WHEAT": available}, [{}])
                market = {"inventory": {product: 10_000 for product in ENGINE.PRODUCTS}}
                realized = 0
                for _ in range(requested):
                    if not ENGINE._commit_unit("SELL", "WHEAT", 1, farm, private,
                                               market, 100):
                        break
                    realized += 1
                result = LEDGER.simulate_capacity(
                    capacity=100,
                    initial_shed={"WHEAT": available},
                    initial_carried={},
                    events=[event("sell", 0, "market", "SELL",
                                  item="WHEAT", quantity=requested)],
                )
                self.assertEqual(result["receipts"][0]["realized"], realized)
                self.assertEqual(result["final"]["shed"], positive(private["shed"]))
                cases += 1
        self.assertEqual(cases, 373)

    def test_eod_drop_matches_official_engine_exhaustively(self):
        cases = 0
        for capacity in range(1, 7):
            for occupied in range(capacity + 1):
                for first in range(4):
                    for second in range(4):
                        inventories = [{"MILK": first}, {"WOOL": second}]
                        farm, private = actual_state({"EGG": occupied}, inventories)
                        before_total = occupied + first + second
                        ENGINE._drop_inventories_to_shed(private, capacity)
                        result = LEDGER.simulate_capacity(
                            capacity=capacity,
                            initial_shed={"EGG": occupied},
                            initial_carried={0: inventories[0], 1: inventories[1]},
                            events=[event("eod", 23, "eod", "EOD_DROP")],
                        )
                        self.assertEqual(result["final"]["shed"], positive(private["shed"]))
                        self.assertEqual(ledger_carried(result, 2),
                                         [positive(value) for value in private["inventories"]])
                        actual_discard = before_total - sum(private["shed"].values())
                        self.assertEqual(result["summary"]["discarded_total"], actual_discard)
                        cases += 1
        self.assertEqual(cases, 432)

    def test_intervening_sale_and_buy_countercase_match_official_engine(self):
        for refill, expected_discard in ((False, 0), (True, 1)):
            farm, private = actual_state(
                {"WHEAT": 99},
                [{"WHEAT": 1}, {"WHEAT": 1}],
            )
            market = {"inventory": {product: 10_000 for product in ENGINE.PRODUCTS}}
            ENGINE._apply_unit_action(farm, private, 0, ["PLACE", "WHEAT", 1],
                                      10, 0, 24, shed_capacity=100)
            self.assertTrue(ENGINE._commit_unit("SELL", "WHEAT", 1, farm, private,
                                                market, 100))
            if refill:
                self.assertTrue(ENGINE._commit_unit("BUY_PRODUCT", "MILK", 1,
                                                    farm, private, market, 100))
            before_drop = sum(private["shed"].values()) + sum(private["inventories"][1].values())
            ENGINE._apply_unit_action(farm, private, 1, ["DROP"],
                                      10, 0, 24, shed_capacity=100)
            actual_discard = before_drop - sum(private["shed"].values())

            events = [
                event("place", 1, "unit", "PLACE", actor=0,
                      item="WHEAT", quantity=1),
                event("sell", 1, "market", "SELL", item="WHEAT", quantity=1,
                      sequence=0),
            ]
            if refill:
                events.append(event("buy", 1, "market", "BUY_PRODUCT",
                                    item="MILK", quantity=1, sequence=1))
            events.append(event("drop", 2, "unit", "DROP", actor=1))
            result = LEDGER.simulate_capacity(
                capacity=100,
                initial_shed={"WHEAT": 99},
                initial_carried={0: {"WHEAT": 1}, 1: {"WHEAT": 1}},
                events=events,
            )
            self.assertEqual(result["final"]["shed"], positive(private["shed"]))
            self.assertEqual(result["summary"]["discarded_total"], actual_discard)
            self.assertEqual(actual_discard, expected_discard)


if __name__ == "__main__":
    unittest.main(verbosity=2)
