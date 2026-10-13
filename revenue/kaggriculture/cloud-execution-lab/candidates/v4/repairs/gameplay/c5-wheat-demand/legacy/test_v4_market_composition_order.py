# SPDX-License-Identifier: Apache-2.0
"""Cross-lane V4 market composition custody.

The four market-facing V4 transforms are individually guarded, but their
persistent evidence/state makes source order part of the theorem.  Freeze the
one safe order here so future single-tree recompositions cannot silently
reintroduce self-attribution or stale-shed hazards.
"""
from __future__ import annotations

import inspect
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import r04_full_router as r04  # noqa: E402
from titan_runtime import Features  # noqa: E402


MARKET_KEYS = (
    "r04_m1_wheat_trade",
    "r04_eod_capacity_rescue",
    "r04_b10_public_supply_order",
    "r04_c5_wheat_demand",
)


class V4MarketCompositionOrder(unittest.TestCase):
    def test_outer_market_chain_is_m1_eod_b10_c5(self):
        source = inspect.getsource(r04.v3_agent)
        markers = (
            "if M1_WHEAT_TRADE:",
            "if EOD_CAPACITY_RESCUE:",
            "if B10_PUBLIC_SUPPLY_ORDER:",
            "if C5_WHEAT_DEMAND:",
        )
        positions = [source.index(marker) for marker in markers]
        self.assertEqual(positions, sorted(positions))

        calls = (
            "apply_m1_wheat_trade",
            "apply_eod_capacity_rescue",
            "apply_public_supply_order",
            "apply_c5_wheat_demand",
        )
        call_positions = [source.index(call) for call in calls]
        self.assertEqual(call_positions, sorted(call_positions))

    def test_order_is_documented_at_the_generated_seam(self):
        source = (ROOT / "r04_full_router.py").read_text(encoding="utf-8")
        self.assertIn("market composition is deliberately M1 -> EOD -> B10 -> C5", source)

    def test_all_market_keys_ship_literal_false(self):
        data = json.loads((ROOT / "TITAN-CONFIG.json").read_text(encoding="utf-8"))
        features = Features(**data)
        for key in MARKET_KEYS:
            self.assertIn(key, data)
            self.assertIs(data[key], False)
            self.assertIs(getattr(features, key), False)

    def test_b10_and_c5_remain_after_synthetic_action_producers(self):
        source = inspect.getsource(r04.v3_agent)
        # B10 persists current own SELL upper bounds for the next callback, so
        # EOD's synthetic SELL must already be present when B10 records action.
        self.assertLess(source.index("apply_eod_capacity_rescue"),
                        source.index("apply_public_supply_order"))
        # C5 persists current own WHEAT BUY upper bounds for the next callback,
        # so M1's synthetic BUY must already be present when C5 records action.
        self.assertLess(source.index("apply_m1_wheat_trade"),
                        source.index("apply_c5_wheat_demand"))


if __name__ == "__main__":
    unittest.main()
