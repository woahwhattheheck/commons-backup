#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import current_abi_audit as r5  # noqa: E402


class R5CurrentAbiClosure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = r5.audit()
        cls.manifest = json.loads(r5.MANIFEST.read_text(encoding="utf-8"))

    def test_preserved_contract_is_the_exact_legacy_remap(self):
        contract = self.manifest["mechanism_contract"]
        self.assertIn("leave published SHOP_PLANS[(BAKERY,YARN_STORE)] == 3 unchanged", contract)
        self.assertIn(
            "when explicitly enabled, only at ROUTE_STEP=144 and exact full shop list [BAKERY,YARN_STORE], select existing tape 9",
            contract,
        )
        legacy = self.report["legacy_contract"]
        self.assertEqual(legacy["route_step"], 144)
        self.assertEqual(legacy["baseline_plan"], 3)
        self.assertEqual(legacy["target_plan"], 9)
        self.assertEqual(legacy["tape_count"], 13)
        self.assertEqual(legacy["tape_length"], 719)

    def test_historical_donor_git_blobs_are_authenticated(self):
        identity = self.report["source_identity"]
        self.assertEqual(
            identity["legacy_router_git_blob"],
            r5.EXPECTED_LEGACY_ROUTER_GIT_BLOB,
        )
        self.assertEqual(
            identity["legacy_tapes_git_blob"],
            r5.EXPECTED_LEGACY_TAPES_GIT_BLOB,
        )

    def test_router_tamper_is_rejected_before_literal_parse(self):
        with tempfile.TemporaryDirectory() as td:
            tampered = Path(td) / "r04_full_router.py"
            tampered.write_bytes(r5.LEGACY_ROUTER.read_bytes() + b"\n# tamper\n")
            with mock.patch.object(r5, "LEGACY_ROUTER", tampered), mock.patch.object(
                r5, "_literal_assignment", side_effect=AssertionError("parse must not run")
            ):
                with self.assertRaisesRegex(
                    RuntimeError, "historical donor identity mismatch: legacy_router_git_blob"
                ):
                    r5.audit()

    def test_tapes_tamper_is_rejected_before_module_load(self):
        with tempfile.TemporaryDirectory() as td:
            tampered = Path(td) / "r01_tapes.py"
            tampered.write_bytes(r5.LEGACY_TAPES.read_bytes() + b"\n# tamper\n")
            with mock.patch.object(r5, "LEGACY_TAPES", tampered), mock.patch.object(
                r5, "_load_module", side_effect=AssertionError("module load must not run")
            ):
                with self.assertRaisesRegex(
                    RuntimeError, "historical donor identity mismatch: legacy_tapes_git_blob"
                ):
                    r5.audit()

    def test_current_router_is_not_the_legacy_shop_pair_abi(self):
        current = self.report["current_contract"]
        self.assertFalse(current["has_legacy_SHOP_PLANS_symbol"])
        self.assertEqual(current["route_step_decisions"], [])
        self.assertNotIn(144, [row[0] for row in current["decisions"]])

    def test_old_r5_has_no_identity_preserving_current_target(self):
        report = self.report
        self.assertEqual(report["verdict"], "nonportable_no_current_authoritative_target")
        mapping = report["identity_mapping"]
        self.assertFalse(mapping["current_MAIN_matches_legacy_plan3"])
        self.assertEqual(mapping["portable_exact_targets"], [])
        self.assertTrue(report["reason_codes"])

    def test_closure_is_diagnostic_only(self):
        self.assertEqual(
            self.manifest["status"],
            "closed_nonportable_current_abi",
        )
        self.assertFalse(self.manifest["default"])
        closure = self.manifest["current_abi_closure"]
        self.assertEqual(closure["proved_by_pr"], 12836)
        self.assertEqual(
            closure["verdict"],
            "nonportable_no_current_authoritative_target",
        )
        self.assertIn("identity-preserving legacy-plan-3", closure["reopen_only_if"])
        self.assertIn("do not execute legacy apply_v4 against the current production ABI",
                      self.manifest["integration_contract"])
        self.assertIn("do not replace or overwrite the shared modern composer/materializer with the legacy generator",
                      self.manifest["integration_contract"])
        self.assertTrue(any(
            "do not approximate the legacy tape-9 continuation" in line
            for line in self.manifest["integration_contract"]
        ))

    def test_report_records_closed_manifest_state(self):
        self.assertEqual(
            self.report["manifest_status_before_audit"],
            "closed_nonportable_current_abi",
        )

    def test_report_is_stable_json(self):
        encoded = json.dumps(self.report, sort_keys=True, separators=(",", ":"))
        self.assertEqual(json.loads(encoded)["verdict"], self.report["verdict"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
