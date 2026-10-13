import copy
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from revenue.gtri_inventory_acceptance.acceptance import (
    AcceptanceError,
    build_receipt,
    reconcile,
    verify_receipt_integrity,
)


def assets():
    source = [
        {
            "asset_id": "A-100",
            "serial": "SN100",
            "location": "BLDG-1",
            "custodian": "C-1",
            "contract": "W911-1",
        },
        {
            "asset_id": "A-200",
            "serial": "SN200",
            "location": "BLDG-2",
            "custodian": "C-2",
            "contract": "W911-2",
        },
    ]
    target = [
        {
            "source_asset_id": row["asset_id"],
            "asset_id": f"NEW-{row['asset_id']}",
            "serial": row["serial"],
            "location": row["location"],
            "custodian": row["custodian"],
            "contract": row["contract"],
        }
        for row in source
    ]
    return source, target


def histories():
    source = [
        {
            "asset_id": "A-100",
            "event_id": "E-1",
            "event_type": "RECEIPT",
            "occurred_at": "2025-01-01T00:00:00Z",
            "evidence_ref": "sha256:receipt100",
        },
        {
            "asset_id": "A-100",
            "event_id": "E-2",
            "event_type": "MOVE",
            "occurred_at": "2025-02-01T00:00:00Z",
            "evidence_ref": "sha256:move100",
        },
        {
            "asset_id": "A-200",
            "event_id": "E-3",
            "event_type": "RECEIPT",
            "occurred_at": "2025-03-01T00:00:00Z",
            "evidence_ref": "sha256:receipt200",
        },
    ]
    target = [
        {
            "source_asset_id": row["asset_id"],
            "source_event_id": row["event_id"],
            "event_type": row["event_type"],
            "occurred_at": row["occurred_at"],
            "evidence_ref": row["evidence_ref"],
        }
        for row in source
    ]
    return source, target


def contract():
    return {
        "scope_id": "sunflower-wave-1",
        "expected_asset_ids": ["A-100", "A-200"],
        "expected_history_events": {"A-100": ["E-1", "E-2"], "A-200": ["E-3"]},
        "compared_asset_fields": ["serial", "location", "custodian", "contract"],
        "required_asset_fields": ["serial", "location", "custodian", "contract"],
        "history_compare_fields": ["event_type", "occurred_at", "evidence_ref"],
        "expected_interfaces": ["Deltek Costpoint", "Workday"],
        "preserve_asset_id": False,
    }


def interfaces():
    return [
        {"name": "Workday", "status": "PASS", "evidence_id": "sha256:workday"},
        {
            "name": "Deltek Costpoint",
            "status": "PASS",
            "evidence_id": "sha256:costpoint",
        },
    ]


class InventoryAcceptanceTests(unittest.TestCase):
    def make_receipt(self, **overrides):
        source_assets, target_assets = assets()
        source_history, target_history = histories()
        c = contract()
        c.update(overrides.pop("contract_overrides", {}))
        return build_receipt(
            overrides.pop("source_assets", source_assets),
            overrides.pop("target_assets", target_assets),
            overrides.pop("source_history", source_history),
            overrides.pop("target_history", target_history),
            overrides.pop("interfaces", interfaces()),
            scope_id=c["scope_id"],
            expected_asset_ids=c["expected_asset_ids"],
            expected_history_events=c["expected_history_events"],
            compared_asset_fields=c["compared_asset_fields"],
            required_asset_fields=c["required_asset_fields"],
            history_compare_fields=c["history_compare_fields"],
            expected_interfaces=c["expected_interfaces"],
            preserve_asset_id=c["preserve_asset_id"],
        )

    def test_deterministic_under_input_order(self):
        a = self.make_receipt()
        sa, ta = assets()
        sh, th = histories()
        b = self.make_receipt(
            source_assets=list(reversed(sa)),
            target_assets=list(reversed(ta)),
            source_history=list(reversed(sh)),
            target_history=list(reversed(th)),
            interfaces=list(reversed(interfaces())),
        )
        self.assertEqual(a, b)
        self.assertTrue(verify_receipt_integrity(a))

    def test_asset_roster_scope_contraction_is_blocking(self):
        sa, ta = assets()
        sh, th = histories()
        result = reconcile(
            sa[:1],
            ta[:1],
            sh[:2],
            th[:2],
            expected_asset_ids=contract()["expected_asset_ids"],
            expected_history_events=contract()["expected_history_events"],
            compared_asset_fields=contract()["compared_asset_fields"],
            required_asset_fields=contract()["required_asset_fields"],
            history_compare_fields=contract()["history_compare_fields"],
            preserve_asset_id=False,
        )
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["exceptions"]["asset_roster"][0]["missing"], ["A-200"])
        with self.assertRaisesRegex(AcceptanceError, "blocking exceptions"):
            self.make_receipt(
                source_assets=sa[:1],
                target_assets=ta[:1],
                source_history=sh[:2],
                target_history=th[:2],
            )

    def test_history_roster_scope_contraction_is_blocking(self):
        sh, th = histories()
        with self.assertRaisesRegex(AcceptanceError, "blocking exceptions"):
            self.make_receipt(source_history=sh[:-1], target_history=th[:-1])

    def test_asset_field_mismatch_and_required_field_loss_are_blocking(self):
        sa, ta = assets()
        ta[0]["location"] = "WRONG"
        ta[1].pop("custodian")
        result = reconcile(
            sa,
            ta,
            *histories(),
            expected_asset_ids=contract()["expected_asset_ids"],
            expected_history_events=contract()["expected_history_events"],
            compared_asset_fields=contract()["compared_asset_fields"],
            required_asset_fields=contract()["required_asset_fields"],
            history_compare_fields=contract()["history_compare_fields"],
            preserve_asset_id=False,
        )
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(
            result["exceptions"]["asset_field_mismatches"][0]["field"], "location"
        )
        self.assertEqual(
            result["exceptions"]["required_fields"][0]["missing_required_fields"],
            ["custodian"],
        )

    def test_history_value_mismatch_is_blocking(self):
        sh, th = histories()
        th[0]["event_type"] = "DISPOSAL"
        result = reconcile(
            *assets(),
            sh,
            th,
            expected_asset_ids=contract()["expected_asset_ids"],
            expected_history_events=contract()["expected_history_events"],
            compared_asset_fields=contract()["compared_asset_fields"],
            required_asset_fields=contract()["required_asset_fields"],
            history_compare_fields=contract()["history_compare_fields"],
            preserve_asset_id=False,
        )
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(
            result["exceptions"]["history_field_mismatches"][0]["field"],
            "event_type",
        )

    def test_duplicate_and_conflicting_asset_keys_are_rejected(self):
        sa, ta = assets()
        with self.assertRaisesRegex(AcceptanceError, "duplicate key"):
            reconcile(
                sa + [copy.deepcopy(sa[0])],
                ta,
                *histories(),
                expected_asset_ids=contract()["expected_asset_ids"],
                expected_history_events=contract()["expected_history_events"],
                compared_asset_fields=contract()["compared_asset_fields"],
                required_asset_fields=contract()["required_asset_fields"],
                history_compare_fields=contract()["history_compare_fields"],
                preserve_asset_id=False,
            )
        with self.assertRaisesRegex(AcceptanceError, "conflicting duplicate key"):
            bad = copy.deepcopy(sa[0])
            bad["location"] = "DIFFERENT"
            self.make_receipt(source_assets=sa + [bad])

    def test_target_asset_id_reuse_and_preserve_mode_are_blocking(self):
        _, ta = assets()
        ta[1]["asset_id"] = ta[0]["asset_id"]
        with self.assertRaisesRegex(AcceptanceError, "blocking exceptions"):
            self.make_receipt(target_assets=ta)
        with self.assertRaisesRegex(AcceptanceError, "blocking exceptions"):
            self.make_receipt(contract_overrides={"preserve_asset_id": True})

    def test_same_count_different_logical_wave_changes_roots_and_receipt(self):
        first = self.make_receipt()
        sa, ta = assets()
        sa[0]["serial"] = "SN-CHANGED"
        ta[0]["serial"] = "SN-CHANGED"
        second = self.make_receipt(source_assets=sa, target_assets=ta)
        self.assertNotEqual(
            first["payload"]["reconciliation"]["roots"]["source_assets_sha256"],
            second["payload"]["reconciliation"]["roots"]["source_assets_sha256"],
        )
        self.assertNotEqual(first["sha256"], second["sha256"])

    def test_narrower_compare_contract_changes_receipt_even_when_both_pass(self):
        wide = self.make_receipt()
        narrow = self.make_receipt(
            contract_overrides={
                "compared_asset_fields": ["serial", "location", "custodian"]
            }
        )
        self.assertNotEqual(wide["sha256"], narrow["sha256"])
        self.assertNotEqual(
            wide["payload"]["reconciliation"]["contract"]["compared_asset_fields"],
            narrow["payload"]["reconciliation"]["contract"]["compared_asset_fields"],
        )

    def test_interface_roster_omission_and_failed_interface_are_blocking(self):
        with self.assertRaisesRegex(AcceptanceError, "interface roster mismatch"):
            self.make_receipt(interfaces=interfaces()[:1])
        failed = interfaces()
        failed[0]["status"] = "HOLD"
        with self.assertRaisesRegex(AcceptanceError, "not PASS"):
            self.make_receipt(interfaces=failed)

    def test_nonfinite_and_lone_surrogate_fail_closed(self):
        sa, _ = assets()
        sa[0]["serial"] = math.nan
        with self.assertRaisesRegex(AcceptanceError, "non-finite"):
            self.make_receipt(source_assets=sa)
        sa, _ = assets()
        sa[0]["serial"] = "\ud800"
        with self.assertRaisesRegex(AcceptanceError, "not valid UTF-8"):
            self.make_receipt(source_assets=sa)

    def test_receipt_tamper_is_detected(self):
        receipt = self.make_receipt()
        receipt["payload"]["reconciliation"]["counts"]["source_assets"] = 999
        self.assertFalse(verify_receipt_integrity(receipt))

    def test_receipt_integrity_consumes_authority_root(self):
        receipt = self.make_receipt()
        self.assertTrue(verify_receipt_integrity(receipt))
        self.assertTrue(verify_receipt_integrity(receipt, True))
        self.assertFalse(verify_receipt_integrity(receipt, False))
        self.assertFalse(verify_receipt_integrity(receipt, authority_root=None))

    def test_current_readiness_guard_is_clear_on_acceptance_module(self):
        from tools.current_readiness_guard.guard import scan_paths

        root = Path(__file__).resolve().parents[2]
        findings = scan_paths(
            ["revenue/gtri_inventory_acceptance/acceptance.py"],
            root=root,
        )
        self.assertEqual(
            [(item.rule, item.function) for item in findings],
            [],
        )

    def test_invalid_contract_shapes_fail_closed(self):
        with self.assertRaisesRegex(
            AcceptanceError, "preserve_asset_id must be a boolean"
        ):
            self.make_receipt(contract_overrides={"preserve_asset_id": "no"})
        with self.assertRaisesRegex(AcceptanceError, "must be a sequence"):
            self.make_receipt(contract_overrides={"compared_asset_fields": "serial"})

    def test_real_cli_happy_and_surrogate_failure_in_normal_and_optimized_modes(self):
        repo_root = Path(__file__).resolve().parents[2]
        sa, ta = assets()
        sh, th = histories()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            paths = {}
            for name, value in {
                "source_assets": sa,
                "target_assets": ta,
                "source_history": sh,
                "target_history": th,
                "interfaces": interfaces(),
                "contract": contract(),
            }.items():
                path = tmp / f"{name}.json"
                path.write_text(json.dumps(value), encoding="utf-8")
                paths[name] = path

            for optimized in (False, True):
                command = [sys.executable]
                if optimized:
                    command.append("-O")
                command.extend(
                    [
                        "-m",
                        "revenue.gtri_inventory_acceptance.acceptance",
                        "--source-assets",
                        str(paths["source_assets"]),
                        "--target-assets",
                        str(paths["target_assets"]),
                        "--source-history",
                        str(paths["source_history"]),
                        "--target-history",
                        str(paths["target_history"]),
                        "--interfaces",
                        str(paths["interfaces"]),
                        "--contract",
                        str(paths["contract"]),
                    ]
                )
                result = subprocess.run(
                    command,
                    cwd=repo_root,
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(json.loads(result.stdout)["sha256"])

            paths["source_assets"].write_text(
                '[{"asset_id":"A-100","serial":"\\ud800"}]', encoding="ascii"
            )
            command = [
                sys.executable,
                "-O",
                "-m",
                "revenue.gtri_inventory_acceptance.acceptance",
                "--source-assets",
                str(paths["source_assets"]),
                "--target-assets",
                str(paths["target_assets"]),
                "--source-history",
                str(paths["source_history"]),
                "--target-history",
                str(paths["target_history"]),
                "--interfaces",
                str(paths["interfaces"]),
                "--contract",
                str(paths["contract"]),
            ]
            result = subprocess.run(
                command,
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("not valid UTF-8", result.stderr)
            self.assertIn("acceptance.py: error:", result.stderr)


if __name__ == "__main__":
    unittest.main()
