#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import feedstock_fourflag_cross as subject


class FakeFactorial:
    @staticmethod
    def arm_members(baseline, name):
        if name != "all_four_off":
            raise ValueError(name)
        result = dict(baseline)
        result["TITAN-CONFIG.json"] = b'{"all_four_off":true}\n'
        return result


class CrossTests(unittest.TestCase):
    def baseline(self):
        return {
            "main.py": b"pass\n",
            "titan_runtime.py": b"runtime-control\n",
            "operating_stock.py": b"stock-control\n",
            "TITAN-CONFIG.json": b'{"all_four_off":false}\n',
        }

    def test_donor_sources_are_exact_landed_blobs(self):
        kg_root = Path(__file__).resolve().parents[4]
        factorial, feed = subject.load_donors(kg_root)
        self.assertEqual(subject.BASELINE_SHA256, factorial.BASELINE_SHA256)
        self.assertEqual(subject.BASELINE_SHA256, feed.BASELINE_SHA256)

    def test_capture_git_blob_is_single_read_and_fail_closed(self):
        trusted = b"VALUE = 7\n"
        expected = subject.git_blob_bytes(trusted)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "donor.py"
            path.write_bytes(trusted)
            captured = subject.capture_git_blob(path, expected, "donor")
            path.write_bytes(b"VALUE = 9\n")
            loaded = subject.load_captured(captured, path, "cross_captured_test")
            self.assertEqual(7, loaded.VALUE)
            with self.assertRaises(ValueError):
                subject.capture_git_blob(path, expected, "donor")

    def test_compose_cross_changes_only_expected_members(self):
        control = self.baseline()
        feed = dict(control)
        feed["titan_runtime.py"] = b"runtime-feed-off\n"
        arms = subject.compose_cross_arms(control, feed, FakeFactorial)
        self.assertEqual(set(subject.ARMS), set(arms))
        self.assertEqual(
            ("titan_runtime.py",),
            subject.changed_members(control, arms["feed_stock_off"]),
        )
        self.assertEqual(
            ("TITAN-CONFIG.json",),
            subject.changed_members(control, arms["all_four_off"]),
        )
        self.assertEqual(
            ("TITAN-CONFIG.json", "titan_runtime.py"),
            subject.changed_members(control, arms["both_off"]),
        )
        self.assertEqual(
            arms["both_off"]["titan_runtime.py"],
            arms["feed_stock_off"]["titan_runtime.py"],
        )
        self.assertEqual(
            arms["both_off"]["TITAN-CONFIG.json"],
            arms["all_four_off"]["TITAN-CONFIG.json"],
        )
        for arm in arms.values():
            self.assertEqual(control["operating_stock.py"], arm["operating_stock.py"])

    def test_compose_rejects_nonorthogonal_feed_donor(self):
        control = self.baseline()
        feed = dict(control)
        feed["titan_runtime.py"] = b"runtime-feed-off\n"
        feed["main.py"] = b"changed\n"
        with self.assertRaisesRegex(ValueError, "unexpected members"):
            subject.compose_cross_arms(control, feed, FakeFactorial)

    def test_interaction_contrast(self):
        values = {
            "v4": 100,
            "feed_stock_off": 110,
            "all_four_off": 120,
            "both_off": 145,
        }
        result = subject.interaction_contrast(values)
        self.assertEqual(10, result["feed_effect_flags_on"])
        self.assertEqual(20, result["fourflag_effect_feed_on"])
        self.assertEqual(25, result["feed_effect_flags_off"])
        self.assertEqual(35, result["fourflag_effect_feed_off"])
        self.assertEqual(45, result["joint_effect"])
        self.assertEqual(15, result["interaction"])

    def test_interaction_rejects_partial_nonfinite_and_bool(self):
        with self.assertRaises(ValueError):
            subject.interaction_contrast({"v4": 1})
        for bad in (float("nan"), float("inf"), True):
            values = {arm: 0 for arm in subject.ARMS}
            values["both_off"] = bad
            with self.assertRaises(ValueError):
                subject.interaction_contrast(values)

    def test_summary_skips_incomplete_cells(self):
        cells = [
            {
                "opponent": "apex_v7",
                "margins": {
                    "v4": 100,
                    "feed_stock_off": 110,
                    "all_four_off": 120,
                    "both_off": 145,
                },
            },
            {
                "opponent": "apex_v7",
                "margins": {"v4": 10},
            },
        ]
        result = subject.summarize_interaction(cells)
        self.assertEqual(2, result["apex_v7"]["cells"])
        self.assertEqual(1, result["apex_v7"]["complete_cells"])
        self.assertEqual(15, result["apex_v7"]["mean_interaction"])


if __name__ == "__main__":
    unittest.main()
