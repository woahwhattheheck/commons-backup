# SPDX-License-Identifier: Apache-2.0
import copy
import pathlib
import unittest

from redundant_unit_recycle import recycle_redundant_unit_rows, verify_engine_file


def animal(*, fed=True, cared=False, fertilizer=True, yield_units=2):
    return {
        "kind": "PASTURE",
        "animal": "COW",
        "fed_today": fed,
        "cared_today": cared,
        "fertilizer_available": fertilizer,
        "yield_units": yield_units,
    }


def fixture(rows, tile=None, positions=None):
    grid = [[None for _ in range(10)] for _ in range(10)]
    grid[0][0] = tile if tile is not None else animal()
    positions = positions or [[0, 0] for _ in rows]
    farm = {"tiles": grid, "farmer": positions[0], "hands": positions[1:]}
    action = {"farmer": rows[0], "hands": rows[1:], "market": [["SELL", "MILK", 1]]}
    return action, farm


class UnitRecycleTests(unittest.TestCase):
    def test_disabled_is_exact_identity(self):
        action, farm = fixture([["COLLECT_FERTILIZER"], ["COLLECT_FERTILIZER"]])
        out, r = recycle_redundant_unit_rows(action, farm, enabled=False)
        self.assertIs(out, action)
        self.assertEqual(r["replacements"], 0)

    def test_collect_duplicate_becomes_care(self):
        action, farm = fixture([["COLLECT_FERTILIZER"], ["COLLECT_FERTILIZER"]])
        original = copy.deepcopy(action)
        out, r = recycle_redundant_unit_rows(action, farm, enabled=True)
        self.assertEqual(out["farmer"], ["COLLECT_FERTILIZER"])
        self.assertEqual(out["hands"], [["CARE"]])
        self.assertEqual(out["market"], original["market"])
        self.assertEqual(action, original)
        self.assertEqual(r["strict_candidates"], 1)
        self.assertEqual(r["from_ops"]["COLLECT_FERTILIZER"], 1)

    def test_harvest_duplicate_becomes_care(self):
        action, farm = fixture([["HARVEST"], ["HARVEST"]])
        out, r = recycle_redundant_unit_rows(action, farm, enabled=True)
        self.assertEqual(out["hands"], [["CARE"]])
        self.assertEqual(r["from_ops"]["HARVEST"], 1)

    def test_predecessor_is_not_rewritten(self):
        action, farm = fixture([["HARVEST"], ["HARVEST"], ["PASS"]])
        out, _ = recycle_redundant_unit_rows(action, farm, enabled=True)
        self.assertEqual(out["farmer"], ["HARVEST"])

    def test_requires_same_tile(self):
        action, farm = fixture(
            [["COLLECT_FERTILIZER"], ["COLLECT_FERTILIZER"]],
            positions=[[0, 0], [1, 0]],
        )
        out, r = recycle_redundant_unit_rows(action, farm, enabled=True)
        self.assertIs(out, action)
        self.assertEqual(r["strict_candidates"], 0)

    def test_unfed_or_cared_is_identity(self):
        for tile in (animal(fed=False), animal(cared=True)):
            with self.subTest(tile=tile):
                action, farm = fixture([["HARVEST"], ["HARVEST"]], tile=tile)
                out, _ = recycle_redundant_unit_rows(action, farm, enabled=True)
                self.assertIs(out, action)

    def test_source_op_must_be_provably_effective(self):
        cases = (
            (["COLLECT_FERTILIZER"], animal(fertilizer=False)),
            (["HARVEST"], animal(yield_units=0)),
        )
        for row, tile in cases:
            with self.subTest(row=row):
                action, farm = fixture([row, list(row)], tile=tile)
                out, _ = recycle_redundant_unit_rows(action, farm, enabled=True)
                self.assertIs(out, action)

    def test_earlier_care_vetoes(self):
        action, farm = fixture(
            [["COLLECT_FERTILIZER"], ["CARE"], ["COLLECT_FERTILIZER"]]
        )
        out, r = recycle_redundant_unit_rows(action, farm, enabled=True)
        self.assertIs(out, action)
        self.assertEqual(r["strict_candidates"], 1)

    def test_at_most_one_replacement_per_tile(self):
        action, farm = fixture(
            [["COLLECT_FERTILIZER"], ["COLLECT_FERTILIZER"], ["HARVEST"], ["HARVEST"]]
        )
        out, r = recycle_redundant_unit_rows(action, farm, enabled=True)
        self.assertEqual(r["replacements"], 1)
        self.assertEqual(out["hands"][0], ["CARE"])
        self.assertEqual(out["hands"][2], ["HARVEST"])

    def test_unknown_animal_and_type_poison_fail_closed(self):
        bad_tiles = [
            {**animal(), "animal": "DRAGON"},
            {**animal(), "fed_today": 1},
            {**animal(), "cared_today": 0},
            {**animal(), "yield_units": True},
        ]
        for tile in bad_tiles:
            with self.subTest(tile=tile):
                action, farm = fixture([["HARVEST"], ["HARVEST"]], tile=tile)
                out, _ = recycle_redundant_unit_rows(action, farm, enabled=True)
                self.assertIs(out, action)

    def test_malformed_actor_surface_fails_whole_action_closed(self):
        action, farm = fixture([["COLLECT_FERTILIZER"], ["COLLECT_FERTILIZER"]])
        farm["hands"] = [[True, 0]]
        out, _ = recycle_redundant_unit_rows(action, farm, enabled=True)
        self.assertIs(out, action)

    def test_checkout_engine_blob_when_available(self):
        here = pathlib.Path(__file__).resolve()
        matches = list(here.parents[0:8])
        found = None
        for root in matches:
            candidate = root / "revenue/kaggriculture/cloud-execution-lab/reference/engine/kaggriculture.py"
            if candidate.is_file():
                found = candidate
                break
        if found is None:
            self.skipTest("repository engine source not available in this harness")
        self.assertTrue(verify_engine_file(found))


if __name__ == "__main__":
    unittest.main()
