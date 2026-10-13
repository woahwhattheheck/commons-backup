import copy
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import open_door_guard as guard

from revenue.columbia_erp_acceptance.acceptance import (
    AcceptanceError,
    ETL_PHASES,
    build_receipt,
    reconcile_records,
    verify_receipt,
)


def phase_evidence():
    return {phase: f"sha256:{phase}-evidence" for phase in ETL_PHASES}


def interfaces():
    return [
        {
            "name": "Dayforce payroll",
            "status": "PASS",
            "evidence_id": "sha256:dayforce",
        },
        {
            "name": "Club Automation",
            "status": "PASS",
            "evidence_id": "sha256:club",
        },
    ]


def expected_interfaces():
    return ["Dayforce payroll", "Club Automation"]


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.source = [
            {"key": "GL-100", "amount": "10.00", "account": "1000", "version": 3},
            {"key": "GL-200", "amount": "20.00", "account": "2000", "version": 1},
        ]
        self.target = list(reversed(copy.deepcopy(self.source)))

    def receipt(self, source=None, target=None, **kwargs):
        return build_receipt(
            self.source if source is None else source,
            self.target if target is None else target,
            phase_evidence(),
            interfaces(),
            expected_interfaces=expected_interfaces(),
            **kwargs,
        )

    def test_happy_receipt_is_deterministic_across_record_and_interface_order(self):
        a = self.receipt(scope_id="ledger-wave-1")
        b = build_receipt(
            list(reversed(self.source)),
            list(reversed(self.target)),
            phase_evidence(),
            list(reversed(interfaces())),
            expected_interfaces=list(reversed(expected_interfaces())),
            scope_id="ledger-wave-1",
        )
        self.assertEqual(a, b)
        self.assertTrue(verify_receipt(a))
        self.assertEqual(a["payload"]["reconciliation"]["status"], "PASS")

    def test_missing_unexpected_and_field_mismatch_hold(self):
        target = [
            {"key": "GL-100", "amount": "11.00", "account": "1000", "version": 3},
            {"key": "GL-999", "amount": "9.00", "account": "9999", "version": 1},
        ]
        result = reconcile_records(self.source, target)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["missing_target_keys"], ["GL-200"])
        self.assertEqual(result["unexpected_target_keys"], ["GL-999"])
        self.assertEqual(result["field_mismatches"][0]["field"], "amount")
        with self.assertRaisesRegex(AcceptanceError, "blocking exceptions"):
            build_receipt(
                self.source,
                target,
                phase_evidence(),
                interfaces(),
                expected_interfaces=expected_interfaces(),
            )

    def test_duplicate_and_conflicting_duplicate_are_rejected(self):
        same_duplicate = self.source + [copy.deepcopy(self.source[0])]
        with self.assertRaisesRegex(AcceptanceError, "duplicate key"):
            reconcile_records(same_duplicate, self.target)
        conflict = self.source + [{**self.source[0], "amount": "99.00"}]
        with self.assertRaisesRegex(AcceptanceError, "conflicting duplicate"):
            reconcile_records(conflict, self.target)

    def test_nonfinite_values_fail_closed(self):
        bad = copy.deepcopy(self.source)
        bad[0]["amount"] = math.nan
        with self.assertRaisesRegex(AcceptanceError, "non-finite") as ctx:
            reconcile_records(bad, self.target)
        message = str(ctx.exception)
        self.assertRegex(message, r"non-finite")
        self.assertNotRegex(message, r"\b(?:not permitted|not authorized)\b")

    def test_package_source_does_not_add_open_door_denial_locks(self):
        root = Path(__file__).resolve().parent
        repo = Path(__file__).resolve().parents[2]
        chunks = []
        for path in sorted(root.iterdir()):
            if not path.is_file():
                continue
            rel = path.relative_to(repo).as_posix()
            lines = path.read_text(encoding="utf-8").splitlines()
            header = [
                f"diff --git a/{rel} b/{rel}",
                "--- /dev/null",
                f"+++ b/{rel}",
                f"@@ -0,0 +1,{len(lines)} @@",
            ]
            chunks.append(
                "\n".join(header + [f"+{line}" for line in lines]) + "\n"
            )
        found = guard.scan_diff("\n".join(chunks))
        self.assertEqual(found, [], found)

    def test_incomplete_etl_phase_evidence_cannot_issue_receipt(self):
        evidence = phase_evidence()
        evidence.pop("validate")
        with self.assertRaisesRegex(AcceptanceError, "missing ETL evidence: validate"):
            build_receipt(
                self.source,
                self.target,
                evidence,
                interfaces(),
                expected_interfaces=expected_interfaces(),
            )

    def test_failed_or_duplicate_interface_cannot_issue_receipt(self):
        failed = interfaces()
        failed[0]["status"] = "HOLD"
        with self.assertRaisesRegex(AcceptanceError, "not PASS"):
            build_receipt(
                self.source,
                self.target,
                phase_evidence(),
                failed,
                expected_interfaces=expected_interfaces(),
            )
        duplicate = interfaces() + [interfaces()[0]]
        with self.assertRaisesRegex(AcceptanceError, "duplicate interface"):
            build_receipt(
                self.source,
                self.target,
                phase_evidence(),
                duplicate,
                expected_interfaces=expected_interfaces(),
            )

    def test_interface_roster_omission_is_blocking(self):
        with self.assertRaisesRegex(AcceptanceError, "interface roster mismatch"):
            build_receipt(
                self.source,
                self.target,
                phase_evidence(),
                interfaces()[:1],
                expected_interfaces=expected_interfaces(),
            )

    def test_receipt_tamper_is_detected(self):
        receipt = self.receipt()
        receipt["payload"]["reconciliation"]["source_count"] = 999
        self.assertFalse(verify_receipt(receipt))

    def test_compare_fields_can_bound_the_acceptance_contract(self):
        target = copy.deepcopy(self.target)
        target[0]["noncontract_note"] = "target-only annotation"
        result = reconcile_records(
            self.source,
            target,
            compare_fields=["amount", "account", "version"],
        )
        self.assertEqual(result["status"], "PASS")

    def test_receipt_binds_record_roots_and_comparison_contract(self):
        first = self.receipt(scope_id="same-scope")
        other_source = [
            {"key": "GL-300", "amount": "30.00", "account": "3000", "version": 2},
            {"key": "GL-400", "amount": "40.00", "account": "4000", "version": 4},
        ]
        second = self.receipt(
            source=other_source,
            target=list(reversed(copy.deepcopy(other_source))),
            scope_id="same-scope",
        )
        self.assertNotEqual(
            first["payload"]["reconciliation"]["source_records_sha256"],
            second["payload"]["reconciliation"]["source_records_sha256"],
        )
        self.assertNotEqual(first["sha256"], second["sha256"])

        narrow = self.receipt(scope_id="same-scope", compare_fields=["amount"])
        wide = self.receipt(
            scope_id="same-scope", compare_fields=["amount", "account"]
        )
        self.assertNotEqual(narrow["sha256"], wide["sha256"])
        self.assertEqual(narrow["payload"]["contract"]["compare_fields"], ["amount"])
        self.assertEqual(
            wide["payload"]["contract"]["compare_fields"], ["account", "amount"]
        )

    def test_malformed_compare_fields_fail_closed_with_acceptance_error(self):
        with self.assertRaisesRegex(AcceptanceError, "sequence of field names"):
            reconcile_records(self.source, self.target, compare_fields="amount")
        with self.assertRaisesRegex(AcceptanceError, "invalid field name"):
            reconcile_records(self.source, self.target, compare_fields=["amount", 7])

    def test_non_string_phase_key_fails_closed_with_acceptance_error(self):
        evidence = phase_evidence()
        evidence[7] = "sha256:bad-key"
        with self.assertRaisesRegex(AcceptanceError, "phase evidence keys must be strings"):
            build_receipt(
                self.source,
                self.target,
                evidence,
                interfaces(),
                expected_interfaces=expected_interfaces(),
            )

    def test_invalid_key_field_fails_closed_with_acceptance_error(self):
        with self.assertRaisesRegex(AcceptanceError, "key_field must be a non-empty string"):
            reconcile_records(self.source, self.target, key_field="")
        with self.assertRaisesRegex(AcceptanceError, "key_field must be a non-empty string"):
            reconcile_records(self.source, self.target, key_field=7)

    def _write_cli_support_files(self, tmp: Path):
        target = tmp / "target.json"
        phases = tmp / "phases.json"
        interface_evidence = tmp / "interfaces.json"
        expected = tmp / "expected_interfaces.json"
        target.write_text(json.dumps(self.target), encoding="utf-8")
        phases.write_text(json.dumps(phase_evidence()), encoding="utf-8")
        interface_evidence.write_text(json.dumps(interfaces()), encoding="utf-8")
        expected.write_text(json.dumps(expected_interfaces()), encoding="utf-8")
        return target, phases, interface_evidence, expected

    def _run_cli(self, source, target, phases, interface_evidence, expected, optimized):
        repo_root = Path(__file__).resolve().parents[2]
        command = [sys.executable]
        if optimized:
            command.append("-O")
        command.extend(
            [
                "-m",
                "revenue.columbia_erp_acceptance.acceptance",
                "--source",
                str(source),
                "--target",
                str(target),
                "--phases",
                str(phases),
                "--interfaces",
                str(interface_evidence),
                "--expected-interfaces",
                str(expected),
            ]
        )
        return subprocess.run(
            command,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

    def test_lone_surrogate_cli_fails_bounded_in_normal_and_optimized_modes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            source = tmp / "source.json"
            surrogate_fixture = '[{"key":"GL-100","amount":"\\ud800"}]'
            source.write_text(surrogate_fixture, encoding="ascii")
            target, phases, interface_evidence, expected = self._write_cli_support_files(tmp)

            for optimized in (False, True):
                result = self._run_cli(
                    source,
                    target,
                    phases,
                    interface_evidence,
                    expected,
                    optimized,
                )
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("string is not valid UTF-8", result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_raw_invalid_utf8_cli_fails_bounded_in_normal_and_optimized_modes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            source = tmp / "source.json"
            source.write_bytes(b'[{"key":"GL-100","amount":"\xff"}]')
            target, phases, interface_evidence, expected = self._write_cli_support_files(tmp)

            for optimized in (False, True):
                result = self._run_cli(
                    source,
                    target,
                    phases,
                    interface_evidence,
                    expected,
                    optimized,
                )
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("input is not valid UTF-8", result.stderr)
                self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
