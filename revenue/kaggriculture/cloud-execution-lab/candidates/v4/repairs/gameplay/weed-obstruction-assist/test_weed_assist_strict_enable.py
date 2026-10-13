from __future__ import annotations

import unittest

from weed_assist import assist_same_turn_weed_obstructions


def _observation():
    tiles = [[None for _ in range(3)] for _ in range(3)]
    tiles[0][0] = {"kind": "WEED"}
    return {
        "player": 0,
        "farms": [
            {"farmer": [0, 0], "hands": [[0, 0]], "tiles": tiles},
            {"farmer": [2, 2], "hands": [], "tiles": [[None for _ in range(3)] for _ in range(3)]},
        ],
        "private": {
            "seeds": {
                "WHEAT": 0,
                "CARROT": 1,
                "TOMATO": 0,
                "STRAWBERRY": 0,
                "MELON": 0,
            }
        },
    }


def _action():
    return {
        "farmer": ["PASS"],
        "hands": [["PLANT", "CARROT"]],
        "market": [["SELL", "WHEAT", 1]],
    }


class StrictEnableTests(unittest.TestCase):
    def test_malformed_enable_values_fail_closed_by_identity(self):
        observation = _observation()
        malformed = (
            "false",
            "true",
            0,
            1,
            0.0,
            1.0,
            None,
            [],
            {},
            [True],
            {"value": True},
        )
        for enabled in malformed:
            with self.subTest(enabled=repr(enabled)):
                parent = _action()
                out, report = assist_same_turn_weed_obstructions(
                    observation,
                    parent,
                    enabled=enabled,
                )
                self.assertIs(out, parent)
                self.assertFalse(report["changed"])
                self.assertFalse(report["enabled"])
                self.assertEqual(report["reason"], "invalid_enabled")
                self.assertEqual(report["rewrites"], [])

    def test_literal_false_preserves_disabled_identity_contract(self):
        parent = _action()
        out, report = assist_same_turn_weed_obstructions(
            _observation(),
            parent,
            enabled=False,
        )
        self.assertIs(out, parent)
        self.assertFalse(report["enabled"])
        self.assertFalse(report["changed"])
        self.assertEqual(report["reason"], "disabled")

    def test_literal_true_remains_the_only_active_gate(self):
        parent = _action()
        out, report = assist_same_turn_weed_obstructions(
            _observation(),
            parent,
            enabled=True,
        )
        self.assertIsNot(out, parent)
        self.assertTrue(report["enabled"])
        self.assertTrue(report["changed"])
        self.assertEqual(report["reason"], "same_turn_assist")
        self.assertEqual(out["farmer"], ["DIG"])
        self.assertEqual(out["hands"], [["PLANT", "CARROT"]])
        self.assertEqual(out["market"], parent["market"])


if __name__ == "__main__":
    unittest.main()
