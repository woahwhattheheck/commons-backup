#!/usr/bin/env python3
"""Bounded semantic fault injection; does not claim official/Linux integration.

Run with the standard-library unittest runner when host capacity is available.
The fake checker is a subprocess, but only tests orchestration, not feasibility.
"""
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import supervisor


class CheckpointControls(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="roadef-runtime-controls-")
        self.root = Path(self.temporary.name)
        self.checker = self.root / "fake_checker.py"
        self.checker.write_text(
            "import json,sys,time\n"
            "from pathlib import Path\n"
            "p=Path(sys.argv[sys.argv.index('--srpaths')+1])\n"
            "time.sleep(0.1)\n"
            "x=json.loads(p.read_text())\n"
            "marker=p.with_suffix('.attempted')\n"
            "if x.get('fail_once') and not marker.exists():\n"
            " marker.write_text('attempted')\n"
            " sys.exit(7)\n"
            "print(json.dumps({'valid':x.get('valid',True),'total_cost':x.get('cost',0),"
            "'saturations':[{'t':0,'from':1,'to':2,'sat':x['score']}]}))\n",
            encoding="utf-8")
        self.environment = patch.dict(os.environ, {
            "PORTFOLIO_CHECKER": str(self.checker), "PORTFOLIO_SECONDS": "15",
            "PORTFOLIO_ARTIFACTS": str(self.root)})
        self.environment.start()
        self.inputs = [self.root / name for name in ("network.json", "traffic.json", "scenario.json")]
        for path in self.inputs:
            path.write_text("{}", encoding="utf-8")
        self.output = self.root / "solution with spaces.json"
        self.engine = supervisor.Supervisor(self.inputs, self.output)
        self.engine.pending_baseline = None
        real_launch = supervisor.launch

        def python_checker(command, env, stdout, stderr):
            return real_launch([sys.executable, *command], env, stdout, stderr)

        self.launch_patch = patch.object(supervisor, "launch", python_checker)
        self.launch_patch.start()

    def tearDown(self):
        if self.engine.check is not None:
            supervisor.stop_process(self.engine.check["process"], force=True)
            self.engine.check["process"].wait(timeout=2)
            self.engine.check["stdout"].close()
            self.engine.check["stderr"].close()
        self.launch_patch.stop()
        self.environment.stop()
        self.temporary.cleanup()

    def evaluate(self, value, mutate_after_snapshot=None):
        path = self.root / "lane.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        self.engine.enqueue(path, "synthetic_lane")
        if mutate_after_snapshot is not None:
            path.write_text(json.dumps(mutate_after_snapshot), encoding="utf-8")
        deadline = time.monotonic() + 5
        while self.engine.check is not None and time.monotonic() < deadline:
            self.engine.poll_checker()
            self.engine.schedule_check()
            time.sleep(0.02)
        self.assertIsNone(self.engine.check, "Synthetic checker exceeded bounded test timeout")

    def test_snapshot_tie_invalid_and_regression(self):
        self.evaluate({"score": 9, "cost": 90}, mutate_after_snapshot={"score": 1, "cost": 0})
        self.assertEqual(json.loads(self.output.read_text())["score"], 9,
                         "The selected bytes must equal those checked before concurrent source mutation")
        self.evaluate({"score": 8, "cost": 90})
        chosen = self.output.read_bytes()
        self.evaluate({"score": 8, "cost": 1})
        self.assertEqual(self.output.read_bytes(), chosen, "Lower cost must not break an objective tie")
        self.evaluate({"score": 1, "valid": False})
        self.assertEqual(self.output.read_bytes(), chosen, "Infeasible results must not replace the incumbent")
        self.evaluate({"score": 10, "cost": 0})
        self.assertEqual(self.output.read_bytes(), chosen, "Worse vectors must not replace the incumbent")
        self.assertEqual(self.engine.best["vector"][0], 8)

    def test_exited_lane_retries_same_snapshot_after_checker_crash(self):
        path = self.root / "finished-lane.json"
        original = {"score": 3, "fail_once": True}
        path.write_text(json.dumps(original), encoding="utf-8")
        lane = {"name": "finished", "process": None, "solution": path, "executable": self.checker,
                "last_digest": None, "next_check": 0, "final_checked": False,
                "retry_snapshot": None, "read_failures": 0}
        self.engine.lanes = [lane]
        self.engine.schedule_check()
        deadline = time.monotonic() + 5
        while not lane["final_checked"] and time.monotonic() < deadline:
            self.engine.poll_checker()
            self.engine.schedule_check()
            time.sleep(0.02)
        self.assertTrue(lane["final_checked"], "Exited lane's frozen output was not retried to completion")
        self.assertEqual(json.loads(self.output.read_text()), original)
        self.assertEqual(sum(event["event"] == "check_retry_queued" for event in self.engine.events), 1)

    def test_signal_during_drain_clamps_deadline_once(self):
        self.engine.stopping_at = 100.0
        self.engine.deadline = 200.0
        self.engine.signal_received = signal.SIGTERM
        with patch.object(supervisor.time, "monotonic", return_value=101.0):
            self.engine.begin_stop("signal")
        self.assertEqual(self.engine.deadline, 108.0)
        with patch.object(supervisor.time, "monotonic", return_value=104.0):
            self.engine.begin_stop("signal")
        self.assertEqual(self.engine.deadline, 108.0, "Repeated TERM must not extend the shutdown deadline")


if __name__ == "__main__":
    unittest.main()
