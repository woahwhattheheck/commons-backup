# SPDX-License-Identifier: Apache-2.0
"""Freeze predecessor V4 positional ABI while later V4 keys append only."""
from __future__ import annotations

import dataclasses
import inspect
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import r04_full_router as r04  # noqa: E402
from titan_runtime import Features  # noqa: E402

BASE_INSTALL_V4_PREFIX = [
    "place_delivery",
    "goose_pass_rescue",
    "b10_public_supply_order",
]
BASE_FEATURES_V4_PREFIX = [
    "r04_place_delivery",
    "r04_goose_pass_rescue",
    "r04_b10_public_supply_order",
]
LATER_INSTALL_KEYS = [
    "h3b_sheep_clip",
    "h3e_cow_feed_recycle",
    "v233_eod_service",
    "dead_sell_slot",
    "advance_slot_value",
    "eod_capacity_rescue",
    "m1_wheat_trade",
    "c5_wheat_demand",
    "s4_route12_seed_reserve",
]
LATER_FEATURE_KEYS = ["r04_" + name for name in LATER_INSTALL_KEYS]


class PredecessorPositionalAbi(unittest.TestCase):
    def test_install_preserves_predecessor_v4_positional_prefix(self):
        params = list(inspect.signature(r04.install).parameters)
        start = params.index(BASE_INSTALL_V4_PREFIX[0])
        self.assertEqual(params[start:start + len(BASE_INSTALL_V4_PREFIX)],
                         BASE_INSTALL_V4_PREFIX)
        b10 = params.index("b10_public_supply_order")
        for name in LATER_INSTALL_KEYS:
            self.assertGreater(params.index(name), b10, name)

    def test_features_preserve_predecessor_v4_positional_prefix(self):
        fields = [field.name for field in dataclasses.fields(Features)]
        start = fields.index(BASE_FEATURES_V4_PREFIX[0])
        self.assertEqual(fields[start:start + len(BASE_FEATURES_V4_PREFIX)],
                         BASE_FEATURES_V4_PREFIX)
        b10 = fields.index("r04_b10_public_supply_order")
        for name in LATER_FEATURE_KEYS:
            self.assertGreater(fields.index(name), b10, name)


if __name__ == "__main__":
    unittest.main()
