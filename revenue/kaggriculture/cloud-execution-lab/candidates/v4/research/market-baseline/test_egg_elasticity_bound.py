#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

import egg_elasticity_bound as e


class EggElasticityBoundTests(unittest.TestCase):
    def test_git_blob_hash_is_real_git_object_identity(self):
        data = b"pass\n"
        expected = hashlib.sha1(b"blob 5\0pass\n").hexdigest()
        self.assertEqual(expected, e.git_blob_sha1(data))

    def test_log_glut_curve_is_resilient_but_not_infinite(self):
        self.assertEqual(50, e.egg_price(10_000))
        self.assertEqual(40, e.egg_price(10_332))
        self.assertEqual(38, e.egg_price(11_000))
        self.assertEqual(35, e.egg_price(15_000))

    def test_global_one_dollar_floor_is_reached_at_finite_excess(self):
        threshold = e.first_glut_excess_reaching_floor()
        self.assertEqual(1_713_383_311_443, threshold)
        self.assertEqual(2, e.egg_price(e.EGG_I0 + threshold - 1))
        self.assertEqual(1, e.egg_price(e.EGG_I0 + threshold))

    def test_standard_episode_production_outer_bound_is_deliberately_loose(self):
        bounds = e.standard_episode_bounds()
        self.assertEqual(24_000, bounds["max_player_generated_egg_market_increase"])
        self.assertEqual(34_000, bounds["max_market_inventory_outer_bound"])
        self.assertEqual(33, bounds["glut_price_lower_bound"])

    def test_town_depletion_outer_bound_counts_all_possible_egg_shops(self):
        town = e.max_town_egg_depletion()
        self.assertEqual(30, town["town_center_egg_ticks"])
        self.assertEqual(792, town["max_egg_shop_ticks"])
        self.assertEqual(822, town["max_total_egg_depletion"])
        self.assertEqual([162, 144, 126, 108, 90, 72, 54, 36], [row["egg_ticks"] for row in town["shop_instances"]])

    def test_standard_episode_scarcity_is_finite_even_if_every_shop_consumes_egg(self):
        bounds = e.standard_episode_bounds()
        self.assertEqual(9_178, bounds["min_market_inventory_outer_bound"])
        self.assertEqual(448, bounds["scarcity_price_upper_bound"])
        self.assertEqual([33, 448], bounds["reachable_price_outer_interval"])

    def test_receipt_kills_short_squeeze_without_killing_price_resilience(self):
        r = e.receipt()
        self.assertFalse(r["direct_buy_product_egg_supported"])
        self.assertEqual("ASYMMETRIC_BUT_FINITE_NO_DIRECT_EGG_SHORT_SQUEEZE", r["verdict"])
        self.assertFalse(r["decision_authority"])
        self.assertFalse(r["runtime_mutation"])
        self.assertIn("price-resilient", r["interpretation"][0])
        self.assertIn("not a direct short squeeze", r["interpretation"][2])

    def test_checkout_authentication_fails_closed_on_wrong_blobs(self):
        with tempfile.TemporaryDirectory() as td:
            cloud = Path(td) / "cloud-execution-lab"
            packet = cloud / "candidates" / "v4" / "research" / "market-baseline" / "dummy.py"
            packet.parent.mkdir(parents=True)
            packet.write_text("# dummy\n", encoding="utf-8")
            engine_dir = cloud / "reference" / "engine"
            engine_dir.mkdir(parents=True)
            (engine_dir / "kaggriculture.py").write_text("wrong\n", encoding="utf-8")
            (engine_dir / "kaggriculture.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "engine Git blob drift"):
                e.verify_checkout(packet)

    def test_type_poison_inventory_fails_closed(self):
        for bad in (True, 1.0, "10000", -1):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    e.egg_price(bad)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
