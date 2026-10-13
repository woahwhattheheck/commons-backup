# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

import test_worker_reset_deterministic as deterministic

LAB = Path(__file__).resolve().parent
WORKFLOW = LAB.parents[2] / ".github/workflows/titan-reset-invariance.yml"


class DeterministicResetOracleContracts(unittest.TestCase):
    def test_timer_patch_is_test_only_no_trace_and_restorable(self):
        if str(LAB) not in sys.path:
            sys.path.insert(0, str(LAB))
        import titan_runtime

        deadline = titan_runtime.deadline
        original = deadline._DeadlineTimer
        before_trace = sys.gettrace()
        try:
            returned = deterministic.install_deterministic_deadline(LAB)
            self.assertIs(returned, original)
            patched = deadline._DeadlineTimer
            self.assertTrue(getattr(patched, "_titan_reset_deterministic_oracle", False))
            timer = patched(0.000001)
            with timer:
                self.assertIs(sys.gettrace(), before_trace)
                self.assertIsNone(deadline._ACTIVE_TIMER.get())
            self.assertIs(sys.gettrace(), before_trace)
            self.assertIsNone(deadline._ACTIVE_TIMER.get())
        finally:
            deadline._DeadlineTimer = original

    def test_isolated_launcher_can_import_retained_sibling_harness(self):
        completed = subprocess.run(
            [sys.executable, "-I", str(deterministic.HERE), "--help"],
            cwd=LAB.parent,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            0,
            msg=f"stdout={completed.stdout}\nstderr={completed.stderr}",
        )
        self.assertIn("--worker", completed.stdout)

    def test_production_source_is_not_rewritten_by_oracle(self):
        source = (LAB / "main.py").read_text(encoding="utf-8")
        self.assertIn("timer = deadline._DeadlineTimer(remaining)", source)
        deadline_source = (
            LAB / "reference/titan-current/deadline_adapter.py"
        ).read_text(encoding="utf-8")
        self.assertIn("sys.settrace(trace)", deadline_source)
        self.assertIn("time.monotonic() >= self.own_at", deadline_source)

    def test_workflow_uses_deterministic_oracle_for_both_reset_proofs(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("test_worker_reset_deterministic.py", source)
        self.assertIn(
            'python3 -I "$LAB/test_worker_reset_deterministic.py" --worker',
            source,
        )
        self.assertIn(
            "python3 -B revenue/kaggriculture/cloud-execution-lab/test_worker_reset_deterministic.py",
            source,
        )
        self.assertIn("test_reset_invariance_deterministic_oracle.py", source)

    def test_original_reset_oracle_still_owns_state_projection(self):
        import test_worker_reset as reset

        self.assertIn("action_sha256", reset._IDENTITY_KEYS)
        self.assertIn("rewards", reset._IDENTITY_KEYS)
        self.assertIn("singleton_replaced", reset._IDENTITY_KEYS)
        self.assertNotIn("within_episode_instance_discards", reset._IDENTITY_KEYS)


if __name__ == "__main__":
    unittest.main()
