# SPDX-License-Identifier: Apache-2.0
"""R04 key in the V3 tree: the R03 policy with the E184 sale window outermost.

    python -m unittest -v checks/test_v3_r04.py

Covers the E184 reservation rules on constructed tapes (horizon, per-due-step debts, the
72-step boundary, upcoming pickups, WHEAT/FERTILIZER exclusion), the horizon parameter,
the opening round trip, the delegate seam (output identical to the installed agent), precedence
over R03 and R01, off-identity of the wiring, and the V3.1 parameters (FERTILIZER in the sale
window, V231's day-8 cattle window). Standard library only.
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
from r01_tapes import load_tapes  # noqa: E402
from titan_runtime import Features, TitanAgent  # noqa: E402

CONFIG = {"episodeSteps": 720, "turnsPerDay": 24, "boardSize": 10, "shedCapacity": 100,
          "maxMarketOrdersPerTurn": 10, "farmHandCostMult": 1}
DEFAULT_HORIZON = r04.SALE_HORIZON
DEFAULT_OPENING = Features().r04_open_roundtrip
DEFAULT_ROW_ORDER = Features().r04_row_order
DEFAULT_ROW_SHED = Features().r04_row_shed
DEFAULT_FLUSH = Features().r04_evening_flush
DEFAULT_FERT = Features().r04_sale_fertilizer
DEFAULT_CATTLE = Features().r04_cattle_early
PUBLISHED_EXCLUDED = ('WHEAT', 'FERTILIZER')


def synthetic_observation(step, shed=None, shops=("BAKERY", "YARN_STORE"), player=0, money=1000):
    size = 10
    tiles = [["LOCKED"] * size for _ in range(size)]
    for y in range(3, 7):
        for x in range(3, 7):
            tiles[y][x] = {"kind": "SOIL"}
    farm = {"tiles": tiles, "farmer": [4, 4], "hands": [], "money": money,
            "unlocked_quadrants": ["NW"], "hires_today": 0}
    return {"step": step, "day": step // 24, "hour": step % 24, "player": player,
            "farms": [farm, copy.deepcopy(farm)],
            "private": {"inventories": [{}], "shed": dict(shed or {"WHEAT": 5})},
            "market": {"prices": {product: 10 for product in r04.PRODUCTS}},
            "town": {"unlocked_shops": list(shops)}}


def blank_tape():
    return [{"farmer": ["PASS"], "hands": [], "market": []} for _ in range(r04.LAST_STEP + 1)]


def empty_action():
    return {"farmer": ["PASS"], "hands": [], "market": []}


class Horizon(unittest.TestCase):
    def tearDown(self):
        r04.SALE_HORIZON = DEFAULT_HORIZON
        r04.OPEN_ROUNDTRIP = 0
        r04.ROW_ORDER = False
        r04.EVENING_FLUSH = False
        r04.SALE_EXCLUDED = PUBLISHED_EXCLUDED
        r04._V231_EARLY = False
        # TitanAgent installs the shipped-on R04 lanes; leave the module as other checks expect it.
        r04.NO_LATE_SALE_ADVANCE = False
        r04.NO_LATE_SALE_ADVANCE_STEP = 648
        r04.STRAWBERRY_TOPUP = False
        r04.ROW_SHED = False
        r04.KILL_LATE_WATER = False
        r04.STRAWBERRY_ENDGAME = False
        r04._RIVAL_TAPE.update(same=0, seen=0, last=-1, decision=None, valid=True)


class ModuleTests(Horizon):
    def test_inline_tapes_come_from_r01_tapes(self):
        self.assertEqual(r04._INLINE_TAPES, load_tapes())

    def test_e184_is_the_outermost_layer(self):
        self.assertEqual(r04.ADVANCE_START, 288)
        self.assertIs(r04.agent, r04.POLICY_AGENT)
        self.assertIs(r04._SALE_PARENT.telemetry, r04._V233_REPORT)
        self.assertIsNot(r04.advance_sales, r04._SALE_NATIVE_ADVANCE)
        self.assertIsNot(r04.subtract_advanced_sales, r04._SALE_NATIVE_SUBTRACT)
        for name in ("_V216_PARENT", "_V217_PARENT", "_V218_PARENT", "_V219_PARENT", "_V224_PARENT",
                     "_V226_PARENT", "_V231_PARENT", "_V233_PARENT", "_v234_rescue"):
            self.assertTrue(hasattr(r04, name), name)

    def test_install_sets_the_horizon(self):
        self.assertIs(r04.install(None, 5), r04.v3_agent)
        self.assertEqual(r04.SALE_HORIZON, 5)
        with self.assertRaises(ValueError):
            r04.install(None, 0)

    def test_published_license_and_attribution_are_retained(self):
        source = (ROOT / "r04_full_router.py").read_text(encoding="utf-8")
        self.assertIn("Version 2.0, January 2004", source)
        self.assertIn("two-coins-one-sheep", source)
        self.assertIn("shop-router-0909", source)


class ReservationTests(Horizon):
    def reserve(self, tape, step, shed, action=None, horizon=3):
        r04.SALE_HORIZON = horizon
        action = action or empty_action()
        state = r04.DayState()
        view = r04.FarmView(synthetic_observation(step, shed=shed))
        r04.reserve_sales(action, view, state, tape, step)
        return action, state

    def test_sells_now_what_the_tape_sells_within_the_horizon(self):
        tape = blank_tape()
        tape[301]["market"] = [["SELL", "MILK", 4]]
        tape[303]["market"] = [["SELL", "MILK", 2]]
        tape[304]["market"] = [["SELL", "MILK", 9]]
        action, state = self.reserve(tape, 300, {"MILK": 10}, horizon=3)
        self.assertEqual(action["market"], [["SELL", "MILK", 6]])
        self.assertEqual(state.sale_window_debts, {301: {"MILK": 4}, 303: {"MILK": 2}})

    def test_reservation_is_bounded_by_stock(self):
        tape = blank_tape()
        tape[301]["market"] = [["SELL", "EGG", 7]]
        action, state = self.reserve(tape, 300, {"EGG": 3})
        self.assertEqual(action["market"], [["SELL", "EGG", 3]])
        self.assertEqual(state.sale_window_debts, {301: {"EGG": 3}})

    def test_debt_is_subtracted_once_at_the_due_step(self):
        tape = blank_tape()
        tape[301]["market"] = [["SELL", "MILK", 4]]
        _, state = self.reserve(tape, 300, {"MILK": 10})
        due = {"farmer": ["PASS"], "hands": [], "market": [["SELL", "MILK", 4], ["SELL", "EGG", 2]]}
        r04.subtract_advanced_sales(due, state, 301)
        self.assertEqual(due["market"], [["SELL", "MILK", 0], ["SELL", "EGG", 2]])
        self.assertEqual(state.sale_window_debts, {})

    def test_never_crosses_the_72_step_boundary(self):
        tape = blank_tape()
        tape[359]["market"] = [["SELL", "MILK", 2]]
        tape[360]["market"] = [["SELL", "MILK", 5]]
        action, state = self.reserve(tape, 358, {"MILK": 10}, horizon=3)
        self.assertEqual(action["market"], [["SELL", "MILK", 2]])
        self.assertEqual(state.sale_window_debts, {359: {"MILK": 2}})

    def test_upcoming_pickup_stops_the_window(self):
        tape = blank_tape()
        tape[301]["farmer"] = ["PICKUP", "MILK", 3]
        tape[302]["market"] = [["SELL", "MILK", 4]]
        action, _ = self.reserve(tape, 300, {"MILK": 10})
        self.assertEqual(action["market"], [])

    def test_wheat_and_fertilizer_are_never_advanced(self):
        tape = blank_tape()
        tape[301]["market"] = [["SELL", "WHEAT", 4], ["SELL", "FERTILIZER", 4]]
        action, _ = self.reserve(tape, 300, {"WHEAT": 10, "FERTILIZER": 10})
        self.assertEqual(action["market"], [])

    def test_item_already_sold_this_turn_is_not_advanced(self):
        tape = blank_tape()
        tape[301]["market"] = [["SELL", "MILK", 4]]
        action = empty_action()
        action["market"] = [["SELL", "MILK", 1]]
        action, _ = self.reserve(tape, 300, {"MILK": 10}, action=action)
        self.assertEqual(action["market"], [["SELL", "MILK", 1]])

    def test_horizon_one_reaches_only_the_next_action(self):
        tape = blank_tape()
        tape[301]["market"] = [["SELL", "MILK", 4]]
        tape[302]["market"] = [["SELL", "MILK", 4]]
        action, _ = self.reserve(tape, 300, {"MILK": 10}, horizon=1)
        self.assertEqual(action["market"], [["SELL", "MILK", 4]])


class OpeningTests(Horizon):
    ROUNDTRIP = [["BUY_PRODUCT", "WHEAT", 13], ["BUY_PRODUCT", "WHEAT", 45], ["SELL", "WHEAT", 45]]

    def test_published_step0_market_is_the_tape_opening(self):
        self.assertEqual(r04.agent(synthetic_observation(0), dict(CONFIG))["market"], r04.TAPE_OPENING)
        self.assertTrue(all(tape[0]["market"] == r04.TAPE_OPENING for tape in load_tapes()))

    def test_opening_replaces_only_the_step0_market(self):
        on = r04.install(None, DEFAULT_HORIZON, 45)
        first = on(synthetic_observation(0), dict(CONFIG))
        self.assertEqual(first["market"], self.ROUNDTRIP)
        later = on(synthetic_observation(1), dict(CONFIG))
        self.assertEqual(later, r04.agent(synthetic_observation(1), dict(CONFIG)))

    def test_opening_zero_is_the_published_agent(self):
        off = r04.install(None, DEFAULT_HORIZON, 0, False, False)
        steps = list(range(0, 30)) + [288, 300, r04.LAST_STEP]
        direct = [r04.agent(synthetic_observation(t), dict(CONFIG)) for t in steps]
        wrapped = [off(synthetic_observation(t), dict(CONFIG)) for t in steps]
        self.assertEqual(wrapped, direct)

    def test_negative_opening_is_rejected(self):
        with self.assertRaises(ValueError):
            r04.install(None, DEFAULT_HORIZON, -1)


def _reference_engine():
    """Load checks/reference/engine/kaggriculture.py with a stub for its one package import."""
    import importlib.util
    import random
    import types
    utils = types.ModuleType("kaggle_environments.utils")
    utils.resolve_episode_seed = lambda *a, **k: 0
    package = types.ModuleType("kaggle_environments")
    saved = {k: sys.modules.get(k) for k in ("kaggle_environments", "kaggle_environments.utils")}
    sys.modules["kaggle_environments"] = package
    sys.modules["kaggle_environments.utils"] = utils
    try:
        path = ROOT / "checks" / "reference" / "engine" / "kaggriculture.py"
        spec = importlib.util.spec_from_file_location("v3_reference_kaggriculture", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for key, value in saved.items():
            if value is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value


class RowOrderTests(Horizon):
    def test_price_curve_matches_the_reference_engine(self):
        engine = _reference_engine()
        for item in engine.PRODUCTS:
            for level in (9000, 9500, 9900, 9999, 10000, 10001, 10050, 10300, 11000, 14000):
                self.assertEqual(r04._ro_price(item, level), engine.market_price(item, level), (item, level))

    def test_leading_sells_sorted_by_price_drop(self):
        market = [["SELL", "WHEAT", 10], ["SELL", "WOOL", 10], ["HIRE"], ["SELL", "MILK", 3]]
        ordered = r04.order_sells(market, {})
        self.assertEqual(ordered, [["SELL", "WOOL", 10], ["SELL", "WHEAT", 10], ["HIRE"], ["SELL", "MILK", 3]])

    def test_single_or_no_leading_sell_is_untouched(self):
        self.assertEqual(r04.order_sells([["HIRE"], ["SELL", "WOOL", 5]], {}), [["HIRE"], ["SELL", "WOOL", 5]])
        self.assertEqual(r04.order_sells([["SELL", "WOOL", 5], ["HIRE"]], {}), [["SELL", "WOOL", 5], ["HIRE"]])

    def test_row_order_off_is_the_published_agent_after_step0(self):
        off = r04.install(None, DEFAULT_HORIZON, 0, False, False)
        steps = list(range(0, 30)) + [288, 300, r04.LAST_STEP]
        direct = [r04.agent(synthetic_observation(t), dict(CONFIG)) for t in steps]
        self.assertEqual([off(synthetic_observation(t), dict(CONFIG)) for t in steps], direct)

    def test_row_order_applies_and_market_params_override_disables_it(self):
        def stub(observation, configuration=None):
            return {"farmer": ["PASS"], "hands": [], "market": [["SELL", "WHEAT", 10], ["SELL", "WOOL", 10]]}
        saved = r04.POLICY_AGENT
        r04.POLICY_AGENT = stub
        try:
            on = r04.install(None, DEFAULT_HORIZON, 0, True)
            reordered = on(synthetic_observation(5), dict(CONFIG))["market"]
            kept = on(synthetic_observation(5), dict(CONFIG, marketParams={"WOOL": {"base": 10}}))["market"]
            off = r04.install(None, DEFAULT_HORIZON, 0, False)(synthetic_observation(5), dict(CONFIG))["market"]
        finally:
            r04.POLICY_AGENT = saved
        self.assertEqual(reordered, [["SELL", "WOOL", 10], ["SELL", "WHEAT", 10]])
        self.assertEqual(kept, [["SELL", "WHEAT", 10], ["SELL", "WOOL", 10]])
        self.assertEqual(off, [["SELL", "WHEAT", 10], ["SELL", "WOOL", 10]])


class FlushTests(Horizon):
    SHED = {"WOOL": 7, "MILK": 3, "WHEAT": 5, "FERTILIZER": 4}

    def run_stub(self, step, market, flush=True, shed=None):
        def stub(observation, configuration=None):
            return {"farmer": ["PASS"], "hands": [], "market": [list(o) for o in market]}
        saved = r04.POLICY_AGENT
        r04.POLICY_AGENT = stub
        try:
            agent = r04.install(None, DEFAULT_HORIZON, 0, False, flush)
            return agent(synthetic_observation(step, shed=shed or self.SHED), dict(CONFIG))["market"]
        finally:
            r04.POLICY_AGENT = saved

    def test_flushes_steep_stock_at_hours_21_to_23(self):
        for step in (45, 46, 47, 21 + 24 * 20):
            self.assertEqual(self.run_stub(step, [["HIRE"]]), [["SELL", "WOOL", 7], ["SELL", "MILK", 3], ["HIRE"]], step)

    def test_no_flush_outside_the_window_or_on_day_zero(self):
        for step in (21, 22, 23, 24, 40, 44, 48, r04.LAST_STEP):
            self.assertEqual(self.run_stub(step, [["HIRE"]]), [["HIRE"]], step)

    def test_quantities_already_being_sold_are_not_doubled(self):
        self.assertEqual(self.run_stub(45, [["SELL", "WOOL", 2]]),
                         [["SELL", "WOOL", 5], ["SELL", "MILK", 3], ["SELL", "WOOL", 2]])

    def test_order_cap_is_respected(self):
        market = [["HIRE"]] * 9
        out = self.run_stub(45, market)
        self.assertEqual(len(out), 10)
        self.assertEqual(out[0], ["SELL", "WOOL", 7])

    def test_off_is_identity(self):
        self.assertEqual(self.run_stub(45, [["HIRE"]], flush=False), [["HIRE"]])


def herd_observation(step, shops, cows=4, sheep=2, shed=None):
    """A farm with `cows` cows and `sheep` sheep placed, nothing carried, nothing in the shed."""
    obs = synthetic_observation(step, shed=shed or {"WHEAT": 5}, shops=shops)
    tiles = obs["farms"][0]["tiles"]
    spots = [(x, y) for y in range(3, 7) for x in range(3, 7) if (x, y) != (4, 4)]
    for n, (x, y) in enumerate(spots[:cows + sheep]):
        tiles[y][x] = {"kind": "PASTURE", "animal": "COW" if n < cows else "SHEEP", "placed_day": 3,
                       "yield_units": 0}
    obs["market"]["prices"].update({"MILK": 200, "WOOL": 150})
    return obs


class V31Tests(Horizon):
    MILK_PAIR = ("PIZZA_SHOP", "ICE_CREAM_SHOP")

    def gate(self, step, shops, early, order=("BUY_ANIMAL", "SHEEP", 2)):
        r04._V231_EARLY = early
        action = {"farmer": ["PASS"], "hands": [], "market": [list(order)]}
        out = r04._v231_controller(herd_observation(step, shops), action, r04._v231_new_state(), r04._V231_CAP)
        return out["market"]

    def test_parameter_defaults_are_the_published_values(self):
        self.assertEqual(r04.SALE_EXCLUDED, PUBLISHED_EXCLUDED)
        self.assertIs(r04._V231_EARLY, False)
        source = (ROOT / "r04_full_router.py").read_text(encoding="utf-8")
        self.assertIn("SALE_EXCLUDED = ('WHEAT', 'FERTILIZER')", source)
        self.assertIn("_V231_EARLY=False", source)

    def test_sale_fertilizer_lets_the_window_advance_fertilizer_only(self):
        tape = blank_tape()
        tape[301]["market"] = [["SELL", "WHEAT", 4], ["SELL", "FERTILIZER", 4]]
        r04.install(None, 3, None, None, None, True, None)
        self.assertEqual(r04.SALE_EXCLUDED, ("WHEAT",))
        action = empty_action()
        view = r04.FarmView(synthetic_observation(300, shed={"WHEAT": 10, "FERTILIZER": 10}))
        r04.reserve_sales(action, view, r04.DayState(), tape, 300)
        self.assertEqual(action["market"], [["SELL", "FERTILIZER", 4]])
        r04.install(None, 3, None, None, None, False, None)
        self.assertEqual(r04.SALE_EXCLUDED, PUBLISHED_EXCLUDED)
        action = empty_action()
        r04.reserve_sales(action, view, r04.DayState(), tape, 300)
        self.assertEqual(action["market"], [])

    def test_cattle_early_swaps_the_day8_sheep_purchase_on_a_milk_pair(self):
        self.assertEqual(self.gate(196, self.MILK_PAIR, True), [["BUY_ANIMAL", "COW", 2]])
        self.assertEqual(self.gate(196, self.MILK_PAIR, False), [["BUY_ANIMAL", "SHEEP", 2]])

    def test_cattle_early_needs_two_milk_shops_and_no_yarn_store(self):
        for shops in (("PIZZA_SHOP", "BAKERY"), ("YARN_STORE", "PIZZA_SHOP"), ("ICE_CREAM_SHOP", "YARN_STORE"),
                      ("PIZZA_SHOP",)):
            self.assertEqual(self.gate(196, shops, True), [["BUY_ANIMAL", "SHEEP", 2]], shops)

    def test_cattle_early_window_is_steps_190_to_215(self):
        for step in (189, 216):
            self.assertEqual(self.gate(step, self.MILK_PAIR, True), [["BUY_ANIMAL", "SHEEP", 2]], step)
        for step in (190, 215):
            self.assertEqual(self.gate(step, self.MILK_PAIR, True), [["BUY_ANIMAL", "COW", 2]], step)

    def test_published_day9_window_is_unchanged(self):
        shops = ("PIZZA_SHOP", "ICE_CREAM_SHOP", "BAKERY")
        for early in (False, True):
            self.assertEqual(self.gate(220, shops, early), [["BUY_ANIMAL", "COW", 2]], early)

    def test_install_sets_both_parameters(self):
        r04.install(None, DEFAULT_HORIZON, 0, False, False, True, True)
        self.assertEqual((r04.SALE_EXCLUDED, r04._V231_EARLY), (("WHEAT",), True))
        r04.install(None, DEFAULT_HORIZON, 0, False, False, False, False)
        self.assertEqual((r04.SALE_EXCLUDED, r04._V231_EARLY), (PUBLISHED_EXCLUDED, False))
        r04.install(None, DEFAULT_HORIZON)
        self.assertEqual((r04.SALE_EXCLUDED, r04._V231_EARLY), (PUBLISHED_EXCLUDED, False))


class WiringTests(Horizon):
    def play(self, callable_, steps):
        return [callable_(synthetic_observation(step), dict(CONFIG)) for step in steps]

    def test_keys_ship_off(self):
        data = json.loads((ROOT / "TITAN-CONFIG.json").read_text(encoding="utf-8"))
        self.assertIs(data["r04_sale_window"], False)
        self.assertEqual(data["r04_sale_horizon"], DEFAULT_HORIZON)
        self.assertEqual(data["r04_open_roundtrip"], DEFAULT_OPENING)
        self.assertIs(data["r04_row_order"], DEFAULT_ROW_ORDER)
        self.assertIs(data["r04_evening_flush"], DEFAULT_FLUSH)
        self.assertIs(data["r04_sale_fertilizer"], DEFAULT_FERT)
        self.assertIs(data["r04_cattle_early"], DEFAULT_CATTLE)
        features = Features(**data)
        self.assertIs(features.r04_sale_window, False)
        self.assertEqual(features.r04_sale_horizon, DEFAULT_HORIZON)
        self.assertFalse(TitanAgent(Features())._v3_active())
        self.assertTrue(TitanAgent(Features(r04_sale_window=True))._v3_active())

    def test_delegate_runs_before_any_canonical_state(self):
        agent = TitanAgent(Features(r04_sale_window=True))
        action = agent.act(synthetic_observation(0), dict(CONFIG))
        self.assertEqual(set(action), {"farmer", "hands", "market"})
        self.assertEqual(agent.diagnostics["status"], "completed")
        self.assertEqual(agent.diagnostics["route"], "r04_sale_window")
        self.assertEqual(agent.diagnostics["sale_horizon"], DEFAULT_HORIZON)
        self.assertEqual(agent.diagnostics["open_roundtrip"], DEFAULT_OPENING)
        self.assertIs(agent.diagnostics["row_order"], DEFAULT_ROW_ORDER)
        self.assertIs(agent.diagnostics["evening_flush"], DEFAULT_FLUSH)
        self.assertIs(agent.diagnostics["sale_fertilizer"], DEFAULT_FERT)
        self.assertIs(agent.diagnostics["cattle_early"], DEFAULT_CATTLE)
        self.assertFalse(agent.ready)
        self.assertIsNone(getattr(agent, "controller", None))

    def test_delegate_output_equals_the_published_agent(self):
        steps = list(range(0, 40)) + [143, 144, 145, 287, 288, 289, 300, 301, 647, 648, 700, 712, 717, r04.LAST_STEP]
        direct = self.play(r04.install(None, DEFAULT_HORIZON, DEFAULT_OPENING, DEFAULT_ROW_ORDER, DEFAULT_FLUSH,
                                       DEFAULT_FERT, DEFAULT_CATTLE, row_shed=DEFAULT_ROW_SHED), steps)
        agent = TitanAgent(Features(r04_sale_window=True))
        delegated = self.play(lambda obs, cfg: agent.act(obs, cfg), steps)
        self.assertEqual(delegated, direct)

    def test_horizon_parameter_reaches_the_policy(self):
        agent = TitanAgent(Features(r04_sale_window=True, r04_sale_horizon=5))
        agent.act(synthetic_observation(0), dict(CONFIG))
        self.assertEqual(r04.SALE_HORIZON, 5)
        self.assertEqual(agent.diagnostics["sale_horizon"], 5)

    def test_v31_parameters_reach_the_policy(self):
        for on in (True, False):
            agent = TitanAgent(Features(r04_sale_window=True, r04_sale_fertilizer=on, r04_cattle_early=on))
            agent.act(synthetic_observation(0), dict(CONFIG))
            self.assertEqual(r04.SALE_EXCLUDED, ("WHEAT",) if on else PUBLISHED_EXCLUDED)
            self.assertIs(r04._V231_EARLY, on)
            self.assertIs(agent.diagnostics["sale_fertilizer"], on)
            self.assertIs(agent.diagnostics["cattle_early"], on)

    def test_r04_takes_precedence_over_r03_and_r01(self):
        agent = TitanAgent(Features(r01_shop_router=True, r03_full_router=True, r04_sale_window=True))
        agent.act(synthetic_observation(0), dict(CONFIG))
        self.assertEqual(agent.diagnostics["route"], "r04_sale_window")

    def test_notice_carries_attribution(self):
        notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
        self.assertIn("r04_sale_window", notice)
        self.assertIn("two-coins-one-sheep", notice)


if __name__ == "__main__":
    unittest.main(verbosity=2)
