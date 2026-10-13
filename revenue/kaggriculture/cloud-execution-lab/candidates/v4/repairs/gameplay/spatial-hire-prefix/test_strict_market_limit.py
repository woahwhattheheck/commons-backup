# SPDX-License-Identifier: Apache-2.0
"""Focused scalar-custody regressions for SpatialTempo HIRE prefix transform."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import textwrap
import unittest


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "spatial_hire_prefix", HERE / "spatial_hire_prefix.py"
)
assert SPEC is not None and SPEC.loader is not None
SPATIAL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SPATIAL)


def _probe_from_transform():
    body = textwrap.indent(textwrap.dedent(SPATIAL.NEW), "    ")
    namespace = {}
    exec(
        "def probe(self, selected, route, now, end):\n"
        + body
        + "\n    return ('continued', end)\n",
        namespace,
    )
    return namespace["probe"]


class FakeSelf:
    def __init__(self, market_limit):
        self.configuration = {"maxMarketOrdersPerTurn": market_limit}


class MarketLimitCustodyTests(unittest.TestCase):
    def setUp(self):
        self.probe = _probe_from_transform()
        self.selected = {"market": [["PASS"]]}
        self.route = [{"market": [["PASS"]]} for _ in range(4)]

    def test_plain_integer_keeps_scan_live(self):
        result = self.probe(FakeSelf(10), self.selected, self.route, 0, 2)
        self.assertEqual(result, ("continued", 2))

    def test_missing_limit_uses_integer_default(self):
        owner = FakeSelf(10)
        owner.configuration = {}
        result = self.probe(owner, self.selected, self.route, 0, 2)
        self.assertEqual(result, ("continued", 2))

    def test_noninteger_limit_fails_closed_to_selected(self):
        for value in (True, False, 10.0, "10", [10], {"limit": 10}, None):
            with self.subTest(value=repr(value)):
                result = self.probe(FakeSelf(value), self.selected, self.route, 0, 2)
                self.assertIs(result, self.selected)

    def test_valid_limit_still_bounds_hire_scan(self):
        selected = {"market": [["PASS"], ["HIRE"]]}
        result = self.probe(FakeSelf(1), selected, self.route, 0, 2)
        self.assertEqual(result, ("continued", 2))
        self.assertIs(
            self.probe(FakeSelf(2), selected, self.route, 0, 2),
            selected,
        )


if __name__ == "__main__":
    unittest.main()
