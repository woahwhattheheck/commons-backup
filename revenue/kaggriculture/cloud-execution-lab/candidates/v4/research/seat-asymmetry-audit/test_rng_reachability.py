#!/usr/bin/env python3
import unittest

from rng_reachability import (
    Refusal,
    authenticate_engine_bytes,
    authored_vacancy_projection,
    offline_delta_panel,
    reachability_report,
    shop_unlock_due,
)


def farm(tile00=None, *, hands=None):
    tiles = [[None for _ in range(5)] for _ in range(5)]
    tiles[0][0] = tile00
    return {
        "tiles": tiles,
        "farmer": [0, 0],
        "hands": [[1, 0]] if hands is None else hands,
    }


class RNGReachabilityTests(unittest.TestCase):
    def test_source_auth_rejects_drift(self):
        with self.assertRaises(Refusal):
            authenticate_engine_bytes(b"not-the-official-engine")

    def test_authored_build_changes_vacancy(self):
        result = authored_vacancy_projection(
            farm=farm(None),
            own_seeds={},
            authored_action={"farmer": ["BUILD_COOP"], "hands": []},
            market_prefix_limit=10,
        )
        self.assertEqual(result["delta"], -1)
        self.assertTrue(result["natural_engagement"])
        self.assertEqual(result["effects"][0]["op"], "BUILD_COOP")
        self.assertEqual(result["market_prefix_limit"], 10)
        self.assertTrue(result["market_vacancy_resolved"])

    def test_atomic_plant_oversubscription_blocks_all_same_crop(self):
        result = authored_vacancy_projection(
            farm=farm(None),
            own_seeds={"WHEAT": 1},
            authored_action={
                "farmer": ["PLANT", "WHEAT"],
                "hands": [["PLANT", "WHEAT"]],
            },
            market_prefix_limit=10,
        )
        self.assertEqual(result["blocked_plant_crops"], ["WHEAT"])
        self.assertEqual(result["delta"], 0)
        self.assertEqual(result["effects"], [])

    def test_extra_nonexistent_hand_row_can_poison_plant_preflight(self):
        f = farm(None, hands=[])
        result = authored_vacancy_projection(
            farm=f,
            own_seeds={"WHEAT": 1},
            authored_action={
                "farmer": ["PLANT", "WHEAT"],
                "hands": [["PLANT", "WHEAT"]],
            },
            market_prefix_limit=10,
        )
        self.assertEqual(result["blocked_plant_crops"], ["WHEAT"])
        self.assertEqual(result["delta"], 0)

    def test_malformed_plant_crop_fails_closed(self):
        for crop in ([], {}, True, 1):
            with self.subTest(crop=crop):
                with self.assertRaisesRegex(Refusal, "PLANT crop must be a string"):
                    authored_vacancy_projection(
                        farm=farm(None, hands=[]),
                        own_seeds={"WHEAT": 1},
                        authored_action={"farmer": ["PLANT", crop]},
                        market_prefix_limit=10,
                    )

    def test_exact_seed_plant_changes_vacancy(self):
        result = authored_vacancy_projection(
            farm=farm(None, hands=[]),
            own_seeds={"WHEAT": 1},
            authored_action={"farmer": ["PLANT", "WHEAT"]},
            market_prefix_limit=10,
        )
        self.assertEqual(result["delta"], -1)

    def test_sequential_same_tile_build_then_dig_is_net_neutral(self):
        f = farm(None, hands=[[0, 0]])
        result = authored_vacancy_projection(
            farm=f,
            own_seeds={},
            authored_action={
                "farmer": ["BUILD_COOP"],
                "hands": [["DIG"]],
            },
            market_prefix_limit=10,
        )
        self.assertEqual([e["delta"] for e in result["effects"]], [-1, 1])
        self.assertEqual(result["delta"], 0)
        self.assertFalse(result["natural_engagement"])

    def test_dig_weed_changes_but_dig_animal_does_not(self):
        weed = authored_vacancy_projection(
            farm=farm({"kind": "WEED"}, hands=[]),
            own_seeds={},
            authored_action={"farmer": ["DIG"]},
            market_prefix_limit=10,
        )
        self.assertEqual(weed["delta"], 1)
        animal = authored_vacancy_projection(
            farm=farm({"kind": "COOP", "animal": "GOOSE"}, hands=[]),
            own_seeds={},
            authored_action={"farmer": ["DIG"]},
            market_prefix_limit=10,
        )
        self.assertEqual(animal["delta"], 0)

    def test_hire_and_movement_do_not_change_tile_vacancy(self):
        for row in (["HIRE"], ["NORTH"], ["PASS"]):
            with self.subTest(row=row):
                result = authored_vacancy_projection(
                    farm=farm(None, hands=[]),
                    own_seeds={},
                    authored_action={"farmer": row},
                    market_prefix_limit=10,
                )
                self.assertEqual(result["delta"], 0)

    def test_executable_prefix_buy_land_fails_closed(self):
        with self.assertRaisesRegex(Refusal, "BUY_LAND requires exact market replay"):
            authored_vacancy_projection(
                farm=farm(None, hands=[]),
                own_seeds={},
                authored_action={"farmer": ["PASS"], "market": [["BUY_LAND"]]},
                market_prefix_limit=10,
            )

    def test_buy_land_beyond_executable_prefix_is_inert(self):
        result = authored_vacancy_projection(
            farm=farm(None, hands=[]),
            own_seeds={},
            authored_action={
                "farmer": ["BUILD_COOP"],
                "market": [["BUY_SEED", "WHEAT", 1], ["BUY_LAND"]],
            },
            market_prefix_limit=1,
        )
        self.assertEqual(result["delta"], -1)
        self.assertEqual(result["market_prefix_limit"], 1)

    def test_engine_min_one_prefix_keeps_row_zero_buy_land(self):
        for limit in (0, -1, -99):
            with self.subTest(limit=limit):
                with self.assertRaisesRegex(Refusal, "BUY_LAND requires exact market replay"):
                    authored_vacancy_projection(
                        farm=farm(None, hands=[]),
                        own_seeds={},
                        authored_action={
                            "farmer": ["PASS"],
                            "market": [["BUY_LAND"], ["BUY_SEED", "WHEAT", 1]],
                        },
                        market_prefix_limit=limit,
                    )

    def test_market_prefix_type_poison_fails_closed(self):
        for limit in (True, 1.0, "1", None, [], {}):
            with self.subTest(limit=limit):
                with self.assertRaisesRegex(Refusal, "market_prefix_limit must be a plain int"):
                    authored_vacancy_projection(
                        farm=farm(None, hands=[]),
                        own_seeds={},
                        authored_action={"farmer": ["PASS"], "market": []},
                        market_prefix_limit=limit,
                    )

    def test_visible_cash_does_not_guess_buy_land_execution(self):
        f = farm(None, hands=[])
        f["money"] = 0
        with self.assertRaisesRegex(Refusal, "BUY_LAND requires exact market replay"):
            authored_vacancy_projection(
                farm=f,
                own_seeds={},
                authored_action={
                    "farmer": ["PASS"],
                    "market": [["SELL", "MELON", 100], ["BUY_LAND"]],
                },
                market_prefix_limit=2,
            )

    def test_unlock_schedule_matches_next_day_boundary_and_cap(self):
        self.assertTrue(shop_unlock_due(day=2, shop_interval=3, unlocked_shop_count=0))
        self.assertFalse(shop_unlock_due(day=1, shop_interval=3, unlocked_shop_count=0))
        self.assertFalse(shop_unlock_due(day=2, shop_interval=3, unlocked_shop_count=8))

    def test_offline_panel_reproduces_shopstream_337_175(self):
        report = offline_delta_panel(
            day=2,
            empty_tiles_by_farm=[25, 25],
            farm_id=0,
            delta=-1,
            seed_start=1,
            seed_stop=512,
        )
        self.assertEqual(report["shop_changed"], 337)
        self.assertEqual(report["shop_unchanged"], 175)
        self.assertFalse(report["hidden_seed_live_input"])
        self.assertFalse(report["authority"]["desired_shop_targeting"])

    def test_reachability_reports_only_authored_natural_engagement(self):
        report = reachability_report(
            farms=[farm(None, hands=[]), farm(None, hands=[])],
            own_farm_id=0,
            own_seeds={},
            authored_action={"farmer": ["BUILD_COOP"]},
            day=2,
            shop_interval=3,
            unlocked_shop_count=0,
            market_prefix_limit=10,
            seed_start=1,
            seed_stop=512,
        )
        self.assertTrue(report["unlock_due"])
        self.assertEqual(report["authored_projection"]["delta"], -1)
        self.assertEqual(
            report["offline_shop_sensitivity"]["shop_changed"], 337
        )
        self.assertTrue(
            report["authority"]["natural_current_policy_engagement"]
        )
        self.assertFalse(report["authority"]["invented_action"])
        self.assertFalse(report["authority"]["desired_shop_targeting"])
        self.assertFalse(report["authority"]["activation_authority"])

    def test_nonunlock_callback_has_no_shop_sensitivity(self):
        report = reachability_report(
            farms=[farm(None, hands=[]), farm(None, hands=[])],
            own_farm_id=0,
            own_seeds={},
            authored_action={"farmer": ["BUILD_COOP"]},
            day=1,
            shop_interval=3,
            unlocked_shop_count=0,
            market_prefix_limit=10,
        )
        self.assertFalse(report["unlock_due"])
        self.assertIsNone(report["offline_shop_sensitivity"])
        self.assertFalse(
            report["authority"]["natural_current_policy_engagement"]
        )

    def test_bool_integer_poison_rejected(self):
        with self.assertRaises(Refusal):
            shop_unlock_due(day=True, shop_interval=3, unlocked_shop_count=0)


if __name__ == "__main__":
    unittest.main()
