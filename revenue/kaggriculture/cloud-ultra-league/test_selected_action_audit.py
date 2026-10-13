"""Synthetic regression checks; requires an existing official-engine checkout."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import unittest

from selected_action_audit import duplicate_harvest_targets


class AuditTests(unittest.TestCase):
    engine = None
    Struct = None

    def fixture(self):
        farm = self.engine._new_farm(10, 3000)
        farm["hands"] = [[4, 2]] + [[0, 0] for _ in range(6)] + [[4, 2]]
        cow = self.engine._new_animal("COW", 0)
        cow["yield_units"] = 3
        farm["tiles"][2][4] = cow
        obs = {"player": 0, "farms": [farm]}
        action = {"farmer": ["PASS"], "hands": [["HARVEST"]]
            + [["PASS"] for _ in range(6)] + [["HARVEST"]], "market": []}
        return obs, action

    def test_duplicate_is_read_only(self):
        obs, action = self.fixture()
        before = copy.deepcopy((obs, action))
        self.assertEqual(duplicate_harvest_targets(obs, action), [{
            "position": [4, 2], "actors": [1, 8], "redundant_orders": 1,
            "visible_yield_units": 3, "tile_kind": "PASTURE"}])
        self.assertEqual((obs, action), before)

    def test_different_targets_and_absent_actor(self):
        obs, action = self.fixture()
        obs["farms"][0]["hands"][7] = [3, 2]
        action["hands"].append(["HARVEST"])
        action["market"] = [["HIRE"]]
        self.assertEqual(duplicate_harvest_targets(obs, action), [])

    def test_official_engine_assigns_three_units_once(self):
        obs, action = self.fixture()
        private = self.engine._new_private()
        private["inventories"] = [{} for _ in range(9)]
        farm = obs["farms"][0]
        for actor, order in enumerate([action["farmer"], *action["hands"]]):
            self.engine._apply_unit_action(farm, private, actor, order, 10, 10, 24, 100)
        self.assertEqual(private["inventories"][1], {"MILK": 3})
        self.assertEqual(private["inventories"][8], {})
        self.assertEqual(farm["tiles"][2][4]["yield_units"], 0)
        self.assertEqual(sum(inv.get("MILK", 0) for inv in private["inventories"]), 3)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--loader-path", type=Path, required=True)
    parser.add_argument("--engine-dir", type=Path, required=True)
    args = parser.parse_args()
    for filename in ("kaggriculture.py", "kaggriculture.json", "utils.py"):
        if not (args.engine_dir / filename).is_file():
            parser.error(f"existing engine file required: {filename}")
    spec = importlib.util.spec_from_file_location("retained_engine_loader", args.loader_path)
    loader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loader)
    AuditTests.engine, hashes = loader.get_engine(args.engine_dir)
    AuditTests.Struct = loader.Struct
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(AuditTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({"engine_ref": loader.ENGINE_REF, "engine_hashes": hashes,
        "tests_run": result.testsRun, "success": result.wasSuccessful()}))
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
