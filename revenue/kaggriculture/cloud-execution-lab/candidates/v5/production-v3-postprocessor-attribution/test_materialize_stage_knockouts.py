# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import materialize_stage_knockouts as m

EXACT_CONFIG = b'''{
  "consumer": "frozen",
  "seed": true,
  "funding": true,
  "terminal_route": false,
  "committed": true,
  "budget_seconds": 1.0,
  "reserve_seconds": 0.01,
  "terminal_history": false,
  "redundant_hire": true,
  "fourth_quadrant": false,
  "market_pressure": true,
  "committed_seed_retry": false,
  "operating_stock": true,
  "idle_fertilizer": true,
  "crop_release": true,
  "early_capital": true,
  "town_procurement": true
}
'''


class ProductionV3PostprocessorAttributionTest(unittest.TestCase):
    def baseline(self):
        return {
            "TITAN-CONFIG.json": EXACT_CONFIG,
            "main.py": b"v3 entry placeholder\n",
            "retained.py": b"retained\n",
        }

    def cfg(self, arm):
        return json.loads(m.arm_members(self.baseline(), arm)["TITAN-CONFIG.json"])

    def test_exact_production_config_is_bound(self):
        self.assertEqual(m.digest(EXACT_CONFIG), m.BASELINE_CONFIG_SHA256)
        config = m._baseline_config(self.baseline())
        for key, value in m.SCREEN_PREIMAGE.items():
            self.assertEqual(config[key], value)

    def test_original_three_stage_arms_are_semantically_unchanged(self):
        self.assertEqual(
            m.STAGE_ARMS,
            {
                "seed_hire_off": {
                    "seed": False,
                    "funding": False,
                    "redundant_hire": False,
                },
                "inventory_spatial_off": {
                    "operating_stock": False,
                    "idle_fertilizer": False,
                    "crop_release": False,
                },
                "late_market_off": {
                    "market_pressure": False,
                    "early_capital": False,
                },
            },
        )
        seen = set()
        for name in sorted(m.STAGE_ARMS):
            changes = m.STAGE_ARMS[name]
            self.assertTrue(seen.isdisjoint(changes), name)
            seen.update(changes)
        self.assertEqual(
            seen,
            {
                "seed", "funding", "redundant_hire",
                "operating_stock", "idle_fertilizer", "crop_release",
                "market_pressure", "early_capital",
            },
        )

    def test_boundary_pair_has_exact_required_off_leaves(self):
        self.assertEqual(
            m.BOUNDARY_PAIR,
            {
                "consumer_boundary_control": {
                    "redundant_hire": False,
                    "idle_fertilizer": False,
                    "crop_release": False,
                    "town_procurement": False,
                },
                "consumer_boundary_parent": {
                    "consumer": "parent",
                    "redundant_hire": False,
                    "idle_fertilizer": False,
                    "crop_release": False,
                    "town_procurement": False,
                },
            },
        )
        self.assertEqual(set(m.ARMS), set(m.STAGE_ARMS) | set(m.BOUNDARY_PAIR))

    def test_boundary_pair_diff_is_consumer_only(self):
        self.assertEqual(m._boundary_pair_diff(self.baseline()), ["consumer"])
        control = self.cfg("consumer_boundary_control")
        parent = self.cfg("consumer_boundary_parent")
        keys = set(control) | set(parent)
        self.assertEqual(
            {key for key in keys if control.get(key) != parent.get(key)},
            {"consumer"},
        )
        self.assertEqual(control["consumer"], "frozen")
        self.assertEqual(parent["consumer"], "parent")
        for cfg in (control, parent):
            self.assertFalse(cfg["redundant_hire"])
            self.assertFalse(cfg["idle_fertilizer"])
            self.assertFalse(cfg["crop_release"])
            self.assertFalse(cfg["town_procurement"])
            self.assertTrue(cfg["seed"])
            self.assertTrue(cfg["funding"])
            self.assertTrue(cfg["operating_stock"])
            self.assertTrue(cfg["market_pressure"])
            self.assertTrue(cfg["early_capital"])

    def test_entrypoint_contract_rejects_parent_plus_town(self):
        cfg = json.loads(EXACT_CONFIG)
        cfg["consumer"] = "parent"
        cfg["redundant_hire"] = False
        cfg["idle_fertilizer"] = False
        cfg["crop_release"] = False
        with self.assertRaisesRegex(AssertionError, "town_procurement requires"):
            m._assert_composition_contract(cfg, "consumer_boundary_parent")

    def test_each_arm_changes_only_config_and_preserves_retained_members(self):
        baseline = self.baseline()
        for arm, changes in m.ARMS.items():
            treatment = m.arm_members(baseline, arm)
            self.assertEqual(
                [name for name in baseline if baseline[name] != treatment[name]],
                ["TITAN-CONFIG.json"],
            )
            cfg = json.loads(treatment["TITAN-CONFIG.json"])
            for key, before in m.SCREEN_PREIMAGE.items():
                expected = changes.get(key, before)
                self.assertEqual(cfg[key], expected, (arm, key))
            self.assertEqual(treatment["main.py"], baseline["main.py"])
            self.assertEqual(treatment["retained.py"], baseline["retained.py"])

    def test_original_stage_arms_keep_frozen_town_composition(self):
        for arm in m.STAGE_ARMS:
            cfg = self.cfg(arm)
            self.assertEqual(cfg["consumer"], "frozen")
            self.assertIs(cfg["town_procurement"], True)
        inventory = self.cfg("inventory_spatial_off")
        self.assertFalse(inventory["operating_stock"])
        self.assertFalse(inventory["idle_fertilizer"])
        self.assertFalse(inventory["crop_release"])
        seed_hire = self.cfg("seed_hire_off")
        self.assertFalse(seed_hire["seed"])
        self.assertFalse(seed_hire["funding"])
        self.assertFalse(seed_hire["redundant_hire"])
        late = self.cfg("late_market_off")
        self.assertFalse(late["market_pressure"])
        self.assertFalse(late["early_capital"])

    def test_parent_effective_gate_disclosure_is_explicit(self):
        self.assertEqual(
            set(m.EFFECTIVE_PARENT_GATES),
            {"frozen_selected", "spatial", "operating_stock", "feed_stock", "early_capital"},
        )

    def test_wrong_preimage_rejects_before_treatment(self):
        baseline = self.baseline()
        baseline["TITAN-CONFIG.json"] = EXACT_CONFIG.replace(
            b'"market_pressure": true', b'"market_pressure": false'
        )
        with self.assertRaisesRegex(ValueError, "exact production-v3"):
            m.arm_members(baseline, "late_market_off")

    def test_unknown_arm_rejects(self):
        with self.assertRaisesRegex(ValueError, "unknown attribution arm"):
            m.arm_members(self.baseline(), "not-an-arm")

    def test_bundle_is_deterministic_and_binds_every_arm(self):
        baseline = self.baseline()
        baseline_members = {name: m.digest(body) for name, body in sorted(baseline.items())}
        first_bundle, first_receipt = m.build_screen(baseline)
        second_bundle, second_receipt = m.build_screen(baseline)
        self.assertEqual(first_bundle, second_bundle)
        self.assertEqual(first_receipt, second_receipt)
        self.assertEqual(first_receipt["bundle_sha256"], m.digest(first_bundle))
        self.assertEqual(first_receipt["baseline_members"], baseline_members)
        self.assertEqual(set(first_receipt["arms"]), set(m.ARMS))
        self.assertEqual(first_receipt["schema"], m.SCHEMA)
        self.assertEqual(first_receipt["native_economics_status"], "PENDING_MATCHED_NATIVE_9901")
        self.assertTrue(first_receipt["kaggle_submission_hold"])
        pair = first_receipt["consumer_boundary_pair"]
        self.assertEqual(pair["control"], "consumer_boundary_control")
        self.assertEqual(pair["treatment"], "consumer_boundary_parent")
        self.assertEqual(pair["config_diff_keys"], ["consumer"])
        self.assertEqual(pair["effective_parent_gates"], m.EFFECTIVE_PARENT_GATES)
        for arm, record in first_receipt["arms"].items():
            treatment = m.arm_members(baseline, arm)
            expected_members = {
                name: m.digest(body) for name, body in sorted(treatment.items())
            }
            self.assertEqual(record["changed_members"], ["TITAN-CONFIG.json"])
            self.assertEqual(record["member_count"], len(baseline))
            self.assertEqual(set(record["config_changes"]), set(m.ARMS[arm]))
            self.assertEqual(record["members"], expected_members)
            for name, member_sha in baseline_members.items():
                if name != "TITAN-CONFIG.json":
                    self.assertEqual(record["members"][name], member_sha, (arm, name))

    def test_bundle_contains_screen_and_five_nested_archives(self):
        baseline = self.baseline()
        baseline_members = {name: m.digest(body) for name, body in sorted(baseline.items())}
        bundle, receipt = m.build_screen(baseline)
        members = m.support.parse_archive_bytes(bundle, receipt["bundle_sha256"])
        self.assertEqual(set(members), {"SCREEN.json"} | {f"arms/{arm}.tar.gz" for arm in m.ARMS})
        screen = json.loads(members["SCREEN.json"])
        self.assertEqual(screen["schema"], m.SCHEMA)
        self.assertEqual(screen["baseline_archive_sha256"], m.BASELINE_ARCHIVE_SHA256)
        self.assertEqual(screen["baseline_members"], baseline_members)
        self.assertEqual(screen["consumer_boundary_pair"]["config_diff_keys"], ["consumer"])
        for arm in m.ARMS:
            nested = m.support.parse_archive_bytes(
                members[f"arms/{arm}.tar.gz"], screen["arms"][arm]["archive_sha256"]
            )
            nested_members = {name: m.digest(body) for name, body in sorted(nested.items())}
            self.assertEqual(set(nested), set(baseline))
            self.assertEqual(nested_members, screen["arms"][arm]["members"])
            self.assertEqual(nested["main.py"], baseline["main.py"])
            for name, member_sha in baseline_members.items():
                if name != "TITAN-CONFIG.json":
                    self.assertEqual(nested_members[name], member_sha, (arm, name))

    def test_semantic_map_rotates_only_v3_main_identity(self):
        self.assertEqual(
            m.SEMANTIC_MEMBER_SHA256["main.py"],
            "b98aec64f83ea9a216def7ab1fef320a6498ae37816f506af1f891c934027035",
        )
        for name, sha in m.support.SEMANTIC_MEMBER_SHA256.items():
            if name != "main.py":
                self.assertEqual(m.SEMANTIC_MEMBER_SHA256[name], sha)


if __name__ == "__main__":
    unittest.main()
