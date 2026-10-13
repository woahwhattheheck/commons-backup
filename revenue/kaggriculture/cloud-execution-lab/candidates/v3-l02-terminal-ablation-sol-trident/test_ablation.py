# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import types
import unittest

import ablation


class ArmWindowTests(unittest.TestCase):
    def test_all_single_step_arms_are_exactly_step_672(self):
        for arm in set(ablation.ARMS) - {"day28_all"}:
            self.assertFalse(ablation.arm_window(arm, 671)[0])
            self.assertTrue(ablation.arm_window(arm, 672)[0])
            self.assertFalse(ablation.arm_window(arm, 673)[0])

    def test_day28_arm_stops_before_day29(self):
        self.assertTrue(ablation.arm_window("day28_all", 672)[0])
        self.assertTrue(ablation.arm_window("day28_all", 695)[0])
        self.assertFalse(ablation.arm_window("day28_all", 696)[0])

    def test_window_respects_short_episode_bound(self):
        self.assertFalse(ablation.arm_window("once_all", 672, {"episodeSteps": 673})[0])

    def test_boolean_and_unknown_arm_fail_closed(self):
        with self.assertRaises(ValueError):
            ablation.arm_window("bogus", 672)
        with self.assertRaises(ValueError):
            ablation.arm_window("once_all", True)


class ConfigureTests(unittest.TestCase):
    @staticmethod
    def overlay():
        def unchanged(selected, *_args, **_kwargs):
            return selected, {"changed": False}
        return types.SimpleNamespace(
            _late_window=lambda step, cfg: (True, 24, 718),
            apply_product_tranche=unchanged,
            apply_wheat_before_feed_guard=unchanged,
            SELL_ALL_WHEN_ABSENT=("MILK", "WOOL"),
            CARROT_FLOOR=32,
            install=lambda agent: agent,
        )

    def test_carrot_arm_disables_other_components(self):
        overlay = self.overlay()
        manifest = ablation.configure_overlay(overlay, "once_carrot")
        self.assertEqual(overlay.SELL_ALL_WHEN_ABSENT, ())
        self.assertEqual(manifest["components"], {"carrot": True, "noncarrot": False, "wheat": False})
        action = {"market": []}
        self.assertIs(overlay.apply_wheat_before_feed_guard(action, {}, {}, {})[0], action)

    def test_wheat_arm_disables_product_tranche(self):
        overlay = self.overlay()
        manifest = ablation.configure_overlay(overlay, "once_wheat")
        self.assertEqual(manifest["components"], {"carrot": False, "noncarrot": False, "wheat": True})
        action = {"market": []}
        self.assertIs(overlay.apply_product_tranche(action, {}, {}, {})[0], action)

    def test_noncarrot_arm_zeroes_carrot_and_disables_wheat(self):
        overlay = self.overlay()
        manifest = ablation.configure_overlay(overlay, "once_noncarrot")
        self.assertEqual(overlay.CARROT_FLOOR, 0)
        self.assertEqual(manifest["components"], {"carrot": False, "noncarrot": True, "wheat": False})


if __name__ == "__main__":
    unittest.main()
