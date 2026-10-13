# SPDX-License-Identifier: Apache-2.0
"""Fail closed on policy-changing type aliases at the Features boundary."""
from __future__ import annotations

import json
from pathlib import Path
import unittest

from titan_runtime import Features


HERE = Path(__file__).resolve().parent
BOOL_FIELDS = (
    "seed",
    "funding",
    "redundant_hire",
    "terminal_route",
    "committed",
    "terminal_history",
    "spatial_pathing",
    "spatial_tempo",
    "fourth_quadrant",
    "market_pressure",
    "committed_seed_retry",
    "operating_stock",
    "idle_fertilizer",
    "crop_release",
    "early_capital",
)


def canonical_features():
    data = json.loads((HERE / "TITAN-CONFIG.json").read_text())
    # main.py owns this separate runtime stage; it is not a Features field.
    data.pop("town_procurement", None)
    return data


class FeatureTypeExactnessTests(unittest.TestCase):
    def test_canonical_config_constructs_unchanged(self):
        data = canonical_features()
        features = Features(**data)
        for name, value in data.items():
            self.assertEqual(getattr(features, name), value)
            self.assertIs(type(getattr(features, name)), type(value))

    def test_every_toggle_requires_exact_bool(self):
        base = canonical_features()
        for name in BOOL_FIELDS:
            for bad in (0, 1, "false", [], None):
                with self.subTest(name=name, bad=bad):
                    data = dict(base)
                    data[name] = bad
                    with self.assertRaises(TypeError):
                        Features(**data)

    def test_deadline_numbers_are_finite_non_bool_int_or_float(self):
        base = canonical_features()
        for name in ("budget_seconds", "reserve_seconds"):
            for bad in (False, True, "0.1", [], None, float("nan"),
                        float("inf"), float("-inf")):
                with self.subTest(name=name, bad=bad):
                    data = dict(base)
                    data[name] = bad
                    with self.assertRaises(TypeError):
                        Features(**data)
        self.assertEqual(Features(budget_seconds=1, reserve_seconds=0).budget_seconds, 1)

    def test_history_hypotheses_requires_dict_or_none(self):
        for bad in ([], (), "{}", 1, False):
            with self.subTest(bad=bad):
                with self.assertRaises(TypeError):
                    Features(history_hypotheses=bad)
        self.assertEqual(Features(terminal_history=True, history_hypotheses={}).history_hypotheses, {})

    def test_terminal_tie_break_requires_string(self):
        for bad in (None, 1, False, [], {}):
            with self.subTest(bad=bad):
                with self.assertRaises(TypeError):
                    Features(terminal_tie_break=bad)


if __name__ == "__main__":
    unittest.main(verbosity=2)
