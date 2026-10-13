#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("phase_barrier", HERE / "phase_barrier.py")
assert SPEC is not None and SPEC.loader is not None
pb = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pb)


def blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


class EngineCustodyTests(unittest.TestCase):
    def synthetic(self, market_first: bool = False) -> bytes:
        if market_first:
            body = """
def interpreter(state, env):
    _process_market(state, env)
    _apply_unit_action(None, None, 0, None, 0, 0, 0)
    _apply_unit_action(None, None, 1, None, 0, 0, 0)
"""
        else:
            body = """
def interpreter(state, env):
    _apply_unit_action(None, None, 0, None, 0, 0, 0)
    for _ in (0,):
        _apply_unit_action(None, None, 1, None, 0, 0, 0)
    _process_market(state, env)
"""
        return body.encode()

    def test_phase_certificate_accepts_unit_before_market(self):
        raw = self.synthetic()
        out = pb.certify_engine_source(raw, expected_blob=blob(raw))
        self.assertTrue(out["unit_before_market"])
        self.assertLess(max(out["unit_apply_lines"]), out["market_process_line"])

    def test_phase_certificate_rejects_reordered_interpreter(self):
        raw = self.synthetic(market_first=True)
        with self.assertRaisesRegex(pb.PhaseBarrierError, "PHASE_ORDER_VIOLATION"):
            pb.certify_engine_source(raw, expected_blob=blob(raw))

    def test_phase_certificate_rejects_blob_drift(self):
        raw = self.synthetic()
        with self.assertRaisesRegex(pb.PhaseBarrierError, "ENGINE_BLOB_MISMATCH"):
            pb.certify_engine_source(raw, expected_blob="0" * 40)

    def test_default_pin_is_current_official_engine(self):
        self.assertEqual(pb.EXPECTED_ENGINE_BLOB, "3c202c7ee921da239356789e266b694635103fc4")

    def test_checkout_engine_certifies_if_repository_is_present(self):
        path = pb.default_engine_path()
        if not path.exists():
            self.skipTest("full repository checkout not mounted in authoring container")
        out = pb.certify_engine_path(path)
        self.assertTrue(out["unit_before_market"])
        self.assertEqual(out["engine_git_blob"], pb.EXPECTED_ENGINE_BLOB)


class DependencyTests(unittest.TestCase):
    def pre(self, *, seeds=None, shed=None, inventories=None, hands=0):
        return {
            "seeds": seeds or {},
            "shed": shed or {},
            "inventories": inventories or [{} for _ in range(hands + 1)],
            "existing_hands": hands,
        }

    def codes(self, pre, action):
        return [v["code"] for v in pb.detect_same_callback_dependencies(pre, action)]

    def test_buy_seed_cannot_rescue_atomic_plant_wave(self):
        pre = self.pre(seeds={"WHEAT": 1})
        action = {
            "farmer": ["PLANT", "WHEAT"],
            "hands": [["PLANT", "WHEAT"]],
            "market": [["BUY_SEED", "WHEAT", 1]],
        }
        # Snapshot says no hands, so the extra authored hand is independently
        # ignored here because there is no HIRE.  Aggregate PLANT demand is still
        # exactly what the engine validates before market.
        self.assertEqual(self.codes(pre, action), ["BUY_SEED_AFTER_PLANT_PHASE"])

    def test_preexisting_seed_avoids_false_block(self):
        pre = self.pre(seeds={"WHEAT": 2}, inventories=[{}, {}], hands=1)
        action = {
            "farmer": ["PLANT", "WHEAT"],
            "hands": [["PLANT", "WHEAT"]],
            "market": [["BUY_SEED", "WHEAT", 5]],
        }
        self.assertEqual(self.codes(pre, action), [])

    def test_buy_product_cannot_feed_same_callback(self):
        pre = self.pre(inventories=[{}])
        action = {
            "farmer": ["FEED"],
            "hands": [],
            "market": [["BUY_PRODUCT", "WHEAT", 3]],
        }
        self.assertEqual(self.codes(pre, action), ["BUY_PRODUCT_AFTER_FEED_PHASE"])

    def test_precarried_wheat_avoids_false_block(self):
        pre = self.pre(inventories=[{"WHEAT": 1}])
        action = {
            "farmer": ["FEED"],
            "hands": [],
            "market": [["BUY_PRODUCT", "WHEAT", 3]],
        }
        self.assertEqual(self.codes(pre, action), [])

    def test_buy_product_cannot_fertilize_same_callback(self):
        pre = self.pre(inventories=[{}])
        action = {
            "farmer": ["FERTILIZE"],
            "hands": [],
            "market": [["BUY_PRODUCT", "FERTILIZER", 1]],
        }
        self.assertEqual(
            self.codes(pre, action), ["BUY_PRODUCT_AFTER_FERTILIZE_PHASE"]
        )

    def test_buy_animal_cannot_supply_pickup_or_place_same_callback(self):
        pre = self.pre(shed={}, inventories=[{}, {}], hands=1)
        pickup = {
            "farmer": ["PICKUP", "SHEEP", 1],
            "hands": [["PASS"]],
            "market": [["BUY_ANIMAL", "SHEEP", 1]],
        }
        place = {
            "farmer": ["PLACE", "SHEEP"],
            "hands": [["PASS"]],
            "market": [["BUY_ANIMAL", "SHEEP", 1]],
        }
        self.assertEqual(self.codes(pre, pickup), ["BUY_AFTER_PICKUP_PHASE"])
        self.assertEqual(self.codes(pre, place), ["BUY_ANIMAL_AFTER_PLACE_PHASE"])

    def test_preexisting_shed_animal_avoids_pickup_false_block(self):
        pre = self.pre(shed={"SHEEP": 1}, inventories=[{}])
        action = {
            "farmer": ["PICKUP", "SHEEP", 1],
            "hands": [],
            "market": [["BUY_ANIMAL", "SHEEP", 1]],
        }
        self.assertEqual(self.codes(pre, action), [])

    def test_hire_cannot_create_same_callback_actor(self):
        pre = self.pre(inventories=[{}], hands=0)
        action = {
            "farmer": ["PASS"],
            "hands": [["NORTH"]],
            "market": [["HIRE"]],
        }
        self.assertEqual(self.codes(pre, action), ["HIRE_AFTER_UNIT_PHASE"])

    def test_existing_hand_is_not_blocked_by_hire(self):
        pre = self.pre(inventories=[{}, {}], hands=1)
        action = {
            "farmer": ["PASS"],
            "hands": [["NORTH"]],
            "market": [["HIRE"]],
        }
        self.assertEqual(self.codes(pre, action), [])

    def test_unrelated_buy_does_not_turn_legality_checker_on(self):
        pre = self.pre(inventories=[{}])
        action = {
            "farmer": ["FEED"],
            "hands": [],
            "market": [["BUY_SEED", "WHEAT", 9]],
        }
        self.assertEqual(self.codes(pre, action), [])

    def test_market_rows_after_live_order_cap_do_not_create_false_dependency(self):
        pre = self.pre(inventories=[{}])
        market = [["SELL", "EGG", 1] for _ in range(10)]
        market.append(["BUY_PRODUCT", "WHEAT", 1])
        action = {"farmer": ["FEED"], "hands": [], "market": market}
        self.assertEqual(self.codes(pre, action), [])

    def test_snapshot_shape_fails_closed(self):
        bad = {
            "seeds": {},
            "shed": {},
            "inventories": [{}],
            "existing_hands": 1,
        }
        with self.assertRaisesRegex(pb.PhaseBarrierError, "inventories length"):
            pb.detect_same_callback_dependencies(bad, {"farmer": ["PASS"]})


if __name__ == "__main__":
    unittest.main()
