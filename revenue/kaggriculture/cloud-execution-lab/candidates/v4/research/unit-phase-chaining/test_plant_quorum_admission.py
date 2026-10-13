from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).with_name("plant_quorum_admission.py")
spec = importlib.util.spec_from_file_location("plant_quorum_admission", MODULE_PATH)
assert spec is not None and spec.loader is not None
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def obs(*, farmer=(0, 0), hands=(), tiles=None, seeds=None):
    if tiles is None:
        tiles = [[None, None], [None, None]]
    farm = {
        "farmer": list(farmer),
        "hands": [list(p) for p in hands],
        "tiles": tiles,
    }
    return {
        "player": 0,
        "farms": [farm],
        "private": {"seeds": dict(seeds or {})},
    }


def action(farmer, hands=(), market=None):
    return {
        "farmer": farmer,
        "hands": list(hands),
        "market": list(market or []),
    }


class PlantQuorumAdmissionTests(unittest.TestCase):
    def test_off_is_exact_content_identity(self):
        source = action(["PLANT", "WHEAT"], [["PLANT", "WHEAT"]], [["BUY_SEED", "WHEAT", 1]])
        out, report = m.relieve_atomic_plant_collateral(
            obs(hands=((1, 0),), seeds={"WHEAT": 1}), source, enabled=False
        )
        self.assertEqual(out, source)
        self.assertFalse(report["changed"])
        self.assertFalse(report["enabled"])

    def test_engine_preflight_blocks_every_same_crop_row(self):
        rows = [["PLANT", "WHEAT"], ["PLANT", "WHEAT"]]
        self.assertEqual(
            m.effective_rows_under_engine_preflight(rows, {"WHEAT": 1}),
            [["PASS"], ["PASS"]],
        )

    def test_unique_nonempty_poison_unblocks_unique_empty_plant(self):
        tiles = [[None, {"kind": "WEED"}], [None, None]]
        source = action(["PLANT", "WHEAT"], [["PLANT", "WHEAT"]])
        out, report = m.relieve_atomic_plant_collateral(
            obs(hands=((1, 0),), tiles=tiles, seeds={"WHEAT": 1}), source, enabled=True
        )
        self.assertEqual(out["farmer"], ["PLANT", "WHEAT"])
        self.assertEqual(out["hands"], [["PASS"]])
        self.assertTrue(report["changed"])
        self.assertEqual(report["changed_actors"], [1])
        self.assertEqual(
            m.effective_rows_under_engine_preflight(
                [out["farmer"], *out["hands"]], {"WHEAT": 1}
            ),
            [["PLANT", "WHEAT"], ["PASS"]],
        )

    def test_locked_unique_actor_is_source_certain_poison(self):
        tiles = [[None, "LOCKED"], [None, None]]
        source = action(["PLANT", "WHEAT"], [["PLANT", "WHEAT"]])
        out, report = m.relieve_atomic_plant_collateral(
            obs(hands=((1, 0),), tiles=tiles, seeds={"WHEAT": 1}), source, enabled=True
        )
        self.assertTrue(report["changed"])
        self.assertEqual(out["hands"], [["PASS"]])

    def test_phantom_hand_row_can_poison_and_is_removed(self):
        source = action(["PLANT", "WHEAT"], [["PLANT", "WHEAT"]])
        out, report = m.relieve_atomic_plant_collateral(
            obs(hands=(), seeds={"WHEAT": 1}), source, enabled=True
        )
        self.assertTrue(report["changed"])
        self.assertEqual(out["farmer"], ["PLANT", "WHEAT"])
        self.assertEqual(out["hands"], [["PASS"]])
        crop = next(item for item in report["crops"] if item["crop"] == "WHEAT")
        self.assertEqual(crop["rows"][1]["classification"], "SOURCE_CERTAIN_NOOP_MISSING_ACTOR")

    def test_does_not_choose_between_two_legal_plants(self):
        source = action(["PLANT", "WHEAT"], [["PLANT", "WHEAT"]])
        out, report = m.relieve_atomic_plant_collateral(
            obs(hands=((1, 0),), seeds={"WHEAT": 1}), source, enabled=True
        )
        self.assertEqual(out, source)
        self.assertFalse(report["changed"])
        crop = next(item for item in report["crops"] if item["crop"] == "WHEAT")
        self.assertEqual(crop["status"], "BLOCKED_NO_SOURCE_CERTAIN_POISON")

    def test_poison_removal_must_be_sufficient_without_legal_selection(self):
        tiles = [[None, None, {"kind": "WEED"}]]
        source = action(
            ["PLANT", "WHEAT"],
            [["PLANT", "WHEAT"], ["PLANT", "WHEAT"]],
        )
        out, report = m.relieve_atomic_plant_collateral(
            obs(hands=((1, 0), (2, 0)), tiles=tiles, seeds={"WHEAT": 1}),
            source,
            enabled=True,
        )
        self.assertEqual(out, source)
        self.assertFalse(report["changed"])
        crop = next(item for item in report["crops"] if item["crop"] == "WHEAT")
        self.assertEqual(crop["status"], "BLOCKED_POISON_REMOVAL_INSUFFICIENT")

    def test_colocation_is_ambiguous_and_not_used_as_poison(self):
        source = action(["PLANT", "WHEAT"], [["PLANT", "WHEAT"]])
        out, report = m.relieve_atomic_plant_collateral(
            obs(farmer=(0, 0), hands=((0, 0),), seeds={"WHEAT": 1}), source, enabled=True
        )
        self.assertEqual(out, source)
        self.assertFalse(report["changed"])
        crop = next(item for item in report["crops"] if item["crop"] == "WHEAT")
        self.assertTrue(all(row["classification"] == "AMBIGUOUS_COLOCATED" for row in crop["rows"]))

    def test_zero_seed_never_creates_a_plant(self):
        tiles = [[None, {"kind": "WEED"}]]
        source = action(["PLANT", "WHEAT"], [["PLANT", "WHEAT"]])
        out, report = m.relieve_atomic_plant_collateral(
            obs(hands=((1, 0),), tiles=tiles, seeds={"WHEAT": 0}), source, enabled=True
        )
        self.assertEqual(out, source)
        self.assertFalse(report["changed"])

    def test_crop_isolation_and_market_preservation(self):
        tiles = [[None, {"kind": "WEED"}, None]]
        source = action(
            ["PLANT", "WHEAT"],
            [["PLANT", "WHEAT"], ["PLANT", "CARROT"]],
            [["BUY_SEED", "MELON", 2]],
        )
        out, report = m.relieve_atomic_plant_collateral(
            obs(hands=((1, 0), (2, 0)), tiles=tiles, seeds={"WHEAT": 1, "CARROT": 1}),
            source,
            enabled=True,
        )
        self.assertTrue(report["changed"])
        self.assertEqual(out["farmer"], ["PLANT", "WHEAT"])
        self.assertEqual(out["hands"], [["PASS"], ["PLANT", "CARROT"]])
        self.assertEqual(out["market"], source["market"])

    def test_non_plant_rows_are_never_rewritten(self):
        tiles = [[None, {"kind": "WEED"}, None]]
        source = action(
            ["PLANT", "WHEAT"],
            [["PLANT", "WHEAT"], ["WATER"]],
            [["SELL", "WHEAT", 2]],
        )
        out, report = m.relieve_atomic_plant_collateral(
            obs(hands=((1, 0), (2, 0)), tiles=tiles, seeds={"WHEAT": 1}), source, enabled=True
        )
        self.assertTrue(report["changed"])
        self.assertEqual(out["hands"][1], ["WATER"])
        self.assertEqual(out["market"], source["market"])

    def test_malformed_context_fails_closed(self):
        source = action(["PLANT", "WHEAT"])
        out, report = m.relieve_atomic_plant_collateral(
            {"player": 0, "farms": [], "private": {"seeds": {"WHEAT": 1}}},
            source,
            enabled=True,
        )
        self.assertEqual(out, source)
        self.assertFalse(report["changed"])
        self.assertIsNotNone(report["error"])

    def test_bad_seed_count_fails_closed(self):
        source = action(["PLANT", "WHEAT"], [["PLANT", "WHEAT"]])
        out, report = m.relieve_atomic_plant_collateral(
            obs(hands=((1, 0),), seeds={"WHEAT": "1"}), source, enabled=True
        )
        self.assertEqual(out, source)
        self.assertFalse(report["changed"])
        self.assertIn("malformed seed count", report["error"])

    def test_engine_checkout_pin_if_present(self):
        if not m.ENGINE_PATH.exists():
            self.skipTest("repository engine source not mounted")
        receipt = m.verify_engine_source()
        self.assertEqual(receipt["engine_blob"], m.EXPECTED_ENGINE_BLOB)


if __name__ == "__main__":
    unittest.main()
