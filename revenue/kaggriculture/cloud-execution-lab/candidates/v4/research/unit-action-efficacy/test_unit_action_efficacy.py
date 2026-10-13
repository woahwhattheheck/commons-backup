# SPDX-License-Identifier: Apache-2.0
import copy
import unittest
import unit_action_efficacy as u


class MiniEngine:
    @staticmethod
    def _apply_unit_action(farm, private, idx, action, board_size, day, turns_per_day, shed_capacity):
        if not isinstance(action, list) or not action:
            return
        op = action[0]
        if op == "PASS":
            return
        pos = farm["farmer"] if idx == 0 else farm["hands"][idx - 1]
        tile = farm["tiles"][pos[1]][pos[0]]
        if op == "CARE" and isinstance(tile, dict) and tile.get("animal") and not tile.get("cared_today"):
            tile["cared_today"] = True
        elif op == "WATER" and isinstance(tile, dict) and tile.get("kind") == "PLANT" and not tile.get("watered_today"):
            tile["watered_today"] = True
        elif op == "COLLECT_FERTILIZER" and isinstance(tile, dict) and tile.get("animal") and tile.get("fertilizer_available"):
            tile["fertilizer_available"] = False
            private["inventories"][idx]["FERTILIZER"] = private["inventories"][idx].get("FERTILIZER", 0) + 1
        elif op == "HARVEST" and isinstance(tile, dict) and tile.get("yield_units", 0) > 0:
            tile["yield_units"] = 0
        elif op == "PLANT" and tile is None and len(action) >= 2 and private["seeds"].get(action[1], 0) > 0:
            private["seeds"][action[1]] -= 1
            farm["tiles"][pos[1]][pos[0]] = {"kind":"PLANT", "crop":action[1]}


def base(tile, *, seeds=None, actors=2):
    farm = {"farmer":[0,0], "hands":[[0,0] for _ in range(actors-1)], "tiles":[[copy.deepcopy(tile)]]}
    private = {"seeds":dict(seeds or {}), "inventories":[{} for _ in range(actors)], "shed":{}}
    return farm, private


CFG = {"boardSize":1, "turnsPerDay":24, "shedCapacity":100}


class EfficacyTests(unittest.TestCase):
    def test_git_blob(self):
        self.assertEqual(u.git_blob_sha(b"hello\n"), "ce013625030ba8dba906f756967f9e9ca394464a")

    def test_care_predecessor_is_exact(self):
        farm, private = base({"animal":"COW", "cared_today":False})
        rows = u.trace_unit_vector(MiniEngine, farm, private,
            {"farmer":["CARE"], "hands":[["CARE"]]}, step=1, cfg=CFG)
        self.assertTrue(rows[0]["changed"])
        self.assertFalse(rows[1]["changed"])
        self.assertEqual(rows[1]["same_target_successful_predecessor"], 0)

    def test_different_operation_not_misattributed(self):
        farm, private = base({"animal":"COW", "cared_today":False, "yield_units":0})
        rows = u.trace_unit_vector(MiniEngine, farm, private,
            {"farmer":["CARE"], "hands":[["HARVEST"]]}, step=1, cfg=CFG)
        self.assertTrue(rows[0]["changed"])
        self.assertFalse(rows[1]["changed"])
        self.assertIsNone(rows[1]["same_target_successful_predecessor"])

    def test_different_tile_not_misattributed(self):
        farm = {"farmer":[0,0], "hands":[[1,0]], "tiles":[[
            {"kind":"PLANT","watered_today":False}, {"kind":"PLANT","watered_today":True}
        ]]}
        private={"seeds":{},"inventories":[{},{}],"shed":{}}
        rows=u.trace_unit_vector(MiniEngine,farm,private,{"farmer":["WATER"],"hands":[["WATER"]]},step=1,cfg={**CFG,"boardSize":2})
        self.assertTrue(rows[0]["changed"]); self.assertFalse(rows[1]["changed"])
        self.assertIsNone(rows[1]["same_target_successful_predecessor"])

    def test_atomic_plant_oversubscription_is_preserved(self):
        farm, private = base(None, seeds={"CARROT":1})
        rows = u.trace_unit_vector(MiniEngine, farm, private,
            {"farmer":["PLANT","CARROT"], "hands":[["PLANT","CARROT"]]}, step=1, cfg=CFG)
        self.assertEqual([r["effective_action"] for r in rows], [["PASS"],["PASS"]])
        self.assertTrue(all(r["atomic_plant_blocked"] for r in rows))
        self.assertTrue(all(not r["changed"] for r in rows))

    def test_exact_seed_demand_is_allowed(self):
        farm, private = base(None, seeds={"CARROT":2})
        rows = u.trace_unit_vector(MiniEngine, farm, private,
            {"farmer":["PLANT","CARROT"], "hands":[["PLANT","CARROT"]]}, step=1, cfg=CFG)
        self.assertFalse(any(r["atomic_plant_blocked"] for r in rows))
        self.assertTrue(rows[0]["changed"])
        # second actor is same tile and therefore naturally no-ops, but PLANT is
        # deliberately outside one-shot predecessor attribution.
        self.assertFalse(rows[1]["changed"])
        self.assertIsNone(rows[1]["same_target_successful_predecessor"])

    def test_effect_target_is_intentionally_narrow(self):
        self.assertEqual(u.effect_target((2,3),["CARE"]),("tile",(2,3),"CARE"))
        self.assertIsNone(u.effect_target((2,3),["FERTILIZE"]))
        self.assertIsNone(u.effect_target((2,3),["PICKUP","WHEAT",2]))

    def test_input_objects_are_not_mutated(self):
        farm, private = base({"animal":"COW", "cared_today":False})
        f0,p0=copy.deepcopy(farm),copy.deepcopy(private)
        u.trace_unit_vector(MiniEngine,farm,private,{"farmer":["CARE"],"hands":[["CARE"]]},step=1,cfg=CFG)
        self.assertEqual(farm,f0); self.assertEqual(private,p0)


if __name__ == "__main__": unittest.main()
