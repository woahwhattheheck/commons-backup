from __future__ import annotations
import importlib.util
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "town_rng", HERE / "town_rng_coupling.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class TownRngTests(unittest.TestCase):
    def test_constants_bind_current_engine(self):
        self.assertEqual(
            mod.ENGINE_GIT_BLOB,
            "3c202c7ee921da239356789e266b694635103fc4",
        )
        self.assertEqual(mod.DEFAULT_SHOP_UNLOCK_INTERVAL, 3)
        self.assertEqual(mod.MAX_SHOP_INSTANCES, 8)
        self.assertEqual(
            mod.SHOPS,
            ("BAKERY", "BRUNCH_SPOT", "FARMERS_MARKET", "ICE_CREAM_SHOP",
             "PET_CAFE", "PIZZA_SHOP", "SMOOTHIE_SHOP", "YARN_STORE"),
        )

    def test_draw_count_is_sum(self):
        self.assertEqual(mod.weed_rng_draw_count([13, 27]), 40)
        self.assertEqual(mod.weed_rng_draw_count([27, 13]), 40)

    def test_equal_total_seat_swap_preserves_shop_many_seeds(self):
        for seed in range(200):
            a = mod.official_shop_projection(
                seed=seed, day=2, empty_counts=[13, 27]
            )
            b = mod.official_shop_projection(
                seed=seed, day=2, empty_counts=[27, 13]
            )
            self.assertEqual(a, b)

    def test_equal_total_partition_preserves_shop(self):
        for seed in range(50):
            self.assertEqual(
                mod.official_shop_projection(
                    seed=seed, day=2, empty_counts=[1, 39]
                ),
                mod.official_shop_projection(
                    seed=seed, day=2, empty_counts=[20, 20]
                ),
            )

    def test_fixed_one_extra_empty_witness(self):
        base = mod.official_shop_projection(
            seed=1, day=2, empty_counts=[20, 20]
        )
        cand = mod.official_shop_projection(
            seed=1, day=2, empty_counts=[20, 21]
        )
        self.assertEqual(base, "SMOOTHIE_SHOP")
        self.assertEqual(cand, "BAKERY")
        self.assertNotEqual(base, cand)

    def test_pair_gate_marks_environment_divergence(self):
        got = mod.compare_pair(
            seed=1, day=2,
            baseline_empty_counts=[20, 20],
            candidate_empty_counts=[20, 21],
        )
        self.assertEqual(got["rng_cursor_shift"], 1)
        self.assertTrue(got["shop_diverged"])
        self.assertEqual(got["causal_gate"], "ENVIRONMENT_PATH_DIVERGED")
        self.assertFalse(got["weed_chance_affects_cursor"])
        self.assertFalse(got["policy_claim"])
        self.assertFalse(got["economic_claim"])
        self.assertFalse(got["live_seed_targeting_claim"])

    def test_decoupled_control_removes_empty_dependence(self):
        got = mod.compare_pair(
            seed=1, day=2,
            baseline_empty_counts=[20, 20],
            candidate_empty_counts=[20, 21],
        )
        self.assertTrue(got["decoupled_control_equal"])
        self.assertEqual(
            got["decoupled_control_baseline_shop"],
            got["decoupled_control_candidate_shop"],
        )

    def test_non_unlock_day_and_cap_return_none(self):
        self.assertIsNone(mod.official_shop_projection(
            seed=1, day=1, empty_counts=[20, 20]
        ))
        self.assertIsNone(mod.official_shop_projection(
            seed=1, day=2, empty_counts=[20, 20], next_shop_count=8
        ))

    def test_custom_unlock_interval(self):
        self.assertIsNotNone(mod.official_shop_projection(
            seed=1, day=3, empty_counts=[20, 20], shop_unlock_interval=2
        ))
        self.assertIsNone(mod.official_shop_projection(
            seed=1, day=2, empty_counts=[20, 20], shop_unlock_interval=2
        ))

    def test_find_witness_is_deterministic(self):
        self.assertEqual(
            mod.find_coupling_witness(
                day=2, baseline_total_empty=40, delta=1, seed_limit=100
            ),
            {
                "seed": 1,
                "day": 2,
                "baseline_total_empty": 40,
                "candidate_total_empty": 41,
                "baseline_shop": "SMOOTHIE_SHOP",
                "candidate_shop": "BAKERY",
            },
        )

    def test_invalid_types_fail_closed(self):
        for counts in ([True], [-1], ["4"], [], "4"):
            with self.assertRaises(ValueError):
                mod.weed_rng_draw_count(counts)
        with self.assertRaises(ValueError):
            mod.official_shop_projection(
                seed=True, day=2, empty_counts=[1]
            )
        with self.assertRaises(ValueError):
            mod.official_shop_projection(
                seed=1, day=-1, empty_counts=[1]
            )
        with self.assertRaises(ValueError):
            mod.official_shop_projection(
                seed=1, day=2, empty_counts=[1], shop_unlock_interval=True
            )
        with self.assertRaises(ValueError):
            mod.find_coupling_witness(delta=0)
        with self.assertRaises(ValueError):
            mod.tail_fill_counterfactual(
                seed=1, day=2, empty_counts=[25, 0], seat=1
            )
        with self.assertRaises(ValueError):
            mod.stream_snapshot(
                seed=1, day=2, empty_counts=[25, 25], weed_chance=1.1
            )

    def test_engine_verifier_rejects_drift(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "kaggriculture.py"
            path.write_text("not the pinned engine\n")
            with self.assertRaisesRegex(ValueError, "engine source drift"):
                mod.verify_engine_source(path)

    def test_probe_contains_control_and_witness(self):
        got = mod.run_probe()
        self.assertFalse(got["equal_total_seat_swap_control"]["shop_diverged"])
        self.assertTrue(got["changed_total_witness"]["shop_diverged"])
        self.assertFalse(got["weed_spawn_chance_zero_removes_coupling"])
        self.assertFalse(got["policy_claim"])
        self.assertFalse(got["economic_claim"])
        self.assertEqual(got["fixed_tail_fill_panel"]["shop_flips"], 1336)

    def test_tail_fill_clean_seat1_witness(self):
        got = mod.tail_fill_counterfactual(
            seed=5, day=2, empty_counts=[25, 25], seat=1
        )
        self.assertEqual(got["baseline"]["shop"], "PIZZA_SHOP")
        self.assertEqual(got["variant"]["shop"], "BRUNCH_SPOT")
        self.assertTrue(got["shop_changed"])
        self.assertTrue(got["prior_seat_weeds_preserved"])
        self.assertTrue(got["own_remaining_weeds_preserved"])
        self.assertEqual(got["later_seats_changed"], [])

    def test_seat0_tail_fill_shifts_later_seat_stream(self):
        got = mod.tail_fill_counterfactual(
            seed=5, day=2, empty_counts=[25, 25], seat=0
        )
        self.assertTrue(got["prior_seat_weeds_preserved"])
        self.assertTrue(got["own_remaining_weeds_preserved"])
        self.assertEqual(got["later_seats_changed"], [1])
        self.assertTrue(got["shop_changed"])

    def test_zero_weed_chance_still_shifts_shop(self):
        got = mod.tail_fill_counterfactual(
            seed=5, day=2, empty_counts=[25, 25], seat=1, weed_chance=0.0
        )
        self.assertTrue(got["shop_changed"])
        self.assertEqual(got["baseline"]["shop"], "PIZZA_SHOP")
        self.assertEqual(got["variant"]["shop"], "BRUNCH_SPOT")
        self.assertTrue(all(
            not hit
            for seat_hits in got["baseline"]["weed_hits"]
            for hit in seat_hits
        ))

    def test_same_total_shop_projection_ignores_seat_partition(self):
        left = mod.stream_snapshot(
            seed=5, day=2, empty_counts=[24, 25]
        )
        right = mod.stream_snapshot(
            seed=5, day=2, empty_counts=[25, 24]
        )
        self.assertEqual(left["rng_draws_before_shop"], 49)
        self.assertEqual(right["rng_draws_before_shop"], 49)
        self.assertEqual(left["shop"], right["shop"])

    def test_shop_demand_vector_matches_engine_shop_rules(self):
        self.assertEqual(mod.shop_demand_vector("YARN_STORE"), {"WOOL": 2})
        self.assertEqual(
            mod.shop_demand_vector("PIZZA_SHOP"),
            {"MILK": 1, "TOMATO": 1, "WHEAT": 1},
        )
        with self.assertRaises(ValueError):
            mod.shop_demand_vector("NOT_A_SHOP")

    def test_fixed_tail_fill_panel_receipt(self):
        got = mod.fixed_tail_fill_panel()
        self.assertEqual(got["cells"], 2048)
        self.assertEqual(got["shop_flips"], 1336)
        self.assertEqual(got["shop_unchanged"], 712)
        self.assertEqual(got["per_day"]["2"]["shop_flips"], 164)
        witness = got["first_shop_flip_witness"]
        self.assertEqual((witness["seed"], witness["day"]), (5, 2))
        self.assertEqual(witness["baseline_shop"], "PIZZA_SHOP")
        self.assertEqual(witness["variant_shop"], "BRUNCH_SPOT")
        self.assertTrue(witness["prior_seat_weeds_preserved"])
        self.assertTrue(witness["own_remaining_weeds_preserved"])


if __name__ == "__main__":
    unittest.main()
