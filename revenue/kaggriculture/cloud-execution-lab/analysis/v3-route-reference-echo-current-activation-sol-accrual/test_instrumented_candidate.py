# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from types import SimpleNamespace
import unittest

import instrumented_candidate as instrumented


class EvidenceHookTests(unittest.TestCase):
    def setUp(self):
        self.original_main = instrumented._SOURCE._CANONICAL_MAIN
        instrumented._LAST_TOKEN = None

    def tearDown(self):
        instrumented._SOURCE._CANONICAL_MAIN = self.original_main
        instrumented._LAST_TOKEN = None

    def install(self, report):
        consumer = SimpleNamespace(diagnostics={"route_reference_echo": report})
        instance = SimpleNamespace(
            consumer=consumer,
            controller=SimpleNamespace(cur=2),
            diagnostics={"status": "completed"},
        )
        instrumented._SOURCE._CANONICAL_MAIN = SimpleNamespace(_INSTANCE=instance)

    def test_affirmative_report_is_bounded_and_deduplicated(self):
        self.install({
            "operation": "titan-v3-route-reference-echo-20260909-sol-accrual-01",
            "status": "NORMALIZED", "changed": True, "now": 17,
            "item": "WHEAT", "removed_quantity": 2,
            "canonical_quantity": 4, "scheduler_owned_quantity": 2,
        })
        first = instrumented.route_reference_echo_evidence()
        self.assertEqual(first["controller_route"], 2)
        self.assertEqual(first["report"]["removed_quantity"], 2)
        self.assertIsNone(instrumented.route_reference_echo_evidence())

    def test_nonactivation_is_not_emitted(self):
        self.install({
            "operation": "titan-v3-route-reference-echo-20260909-sol-accrual-01",
            "status": "NO_PERSISTED_FUTURE", "changed": False, "now": 17,
        })
        self.assertIsNone(instrumented.route_reference_echo_evidence())

    def test_affirmative_zero_removal_fails_closed(self):
        self.install({
            "operation": "titan-v3-route-reference-echo-20260909-sol-accrual-01",
            "status": "NORMALIZED", "changed": True, "now": 17,
            "removed_quantity": 0,
        })
        with self.assertRaises(RuntimeError):
            instrumented.route_reference_echo_evidence()


if __name__ == "__main__":
    unittest.main()
