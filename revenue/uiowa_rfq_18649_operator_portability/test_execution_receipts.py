"""Independent offline fault-receipt contracts for UIOWA-100.

Fixtures are explicitly synthetic stand-ins. Passing these tests is NOT real
workshare/workbench acceptance, hosted CI, or engagement completion.
ZZ-RIVET-9H6P / GPT-6 Astra Pro. Existing builder: COPPERFINCH-8D42.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

TARGET = Path(os.environ.get("UIOWA100_TARGET", str(Path(__file__).with_name("uiowa100_portability.py"))))
SPEC = importlib.util.spec_from_file_location("uiowa100_receipt_review_subject", TARGET)
p = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p)
REVISION = "a" * 40


def fixture_report():
    return {
        "mode": "UNTRUSTED_INSPECTION", "aggregate_state": "HOLD_TRUSTED_AUTHORITY_REQUIRED",
        "trust": {"authority_root_supplied_out_of_band": False,
                  "current_evidence_review_authority": False},
        "external_authority": {"buyer_contact": False, "revenue": False},
        "assessment_matrix": [
            {"group": group, "dimension": dimension, "status": "HOLD_MISSING_EVIDENCE",
             "maturity": None, "confidence_bp": None}
            for group in ("ESS", "RIS", "IAM") for dimension in ("SDLC", "SEC", "OPS", "AI")],
        "receipt_sha256": "b" * 64,
    }


class ExecutionReceiptTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="uiowa100-rivet-faults-")
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.root = self.home / "source"
        self.root.mkdir()
        for name in p.SEEDS:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("# explicit harmless stand-in\n" if name.endswith(".py") else "{}\n",
                              encoding="utf-8")

    def packaged(self):
        p.pack(self.root, self.home / "kit.zip", REVISION)
        destination = self.home / "kit"
        p.unpack(self.home / "kit.zip", destination)
        return destination

    def runnable_standins(self):
        (self.root / p.SELF).write_bytes(TARGET.read_bytes())
        (self.root / p.WORKSHARE / "fixtures/synthetic_packet.json").write_bytes(p.canonical(fixture_report()))
        (self.root / p.WORKSHARE / "compiler.py").write_text(
            "import sys\nfrom pathlib import Path\n"
            "if sys.argv[1] == 'compile':\n"
            "    Path(sys.argv[4]).write_bytes(Path(sys.argv[2]).read_bytes())\n"
            "elif sys.argv[1] == 'verify':\n"
            "    print('UNTRUSTED_INTEGRITY_ONLY ' + 'b' * 64)\n"
            "elif sys.argv[1] == 'render':\n"
            "    Path(sys.argv[3]).write_text('# SYNTHETIC STAND-IN ONLY\\n')\n", encoding="utf-8")
        (self.root / p.WORKBENCH / "server.py").write_text(
            "class CompilerAdapter:\n"
            "    def inspect(self, candidate, authority):\n"
            "        return candidate\n", encoding="utf-8")

    def failed_rehearsal(self, effect, nested=False):
        root = self.packaged()
        output = root / "sample-run" if nested else self.home / "failed-run"
        with patch.object(p.subprocess, "run", side_effect=effect), self.assertRaises(p.PortabilityError):
            p.rehearse(root, output)
        receipt = json.loads((output / "receipt.json").read_text())
        self.assertEqual(receipt["state"], "FAIL")
        self.assertNotIn("outputs", receipt)
        self.assertEqual(receipt["engagement_completion"], "NOT_ESTABLISHED")
        self.assertEqual(receipt["browser_acceptance"], "NOT_RUN")
        return receipt, output

    def failed_acceptance(self, effect):
        output = self.home / "acceptance-run"
        with patch.object(p.subprocess, "run", side_effect=effect):
            with self.assertRaises((p.PortabilityError, subprocess.SubprocessError, OSError)):
                p.acceptance(self.root, output, REVISION)
        self.assertFalse((output / "acceptance.json").exists())
        failure_path = output / "acceptance-failure.json"
        self.assertTrue(failure_path.is_file(), "outer failure must have a durable diagnostic receipt")
        receipt = json.loads(failure_path.read_text())
        self.assertEqual(receipt["state"], "FAIL")
        self.assertEqual(receipt["engagement_completion"], "NOT_ESTABLISHED")
        return receipt

    def test_first_timeout_is_recorded_with_partial_output(self):
        receipt, _ = self.failed_rehearsal(subprocess.TimeoutExpired(
            ["python3", "compiler.py"], 60, output=b"compile progress\n", stderr=b"still working\n"))
        self.assertEqual(len(receipt["commands"]), 1)
        row = receipt["commands"][0]
        self.assertEqual(row["step"], "compiler_compile")
        self.assertEqual(row["state"], "TIMED_OUT")
        self.assertIsNone(row["exit_code"])
        self.assertEqual(row["timeout_s"], 60)
        self.assertEqual(row["stdout"], "compile progress\n")
        self.assertEqual(row["stderr"], "still working\n")

    def test_later_timeout_keeps_the_completed_command(self):
        first = subprocess.CompletedProcess(["python3"], 0, "completed compile\n", "")
        receipt, _ = self.failed_rehearsal([
            first, subprocess.TimeoutExpired(["python3", "verify"], 60, output=b"verify progress")])
        self.assertEqual(len(receipt["commands"]), 2)
        first_row, last_row = receipt["commands"]
        self.assertEqual(first_row["state"], "EXITED")
        self.assertEqual(first_row["exit_code"], 0)
        self.assertEqual(first_row["stdout"], "completed compile\n")
        self.assertEqual(last_row["step"], "compiler_verify")
        self.assertEqual(last_row["state"], "TIMED_OUT")

    def test_timeout_bytes_are_preserved_losslessly(self):
        raw = b"progress\xff\x00\n"
        receipt, _ = self.failed_rehearsal(subprocess.TimeoutExpired(
            ["python3"], 60, output=raw, stderr=b"error\xfe"))
        self.assertEqual(len(receipt["commands"]), 1)
        row = receipt["commands"][0]
        self.assertEqual(bytes.fromhex(row["stdout_bytes_hex"]), raw)
        self.assertEqual(bytes.fromhex(row["stderr_bytes_hex"]), b"error\xfe")
        self.assertIn("\\xff", row["stdout"])

    def test_timeout_without_output_does_not_invent_success(self):
        receipt, _ = self.failed_rehearsal(subprocess.TimeoutExpired(["python3"], 60))
        self.assertEqual(len(receipt["commands"]), 1)
        row = receipt["commands"][0]
        self.assertIsNone(row["exit_code"])
        self.assertEqual((row["stdout"], row["stderr"]), ("", ""))
        self.assertNotIn("stdout_bytes_hex", row)

    def test_launch_error_is_distinct_from_child_exit(self):
        receipt, _ = self.failed_rehearsal(FileNotFoundError("synthetic missing executable"))
        self.assertEqual(len(receipt["commands"]), 1)
        row = receipt["commands"][0]
        self.assertEqual(row["state"], "LAUNCH_ERROR")
        self.assertEqual(row["error_type"], "FileNotFoundError")
        self.assertIsNone(row["exit_code"])

    def test_permission_error_is_not_called_a_timeout(self):
        receipt, _ = self.failed_rehearsal(PermissionError("synthetic execution denied"))
        self.assertEqual(len(receipt["commands"]), 1)
        row = receipt["commands"][0]
        self.assertEqual(row["state"], "LAUNCH_ERROR")
        self.assertEqual(row["error_type"], "PermissionError")
        self.assertNotIn("timeout_s", row)

    def test_normal_nonzero_exit_preserves_real_returncode(self):
        failed = subprocess.CompletedProcess(["python3"], 7, "before failure", "fixture rejected")
        receipt, output = self.failed_rehearsal([failed])
        row = receipt["commands"][0]
        self.assertEqual(row["state"], "EXITED")
        self.assertEqual(row["exit_code"], 7)
        self.assertEqual((row["stdout"], row["stderr"]), ("before failure", "fixture rejected"))
        self.assertIn("exit 7", (output / "REHEARSAL.md").read_text())

    def test_negative_signal_exit_is_not_replaced_with_zero(self):
        receipt, _ = self.failed_rehearsal([subprocess.CompletedProcess(["python3"], -15, "", "")])
        row = receipt["commands"][0]
        self.assertEqual(row["state"], "EXITED")
        self.assertEqual(row["exit_code"], -15)

    def test_nested_output_uses_output_placeholder(self):
        receipt, _ = self.failed_rehearsal([subprocess.CompletedProcess(["python3"], 2, "", "stop")], nested=True)
        self.assertEqual(receipt["commands"][0]["argv"][-1], "{OUT}/report.json")

    def test_generic_subprocess_error_retains_attempt(self):
        receipt, _ = self.failed_rehearsal(subprocess.SubprocessError("synthetic runner transport failure"))
        self.assertEqual(len(receipt["commands"]), 1)
        self.assertEqual(receipt["commands"][0]["state"], "PROCESS_ERROR")
        self.assertEqual(receipt["commands"][0]["error_type"], "SubprocessError")

    def test_launch_failure_after_progress_keeps_both_rows(self):
        receipt, _ = self.failed_rehearsal([
            subprocess.CompletedProcess(["python3"], 0, "compile done", ""),
            PermissionError("synthetic next command denied")])
        self.assertEqual(len(receipt["commands"]), 2)
        self.assertEqual(receipt["commands"][0]["exit_code"], 0)
        self.assertEqual(receipt["commands"][1]["state"], "LAUNCH_ERROR")
        self.assertEqual(receipt["commands"][1]["step"], "compiler_verify")

    def test_success_path_stays_four_non_authorizing_commands(self):
        self.runnable_standins()
        root = self.packaged()
        receipt = p.rehearse(root, self.home / "success")
        self.assertEqual(receipt["state"], "PASS_PORTABLE_SYNTHETIC_REHEARSAL")
        self.assertEqual(len(receipt["commands"]), 4)
        self.assertTrue(all(row.get("state") == "EXITED" and row["exit_code"] == 0 for row in receipt["commands"]))
        self.assertEqual(receipt["inspection"]["aggregate_state"], "HOLD_TRUSTED_AUTHORITY_REQUIRED")
        self.assertEqual(receipt["browser_acceptance"], "NOT_RUN")

    def test_acceptance_timeout_retains_packaged_runner_attempt(self):
        receipt = self.failed_acceptance(subprocess.TimeoutExpired(
            ["python3", "packaged-runner"], 300, output=b"outer progress", stderr=b"outer stalled"))
        row = receipt["packaged_runner_invocations"][0]
        self.assertEqual(row["operator"], "operator-one")
        self.assertEqual(row["state"], "TIMED_OUT")
        self.assertEqual(row["timeout_s"], 300)
        self.assertEqual((row["stdout"], row["stderr"]), ("outer progress", "outer stalled"))
        self.assertIsNone(row["exit_code"])

    def test_acceptance_nonzero_exit_retains_stderr(self):
        receipt = self.failed_acceptance([subprocess.CompletedProcess(["python3"], 9, "partial receipt", "outer error")])
        row = receipt["packaged_runner_invocations"][0]
        self.assertEqual(row["exit_code"], 9)
        self.assertEqual((row["stdout"], row["stderr"]), ("partial receipt", "outer error"))

    def test_acceptance_launch_error_has_no_success_receipt(self):
        receipt = self.failed_acceptance(FileNotFoundError("synthetic outer interpreter unavailable"))
        row = receipt["packaged_runner_invocations"][0]
        self.assertEqual(row["state"], "LAUNCH_ERROR")
        self.assertIsNone(row["exit_code"])

    def test_acceptance_pack_failure_is_not_a_command_launch(self):
        (self.root / p.WORKBENCH / "app.js").unlink()
        receipt = self.failed_acceptance([])
        self.assertEqual(receipt["stage"], "PACKAGING")
        self.assertEqual(receipt["packaged_runner_invocations"], [])

    def test_successful_acceptance_has_no_failure_artifact(self):
        self.runnable_standins()
        output = self.home / "acceptance-success"
        result = p.acceptance(self.root, output, REVISION)
        self.assertEqual(result["state"], "PASS_TWO_OPERATOR_REPRODUCTION")
        self.assertFalse((output / "acceptance-failure.json").exists())
        self.assertEqual(len(result["packaged_runner_invocations"]), 2)
        self.assertTrue(all(row.get("state") == "EXITED" for row in result["packaged_runner_invocations"]))
        self.assertEqual(result["commands_per_operator"], 4)

    def test_ordinary_failure_is_not_left_running(self):
        receipt, output = self.failed_rehearsal(subprocess.TimeoutExpired(["python3"], 60))
        self.assertEqual(receipt["state"], "FAIL")
        self.assertNotIn("RUNNING", (output / "REHEARSAL.md").read_text())


if __name__ == "__main__":
    unittest.main()
