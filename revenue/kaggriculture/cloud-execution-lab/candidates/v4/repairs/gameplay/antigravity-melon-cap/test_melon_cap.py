import copy
import sys
import unittest
from pathlib import Path

import melon_cap as M

HERE = Path(__file__).resolve()
LAB = next((parent for parent in HERE.parents if (parent / "fourth_quadrant.py").is_file()), None)
if LAB is not None and str(LAB) not in sys.path:
    sys.path.insert(0, str(LAB))
try:
    import fourth_quadrant as FQ
except ModuleNotFoundError:
    FQ = None


def base_observation():
    return {
        "player": 0,
        "step": 600,
        "farms": [{
            "sale_counters": {"MELON": 0},
            "tiles": [[None for _ in range(3)] for _ in range(3)],
        }],
        "private": {
            "shed": {"MELON": 0, "WHEAT": 0},
            "inventories": [{}, {}],
        },
        "market": {"inventory": {"MELON": 9975}},
    }


def producer_proposal(tiles, route_ids=("r0", "r1"), start_step=300, workers=2):
    """Minimal producer-faithful FourthQuadrant MELON proposal shape."""
    tiles = [tuple(tile) for tile in tiles]
    variants = {}
    for route_index, route_id in enumerate(route_ids):
        land_step = start_step + route_index * 100
        patches = {}
        lots = []
        for index, tile in enumerate(tiles):
            step = land_step + index
            worker = 1 + (index % workers)
            hands = [["PASS"] for _ in range(worker)]
            hands[worker - 1] = ["PLANT", "MELON"]
            market = []
            if step == land_step:
                market = [
                    ["BUY_LAND"],
                    ["BUY_SEED", "MELON", len(tiles)],
                    *([ ["HIRE"] ] * workers),
                ]
            patches[step] = {"farmer": ["PASS"], "hands": hands, "market": market}
            lots.append({
                "tile": list(tile),
                "crop": "MELON",
                "plant_step": step,
                "water_steps": [],
                "harvest_step": step + 10,
                "worker": worker,
                "drop_step": step + 11,
                "sale_step": step + 11,
                "sale_slot": 0,
            })
        variants[route_id] = {
            "patches": patches,
            "receipts": [],
            "costs": [],
            "worker_days": [],
            "bundle": {
                "route_id": route_id,
                "base_route_id": route_id,
                "target_quadrant": "SE",
                "land": {"step": land_step, "slot": 0},
                "rejoin_step": 600,
                "lots": lots,
            },
        }
    return {
        "crop": "MELON",
        "tiles": tiles,
        "workers": workers,
        "start": start_step,
        "variants": variants,
        "seed_units": len(tiles),
        "cost": 4000,
    }


def executable_patch_plants(proposal):
    counts = []
    for variant in proposal["variants"].values():
        count = 0
        for row in variant["patches"].values():
            actions = [row.get("farmer", ["PASS"]), *row.get("hands", [])]
            for action in actions:
                if isinstance(action, list) and action[:2] == ["PLANT", "MELON"]:
                    count += 1
        counts.append(count)
    return counts


class MelonCapTests(unittest.TestCase):
    def test_empty_commitment_allows_four_tiles(self):
        self.assertEqual(M.remaining_melon_budget(base_observation()), 28)
        self.assertEqual(M.max_melon_plants(base_observation()), 4)

    def test_existing_plants_reserve_max_future_yield(self):
        obs = base_observation()
        obs["farms"][0]["tiles"][0][0] = {"kind": "PLANT", "crop": "MELON", "yield_units": 1}
        obs["farms"][0]["tiles"][0][1] = {"kind": "PLANT", "crop": "MELON", "yield_units": 6}
        self.assertEqual(M.planted_melon_reserve(obs), 12)
        self.assertEqual(M.max_melon_plants(obs), 2)

    def test_held_melon_reserves_budget(self):
        obs = base_observation()
        obs["private"]["shed"]["MELON"] = 10
        obs["private"]["inventories"][1]["MELON"] = 6
        self.assertEqual(M.held_melon_units(obs), 16)
        self.assertEqual(M.max_melon_plants(obs), 2)

    def test_mutually_exclusive_alternatives_do_not_spend_each_other_budget(self):
        obs = base_observation()
        three = producer_proposal([(5, 5), (6, 5), (5, 6)])
        four = producer_proposal([(5, 5), (6, 5), (5, 6), (6, 6)], start_step=400)
        five = producer_proposal([(5, 5), (6, 5), (5, 6), (6, 6), (7, 5)], start_step=500)
        carrot = {"crop": "CARROT", "tiles": list(range(9))}
        out = M.filter_proposals([three, four, five, carrot], obs)
        self.assertEqual(out, [three, four, carrot])
        self.assertIs(out[0], three)
        self.assertIs(out[1], four)
        self.assertNotIn(five, out)

    def test_metadata_shrink_cannot_smuggle_original_executable_body(self):
        obs = base_observation()
        proposal = producer_proposal([(5, 5), (6, 5), (5, 6), (6, 6), (7, 5), (5, 7)])
        self.assertEqual(executable_patch_plants(proposal), [6, 6])
        proposal["tiles"] = proposal["tiles"][:4]
        proposal["seed_units"] = 4
        for variant in proposal["variants"].values():
            step = variant["bundle"]["land"]["step"]
            variant["patches"][step]["market"][1][2] = 4
        self.assertIsNone(M.executable_melon_plants(proposal))
        self.assertEqual(M.filter_proposals([proposal], obs), [])

    def test_hidden_fifth_farmer_plant_is_rejected(self):
        proposal = producer_proposal([(5, 5), (6, 5), (5, 6), (6, 6)])
        variant = proposal["variants"]["r0"]
        step = variant["bundle"]["lots"][0]["plant_step"]
        variant["patches"][step]["farmer"] = ["PLANT", "MELON"]
        self.assertEqual(executable_patch_plants(proposal)[0], 5)
        self.assertIsNone(M.executable_melon_plants(proposal))
        self.assertEqual(M.filter_proposals([proposal], base_observation()), [])

    def test_hidden_extended_hand_plant_is_semantically_rejected(self):
        proposal = producer_proposal([(5, 5), (6, 5), (5, 6), (6, 6)])
        variant = proposal["variants"]["r0"]
        step = variant["bundle"]["lots"][0]["plant_step"]
        variant["patches"][step]["hands"].append(["PLANT", "MELON", "extra"])
        self.assertEqual(executable_patch_plants(proposal)[0], 5)
        self.assertIsNone(M.executable_melon_plants(proposal))

    def test_buy_seed_quantity_mismatch_is_rejected(self):
        proposal = producer_proposal([(5, 5), (6, 5), (5, 6)])
        for variant in proposal["variants"].values():
            step = variant["bundle"]["land"]["step"]
            variant["patches"][step]["market"][1] = ["BUY_SEED", "MELON", 999]
        self.assertIsNone(M.executable_melon_plants(proposal))
        self.assertEqual(M.filter_proposals([proposal], base_observation()), [])

    def test_seed_metadata_and_matching_overspend_cannot_smuggle(self):
        proposal = producer_proposal([(5, 5), (6, 5), (5, 6)])
        proposal["seed_units"] = 999
        for variant in proposal["variants"].values():
            step = variant["bundle"]["land"]["step"]
            variant["patches"][step]["market"][1] = ["BUY_SEED", "MELON", 999]
        self.assertIsNone(M.executable_melon_plants(proposal))

    def test_first_day_suffix_must_be_exact(self):
        proposal = producer_proposal([(5, 5), (6, 5), (5, 6)])
        variant = proposal["variants"]["r0"]
        step = variant["bundle"]["land"]["step"]
        variant["patches"][step]["market"].append(["BUY_SEED", "MELON", 1])
        self.assertIsNone(M.executable_melon_plants(proposal))

    def test_outer_metadata_and_executable_lots_must_agree(self):
        proposal = producer_proposal([(5, 5), (6, 5), (5, 6)])
        proposal["variants"]["r0"]["bundle"]["lots"][1]["tile"] = [9, 9]
        self.assertIsNone(M.executable_melon_plants(proposal))
        self.assertEqual(M.filter_proposals([proposal], base_observation()), [])

    def test_patch_action_must_authenticate_each_lot(self):
        proposal = producer_proposal([(5, 5), (6, 5), (5, 6)])
        variant = proposal["variants"]["r0"]
        lot = variant["bundle"]["lots"][1]
        variant["patches"][lot["plant_step"]]["hands"][lot["worker"] - 1] = ["PASS"]
        self.assertIsNone(M.executable_melon_plants(proposal))
        self.assertEqual(M.filter_proposals([proposal], base_observation()), [])

    def test_plant_step_and_worker_slot_are_custody(self):
        proposal = producer_proposal([(5, 5), (6, 5), (5, 6)])
        lot = proposal["variants"]["r1"]["bundle"]["lots"][0]
        lot["worker"] += 1
        self.assertIsNone(M.executable_melon_plants(proposal))

    def test_duplicate_lot_identity_is_rejected(self):
        proposal = producer_proposal([(5, 5), (6, 5), (5, 6)])
        lots = proposal["variants"]["r0"]["bundle"]["lots"]
        lots[1]["plant_step"] = lots[0]["plant_step"]
        lots[1]["worker"] = lots[0]["worker"]
        self.assertIsNone(M.executable_melon_plants(proposal))

    def test_every_route_variant_must_cover_same_tiles(self):
        proposal = producer_proposal([(5, 5), (6, 5), (5, 6)])
        proposal["variants"]["r1"]["bundle"]["lots"].pop()
        self.assertIsNone(M.executable_melon_plants(proposal))

    def test_duplicate_outer_tile_fails_closed(self):
        proposal = producer_proposal([(5, 5), (6, 5), (5, 6)])
        proposal["tiles"][1] = proposal["tiles"][0]
        self.assertIsNone(M.executable_melon_plants(proposal))

    def test_metadata_only_melon_fails_closed_but_other_crop_passes(self):
        melon = {"crop": "MELON", "tiles": [(5, 5), (6, 5)], "seed_units": 2}
        carrot = {"crop": "CARROT", "tiles": [3, 4]}
        self.assertEqual(M.filter_proposals([melon, carrot], base_observation()), [carrot])

    def test_sold_plus_held_plus_planted_can_close_budget(self):
        obs = base_observation()
        obs["farms"][0]["sale_counters"]["MELON"] = 10
        obs["private"]["shed"]["MELON"] = 7
        obs["farms"][0]["tiles"][0][0] = {"kind": "PLANT", "crop": "MELON"}
        obs["farms"][0]["tiles"][0][1] = {"kind": "PLANT", "crop": "MELON"}
        self.assertEqual(M.committed_melon_units(obs), 29)
        self.assertEqual(M.max_melon_plants(obs), 0)

    def test_malformed_custody_fails_closed_for_melon_only(self):
        props = [
            producer_proposal([(5, 5), (6, 5)]),
            {"crop": "CARROT", "tiles": [3, 4]},
        ]
        out = M.filter_proposals(props, {"player": "0"})
        self.assertEqual(out, [props[1]])
        self.assertEqual(M.remaining_melon_budget(None), 0)

    def test_market_drift_fallback_uses_exact_prior_town_ticks(self):
        obs = base_observation()
        del obs["farms"][0]["sale_counters"]
        obs["step"] = 25
        obs["market"]["inventory"]["MELON"] = 10008
        self.assertEqual(M.lifetime_melon_sold(obs), 10)

    def test_bool_numeric_aliases_fail_closed(self):
        obs = base_observation()
        obs["private"]["shed"]["MELON"] = True
        self.assertEqual(M.remaining_melon_budget(obs), 0)

    def test_input_is_not_mutated(self):
        obs = base_observation()
        props = [producer_proposal([(5, 5), (6, 5), (5, 6), (6, 6), (7, 5)])]
        before = copy.deepcopy(props)
        M.filter_proposals(props, obs)
        self.assertEqual(props, before)

    @unittest.skipIf(FQ is None, "repository fourth_quadrant module not mounted")
    def test_fourth_quadrant_producer_filter_consumer_contract(self):
        class Mechanics:
            CROPS = {"CARROT": {"seed": 1}, "TOMATO": {"seed": 1}, "MELON": {"seed": 1}}

            @staticmethod
            def _hire_cost(_hands, _mult):
                return 1

        obs = {
            "player": 0,
            "step": 11 * 24,
            "farms": [{
                "sale_counters": {"MELON": 0},
                "tiles": [["LOCKED" for _ in range(10)] for _ in range(10)],
                "unlocked_quadrants": ["NW", "NE", "SW"],
                "hands": [],
                "farmer": [4, 4],
            }],
            "private": {"shed": {"MELON": 0}, "inventories": []},
            "market": {"inventory": {"MELON": 10000}},
        }
        route = [{"farmer": ["PASS"], "hands": [], "market": []} for _ in range(720)]
        options = FQ.proposals(Mechanics(), obs, {"r": route}, "r",
                               {"maxMarketOrdersPerTurn": 10, "farmHandCostMult": 1})
        melons = [p for p in options if p.get("crop") == "MELON"]
        self.assertTrue(any(len(p["tiles"]) == 3 for p in melons))
        self.assertTrue(any(len(p["tiles"]) == 4 for p in melons))
        self.assertTrue(any(len(p["tiles"]) == 5 for p in melons))

        filtered = M.filter_proposals(melons, obs)
        sizes = {len(p["tiles"]) for p in filtered}
        self.assertIn(3, sizes)
        self.assertIn(4, sizes)
        self.assertNotIn(5, sizes)
        for proposal in filtered:
            self.assertEqual(proposal["seed_units"], len(proposal["tiles"]))
            self.assertEqual(M.executable_melon_plants(proposal), len(proposal["tiles"]))
            variant = proposal["variants"]["r"]
            land = variant["bundle"]["land"]
            source_market = variant["patches"][land["step"]]["market"]
            self.assertEqual(source_market[land["slot"]], ["BUY_LAND"])
            self.assertEqual(
                source_market[land["slot"] + 1],
                ["BUY_SEED", "MELON", proposal["seed_units"]],
            )
            self.assertEqual(
                source_market[land["slot"] + 2:],
                [["HIRE"]] * proposal["workers"],
            )

            candidate, _bundle = FQ.economic_program(proposal, "r", route)
            executed = sum(
                1
                for row in candidate
                for action in [row.get("farmer", ["PASS"]), *row.get("hands", [])]
                if isinstance(action, list) and action[:2] == ["PLANT", "MELON"]
            )
            self.assertEqual(executed, len(proposal["tiles"]))
            self.assertLessEqual(executed, 4)
            candidate_market = candidate[land["step"]]["market"]
            self.assertEqual(
                candidate_market[land["slot"] + 1],
                ["BUY_SEED", "MELON", proposal["seed_units"]],
            )


if __name__ == "__main__":
    unittest.main()
