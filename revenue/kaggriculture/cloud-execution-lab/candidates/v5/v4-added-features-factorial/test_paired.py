#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("v4_added_features_factorial", HERE / "paired.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

V4_CONFIG = b'''{
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


class CapturedArchiveHelper:
    @staticmethod
    def archive_members(path):
        return {"captured.tar.gz": Path(path).read_bytes()}


class FactorialTests(unittest.TestCase):
    def baseline(self):
        return {
            "main.py": b"main",
            "frozen_selected.py": b"frozen",
            "TITAN-CONFIG.json": V4_CONFIG,
            "other.py": b"same",
        }

    def test_exact_v4_config_authority(self):
        self.assertEqual(hashlib.sha256(V4_CONFIG).hexdigest(), MODULE.V4_CONFIG_SHA256)
        parsed = MODULE.exact_v4_config(V4_CONFIG)
        self.assertTrue(all(parsed[name] is True for name in MODULE.FEATURES))
        bad = V4_CONFIG.replace(b'"town_procurement": true', b'"town_procurement": false')
        with self.assertRaises(ValueError):
            MODULE.exact_v4_config(bad)

    def test_authenticated_helper_uses_captured_bytes_after_path_mutation(self):
        trusted = b"VALUE = 'trusted'\n"
        expected = MODULE.git_blob_bytes(trusted)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "helper.py"
            path.write_bytes(trusted)
            captured = MODULE.capture_authenticated(path, expected)
            path.write_text("VALUE = 'tampered'\n")
            loaded = MODULE.load_captured(captured, path, "factorial_captured_helper_test")
        self.assertEqual(loaded.VALUE, "trusted")
        self.assertEqual(captured, trusted)

    def test_authenticated_helper_uses_captured_bytes_after_path_deletion(self):
        trusted = b"VALUE = 'trusted'\n"
        expected = MODULE.git_blob_bytes(trusted)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "helper.py"
            path.write_bytes(trusted)
            captured = MODULE.capture_authenticated(path, expected)
            path.unlink()
            loaded = MODULE.load_captured(captured, path, "factorial_deleted_helper_test")
        self.assertEqual(loaded.VALUE, "trusted")
        self.assertEqual(captured, trusted)

    def test_captured_baseline_ignores_live_path_mutation(self):
        trusted = b"trusted exact submitted archive bytes"
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "submitted-v4.tar.gz"
            path.write_bytes(trusted)
            captured = MODULE.capture_sha256(
                path, MODULE.sha256_bytes(trusted), "Baseline archive"
            )
            path.write_bytes(b"tampered after authentication")
            members = MODULE.archive_members_captured(CapturedArchiveHelper, captured)
        self.assertEqual(members, {"captured.tar.gz": trusted})

    def test_captured_baseline_ignores_live_path_deletion(self):
        trusted = b"trusted exact submitted archive bytes"
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "submitted-v4.tar.gz"
            path.write_bytes(trusted)
            captured = MODULE.capture_sha256(
                path, MODULE.sha256_bytes(trusted), "Baseline archive"
            )
            path.unlink()
            members = MODULE.archive_members_captured(CapturedArchiveHelper, captured)
        self.assertEqual(members, {"captured.tar.gz": trusted})

    def test_capture_sha256_rejects_drift_and_symlink(self):
        trusted = b"trusted"
        expected = MODULE.sha256_bytes(trusted)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "baseline.tar.gz"
            path.write_bytes(b"wrong")
            with self.assertRaises(ValueError):
                MODULE.capture_sha256(path, expected, "Baseline archive")
            target = root / "target.tar.gz"
            target.write_bytes(trusted)
            link = root / "link.tar.gz"
            link.symlink_to(target)
            with self.assertRaises(ValueError):
                MODULE.capture_sha256(link, expected, "Baseline archive")

    def test_captured_harness_survives_source_swap_after_auth(self):
        raw = b"VALUE = 7\n"
        expected = MODULE.sha256_bytes(raw)
        with tempfile.TemporaryDirectory() as temp:
            origin = Path(temp) / "evaluator.py"
            origin.write_bytes(raw)
            captured = MODULE.capture_sha256(origin, expected, "Evaluator")
            origin.write_bytes(b"VALUE = 99\n")
            loaded = MODULE.load_captured(captured, origin, "factorial_swap_captured")
            self.assertEqual(loaded.VALUE, 7)
            self.assertNotEqual(origin.read_bytes(), captured)

    def test_captured_harness_survives_source_delete_after_auth(self):
        raw = b"VALUE = 11\n"
        expected = MODULE.sha256_bytes(raw)
        with tempfile.TemporaryDirectory() as temp:
            origin = Path(temp) / "pack.py"
            origin.write_bytes(raw)
            captured = MODULE.capture_sha256(origin, expected, "Packer")
            origin.unlink()
            loaded = MODULE.load_captured(captured, origin, "factorial_delete_captured")
            self.assertEqual(loaded.VALUE, 11)
            self.assertFalse(origin.exists())

    def test_private_loader_is_written_only_from_authenticated_capture(self):
        raw = b"VALUE = 23\n"
        expected = MODULE.sha256_bytes(raw)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            origin = root / "public-evidence-loader.py"
            origin.write_bytes(raw)
            captured = MODULE.capture_sha256(origin, expected, "Candidate loader")
            origin.write_bytes(b"VALUE = 101\n")
            private = root / "private-runtime" / "evaluate.py"
            self.assertEqual(
                MODULE.write_private_runtime_bytes(captured, private, expected), private
            )
            self.assertEqual(private.read_bytes(), raw)
            self.assertNotEqual(private.read_bytes(), origin.read_bytes())

    def test_private_loader_rejects_wrong_captured_digest(self):
        raw = b"VALUE = 23\n"
        expected = MODULE.sha256_bytes(raw)
        with tempfile.TemporaryDirectory() as temp:
            private = Path(temp) / "private-runtime" / "evaluate.py"
            with self.assertRaisesRegex(
                ValueError, "Private runtime bytes do not match authenticated SHA256"
            ):
                MODULE.write_private_runtime_bytes(b"VALUE = 24\n", private, expected)
            self.assertFalse(private.exists())

    def test_screen_is_v4_all_four_off_plus_each_single_off(self):
        self.assertEqual(tuple(MODULE.design_arms("screen")), MODULE.SCREEN_ARMS)
        self.assertIn("all_four_off", MODULE.SCREEN_ARMS)
        self.assertNotIn("v31_flags", MODULE.SCREEN_ARMS)
        self.assertEqual(MODULE.feature_vector("v4"), {name: True for name in MODULE.FEATURES})
        self.assertEqual(
            MODULE.feature_vector("all_four_off"),
            {name: False for name in MODULE.FEATURES},
        )
        self.assertEqual(
            MODULE.feature_vector("v31_flags"),
            MODULE.feature_vector("all_four_off"),
        )
        self.assertEqual(MODULE.canonical_arm("v31_flags"), "all_four_off")
        for name in MODULE.FEATURES:
            vector = MODULE.feature_vector("off_" + name)
            self.assertFalse(vector[name])
            self.assertEqual(sum(vector.values()), 3)

    def test_full_design_is_unique_complete_factorial(self):
        arms = MODULE.design_arms("full")
        self.assertEqual(len(arms), 16)
        vectors = {
            tuple(MODULE.feature_vector(arm)[name] for name in MODULE.FEATURES)
            for arm in arms
        }
        self.assertEqual(len(vectors), 16)
        self.assertIn((False, False, False, False), vectors)
        self.assertIn((True, True, True, True), vectors)

    def test_v4_arm_is_byte_identity(self):
        baseline = self.baseline()
        candidate = MODULE.arm_members(baseline, "v4")
        self.assertEqual(candidate, baseline)
        self.assertEqual(candidate["TITAN-CONFIG.json"], baseline["TITAN-CONFIG.json"])

    def test_nonbaseline_arm_changes_only_config(self):
        baseline = self.baseline()
        candidate = MODULE.arm_members(baseline, "off_early_capital")
        self.assertEqual(set(candidate), set(baseline))
        changed = [name for name in baseline if baseline[name] != candidate[name]]
        self.assertEqual(changed, ["TITAN-CONFIG.json"])
        self.assertEqual(candidate["main.py"], baseline["main.py"])
        self.assertEqual(candidate["frozen_selected.py"], baseline["frozen_selected.py"])
        parsed = json.loads(candidate["TITAN-CONFIG.json"])
        self.assertFalse(parsed["early_capital"])
        for name in MODULE.FEATURES:
            if name != "early_capital":
                self.assertTrue(parsed[name])
        original = json.loads(V4_CONFIG)
        for key in original:
            if key not in MODULE.FEATURES:
                self.assertEqual(parsed[key], original[key])

    def test_all_four_off_changes_exactly_four_values_and_alias_matches_bytes(self):
        baseline = self.baseline()
        candidate = MODULE.arm_members(baseline, "all_four_off")
        alias = MODULE.arm_members(baseline, "v31_flags")
        self.assertEqual(candidate, alias)
        original = json.loads(V4_CONFIG)
        changed = json.loads(candidate["TITAN-CONFIG.json"])
        differing = {key for key in original if original[key] != changed[key]}
        self.assertEqual(differing, set(MODULE.FEATURES))
        self.assertTrue(all(changed[name] is False for name in MODULE.FEATURES))

    def test_mask_validation(self):
        self.assertEqual(
            MODULE.feature_vector("mask_1010"),
            {
                "idle_fertilizer": True,
                "crop_release": False,
                "early_capital": True,
                "town_procurement": False,
            },
        )
        for bad in ("mask_2", "mask_00000", "mask_00x0", "off_missing", "wat"):
            with self.assertRaises(ValueError, msg=bad):
                MODULE.feature_vector(bad)

    def test_summary_uses_v4_baseline_and_canonical_off_identity(self):
        cells = [{"opponent": "apex_v7", "margin_delta": {"v4": 0, "all_four_off": 11}}]
        summary = MODULE.summarize(cells, ["v4", "all_four_off"])
        self.assertTrue(summary["v4"]["baseline_equivalent"])
        self.assertEqual(
            summary["all_four_off"]["opponents"]["apex_v7"]["mean_margin_delta"],
            11,
        )
        self.assertNotIn("v31_flags", summary)


if __name__ == "__main__":
    unittest.main()
