# SPDX-License-Identifier: Apache-2.0
"""Focused exact-enable custody regressions for route-12 seed reserve."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest import mock


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "s4_seed_reserve", HERE / "r04_s4_route12_seed_reserve.py"
)
assert SPEC is not None and SPEC.loader is not None
S4 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(S4)


class StrictEnableCustodyTests(unittest.TestCase):
    def setUp(self):
        self.action = {"farmer": ["PASS"], "hands": [], "market": []}
        self.observation = {"step": 212}
        S4.REPORT["probes"] = 0
        self.fake_router = types.ModuleType("r04_full_router")

    def _call(self, enabled):
        with mock.patch.dict(sys.modules, {"r04_full_router": self.fake_router}):
            with mock.patch.object(S4, "_purchase_quantity", return_value=None):
                return S4.apply_route12_seed_reserve(
                    self.observation, self.action, enabled=enabled
                )

    def test_truthy_nonbool_tokens_stay_off(self):
        tokens = (1, "false", "true", (1,), [1], {"enabled": True}, object())
        for token in tokens:
            with self.subTest(token=repr(token)):
                before = S4.REPORT["probes"]
                result = self._call(token)
                self.assertIs(result, self.action)
                self.assertEqual(S4.REPORT["probes"], before)

    def test_falsey_nontrue_tokens_stay_off(self):
        for token in (False, None, 0, "", (), [], {}):
            with self.subTest(token=repr(token)):
                before = S4.REPORT["probes"]
                result = self._call(token)
                self.assertIs(result, self.action)
                self.assertEqual(S4.REPORT["probes"], before)

    def test_literal_true_enters_probe_path(self):
        result = self._call(True)
        self.assertIs(result, self.action)
        self.assertEqual(S4.REPORT["probes"], 1)


if __name__ == "__main__":
    unittest.main()
