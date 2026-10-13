"""Regression gate for evaluator worker optimization-mode inheritance.

Run this file with the parent interpreter in modes 0, 1, and 2.  The Actor
must launch its child in the same mode, attest that mode in the ready frame,
and remain usable for a normal action RPC.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
EVALUATOR = HERE / "evaluate.py"


def load_evaluator():
    spec = importlib.util.spec_from_file_location("titan_v4_evaluator_child_mode_test", EVALUATOR)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load evaluator from {EVALUATOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ChildOptimizationModeInheritanceTest(unittest.TestCase):
    def test_child_matches_parent_mode_and_stays_usable(self):
        evaluator = load_evaluator()
        with tempfile.TemporaryDirectory(prefix="titan-v4-child-mode-test-") as directory:
            agent = Path(directory) / "agent.py"
            agent.write_text("def agent(observation, configuration=None):\n    return {}\n", encoding="utf-8")
            actor = evaluator.Actor(str(agent), HERE, EVALUATOR, 20260915, startup_timeout=5.0)
            try:
                self.assertEqual(actor.ready.get("kind"), "ready", actor.ready)
                self.assertIs(type(actor.ready.get("python_optimize")), int)
                self.assertEqual(actor.ready["python_optimize"], sys.flags.optimize)
                self.assertIs(type(actor.ready.get("python_debug")), bool)
                self.assertEqual(actor.ready["python_debug"], sys.flags.optimize == 0)

                report = actor.report()
                self.assertEqual(report.get("python_optimize"), sys.flags.optimize)
                self.assertEqual(report.get("python_debug"), sys.flags.optimize == 0)

                response = actor.act({}, {}, timeout=2.0)
                self.assertEqual(response.get("kind"), "action", response)
                self.assertEqual(response.get("action"), {})
            finally:
                actor.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
