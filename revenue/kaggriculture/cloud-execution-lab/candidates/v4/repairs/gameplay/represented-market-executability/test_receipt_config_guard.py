#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "represented_physical_materializer",
    HERE / "materialize_represented_physical_transition.py",
)
carrier = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(carrier)


class ReceiptConfigGuardTests(unittest.TestCase):
    def test_market_cap_must_be_exact_int_before_prefix_coercion(self):
        self.assertIn(
            "market_cap_value=config.get('maxMarketOrdersPerTurn',10)",
            carrier.STRICT_HEAD_NEW,
        )
        self.assertIn(
            "if type(market_cap_value) is not int:\n            return lambda _plan: False",
            carrier.STRICT_HEAD_NEW,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
