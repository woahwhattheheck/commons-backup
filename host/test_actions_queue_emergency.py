from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from host.actions_queue_emergency import CANCEL_SCHEMA, build_command, orchestrate, run_one


def receipt(repo: str, *, mode: str = "dry_run", candidates: int = 4,
            accepted: int = 0, holds: int = 0) -> dict:
    return {
        "schema": CANCEL_SCHEMA, "repo": repo, "mode": mode,
        "queued_total_reported": 100, "queued_runs_observed": 100,
        "queued_inventory_complete": True,
        "initial_cancel_candidates": candidates,
        "cancel_posts_attempted": accepted, "cancel_accepted": accepted,
        "holds": holds,
    }


class FakeRunner:
    def __init__(self, data: dict | None, returncode: int = 0):
        self.data, self.returncode, self.commands = data, returncode, []

    def __call__(self, command, *, cwd, text, capture_output, check):
        self.commands.append(command)
        if self.data is not None:
            Path(command[command.index("--out") + 1]).write_text(
                json.dumps(self.data), encoding="utf-8")
        return subprocess.CompletedProcess(command, self.returncode, "", "simulated")


class EmergencyTests(unittest.TestCase):
    def test_dry_run_command_is_bounded_and_secret_free(self):
        command = build_command(
            python="python3", repo="woahwhattheheck/commons",
            receipt=Path("/tmp/r.json"), cap=5000, max_cancels=25,
            min_age_seconds=900, execute=False)
        self.assertNotIn("--execute", command)
        self.assertNotIn("TOKEN", " ".join(command).upper())
        self.assertEqual(command[command.index("--max-cancels") + 1], "25")

    def test_execute_is_explicit(self):
        command = build_command(
            python="python3", repo="woahwhattheheck/commons",
            receipt=Path("/tmp/r.json"), cap=10, max_cancels=1,
            min_age_seconds=60, execute=True)
        self.assertEqual(command[-1], "--execute")

    def test_invalid_repository_fails_closed(self):
        with self.assertRaises(ValueError):
            build_command(python="python3", repo="commons", receipt=Path("x"),
                          cap=1, max_cancels=1, min_age_seconds=0, execute=False)

    def test_hold_returncode_is_valid_when_receipt_is_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = "woahwhattheheck/commons"
            result = run_one(
                repo=repo, round_number=1, receipt=Path(tmp) / "r.json",
                checkout=Path(tmp), python="python3", cap=10,
                max_cancels=1, min_age_seconds=60, execute=False,
                runner=FakeRunner(receipt(repo, holds=1), returncode=2))
            self.assertIsNone(result["error"])
            self.assertEqual(result["holds"], 1)

    def test_missing_receipt_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_one(
                repo="woahwhattheheck/commons", round_number=1,
                receipt=Path(tmp) / "missing.json", checkout=Path(tmp),
                python="python3", cap=10, max_cancels=1,
                min_age_seconds=60, execute=False,
                runner=FakeRunner(None))
            self.assertTrue(result["error"])

    def test_dry_run_deduplicates_repositories_and_stops_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = "woahwhattheheck/commons"
            fake = FakeRunner(receipt(repo))
            summary, path = orchestrate(
                repos=(repo, repo), rounds=3, receipt_root=Path(tmp),
                run_id="case", checkout=Path(tmp), python="python3", cap=10,
                max_cancels=1, min_age_seconds=60, execute=False,
                sleep_seconds=0, runner=fake)
            self.assertEqual(summary["repos"], [repo])
            self.assertEqual(summary["stop_reason"], "DRY_RUN_COMPLETE")
            self.assertEqual(len(fake.commands), 1)
            self.assertTrue(path.exists())

    def test_execute_stops_when_nothing_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = "woahwhattheheck/commons"
            summary, _ = orchestrate(
                repos=(repo,), rounds=5, receipt_root=Path(tmp), run_id="case",
                checkout=Path(tmp), python="python3", cap=10, max_cancels=1,
                min_age_seconds=60, execute=True, sleep_seconds=0,
                runner=FakeRunner(receipt(repo, mode="execute", candidates=2)))
            self.assertEqual(summary["completed_rounds"], 1)
            self.assertEqual(summary["stop_reason"], "NO_CANCELLATIONS_ACCEPTED")


if __name__ == "__main__":
    unittest.main()
