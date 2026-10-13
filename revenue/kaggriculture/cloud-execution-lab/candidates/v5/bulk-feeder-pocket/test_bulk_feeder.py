from __future__ import annotations

import copy
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import bulk_feeder as bf


def animal(kind: str, name: str) -> dict:
    return {
        "kind": kind,
        "animal": name,
        "placed_day": 0,
        "yield_units": 0,
        "consecutive_unfed": 0,
        "fed_today": False,
        "cared_today": False,
        "fertilizer_available": False,
        "pending_care_bonus": 0,
    }


def observation(*, hands=None, inventories=None, shed_wheat=2, step=0, player=0):
    tiles = [[None for _ in range(10)] for _ in range(10)]
    tiles[3][4] = animal("COOP", "GOOSE")
    tiles[4][3] = animal("PASTURE", "COW")
    hand_positions = list(hands or [])
    inv = copy.deepcopy(inventories if inventories is not None
                        else [{} for _ in range(1 + len(hand_positions))])
    farm = {
        "farmer": [4, 4],
        "hands": hand_positions,
        "tiles": tiles,
    }
    return {
        "player": player,
        "step": step,
        "farms": [farm, copy.deepcopy(farm)],
        "private": {
            "shed": {"WHEAT": shed_wheat},
            "inventories": inv,
            "seeds": {},
        },
    }


def row(farmer, hands=None, market=None):
    return {
        "farmer": farmer,
        "hands": list(hands or []),
        "market": list(market or []),
    }


def simple_route(with_hand=False):
    hand_pass = [["PASS"]] if with_hand else []
    return [
        row(["PICKUP", "WHEAT"], hand_pass),
        row(["NORTH"], hand_pass),
        row(["FEED"], hand_pass),
        row(["SOUTH"], hand_pass),
        row(["PICKUP", "WHEAT", 1], hand_pass),
        row(["WEST"], hand_pass),
        row(["FEED"], hand_pass),
    ]


class BulkFeederTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bf._require_sources()
        cls.mechanics = bf._load("bulk_feeder_test_mechanics", bf.MECHANICS_PATH)

    def test_pinned_engine_contract_is_real(self):
        self.assertEqual(bf.git_blob_id(bf.MECHANICS_PATH.read_bytes()), bf.MECHANICS_BLOB)
        self.assertEqual(bf.git_blob_id(bf.ARLENE_PATH.read_bytes()), bf.ARLENE_BLOB)

    def test_scan_finds_repeated_pickup_feed_window(self):
        route = simple_route()
        found = bf.scan_route(route, "fixture")
        self.assertEqual(len(found), 1)
        witness = found[0]
        self.assertEqual(witness["pickup_steps"], [0, 4])
        self.assertEqual(witness["feed_steps"], [2, 6])
        self.assertEqual(witness["bulk_quantity"], 2)
        self.assertEqual(witness["reclaimable_pickup_action_slots"], 1)
        self.assertEqual(witness["travel_savings_lower_bound"], 0)

    def test_rewrite_only_consolidates_pickup_cells(self):
        route = simple_route()
        witness = bf.scan_route(route, "fixture")[0]
        candidate = bf.apply_witness(route, witness)
        self.assertEqual(candidate[0]["farmer"], ["PICKUP", "WHEAT", 2])
        self.assertEqual(candidate[4]["farmer"], ["PASS"])
        for step in (1, 2, 3, 5, 6):
            self.assertEqual(candidate[step], route[step])

    def test_exact_unit_witness_preserves_final_farm_and_private(self):
        route = simple_route()
        witness = bf.scan_route(route, "fixture")[0]
        result = bf.verify_unit_window(
            observation(), route, witness, mechanics=self.mechanics,
        )
        self.assertTrue(result["equivalent"])
        self.assertEqual(result["reclaimable_pickup_action_slots"], 1)
        self.assertIsNotNone(result["candidate"])

    def test_shared_shed_timing_interference_is_rejected(self):
        route = simple_route(with_hand=True)
        route[1]["hands"][0] = ["DROP"]
        obs = observation(
            hands=[[5, 4]],
            inventories=[{}, {"WHEAT": 1}],
            shed_wheat=1,
        )
        witness = bf.scan_route(route, "fixture")[0]
        result = bf.verify_unit_window(obs, route, witness, mechanics=self.mechanics)
        self.assertFalse(result["equivalent"])
        self.assertEqual(result["reclaimable_pickup_action_slots"], 0)
        with self.assertRaises(bf.WitnessError):
            bf.materialize_verified(obs, route, witness, mechanics=self.mechanics)

    def test_market_bearing_window_is_not_proposed(self):
        route = simple_route()
        route[3]["market"] = [["BUY_PRODUCT", "WHEAT", 1]]
        self.assertEqual(bf.scan_route(route, "fixture"), [])

    def test_forged_gain_metadata_is_rejected(self):
        route = simple_route()
        witness = bf.scan_route(route, "fixture")[0]
        witness["reclaimable_pickup_action_slots"] = 99
        with self.assertRaises(bf.WitnessError):
            bf.apply_witness(route, witness)
        witness = bf.scan_route(route, "fixture")[0]
        witness["travel_savings_lower_bound"] = 1
        with self.assertRaises(bf.WitnessError):
            bf.apply_witness(route, witness)

    def test_observation_identity_must_match_witness_start(self):
        route = simple_route()
        witness = bf.scan_route(route, "fixture")[0]
        for obs in (
            observation(step=1),
            observation(player=True),
            observation(player=-1),
        ):
            with self.subTest(player=obs.get("player"), step=obs.get("step")):
                with self.assertRaises(bf.WitnessError):
                    bf.verify_unit_window(obs, route, witness, mechanics=self.mechanics)

    def test_noncanonical_calendar_is_rejected_before_replay(self):
        route = [row(["PASS"]) for _ in range(14)]
        route[11]["farmer"] = ["PICKUP", "WHEAT", 1]
        route[12]["farmer"] = ["PICKUP", "WHEAT", 1]
        route[13]["farmer"] = ["FEED"]
        witness = {
            "route_id": "fixture",
            "actor": 0,
            "start_step": 11,
            "end_step": 13,
            "pickup_steps": [11, 12],
            "feed_steps": [13],
            "bulk_quantity": 2,
            "reclaimable_pickup_action_slots": 1,
            "travel_savings_lower_bound": 0,
        }

        class ReplayMustNotRun:
            @staticmethod
            def _apply_unit_action(*args, **kwargs):
                raise AssertionError("calendar mismatch reached unit replay")

        with self.assertRaisesRegex(bf.WitnessError, "canonical 24-turn route calendar"):
            bf.verify_unit_window(
                observation(step=11), route, witness,
                mechanics=ReplayMustNotRun(), turns_per_day=12,
            )

    def test_day_crossing_witness_is_rejected(self):
        route = [row(["PASS"]) for _ in range(26)]
        route[23]["farmer"] = ["PICKUP", "WHEAT", 1]
        route[24]["farmer"] = ["PICKUP", "WHEAT", 1]
        route[25]["farmer"] = ["FEED"]
        witness = {
            "route_id": "fixture",
            "actor": 0,
            "start_step": 23,
            "end_step": 25,
            "pickup_steps": [23, 24],
            "feed_steps": [25],
            "bulk_quantity": 2,
            "reclaimable_pickup_action_slots": 1,
            "travel_savings_lower_bound": 0,
        }
        with self.assertRaises(bf.WitnessError):
            bf.apply_witness(route, witness)


if __name__ == "__main__":
    unittest.main()
