# SPDX-License-Identifier: Apache-2.0
"""V3.1 lanes by ASTRA · GPT-5.6 SOL around the whole R04 agent: B11, B9 and H3c.

    python -m unittest -v checks/test_v31_astra_lanes.py

Keys `r04_mirror_horizon` (B11, b11_mirror_horizon.py), `r04_terminal_fertilizer` (B9,
b9_terminal_fertilizer.py) and `r04_goose_rescue` (H3c, h3c_goose_eod_cap_rescue.py) act only
inside the R04 delegate. Covers the shipped config, the canonical invariant, TitanAgent wiring,
flag-off identity of v3_agent(), and each lane at its seam: B11 scopes the sale horizon to one
callback after eight exact mirrors, B9 collects terminal fertilizer on a PASS beside the shed and
trails SELL FERTILIZER at 718, H3c turns a clipping hour-23 goose collection into HARVEST.
Standard library only.
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

import b11_mirror_horizon as b11  # noqa: E402
import r04_full_router as r04  # noqa: E402
from titan_runtime import Features, TitanAgent  # noqa: E402

CONFIG = {"episodeSteps": 720, "turnsPerDay": 24, "boardSize": 10, "shedCapacity": 100,
          "maxMarketOrdersPerTurn": 10, "farmHandCostMult": 1}

# Shipped values of the three keys in TITAN-CONFIG.json and in Features().
SHIPPED = {"r04_mirror_horizon": False, "r04_terminal_fertilizer": True, "r04_goose_rescue": True}


def farm(tiles=None, farmer=(4, 4), hands=(), hires=0):
    # The engine's empty unlocked tile is None (there is no SOIL kind).
    grid = [[None if x < 5 and y < 5 else "LOCKED" for x in range(10)] for y in range(10)]
    for (x, y), tile in (tiles or {}).items():
        grid[y][x] = tile
    return {"tiles": grid, "farmer": list(farmer), "hands": [list(h) for h in hands], "money": 1000,
            "unlocked_quadrants": ["NW"], "hires_today": hires}


def observation(step, own=None, rival=None, inventories=None, shed=None):
    own = own or farm()
    rival = rival if rival is not None else copy.deepcopy(own)
    return {"step": step, "day": step // 24, "hour": step % 24, "player": 0,
            "farms": [own, rival],
            "private": {"inventories": inventories if inventories is not None else [{}],
                        "shed": shed if shed is not None else {"WHEAT": 5}, "seeds": {}},
            "market": {"prices": {product: 40 for product in r04.PRODUCTS}, "inventory": {}},
            "town": {"unlocked_shops": ["BAKERY", "YARN_STORE"]}}


def cow(fertilizer=True):
    return {"kind": "PASTURE", "animal": "COW", "placed_day": 3, "yield_units": 1,
            "consecutive_unfed": 0, "fed_today": True, "cared_today": True,
            "fertilizer_available": fertilizer, "pending_care_bonus": 0}


def goose(units=4, fed=True, cared=True, fertilizer=True, placed=2):
    return {"kind": "COOP", "animal": "GOOSE", "placed_day": placed, "yield_units": units,
            "consecutive_unfed": 0, "fed_today": fed, "cared_today": cared,
            "fertilizer_available": fertilizer, "pending_care_bonus": 0}


def reset():
    r04.MIRROR_HORIZON = False
    r04.TERMINAL_FERTILIZER = False
    r04.GOOSE_RESCUE = False
    r04._TERMINAL_FERTILIZER_AGENT = None
    r04.DRIBBLE_DUMP = False
    r04.STRAWBERRY_TOPUP = False
    r04.NO_LATE_SALE_ADVANCE = False
    r04.NO_LATE_SALE_ADVANCE_STEP = 648
    r04.ROW_SHED = False
    r04.ROW_ORDER = False
    r04.EVENING_FLUSH = False
    r04.SALE_HORIZON = 8
    r04.OPEN_ROUNDTRIP = 0
    r04.SALE_EXCLUDED = ("WHEAT", "FERTILIZER")
    r04._V231_EARLY = False
    r04.B5_CARROT_FERTILIZER = False
    r04.B5_JIT_FERTILIZE = False
    r04.FERT_HAND = False
    r04._FERT_HAND_AGENT = None
    r04._RIVAL_TAPE.update(same=0, seen=0, last=-1, decision=None, valid=True)
    b11.reset_state()


class ShippedKeys(unittest.TestCase):
    def tearDown(self):
        reset()

    def test_shipped_values(self):
        data = json.loads((ROOT / "TITAN-CONFIG.json").read_text(encoding="utf-8"))
        features = Features(**data)
        for key, value in SHIPPED.items():
            self.assertIs(data[key], value, key)
            self.assertIs(getattr(features, key), value, key)
            self.assertIs(getattr(Features(), key), value, key)

    def test_canonical_path_untouched_with_route_keys_off(self):
        self.assertFalse(TitanAgent(Features())._v3_active())
        self.assertFalse(TitanAgent(Features(r04_mirror_horizon=True, r04_terminal_fertilizer=True,
                                             r04_goose_rescue=True))._v3_active())

    def test_titan_passes_the_keys_to_the_router(self):
        for on in (True, False):
            agent = TitanAgent(Features(r04_sale_window=True, r04_mirror_horizon=on,
                                        r04_terminal_fertilizer=on, r04_goose_rescue=on))
            agent.act(observation(0), dict(CONFIG))
            self.assertIs(r04.MIRROR_HORIZON, on)
            self.assertIs(r04.TERMINAL_FERTILIZER, on)
            self.assertIs(r04.GOOSE_RESCUE, on)
            for name in ("mirror_horizon", "terminal_fertilizer", "goose_rescue"):
                self.assertIs(agent.diagnostics[name], on)
            reset()


class Seams(unittest.TestCase):
    def setUp(self):
        self.saved = r04._v3_core
        self.horizons = []
        self.parent = {"farmer": ["PASS"], "hands": [], "market": []}

        def core(obs, cfg=None):
            self.horizons.append(r04.SALE_HORIZON)
            return copy.deepcopy(self.parent)

        r04._v3_core = core

    def tearDown(self):
        r04._v3_core = self.saved
        reset()

    def test_all_off_is_the_core_agent(self):
        r04.install(None, 8, 0, False, False, mirror_horizon=False, terminal_fertilizer=False,
                    goose_rescue=False)
        self.parent = {"farmer": ["PASS"], "hands": [], "market": [["SELL", "WHEAT", 3]]}
        self.assertEqual(r04.v3_agent(observation(716, own=farm({(4, 4): cow()})), dict(CONFIG)),
                         self.parent)

    def test_b11_horizon_ten_only_after_eight_mirrors_and_restored(self):
        r04.install(None, 8, 0, False, False, mirror_horizon=True)
        for step in range(300, 310):
            r04.v3_agent(observation(step), dict(CONFIG))
        self.assertEqual(self.horizons, [8] * 7 + [10] * 3)
        self.assertEqual(r04.SALE_HORIZON, 8)

    def test_b11_mismatch_keeps_the_installed_horizon(self):
        r04.install(None, 8, 0, False, False, mirror_horizon=True)
        for step in range(300, 312):
            r04.v3_agent(observation(step, rival=farm(farmer=(5, 5))), dict(CONFIG))
        self.assertEqual(set(self.horizons), {8})

    def test_b9_collects_on_a_pass_beside_the_shed_and_trails_fertilizer_sales(self):
        r04.install(None, 8, 0, False, False, terminal_fertilizer=True)
        own = farm({(4, 4): cow()})
        out = r04.v3_agent(observation(716, own=own), dict(CONFIG))
        self.assertEqual(out["farmer"], ["COLLECT_FERTILIZER"])
        self.parent = {"farmer": ["PASS"], "hands": [],
                       "market": [["SELL", "FERTILIZER", 2], ["SELL", "MILK", 4]]}
        out = r04.v3_agent(observation(718, own=own), dict(CONFIG))
        self.assertEqual(out["market"], [["SELL", "MILK", 4], ["SELL", "FERTILIZER", 2]])

    def test_b9_leaves_other_steps_and_non_pass_commands(self):
        r04.install(None, 8, 0, False, False, terminal_fertilizer=True)
        own = farm({(4, 4): cow()})
        self.assertEqual(r04.v3_agent(observation(715, own=own), dict(CONFIG)), self.parent)
        self.parent = {"farmer": ["FEED"], "hands": [], "market": []}
        self.assertEqual(r04.v3_agent(observation(716, own=own), dict(CONFIG)), self.parent)

    def test_h3c_turns_a_clipping_goose_collection_into_harvest(self):
        r04.install(None, 8, 0, False, False, goose_rescue=True)
        own = farm({(4, 4): goose()})
        self.parent = {"farmer": ["COLLECT_FERTILIZER"], "hands": [], "market": []}
        out = r04.v3_agent(observation(24 * 10 + 23, own=own), dict(CONFIG))
        self.assertEqual(out["farmer"], ["HARVEST"])
        # Not hour 23, or eggs that would not clip tonight: the parent action stands.
        self.assertEqual(r04.v3_agent(observation(24 * 10 + 22, own=own), dict(CONFIG)), self.parent)
        own = farm({(4, 4): goose(units=2)})
        self.assertEqual(r04.v3_agent(observation(24 * 10 + 23, own=own), dict(CONFIG)), self.parent)

    def test_h3c_fails_closed_on_nonstandard_configuration(self):
        r04.install(None, 8, 0, False, False, goose_rescue=True)
        own = farm({(4, 4): goose()})
        self.parent = {"farmer": ["COLLECT_FERTILIZER"], "hands": [], "market": []}
        config = dict(CONFIG, shedCapacity=50)
        self.assertEqual(r04.v3_agent(observation(24 * 10 + 23, own=own), config), self.parent)


if __name__ == "__main__":
    unittest.main()
