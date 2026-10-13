# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import unittest

from route_lifecycle import audit

HERE = Path(__file__).resolve().parent
LAB = HERE.parent.parent


class RouteLifecycleTests(unittest.TestCase):
    def test_deferred_plan_never_crosses_controller_switch(self):
        report = audit(LAB)
        self.assertEqual(
            report["verdict"],
            "NO_DEFERRED_PLAN_CAN_CROSS_A_CONTROLLER_SWITCH",
        )
        self.assertEqual(
            [row["checkpoint"] for row in report["checkpoints"]],
            [226, 360, 433],
        )
        self.assertTrue(
            all(row["end"] < row["checkpoint"] for row in report["checkpoints"])
        )


if __name__ == "__main__":
    unittest.main()
