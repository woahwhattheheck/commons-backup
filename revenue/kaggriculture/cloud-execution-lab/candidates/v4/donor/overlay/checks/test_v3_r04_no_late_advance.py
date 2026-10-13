# SPDX-License-Identifier: Apache-2.0
"""R04 lane L3 (no-late-sale-advance): the peer B10 lane port.

    python -m unittest -v checks/test_v3_r04_no_late_advance.py

Covers the pure suppression predicate (off/at-or-above-threshold/custom
threshold, telemetry report and reset()), install() wiring of the two new
parameters (globals, threshold validation), and the E184 reservation call-site
gate: with the flag on, steps >= the threshold record no reservation and no
debt, while step threshold-1 still reserves; pre-threshold debts still settle
through subtract_advanced_sales(); with the flag off the route is identical
to the pre-lane behavior. Standard library only.
"""
from __future__ import annotations

import copy
import types
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import r04_full_router as r04  # noqa: E402
import r04_no_late_sale_advance as nla  # noqa: E402

DEFAULT_HORIZON = r04.SALE_HORIZON
PUBLISHED_EXCLUDED = ('WHEAT', 'FERTILIZER')
DEFAULT_STEP = 648


def synthetic_observation(step, shed=None, player=0, money=1000):
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
            "town": {"unlocked_shops": ["BAKERY", "YARN_STORE"]}}


def certify_off_tape():
    """Feed the complete public opening (steps 0-143) with the rival elsewhere, so the fail-closed
    L3 rival gate certifies OFF_TAPE; without a complete opening it keeps the E184 reservation."""
    r04._reset_rival_tape()
    for step in range(0, r04.RIVAL_GATE_WINDOW[1]):
        observation = synthetic_observation(step)
        observation["farms"][1]["farmer"] = [9, 9]
        r04.rival_on_tape(observation, step)
    assert r04._RIVAL_TAPE["decision"] is False


def blank_tape():
    return [{"farmer": ["PASS"], "hands": [], "market": []} for _ in range(r04.LAST_STEP + 1)]


class Base(unittest.TestCase):
    def setUp(self):
        # Other checks drive TitanAgent, which installs the shipped-on V3.1 lanes: start clean.
        Base.tearDown(self)

    def tearDown(self):
        r04.SALE_HORIZON = DEFAULT_HORIZON
        r04.SALE_EXCLUDED = PUBLISHED_EXCLUDED
        r04.NO_LATE_SALE_ADVANCE = False
        r04.NO_LATE_SALE_ADVANCE_STEP = DEFAULT_STEP
        r04._reset_rival_tape()
        nla.reset()


class PredicateTests(Base):
    def test_off_is_never_suppressed(self):
        for step in (0, 287, 647, 648, 649, 700, 717):
            self.assertFalse(nla.suppressed(step, False))

    def test_on_suppresses_at_and_above_the_threshold_only(self):
        self.assertFalse(nla.suppressed(647, True))
        self.assertTrue(nla.suppressed(648, True))
        self.assertTrue(nla.suppressed(649, True))
        self.assertTrue(nla.suppressed(717, True))
        self.assertFalse(nla.suppressed(0, True))

    def test_custom_threshold(self):
        self.assertFalse(nla.suppressed(699, True, 700))
        self.assertTrue(nla.suppressed(700, True, 700))
        self.assertTrue(nla.suppressed(701, True, 700))

    def test_default_threshold_is_648(self):
        self.assertEqual(nla.DEFAULT_THRESHOLD, 648)
        self.assertFalse(nla.suppressed(647, True, nla.DEFAULT_THRESHOLD))
        self.assertTrue(nla.suppressed(648, True, nla.DEFAULT_THRESHOLD))

    def test_report_counts_suppressions_and_reset_clears_it(self):
        nla.reset()
        self.assertFalse(nla.suppressed(647, True))
        self.assertTrue(nla.suppressed(648, True))
        self.assertTrue(nla.suppressed(700, True))
        self.assertFalse(nla.suppressed(10, False))
        self.assertEqual(nla.REPORT["suppressed_steps"], 2)
        self.assertEqual(nla.REPORT["last"], 700)
        nla.reset()
        self.assertEqual(nla.REPORT, {"suppressed_steps": 0, "last": None})


class InstallTests(Base):
    def test_install_sets_both_parameters(self):
        r04.install(None, DEFAULT_HORIZON, 0, False, False, None, None,
                    no_late_sale_advance=True, no_late_sale_advance_step=700)
        self.assertTrue(r04.NO_LATE_SALE_ADVANCE)
        self.assertEqual(r04.NO_LATE_SALE_ADVANCE_STEP, 700)

    def test_install_leaves_defaults_when_not_passed(self):
        r04.install(None, DEFAULT_HORIZON)
        self.assertFalse(r04.NO_LATE_SALE_ADVANCE)
        self.assertEqual(r04.NO_LATE_SALE_ADVANCE_STEP, DEFAULT_STEP)

    def test_negative_threshold_is_rejected(self):
        with self.assertRaises(ValueError):
            r04.install(None, DEFAULT_HORIZON, 0, False, False, None, None,
                    no_late_sale_advance=True, no_late_sale_advance_step=-1)
        self.assertEqual(r04.NO_LATE_SALE_ADVANCE_STEP, DEFAULT_STEP)


class CallSiteGateTests(Base):
    """Drive the real E184 agent() wrapper with a stubbed _POLICY and inner
    parent, so the exact gated call-site expression is exercised."""

    def setUp(self):
        super().setUp()
        self.state = r04.DayState()
        self.tape = blank_tape()
        self.real_policy = r04._POLICY
        self.real_parent = r04._SALE_PARENT
        r04._POLICY = types.SimpleNamespace(tapes={0: self.tape},
                                            players=[self.state])
        r04._SALE_PARENT = lambda observation, configuration=None: {
            "farmer": ["PASS"], "hands": [], "market": []}

    def tearDown(self):
        r04._POLICY = self.real_policy
        r04._SALE_PARENT = self.real_parent
        super().tearDown()

    def run_step(self, step, shed):
        return r04.agent(synthetic_observation(step, shed=shed), {"episodeSteps": 720})

    def test_suppressed_at_and_above_threshold(self):
        r04.install(None, 8, 0, False, False, None, None,
                    no_late_sale_advance=True, no_late_sale_advance_step=648)
        self.tape[649]["market"] = [["SELL", "MILK", 4]]
        self.tape[655]["market"] = [["SELL", "MILK", 6]]
        certify_off_tape()
        for step in (648, 649, 655, 700):
            action = self.run_step(step, {"MILK": 20})
            self.assertEqual(action["market"], [], step)
        self.assertEqual(getattr(self.state, "sale_window_debts", {}), {})
        self.assertEqual(nla.REPORT["suppressed_steps"], 4)
        self.assertEqual(nla.REPORT["last"], 700)

    def test_reserves_below_the_threshold(self):
        # Note: step 647 itself is the last step of its 72-step route block, so
        # reserve_sales() is a no-op there in the real code too; 640 is the
        # nearest below-threshold step that can actually reserve.
        r04.install(None, 8, 0, False, False, None, None,
                    no_late_sale_advance=True, no_late_sale_advance_step=648)
        self.tape[641]["market"] = [["SELL", "MILK", 4]]
        action = self.run_step(640, {"MILK": 10})
        self.assertEqual(action["market"], [["SELL", "MILK", 4]])
        self.assertEqual(self.state.sale_window_debts, {641: {"MILK": 4}})
        self.assertEqual(nla.REPORT["suppressed_steps"], 0)

    def test_pre_threshold_debt_still_settles_at_its_due_step(self):
        r04.install(None, 8, 0, False, False, None, None,
                    no_late_sale_advance=True, no_late_sale_advance_step=648)
        self.tape[641]["market"] = [["SELL", "MILK", 4]]
        self.run_step(640, {"MILK": 10})
        self.assertEqual(self.state.sale_window_debts, {641: {"MILK": 4}})
        due = {"farmer": ["PASS"], "hands": [],
               "market": [["SELL", "MILK", 4], ["SELL", "EGG", 2]]}
        r04.subtract_advanced_sales(due, self.state, 641)
        self.assertEqual(due["market"], [["SELL", "MILK", 0], ["SELL", "EGG", 2]])
        self.assertEqual(self.state.sale_window_debts, {})

    def test_tape_own_late_sells_are_not_suppressed(self):
        # Published tape rows are not advancement: the wrapper must keep the
        # parent's own market rows even past the threshold.
        r04.install(None, 8, 0, False, False, None, None,
                    no_late_sale_advance=True, no_late_sale_advance_step=648)
        self.real_parent_holder = r04._SALE_PARENT
        r04._SALE_PARENT = lambda observation, configuration=None: {
            "farmer": ["PASS"], "hands": [],
            "market": [["SELL", "CARROT", 1000]]}
        action = self.run_step(700, {"CARROT": 0})
        self.assertEqual(action["market"], [["SELL", "CARROT", 1000]])
        self.assertEqual(getattr(self.state, "sale_window_debts", {}), {})

    def test_flag_off_is_identical_to_the_pre_lane_route(self):
        r04.install(None, 8, 0, False, False, None, None, None, None)
        self.assertFalse(r04.NO_LATE_SALE_ADVANCE)
        self.tape[649]["market"] = [["SELL", "MILK", 4]]
        action = self.run_step(648, {"MILK": 10})
        self.assertEqual(action["market"], [["SELL", "MILK", 4]])
        self.assertEqual(self.state.sale_window_debts, {649: {"MILK": 4}})
        self.assertEqual(nla.REPORT["suppressed_steps"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
