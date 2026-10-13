# SPDX-License-Identifier: Apache-2.0
"""V3.1 lane A6: grow feed wheat instead of buying wheat product.

    python -m unittest -v checks/test_v3_r04_feed_wheat.py

Covers the r04_feed_wheat seam: default-off wiring through Features,
TITAN-CONFIG.json and the delegate diagnostics; off-identity of apply(); the
pure helpers (seed_order spread, emergency-buy cap, per-day headroom); the
opportunistic crew (plants only on empty tiles with idle units, waters inside
the yield window, harvests from day 5, places carried wheat at the shed, never
touches a busy unit and never risks the tape's own PLANT atomicity); the
install() toggles both ways without state leakage; and delegate/direct
equivalence with the lane on. Standard library only.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import r04_full_router as r04  # noqa: E402
import r04_feed_wheat as fw  # noqa: E402
from titan_runtime import Features, TitanAgent  # noqa: E402

CONFIG = {"episodeSteps": 720, "turnsPerDay": 24, "boardSize": 10, "shedCapacity": 100,
          "maxMarketOrdersPerTurn": 10, "farmHandCostMult": 1}
DEFAULT_SEEDS = fw.DEFAULT_EXTRA_SEEDS


def synthetic_observation(step, player=0, money=1000, farmer=(4, 4),
                          hands=(), inventories=None, seeds=0, tiles=None):
    """Bare observation shaped like the published one; None tiles are empty."""
    size = 10
    if tiles is None:
        tiles = [[None] * size for _ in range(size)]
        for y in range(size):
            for x in range(size):
                if x < 3 or x > 6 or y < 3 or y > 6:
                    tiles[y][x] = "LOCKED"
    farm = {"tiles": tiles, "farmer": list(farmer),
            "hands": [list(h) for h in hands], "money": money,
            "unlocked_quadrants": ["NW"], "hires_today": 0}
    private = {"inventories": [dict(i) for i in (inventories if inventories is not None else [{}])],
               "seeds": {"WHEAT": seeds}, "shed": {"WHEAT": 5}}
    return {"step": step, "day": step // 24, "hour": step % 24, "player": player,
            "farms": [farm, copy.deepcopy(farm)],
            "private": private,
            "market": {"prices": {"WHEAT": 38, "CARROT": 10}},
            "town": {"unlocked_shops": ["BAKERY", "YARN_STORE"]}}


def empty_action(farmer=("PASS",), hands=(), market=()):
    return {"farmer": list(farmer), "hands": [list(h) for h in hands],
            "market": [list(o) for o in market]}


def _snap_globals():
    return (r04.SALE_HORIZON, r04.OPEN_ROUNDTRIP, r04.ROW_ORDER, r04.EVENING_FLUSH,
            r04.SALE_EXCLUDED, r04._V231_EARLY, r04.FEED_WHEAT, r04.FEED_WHEAT_SEEDS,
            r04.FEED_WHEAT_BUY_CAP)


def _restore_globals(snap):
    (r04.SALE_HORIZON, r04.OPEN_ROUNDTRIP, r04.ROW_ORDER, r04.EVENING_FLUSH,
     r04.SALE_EXCLUDED, r04._V231_EARLY, r04.FEED_WHEAT, r04.FEED_WHEAT_SEEDS,
     r04.FEED_WHEAT_BUY_CAP) = snap
    fw.reset()


class Helpers(unittest.TestCase):
    def test_seed_order_spreads_quota_over_plant_days(self):
        self.assertEqual(fw.seed_order(0, True, 26, 0), 9)
        self.assertEqual(fw.seed_order(1, True, 26, 9), 9)
        self.assertEqual(fw.seed_order(2, True, 26, 18), 8)

    def test_seed_order_off_day_and_quota(self):
        self.assertEqual(fw.seed_order(0, False, 26, 0), 0)
        self.assertEqual(fw.seed_order(3, True, 26, 0), 0)
        self.assertEqual(fw.seed_order(2, True, 26, 26), 0)
        self.assertEqual(fw.seed_order(2, True, 26, 40), 0)

    def test_headroom_and_note_bought(self):
        fw.reset()
        self.assertEqual(fw.buy_headroom(0, 120, None), float("inf"))
        self.assertEqual(fw.buy_headroom(0, 120, 1.2), 1.2)
        fw.note_bought(0, 120, 1)
        self.assertAlmostEqual(fw.buy_headroom(0, 120, 1.2), 0.2)
        # next day the allowance renews
        self.assertEqual(fw.buy_headroom(0, 121, 1.2), 1.2)
        fw.reset()

    def test_capped_only_binds_from_day_5(self):
        fw.reset()
        self.assertEqual(fw.capped(4, 0, 4, 1.2), 4)    # day 4: untouched
        self.assertEqual(fw.capped(4, 0, 5, 1.2), 1)    # day 5: capped
        self.assertEqual(fw.capped(4, 0, 5, None), 4)   # cap disabled
        self.assertEqual(fw.REPORT["buy_caps"], 1)
        self.assertEqual(fw.REPORT["capped_units"], 3)
        fw.reset()

    def test_reset_clears_report_and_states(self):
        fw.reset()
        fw.note_bought(0, 120, 1)
        fw.REPORT["plants"] = 3
        fw.reset()
        self.assertEqual(fw.REPORT["plants"], 0)
        self.assertEqual(fw.buy_headroom(0, 120, 1.2), 1.2)


class ApplyOff(unittest.TestCase):
    def test_off_is_identity(self):
        fw.reset()
        action = empty_action(market=[["BUY_PRODUCT", "WHEAT", 13]])
        obs = synthetic_observation(0)
        self.assertIs(fw.apply(obs, action, False, 26, 1.2), action)

    def test_terminal_step_untouched_even_when_on(self):
        fw.reset()
        action = empty_action(market=[["SELL", "WHEAT", 50]])
        obs = synthetic_observation(719)
        self.assertIs(fw.apply(obs, action, True, 26, 1.2), action)
        fw.reset()


class SeedOrders(unittest.TestCase):
    def setUp(self):
        fw.reset()

    def tearDown(self):
        fw.reset()

    def test_day0_appends_seed_order_and_preserves_inherited_rows(self):
        obs = synthetic_observation(0)
        action = empty_action(market=[["BUY_PRODUCT", "WHEAT", 13], ["SELL", "WHEAT", 13]])
        out = fw.apply(obs, action, True, 26, 1.2)
        self.assertIsNot(out, action)
        self.assertEqual(out["market"][:2], [["BUY_PRODUCT", "WHEAT", 13], ["SELL", "WHEAT", 13]])
        self.assertEqual(out["market"][2], ["BUY_SEED", "WHEAT", 9])
        self.assertEqual(fw.REPORT["seed_orders"], 1)
        self.assertEqual(fw.REPORT["seed_units"], 9)

    def test_quota_is_bounded_and_spread(self):
        totals = []
        for step in (0, 24, 48):
            obs = synthetic_observation(step)
            out = fw.apply(obs, empty_action(), True, 26, 1.2)
            totals.append(out["market"][0][2] if out["market"] else 0)
        self.assertEqual(totals, [9, 9, 8])
        self.assertEqual(fw.REPORT["seed_units"], 26)
        # a fourth plant-day call orders nothing more
        out = fw.apply(synthetic_observation(48), empty_action(), True, 26, 1.2)
        self.assertEqual(out["market"], [])

    def test_no_order_off_plant_days(self):
        obs = synthetic_observation(72)  # day 3
        out = fw.apply(obs, empty_action(), True, 26, 1.2)
        self.assertEqual(out["market"], [])

    def test_market_slot_cap_respected(self):
        obs = synthetic_observation(0)
        market = [["SELL", "WHEAT", 1]] * 10
        action = empty_action(market=market)
        out = fw.apply(obs, action, True, 26, 1.2)
        self.assertEqual(out["market"], market)

    def test_budget_floor(self):
        obs = synthetic_observation(0, money=100)
        out = fw.apply(obs, empty_action(), True, 26, 1.2)
        self.assertEqual(out["market"], [])


class Crew(unittest.TestCase):
    def setUp(self):
        fw.reset()

    def tearDown(self):
        fw.reset()

    def test_idle_unit_plants_on_empty_tile(self):
        obs = synthetic_observation(0, farmer=(4, 4), seeds=10)
        out = fw.apply(obs, empty_action(), True, 26, 1.2)
        self.assertEqual(out["farmer"], ["PLANT", "WHEAT"])
        self.assertEqual(fw.REPORT["plants"], 1)

    def test_busy_unit_never_redirected(self):
        obs = synthetic_observation(0, farmer=(4, 4), seeds=10)
        action = empty_action(farmer=("WATER",))
        out = fw.apply(obs, action, True, 26, 1.2)
        self.assertEqual(out["farmer"], ["WATER"])
        self.assertEqual(fw.REPORT["plants"], 0)

    def test_tape_plant_atomicity_never_risked(self):
        # The tape plants its last seed; an idle hand must not add a PLANT
        # because the engine drops ALL wheat PLANTs when demand exceeds seeds.
        obs = synthetic_observation(0, farmer=(4, 4), seeds=1)
        action = empty_action(farmer=("PLANT", "WHEAT"))
        out = fw.apply(obs, action, True, 26, 1.2)
        self.assertEqual(out["farmer"], ["PLANT", "WHEAT"])
        self.assertEqual(fw.REPORT["plants"], 0)

    def test_no_plant_without_seeds(self):
        obs = synthetic_observation(0, farmer=(4, 4), seeds=0)
        out = fw.apply(obs, empty_action(), True, 26, 1.2)
        self.assertEqual(out["farmer"], ["PASS"])

    def test_water_inside_yield_window(self):
        obs = synthetic_observation(0, farmer=(4, 4), seeds=10)
        out = fw.apply(obs, empty_action(), True, 26, 1.2)
        self.assertEqual(out["farmer"], ["PLANT", "WHEAT"])
        # day 2: the recorded plant gets watered by the idle farmer standing on it
        tiles = obs["farms"][0]["tiles"]
        tiles[4][4] = {"crop": "WHEAT"}
        obs2 = synthetic_observation(48, farmer=(4, 4), tiles=tiles)
        out2 = fw.apply(obs2, empty_action(), True, 26, 1.2)
        self.assertEqual(out2["farmer"], ["WATER"])
        self.assertGreaterEqual(fw.REPORT["waters"], 1)

    def test_no_water_outside_window(self):
        tiles = [[None] * 10 for _ in range(10)]
        tiles[4][4] = {"crop": "WHEAT"}
        fw._state(0, 5)["planted"].append((4, 4))
        obs = synthetic_observation(120, farmer=(4, 4), tiles=tiles)  # day 5
        out = fw.apply(obs, empty_action(), True, 26, 1.2)
        # day 5 is harvest territory, not watering
        self.assertNotEqual(out["farmer"], ["WATER"])

    def test_harvest_from_day_5(self):
        tiles = [[None] * 10 for _ in range(10)]
        tiles[4][4] = {"crop": "WHEAT", "yield_units": 3}
        fw._state(0, 5)["planted"].append((4, 4))
        obs = synthetic_observation(120, farmer=(4, 4), tiles=tiles)
        out = fw.apply(obs, empty_action(), True, 26, 1.2)
        self.assertEqual(out["farmer"], ["HARVEST"])
        self.assertEqual(fw.REPORT["harvests"], 1)

    def test_place_carried_wheat_at_shed(self):
        obs = synthetic_observation(0, farmer=(4, 4),
                                    inventories=[{"WHEAT": 3}])
        out = fw.apply(obs, empty_action(), True, 26, 1.2)
        self.assertEqual(out["farmer"], ["PLACE", "WHEAT", 3])
        self.assertEqual(fw.REPORT["places"], 1)

    def test_unit_walks_to_shed_when_far(self):
        obs = synthetic_observation(0, farmer=(6, 6),
                                    inventories=[{"WHEAT": 2}])
        out = fw.apply(obs, empty_action(), True, 26, 1.2)
        self.assertEqual(out["farmer"], ["WEST"])

    def test_dead_plant_pruned_from_tracking(self):
        fw._state(0, 2)["planted"].append((4, 4))
        tiles = [[None] * 10 for _ in range(10)]  # tile dug: no longer wheat
        obs = synthetic_observation(48, farmer=(4, 4), tiles=tiles)
        out = fw.apply(obs, empty_action(), True, 26, 1.2)
        self.assertNotEqual(out["farmer"], ["WATER"])


class InstallWiring(unittest.TestCase):
    def setUp(self):
        self._globals = _snap_globals()
        r04.install(feed_wheat=False)

    def tearDown(self):
        _restore_globals(self._globals)

    def test_defaults_ship_off(self):
        self.assertIs(r04.FEED_WHEAT, False)
        self.assertEqual(r04.FEED_WHEAT_SEEDS, DEFAULT_SEEDS)
        self.assertEqual(r04.FEED_WHEAT_BUY_CAP, 1.2)
        features = Features()
        self.assertIs(features.r04_feed_wheat, False)
        self.assertEqual(features.r04_feed_wheat_seeds, DEFAULT_SEEDS)
        self.assertEqual(features.r04_feed_wheat_buy_cap, 1.2)

    def test_install_toggles_both_ways(self):
        r04.install(feed_wheat=True, feed_wheat_seeds=10, feed_wheat_buy_cap=2.5)
        self.assertIs(r04.FEED_WHEAT, True)
        self.assertEqual(r04.FEED_WHEAT_SEEDS, 10)
        self.assertEqual(r04.FEED_WHEAT_BUY_CAP, 2.5)
        r04.install(feed_wheat=False)
        self.assertIs(r04.FEED_WHEAT, False)

    def test_toggle_resets_lane_state(self):
        fw.note_bought(0, 120, 1)
        r04.install(feed_wheat=True)
        self.assertEqual(fw.buy_headroom(0, 120, 1.2), 1.2)

    def test_same_value_install_keeps_state(self):
        # The delegate calls install() on every act; that must not wipe the lane.
        r04.install(feed_wheat=True)
        fw.note_bought(0, 120, 1)
        r04.install(feed_wheat=True)
        self.assertAlmostEqual(fw.buy_headroom(0, 120, 1.2), 0.2)


class ConfigAndDiagnostics(unittest.TestCase):
    def setUp(self):
        self._globals = _snap_globals()

    def tearDown(self):
        _restore_globals(self._globals)

    def test_keys_ship_off_in_config(self):
        data = json.loads((ROOT / "TITAN-CONFIG.json").read_text(encoding="utf-8"))
        self.assertIs(data["r04_feed_wheat"], False)
        self.assertEqual(data["r04_feed_wheat_seeds"], DEFAULT_SEEDS)
        self.assertEqual(data["r04_feed_wheat_buy_cap"], 1.2)
        features = Features(**data)
        self.assertIs(features.r04_feed_wheat, False)
        self.assertEqual(features.r04_feed_wheat_seeds, DEFAULT_SEEDS)
        self.assertEqual(features.r04_feed_wheat_buy_cap, 1.2)

    def test_diagnostics_carry_the_keys(self):
        agent = TitanAgent(Features(r04_sale_window=True, r04_feed_wheat=True,
                                    r04_feed_wheat_seeds=10, r04_feed_wheat_buy_cap=2.5))
        agent.act(synthetic_observation(0), dict(CONFIG))
        self.assertIs(agent.diagnostics["feed_wheat"], True)
        self.assertEqual(agent.diagnostics["feed_wheat_seeds"], 10)
        self.assertEqual(agent.diagnostics["feed_wheat_buy_cap"], 2.5)

    def test_delegate_output_equals_direct_with_lane_on(self):
        steps = [0, 1, 24, 25, 48, 49, 72, 120, 121, 200, 300, 500, 700, 717]
        # Explicit install args on the direct path, exactly what the delegate
        # passes per act; stale module globals must not leak into the lane.
        # Each sequence starts from reset lane state so both accumulate identically.
        fw.reset()
        direct = [r04.install(None, 8, 0, True, True, True, True,
                              True, 26, 1.2)(synthetic_observation(s), dict(CONFIG))
                  for s in steps]
        fw.reset()
        agent = TitanAgent(Features(r04_sale_window=True, r04_feed_wheat=True))
        delegated = [agent.act(synthetic_observation(s), dict(CONFIG)) for s in steps]
        self.assertEqual(delegated, direct)

    def test_lane_gate_in_v3_agent(self):
        r04.install(feed_wheat=True, feed_wheat_seeds=7)
        on = r04.v3_agent(synthetic_observation(0), dict(CONFIG))
        # day-0 share of 7 seeds over 3 plant days: ceil(7/3) = 3
        self.assertEqual(on["market"][-1], ["BUY_SEED", "WHEAT", 3])
        r04.install(feed_wheat=False)
        off = r04.v3_agent(synthetic_observation(0), dict(CONFIG))
        self.assertNotIn(["BUY_SEED", "WHEAT", 3], off["market"])


if __name__ == "__main__":
    unittest.main()
