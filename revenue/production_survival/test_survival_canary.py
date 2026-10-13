import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from survival_canary import run_canary


class SurvivalCanaryTest(unittest.TestCase):
    def test_forced_failure_recovers_exactly_once_and_replay_is_stable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            intake = root / "intake.json"
            state = root / "state.json"
            receipt = root / "receipt.json"
            intake.write_text(
                json.dumps(
                    {
                        "sentence": (
                            "My agent should record one customer action, but in production "
                            "it retries after a timeout and records the action twice."
                        )
                    }
                ),
                encoding="utf-8",
            )

            first = run_canary(intake, state, receipt)
            second = run_canary(intake, state, receipt)

            self.assertEqual(first["status"], "LANDED")
            self.assertEqual(first["canary"]["external_effect_count"], 1)
            self.assertEqual(first["canary"]["attempts"], 2)
            self.assertEqual(first["canary"]["recovery_result"], "DEDUPED")
            self.assertTrue(first["acceptance"]["replay_deduped"])
            self.assertEqual(
                first["contract"]["window"]["kind"],
                "PUBLIC_EXAMPLE_NOT_CUSTOMER_SLA",
            )
            self.assertEqual(
                first["artifacts"]["schema"],
                "revenue/production_survival/receipt.schema.json",
            )
            self.assertEqual(second["canary"], first["canary"])

    def test_separate_process_resumes_persisted_failure_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            intake = root / "intake.json"
            state = root / "state.json"
            receipt = root / "receipt.json"
            intake.write_text(
                json.dumps(
                    {
                        "sentence": (
                            "My agent should record one action, but a timeout after the "
                            "effect makes the worker crash before its done checkpoint."
                        )
                    }
                ),
                encoding="utf-8",
            )
            script = Path(__file__).resolve().parent / "survival_canary.py"
            base_command = [
                sys.executable,
                str(script),
                "--intake",
                str(intake),
                "--state",
                str(state),
                "--receipt",
                str(receipt),
            ]

            crashed = subprocess.run(
                base_command + ["--halt-after-injected-failure"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(crashed.returncode, 75)
            persisted = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(persisted["phase"], "EFFECT_OBSERVED_BEFORE_CHECKPOINT")
            self.assertEqual(len(persisted["effects"]), 1)

            resumed = subprocess.run(
                base_command,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            landed = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(landed["status"], "LANDED")
            self.assertEqual(landed["canary"]["attempts"], 2)
            self.assertEqual(landed["canary"]["dedupe_hits"], 1)
            self.assertEqual(landed["canary"]["external_effect_count"], 1)
            self.assertEqual(landed["canary"]["final_phase"], "DONE")


if __name__ == "__main__":
    unittest.main()
