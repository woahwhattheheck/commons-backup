# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest import mock

import route_arm


class Controller:
    def __init__(self, legal=True):
        self.cur = "MAIN"
        self.legal = legal

    def _switch_ok(self, target, turn):
        return self.legal


class RouteArmTests(unittest.TestCase):
    def namespace(self):
        return {
            "DECISIONS": tuple(
                route_arm.CHECKPOINTS[key] for key in sorted(route_arm.CHECKPOINTS)
            ),
            "_feature": lambda observation, name: observation["value"],
        }

    def test_stay_restores_decisions_after_base_exception(self):
        controller = Controller()
        namespace = self.namespace()
        original = namespace["DECISIONS"]
        base = SimpleNamespace(_INSTANCE=SimpleNamespace(controller=controller))

        def explode(observation, configuration):
            self.assertNotIn(226, [row[0] for row in namespace["DECISIONS"]])
            raise RuntimeError("boom")

        base.agent = explode
        with mock.patch.object(route_arm, "_load_base", return_value=base), mock.patch.object(
            route_arm, "_producer", return_value=(controller, namespace)
        ):
            with self.assertRaisesRegex(RuntimeError, "boom"):
                route_arm._instrumented(
                    {"step": 226, "player": 0, "value": 0},
                    {},
                    mode="stay",
                    checkpoint=226,
                )
        self.assertIs(namespace["DECISIONS"], original)

    def test_force_refuses_non_prefix_legal_switch(self):
        controller = Controller(legal=False)
        namespace = self.namespace()
        instance = SimpleNamespace(controller=controller, diagnostics={"status": "completed"})
        base = SimpleNamespace(
            _INSTANCE=instance,
            agent=lambda observation, configuration: {
                "farmer": ["PASS"],
                "hands": [],
                "market": [],
            },
        )
        with mock.patch.object(route_arm, "_load_base", return_value=base), mock.patch.object(
            route_arm, "_producer", return_value=(controller, namespace)
        ):
            output = route_arm._instrumented(
                {"step": 226, "player": 0, "value": 0},
                {},
                mode="force",
                checkpoint=226,
            )
        marker = output[route_arm.DIAGNOSTIC_KEY]
        self.assertFalse(marker["override_applied"])
        self.assertEqual(marker["unavailable_reason"], "force_not_prefix_legal")
        self.assertEqual(controller.cur, "MAIN")

    def test_auto_does_not_patch_decision_table(self):
        controller = Controller()
        namespace = self.namespace()
        original = namespace["DECISIONS"]
        instance = SimpleNamespace(controller=controller, diagnostics={"status": "completed"})
        base = SimpleNamespace(
            _INSTANCE=instance,
            agent=lambda observation, configuration: {
                "farmer": ["PASS"],
                "hands": [],
                "market": [],
            },
        )
        with mock.patch.object(route_arm, "_load_base", return_value=base), mock.patch.object(
            route_arm, "_producer", return_value=(controller, namespace)
        ):
            route_arm._instrumented(
                {"step": 226, "player": 0, "value": 0},
                {},
                mode="auto",
                checkpoint=None,
            )
        self.assertIs(namespace["DECISIONS"], original)
        self.assertEqual(controller.cur, "MAIN")


if __name__ == "__main__":
    unittest.main()
