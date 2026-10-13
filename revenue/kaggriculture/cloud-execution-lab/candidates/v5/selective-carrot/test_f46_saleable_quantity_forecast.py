# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
from pathlib import Path
import unittest

import build_f46_saleable_quantity_forecast as build
import f46_saleable_quantity_forecast as f46


class F46ForecastTests(unittest.TestCase):
    def post(self, **shed):
        return {"private": {"shed": dict(shed)}}

    def test_trims_only_proven_dead_suffix(self):
        action = {
            "farmer": ["PASS"],
            "market": [["SELL", "STRAWBERRY", 3], ["SELL", "MILK", 7]],
        }
        result, report = f46.suppress_dead_sell_suffix(
            action, self.post(STRAWBERRY=3, MILK=0)
        )
        self.assertEqual(result["market"], [["SELL", "STRAWBERRY", 3]])
        self.assertTrue(report["changed"])
        self.assertEqual(report["removed_slots"], [1])
        self.assertEqual(action["market"], [
            ["SELL", "STRAWBERRY", 3], ["SELL", "MILK", 7]
        ])

    def test_interior_dead_row_is_not_shifted(self):
        action = {
            "market": [
                ["SELL", "MILK", 7],
                ["SELL", "STRAWBERRY", 3],
            ]
        }
        result, report = f46.suppress_dead_sell_suffix(
            action, self.post(MILK=0, STRAWBERRY=3)
        )
        self.assertEqual(result, action)
        self.assertFalse(report["changed"])
        self.assertEqual(report["blocked_dead_slots"], [0])
        self.assertEqual(report["reason"], "dead_rows_not_suffix")

    def test_multiple_dead_tail_rows_are_removed_without_touching_prefix(self):
        action = {
            "market": [
                ["SELL", "STRAWBERRY", 2],
                ["SELL", "MILK", 1],
                ["SELL", "EGG", 0],
            ]
        }
        result, report = f46.suppress_dead_sell_suffix(
            action, self.post(STRAWBERRY=2, MILK=0, EGG=5)
        )
        self.assertEqual(result["market"], [["SELL", "STRAWBERRY", 2]])
        self.assertEqual(report["removed_slots"], [1, 2])

    def test_partial_sale_is_preserved_and_exhausts_known_stock(self):
        action = {
            "market": [
                ["SELL", "MILK", 3],
                ["SELL", "MILK", 3],
                ["SELL", "MILK", 1],
            ]
        }
        result, report = f46.suppress_dead_sell_suffix(
            action, self.post(MILK=5)
        )
        self.assertEqual(result["market"], [
            ["SELL", "MILK", 3],
            ["SELL", "MILK", 3],
        ])
        self.assertEqual(report["removed_slots"], [2])

    def test_prior_buy_makes_later_sale_uncertain_not_dead(self):
        action = {
            "market": [
                ["BUY_PRODUCT", "MILK", 2],
                ["SELL", "MILK", 2],
            ]
        }
        result, report = f46.suppress_dead_sell_suffix(
            action, self.post(MILK=0)
        )
        self.assertEqual(result, action)
        self.assertFalse(report["changed"])
        self.assertEqual(report["reason"], "no_proven_dead_sell")

    def test_unknown_market_row_freezes_later_classification(self):
        action = {
            "market": [
                ["MYSTERY", "MILK", 1],
                ["SELL", "MILK", 1],
            ]
        }
        result, report = f46.suppress_dead_sell_suffix(
            action, self.post(MILK=0)
        )
        self.assertEqual(result, action)
        self.assertFalse(report["changed"])

    def test_malformed_sell_is_preserved(self):
        for row in (
            ["SELL"],
            ["SELL", "MILK", -1],
            ["SELL", "MILK", True],
            ["SELL", "", 1],
        ):
            with self.subTest(row=row):
                action = {"market": [row]}
                result, report = f46.suppress_dead_sell_suffix(
                    action, self.post(MILK=0)
                )
                self.assertEqual(result, action)
                self.assertFalse(report["changed"])

    def test_missing_shed_fails_open(self):
        action = {"market": [["SELL", "MILK", 5]]}
        result, report = f46.suppress_dead_sell_suffix(action, {"private": {}})
        self.assertEqual(result, action)
        self.assertEqual(report["reason"], "missing_post_unit_shed")

    def test_inputs_are_not_mutated(self):
        action = {"market": [["SELL", "MILK", 1]], "hands": [["PASS"]]}
        post = self.post(MILK=0)
        action_before = repr(action)
        post_before = repr(post)
        f46.suppress_dead_sell_suffix(action, post)
        self.assertEqual(repr(action), action_before)
        self.assertEqual(repr(post), post_before)

    def test_patch_is_single_anchor_and_preserves_unrelated_bytes(self):
        prefix = b"# prefix\n"
        suffix = b"# suffix\n"
        source = prefix + build._ANCHOR + suffix
        patched = build.patch_delivery_choice(source)
        self.assertEqual(patched, prefix + build._PATCH + suffix)
        with self.assertRaisesRegex(ValueError, "found 0"):
            build.patch_delivery_choice(prefix + suffix)
        with self.assertRaisesRegex(ValueError, "found 2"):
            build.patch_delivery_choice(
                prefix + build._ANCHOR + build._ANCHOR + suffix
            )

    def test_inject_rejects_non_c02_preimage(self):
        with self.assertRaisesRegex(ValueError, "exact C02"):
            build.inject({"delivery_choice.py": build._ANCHOR}, b"x")

    def test_checked_in_c02_fixture_is_exact_and_injects(self):
        root = Path(__file__).resolve().parent
        fixture = (
            root / "components" / "c02-deferred-replacement-v1" / "files"
            / "8d130a850ac714780733dccf058864246cd85d67f0171c05ec521d9879d3a6cc.bin"
        )
        raw = fixture.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), build.C02_POSTIMAGE_SHA256)
        files = build.inject({"delivery_choice.py": raw}, b"helper\r\n")
        self.assertIn(b"f46.suppress_dead_sell_suffix(out, post)", files["delivery_choice.py"])
        self.assertEqual(files["f46_saleable_quantity_forecast.py"], b"helper\n")
        self.assertEqual(hashlib.sha256(raw).hexdigest(), build.C02_POSTIMAGE_SHA256)


if __name__ == "__main__":
    unittest.main()
