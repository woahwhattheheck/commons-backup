import copy
import tempfile
import unittest
from pathlib import Path

from animal_headroom_harvest import (
    EXPECTED_ENGINE_GIT_BLOB,
    apply_animal_headroom_harvest,
    git_blob_sha1,
    plan_animal_headroom_harvest,
)


def animal(species="GOOSE", *, placed_day=0, yield_units=4, fed_today=True,
           pending=0, consecutive_unfed=0, cared_today=False):
    kind = "COOP" if species == "GOOSE" else "PASTURE"
    return {
        "kind": kind,
        "animal": species,
        "placed_day": placed_day,
        "yield_units": yield_units,
        "consecutive_unfed": consecutive_unfed,
        "fed_today": fed_today,
        "cared_today": cared_today,
        "fertilizer_available": False,
        "pending_care_bonus": pending,
    }


def world(tile, *, day=3, hour=23, shed=None, inv=None, hands=None, step=None):
    tiles = [[None for _ in range(10)] for _ in range(10)]
    tiles[1][1] = tile
    farm = {
        "farmer": [1, 1],
        "hands": list(hands or []),
        "tiles": tiles,
    }
    obs = {
        "player": 0,
        "farms": [farm],
        "private": {
            "shed": dict(shed or {"WHEAT": 0, "FERTILIZER": 0}),
            "inventories": list(inv or [{} for _ in range(1 + len(farm["hands"]))]),
        },
        "day": day,
        "hour": hour,
    }
    if step is not None:
        obs["step"] = step
    return obs


CFG = {"turnsPerDay": 24, "shedCapacity": 100}


class HeadroomTests(unittest.TestCase):
    def test_default_off_is_object_identity(self):
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        obs = world(animal(), day=4)
        self.assertIs(apply_animal_headroom_harvest(action, obs, CFG), action)

    def test_reachable_goose_cap_before_later_due_production_rewrites(self):
        # placed day0 first produces at EOD day3; if those eggs remain held,
        # next-day EOD production on day4 would clip at max_held=4.
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        obs = world(animal("GOOSE", placed_day=0, yield_units=4), day=4)
        plan = plan_animal_headroom_harvest(action, obs, CFG)
        self.assertTrue(plan["eligible"])
        self.assertEqual(plan["saved_clipped_units"], 1)
        self.assertEqual(
            apply_animal_headroom_harvest(action, obs, CFG, enabled=True)["farmer"],
            ["HARVEST"],
        )

    def test_care_bonus_current_bank_is_counted_but_cared_today_is_not(self):
        # Existing pending=2 is consumed on this fed production day; cared_today
        # adds a *future* pending bonus only after production in the engine.
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        obs = world(
            animal(
                "SHEEP",
                placed_day=0,
                yield_units=5,
                fed_today=True,
                pending=2,
                cared_today=True,
            ),
            day=8,  # next_day9: due; pending care can bank between sheep cycles
        )
        plan = plan_animal_headroom_harvest(action, obs, CFG)
        self.assertTrue(plan["eligible"])
        row = plan["rewrites"][0]
        self.assertEqual(row["gain"], 3)
        self.assertEqual(row["clipped_units"], 2)
        self.assertEqual(row["recoverable_clipped_units"], 2)

    def test_unfed_streak_one_escapes_before_production(self):
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        obs = world(
            animal(
                "GOOSE",
                placed_day=0,
                yield_units=4,
                fed_today=False,
                consecutive_unfed=1,
            ),
            day=4,
        )
        self.assertFalse(plan_animal_headroom_harvest(action, obs, CFG)["eligible"])

    def test_unfed_streak_zero_can_produce_base_only(self):
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        obs = world(
            animal(
                "GOOSE",
                placed_day=0,
                yield_units=4,
                fed_today=False,
                pending=99,
                consecutive_unfed=0,
            ),
            day=4,
        )
        row = plan_animal_headroom_harvest(action, obs, CFG)["rewrites"][0]
        self.assertEqual(row["gain"], 1)
        self.assertEqual(row["clipped_units"], 1)

    def test_not_due_is_unchanged(self):
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        obs = world(animal("COW", placed_day=0, yield_units=6), day=6)
        self.assertIs(apply_animal_headroom_harvest(action, obs, CFG, enabled=True), action)

    def test_headroom_sufficient_is_unchanged(self):
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        obs = world(animal("GOOSE", placed_day=0, yield_units=1), day=4)
        self.assertFalse(plan_animal_headroom_harvest(action, obs, CFG)["eligible"])

    def test_non_pass_is_never_stolen(self):
        action = {"farmer": ["CARE"], "hands": [], "market": []}
        obs = world(animal("GOOSE", placed_day=0, yield_units=4), day=4)
        self.assertIs(apply_animal_headroom_harvest(action, obs, CFG, enabled=True), action)

    def test_only_final_hour(self):
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        obs = world(animal("GOOSE", placed_day=0, yield_units=4), day=4, hour=22)
        self.assertEqual(plan_animal_headroom_harvest(action, obs, CFG)["reason"], "not_eod_callback")

    def test_clock_inconsistency_fails_closed(self):
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        obs = world(animal(), day=3, hour=23, step=94)  # step94 => d3 h22
        self.assertEqual(
            plan_animal_headroom_harvest(action, obs, CFG)["reason"],
            "malformed_observation_or_clock",
        )

    def test_capacity_counts_harvest_cargo_and_same_turn_buys(self):
        action = {
            "farmer": ["PASS"],
            "hands": [],
            "market": [["BUY_PRODUCT", "WHEAT", 2]],
        }
        obs = world(
            animal("GOOSE", placed_day=0, yield_units=4),
            day=4,
            shed={"WHEAT": 94},
            inv=[{}],
        )
        # 94 existing + 2 possible buys + 4 harvest = 100 -> safe.
        self.assertTrue(plan_animal_headroom_harvest(action, obs, CFG)["eligible"])
        obs2 = copy.deepcopy(obs)
        obs2["private"]["shed"]["WHEAT"] = 95
        self.assertEqual(
            plan_animal_headroom_harvest(action, obs2, CFG)["reason"],
            "eod_shed_capacity_not_certified",
        )

    def test_capacity_does_not_credit_same_turn_sell(self):
        action = {
            "farmer": ["PASS"],
            "hands": [],
            "market": [["SELL", "WHEAT", 20]],
        }
        obs = world(
            animal("GOOSE", placed_day=0, yield_units=4),
            day=4,
            shed={"WHEAT": 98},
            inv=[{}],
        )
        self.assertFalse(plan_animal_headroom_harvest(action, obs, CFG)["eligible"])

    def test_other_authored_harvest_is_capacity_charged(self):
        tiles = [[None for _ in range(10)] for _ in range(10)]
        tiles[1][1] = animal("GOOSE", placed_day=0, yield_units=4)
        tiles[1][2] = {
            "kind": "PLANT",
            "crop": "WHEAT",
            "planted_day": 0,
            "watered_today": True,
            "consecutive_unwatered": 0,
            "yield_units": 3,
            "max_lifespan_step": 999,
            "fertilized_until_day": -1,
        }
        farm = {"farmer": [1, 1], "hands": [[2, 1]], "tiles": tiles}
        obs = {
            "player": 0,
            "farms": [farm],
            "private": {"shed": {"WHEAT": 94}, "inventories": [{}, {}]},
            "day": 4,
            "hour": 23,
        }
        action = {"farmer": ["PASS"], "hands": [["HARVEST"]], "market": []}
        # 94 + 3 existing authored harvest + 4 candidate = 101 -> refuse.
        self.assertFalse(plan_animal_headroom_harvest(action, obs, CFG)["eligible"])

    def test_colocated_actor_order_is_refused(self):
        tile = animal("GOOSE", placed_day=0, yield_units=4)
        obs = world(tile, day=4, hands=[[1, 1]])
        action = {"farmer": ["PASS"], "hands": [["PASS"]], "market": []}
        self.assertEqual(
            plan_animal_headroom_harvest(action, obs, CFG)["reason"],
            "co_located_actor_order_ambiguous",
        )

    def test_hand_pass_can_rewrite_without_cardinality_change(self):
        tiles = [[None for _ in range(10)] for _ in range(10)]
        tiles[1][1] = None
        tiles[1][2] = animal("GOOSE", placed_day=0, yield_units=4)
        farm = {"farmer": [1, 1], "hands": [[2, 1]], "tiles": tiles}
        obs = {
            "player": 0,
            "farms": [farm],
            "private": {"shed": {}, "inventories": [{}, {}]},
            "day": 4,
            "hour": 23,
        }
        action = {"farmer": ["PASS"], "hands": [["PASS"]], "market": []}
        out = apply_animal_headroom_harvest(action, obs, CFG, enabled=True)
        self.assertEqual(out["farmer"], ["PASS"])
        self.assertEqual(out["hands"], [["HARVEST"]])
        self.assertEqual(len(out["hands"]), len(action["hands"]))

    def test_two_independent_animals_rewrite_if_capacity_allows(self):
        tiles = [[None for _ in range(10)] for _ in range(10)]
        tiles[1][1] = animal("GOOSE", placed_day=0, yield_units=4)
        tiles[1][2] = animal("GOOSE", placed_day=0, yield_units=4)
        farm = {"farmer": [1, 1], "hands": [[2, 1]], "tiles": tiles}
        obs = {
            "player": 0,
            "farms": [farm],
            "private": {"shed": {}, "inventories": [{}, {}]},
            "day": 4,
            "hour": 23,
        }
        action = {"farmer": ["PASS"], "hands": [["PASS"]], "market": []}
        plan = plan_animal_headroom_harvest(action, obs, CFG)
        self.assertEqual(len(plan["rewrites"]), 2)
        self.assertEqual(plan["saved_clipped_units"], 2)

    def test_malformed_counts_fail_closed(self):
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        obs = world(animal("GOOSE", placed_day=0, yield_units=4), day=4)
        obs["private"]["shed"]["WHEAT"] = True
        self.assertEqual(
            plan_animal_headroom_harvest(action, obs, CFG)["reason"],
            "malformed_capacity_state",
        )


    def test_first_production_with_zero_held_product_cannot_be_rescued_pre_eod(self):
        # Pre-maturity CARE can make first production itself exceed max_held,
        # but a pre-EOD HARVEST cannot save production that does not exist yet.
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        obs = world(
            animal(
                "GOOSE",
                placed_day=0,
                yield_units=0,
                fed_today=True,
                pending=7,
            ),
            day=3,
        )
        plan = plan_animal_headroom_harvest(action, obs, CFG)
        self.assertFalse(plan["eligible"])
        self.assertEqual(plan["reason"], "no_provable_clipping_pass")

    def test_saved_units_are_bounded_by_current_product_when_gain_itself_overflows(self):
        # Sheep can bank CARE across non-production days.  Baseline clip can be
        # larger than held product; HARVEST can recover only the held units.
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        obs = world(
            animal(
                "SHEEP",
                placed_day=0,
                yield_units=6,
                fed_today=True,
                pending=9,
            ),
            day=8,  # next_day9: due (first day6, interval3)
        )
        plan = plan_animal_headroom_harvest(action, obs, CFG)
        self.assertTrue(plan["eligible"])
        row = plan["rewrites"][0]
        self.assertEqual(row["gain"], 10)
        self.assertEqual(row["clipped_units"], 10)
        self.assertEqual(row["recoverable_clipped_units"], 6)
        self.assertEqual(plan["saved_clipped_units"], 6)

    def test_corrupted_over_cap_animal_state_fails_closed(self):
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        obs = world(animal("GOOSE", placed_day=0, yield_units=5), day=4)
        self.assertFalse(plan_animal_headroom_harvest(action, obs, CFG)["eligible"])

    def test_engine_pin_constant_and_git_blob_helper(self):
        self.assertEqual(EXPECTED_ENGINE_GIT_BLOB, "3c202c7ee921da239356789e266b694635103fc4")
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.py"
            p.write_bytes(b"abc\n")
            expected = __import__("hashlib").sha1(b"blob 4\0abc\n").hexdigest()
            self.assertEqual(git_blob_sha1(p), expected)


if __name__ == "__main__":
    unittest.main()
