# SPDX-License-Identifier: Apache-2.0
"""Strict default-OFF activation boundary for the A4 second-melon lane."""
from __future__ import annotations

import unittest

import a4_second_melons as a4


class StrictEnableTests(unittest.TestCase):
    def setUp(self):
        a4.reset()

    def tearDown(self):
        a4.reset()

    def test_truthy_non_bool_enable_values_fail_closed_before_input_access(self):
        poisons = (1, 1.0, "false", [True], {"enabled": True})
        for poison in poisons:
            with self.subTest(enabled=repr(poison)):
                a4.reset()
                action = {"farmer": ["PASS"], "hands": [], "market": []}
                out = a4.apply_a4(None, action, enabled=poison)
                self.assertIs(out, action)
                self.assertFalse(a4.REPORT["enabled"])
                self.assertFalse(a4._STATES)

    def test_literal_true_remains_the_only_armed_value(self):
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        a4.apply_a4(None, action, enabled=True)
        self.assertTrue(a4.REPORT["enabled"])


if __name__ == "__main__":
    unittest.main()
