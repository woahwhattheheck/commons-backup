# SPDX-License-Identifier: Apache-2.0
"""V3.1 shipped R04 lanes: H4 `r04_strawberry_topup` and rival-gated L3 `r04_no_late_sale_advance`.

    python -m unittest -v checks/test_v31_shipped_keys.py

Both keys ship on in TITAN-CONFIG.json and act only inside the R04 whole-turn delegate, like
`r04_sale_fertilizer` and `r04_cattle_early`: with every route key off the canonical runtime
path is untouched. TitanAgent passes both to r04_full_router.install(); v3_agent() calls the
H4 top-up first after the policy only while its flag is on. Standard library only.
"""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import r04_full_router as r04  # noqa: E402
from titan_runtime import Features, TitanAgent  # noqa: E402

CONFIG = {"episodeSteps": 720, "turnsPerDay": 24, "boardSize": 10, "shedCapacity": 100,
          "maxMarketOrdersPerTurn": 10, "farmHandCostMult": 1}


def synthetic_observation(step):
    tiles = [["LOCKED"] * 10 for _ in range(10)]
    for y in range(3, 7):
        for x in range(3, 7):
            tiles[y][x] = {"kind": "SOIL"}
    farm = {"tiles": tiles, "farmer": [4, 4], "hands": [], "money": 1000,
            "unlocked_quadrants": ["NW"], "hires_today": 0}
    return {"step": step, "day": step // 24, "hour": step % 24, "player": 0,
            "farms": [farm, copy.deepcopy(farm)],
            "private": {"inventories": [{}], "shed": {"WHEAT": 5}},
            "market": {"prices": {product: 10 for product in r04.PRODUCTS}},
            "town": {"unlocked_shops": ["BAKERY", "YARN_STORE"]}}


def reset():
    r04.NO_LATE_SALE_ADVANCE = False
    r04.NO_LATE_SALE_ADVANCE_STEP = 648
    r04.STRAWBERRY_TOPUP = False
    r04.ROW_SHED = False
    r04.SALE_HORIZON = 8
    r04.OPEN_ROUNDTRIP = 0
    r04.ROW_ORDER = False
    r04.EVENING_FLUSH = False
    r04.SALE_EXCLUDED = ("WHEAT", "FERTILIZER")
    r04._V231_EARLY = False
    r04._RIVAL_TAPE.update(same=0, seen=0, last=-1, decision=None, valid=True)


class ShippedKeys(unittest.TestCase):
    def tearDown(self):
        reset()

    def test_both_keys_ship_on(self):
        data = json.loads((ROOT / "TITAN-CONFIG.json").read_text(encoding="utf-8"))
        self.assertIs(data["r04_strawberry_topup"], True)
        self.assertIs(data["r04_no_late_sale_advance"], True)
        self.assertEqual(data["r04_no_late_sale_advance_step"], 648)
        features = Features(**data)
        self.assertIs(features.r04_strawberry_topup, True)
        self.assertIs(features.r04_no_late_sale_advance, True)

    def test_canonical_path_untouched_with_route_keys_off(self):
        self.assertFalse(TitanAgent(Features())._v3_active())
        self.assertTrue(TitanAgent(Features(r04_sale_window=True))._v3_active())

    def test_titan_passes_both_keys_to_the_router(self):
        for on in (True, False):
            agent = TitanAgent(Features(r04_sale_window=True, r04_strawberry_topup=on,
                                        r04_no_late_sale_advance=on))
            agent.act(synthetic_observation(0), dict(CONFIG))
            self.assertIs(r04.STRAWBERRY_TOPUP, on)
            self.assertIs(r04.NO_LATE_SALE_ADVANCE, on)
            self.assertIs(agent.diagnostics["strawberry_topup"], on)
            self.assertIs(agent.diagnostics["no_late_sale_advance"], on)

    def test_h4_runs_only_while_its_flag_is_on(self):
        calls = []
        saved = (r04.POLICY_AGENT, r04._strawberry_topup)
        try:
            r04.POLICY_AGENT = lambda obs, cfg=None: {"farmer": ["PASS"], "hands": [], "market": []}
            r04._strawberry_topup = lambda obs, action: calls.append(obs["step"]) or action
            r04.install(None, 8, 0, False, False, strawberry_topup=False)
            r04.v3_agent(synthetic_observation(300), dict(CONFIG))
            self.assertEqual(calls, [])
            r04.install(None, 8, 0, False, False, strawberry_topup=True)
            r04.v3_agent(synthetic_observation(301), dict(CONFIG))
            self.assertEqual(calls, [301])
        finally:
            r04.POLICY_AGENT, r04._strawberry_topup = saved


if __name__ == "__main__":
    unittest.main()
