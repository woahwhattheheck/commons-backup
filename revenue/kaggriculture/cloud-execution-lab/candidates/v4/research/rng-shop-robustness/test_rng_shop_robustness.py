# SPDX-License-Identifier: Apache-2.0
from hashlib import sha1
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from rng_shop_robustness import (
    ENGINE_SOURCE_BLOB,
    SHOPS,
    robust_options,
    shop_draw,
    shop_unlock_due,
    stable_shop_intervals,
)


def git_blob_sha(data: bytes) -> str:
    return sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


class RngShopRobustnessTest(unittest.TestCase):
    def test_reference_engine_source_is_exactly_pinned(self):
        engine = HERE.parents[3] / "reference" / "engine" / "kaggriculture.py"
        data = engine.read_bytes()
        self.assertEqual(git_blob_sha(data), ENGINE_SOURCE_BLOB)
        text = data.decode("utf-8")
        self.assertIn('rng = random.Random((seed * 1_000_003) ^ day)', text)
        self.assertIn('_spawn_weeds(farm, board_size, weed_chance, rng)', text)
        self.assertIn('town["unlocked_shops"].append(rng.choice(sorted(SHOPS)))', text)

    def test_unlock_cadence_and_cap_match_engine(self):
        self.assertFalse(shop_unlock_due(1, 0))
        self.assertTrue(shop_unlock_due(2, 0))
        self.assertTrue(shop_unlock_due(5, 7))
        self.assertFalse(shop_unlock_due(5, 8))

    def test_order_of_player_counts_is_irrelevant_but_total_is_not(self):
        seed = 2051966578
        day = 5
        self.assertEqual(shop_draw(seed, day, (22, 20)), "BRUNCH_SPOT")
        self.assertEqual(shop_draw(seed, day, (20, 22)), "BRUNCH_SPOT")
        self.assertNotEqual(shop_draw(seed, day, (22, 19)), "BRUNCH_SPOT")

    def test_fresh_sian_loss_seed_has_six_cursor_brunch_window(self):
        intervals = stable_shop_intervals(2051966578, 5, 40, 49)
        self.assertIn((42, 47, "BRUNCH_SPOT"), intervals)

    def test_fresh_sian_loss_seed_has_five_cursor_bakery_window(self):
        intervals = stable_shop_intervals(2051966578, 11, 31, 39)
        self.assertIn((33, 37, "BAKERY"), intervals)

    def test_fresh_gracie_loss_seed_has_five_cursor_bakery_window(self):
        intervals = stable_shop_intervals(1378040481, 14, 40, 48)
        self.assertIn((42, 46, "BAKERY"), intervals)

    def test_bounded_rival_uncertainty_can_still_force_exact_shop(self):
        result = robust_options(
            2051966578,
            5,
            [21, 22, 23],
            range(20, 26),
            target_shops={"BAKERY", "BRUNCH_SPOT"},
        )
        by_own = {row.own_empty_count: row for row in result}
        self.assertEqual(by_own[22].exact_shop, "BRUNCH_SPOT")
        self.assertTrue(by_own[22].all_in_target_set)
        self.assertEqual(by_own[22].target_hits, 6)
        self.assertIsNone(by_own[21].exact_shop)

    def test_target_set_robustness_does_not_invent_probability(self):
        rows = robust_options(
            2051966578,
            5,
            [22],
            [19, 20, 21, 22, 23, 24, 25, 26],
            target_shops={"BAKERY", "BRUNCH_SPOT"},
        )
        self.assertFalse(rows[0].all_in_target_set)
        self.assertLess(rows[0].target_hits, len(rows[0].rival_outcomes))

    def test_invalid_inputs_fail_closed(self):
        invalid_calls = (
            lambda: shop_draw(True, 5, (1, 2)),
            lambda: shop_draw(1, -1, (1, 2)),
            lambda: shop_draw(1, 5, (1, False)),
            lambda: robust_options(1, 5, [], [1]),
            lambda: robust_options(1, 5, [1], [], target_shops=SHOPS),
            lambda: robust_options(1, 5, [1], [1], target_shops={"NOPE"}),
            lambda: stable_shop_intervals(1, 5, 4, 3),
        )
        for call in invalid_calls:
            with self.subTest(call=call):
                with self.assertRaises(ValueError):
                    call()


if __name__ == "__main__":
    unittest.main()
