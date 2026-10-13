# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import rank_arms


def report(arm, own, margin, worst=-20, changed=4):
    per = {
        "arlene": {"mean_own_delta": worst},
        "v1": {"mean_own_delta": own},
    }
    return {
        "status": "complete",
        "identity": {"git_head": "a" * 40, "ablation_arm": arm},
        "seeds": [1],
        "opponents": ["arlene", "v1"],
        "expected_cells_per_variant": 4,
        "summary": {"mean_own_delta": own, "mean_margin_delta": margin,
                    "min_own_delta": worst, "cells": 4, "trace_changed_cells": changed},
        "per_opponent": per,
    }


class RankTests(unittest.TestCase):
    def write(self, root, name, value):
        path = root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_positive_bounded_arm_requires_full_panel(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = [self.write(root, "a.json", report("once_all", 3, 1)),
                     self.write(root, "b.json", report("once_wheat", -2, 8))]
            result = rank_arms.rank(paths)
        self.assertEqual(result["decision"], "FULL_PANEL_REQUIRED")
        self.assertEqual(result["recommended_arm"], "once_all")

    def test_margin_only_denial_does_not_survive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = [self.write(root, "a.json", report("once_all", -1, 100))]
            result = rank_arms.rank(paths)
        self.assertEqual(result["decision"], "NO_ARM_SURVIVES_SCREEN")
        self.assertIsNone(result["recommended_arm"])

    def test_grid_drift_and_duplicate_json_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = report("once_all", 1, 1)
            second = report("once_wheat", 1, 1)
            second["seeds"] = [2]
            with self.assertRaises(ValueError):
                rank_arms.rank([self.write(root, "a.json", first), self.write(root, "b.json", second)])
            bad = root / "bad.json"
            bad.write_text('{"status":"complete","status":"complete"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                rank_arms.load_report(bad)


if __name__ == "__main__":
    unittest.main()
