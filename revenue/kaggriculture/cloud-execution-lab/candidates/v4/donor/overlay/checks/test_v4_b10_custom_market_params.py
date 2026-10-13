# SPDX-License-Identifier: Apache-2.0
"""Regression checks for B10 fail-closed edge cases."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import r04_b10_public_supply_order as b10  # noqa: E402
import r04_full_router as r04  # noqa: E402


def obs(step: int, wool_inventory: int = 10_000, *, shops=None):
    inventory = {item: 10_000 for item in b10.PRODUCTS}
    inventory["WOOL"] = wool_inventory
    return {
        "step": step,
        "player": 0,
        "market": {"inventory": inventory},
        "town": {"unlocked_shops": list(shops or [])},
    }


def parent_action():
    return {
        "farmer": ["PASS"],
        "hands": [],
        "market": [["SELL", "MILK", 1], ["SELL", "WOOL", 1]],
    }


STANDARD_CONFIG = {"episodeSteps": 720, "maxMarketOrdersPerTurn": 10}


class CustomMarketParams(unittest.TestCase):
    def tearDown(self):
        if hasattr(r04, "B10_PUBLIC_SUPPLY_ORDER"):
            r04.B10_PUBLIC_SUPPLY_ORDER = False
        b10.ORDER.players.clear()

    def test_installed_missing_configuration_breaks_evidence_continuity(self):
        original_core = r04._v3_core
        original_mirror = r04.MIRROR_HORIZON
        original_terminal = r04.TERMINAL_FERTILIZER
        original_goose = r04.GOOSE_RESCUE
        original_place = r04.PLACE_DELIVERY
        original_goose_pass = r04.GOOSE_PASS_RESCUE
        original_b10 = r04.B10_PUBLIC_SUPPLY_ORDER
        try:
            parent = parent_action()
            empty = {"farmer": ["PASS"], "hands": [], "market": []}
            r04._v3_core = lambda observation, configuration=None: parent
            r04.MIRROR_HORIZON = False
            r04.TERMINAL_FERTILIZER = False
            r04.GOOSE_RESCUE = False
            r04.PLACE_DELIVERY = False
            r04.GOOSE_PASS_RESCUE = False
            r04.B10_PUBLIC_SUPPLY_ORDER = True
            b10.ORDER.players.clear()

            # Direct helper use can still construct a focused predecessor latch.
            b10.ORDER.apply(obs(1), empty, dict(STANDARD_CONFIG))
            self.assertIn(0, b10.ORDER.players)
            out = r04.v3_agent(obs(2, wool_inventory=10_003), None)
            self.assertIs(out, parent)
            self.assertEqual(b10.ORDER.players, {})

            # Correcting the same logical callback cannot resurrect evidence:
            # the installed strict epoch can only seed on a valid step 0.
            retry = r04.v3_agent(obs(2, wool_inventory=10_003), dict(STANDARD_CONFIG))
            self.assertIs(retry, parent)
            self.assertEqual(b10.ORDER.telemetry["reorders"], 0)
            self.assertEqual(b10.ORDER.players, {})
        finally:
            r04._v3_core = original_core
            r04.MIRROR_HORIZON = original_mirror
            r04.TERMINAL_FERTILIZER = original_terminal
            r04.GOOSE_RESCUE = original_goose
            r04.PLACE_DELIVERY = original_place
            r04.GOOSE_PASS_RESCUE = original_goose_pass
            r04.B10_PUBLIC_SUPPLY_ORDER = original_b10

    def test_falsey_malformed_overrides_fail_closed_and_clear_latch(self):
        for bad in ([], "", 0, False):
            with self.subTest(value=bad):
                tracker = b10.RivalSupplyOrder(enabled=True)
                tracker.apply(obs(1), {"farmer": ["PASS"], "hands": [], "market": []})
                self.assertIn(0, tracker.players)
                parent = parent_action()
                result = tracker.apply(
                    obs(2, wool_inventory=10_003), parent, {"marketParams": bad}
                )
                self.assertIs(result, parent)
                self.assertEqual(tracker.players, {})
                self.assertEqual(tracker.telemetry["reorders"], 0)

    def test_empty_mapping_keeps_standard_market_semantics(self):
        tracker = b10.RivalSupplyOrder(enabled=True)
        tracker.apply(
            obs(1), {"farmer": ["PASS"], "hands": [], "market": []},
            {"marketParams": {}},
        )
        parent = parent_action()
        result = tracker.apply(
            obs(2, wool_inventory=10_003), parent, {"marketParams": {}}
        )
        self.assertIsNot(result, parent)
        self.assertEqual(
            result["market"][:2],
            [["SELL", "WOOL", 1], ["SELL", "MILK", 1]],
        )

    def test_tuple_sell_rows_are_engine_noop_barriers(self):
        evidence = {item: 0 for item in b10.PRODUCTS}
        evidence["WOOL"] = 9
        cases = (
            [("SELL", "MILK", 1), ["SELL", "WOOL", 1]],
            [["SELL", "MILK", 1], ("SELL", "WOOL", 1)],
        )
        for market in cases:
            with self.subTest(market=market):
                parent = {"farmer": ["PASS"], "hands": [], "market": market}
                result, detail = b10._reorder_leading_sells(parent, evidence)
                self.assertIs(result, parent)
                self.assertIsNone(detail)
                self.assertEqual(result["market"], market)

    def test_negative_public_inventory_remains_valid_evidence_state(self):
        tracker = b10.RivalSupplyOrder(enabled=True)
        empty = {"farmer": ["PASS"], "hands": [], "market": []}

        # Focused direct trackers may start from synthetic public state; the
        # installed strict epoch is separately step-0 anchored.
        first = tracker.apply(obs(1, wool_inventory=-2), empty)
        self.assertIs(first, empty)
        self.assertEqual(tracker.players[0]["inventory"]["WOOL"], -2)

        parent = parent_action()
        result = tracker.apply(obs(2, wool_inventory=1), parent)
        self.assertIsNot(result, parent)
        self.assertEqual(
            result["market"][:2],
            [["SELL", "WOOL", 1], ["SELL", "MILK", 1]],
        )
        self.assertEqual(tracker.telemetry["reorders"], 1)

    def test_terminal_step_718_records_evidence_but_never_reorders(self):
        tracker = b10.RivalSupplyOrder(enabled=True)
        empty = {"farmer": ["PASS"], "hands": [], "market": []}
        shops = ["YARN_STORE"] * 8
        tracker.apply(obs(717, shops=shops), empty, dict(STANDARD_CONFIG))
        parent = parent_action()

        result = tracker.apply(
            obs(718, wool_inventory=10_003, shops=shops), parent, dict(STANDARD_CONFIG)
        )
        self.assertIs(result, parent)
        self.assertEqual(result["market"],
                         [["SELL", "MILK", 1], ["SELL", "WOOL", 1]])
        self.assertEqual(tracker.telemetry["confirmed_supply_transitions"], 1)
        self.assertEqual(tracker.telemetry["reorders"], 0)
        self.assertEqual(tracker.players[0]["step"], 718)

    def test_engine_unreachable_step_719_fails_closed_and_clears_latch(self):
        tracker = b10.RivalSupplyOrder(enabled=True)
        empty = {"farmer": ["PASS"], "hands": [], "market": []}
        shops = ["YARN_STORE"] * 8
        tracker.apply(obs(718, shops=shops), empty, dict(STANDARD_CONFIG))
        self.assertIn(0, tracker.players)
        parent = parent_action()
        result = tracker.apply(
            obs(719, wool_inventory=10_003, shops=shops), parent, dict(STANDARD_CONFIG)
        )
        self.assertIs(result, parent)
        self.assertEqual(tracker.players, {})
        self.assertEqual(tracker.telemetry["reorders"], 0)

    def test_nonstandard_episode_steps_clear_latch_and_cannot_reuse_evidence(self):
        empty = {"farmer": ["PASS"], "hands": [], "market": []}
        parent = parent_action()
        for bad in (719, 721, True, 720.0, "720"):
            with self.subTest(episodeSteps=bad):
                tracker = b10.RivalSupplyOrder(enabled=True)
                tracker.apply(obs(1), empty, {"episodeSteps": 720})
                self.assertIn(0, tracker.players)

                result = tracker.apply(
                    obs(2, wool_inventory=10_003), parent, {"episodeSteps": bad}
                )
                self.assertIs(result, parent)
                self.assertEqual(tracker.players, {})
                self.assertEqual(tracker.telemetry["reorders"], 0)

                retry = tracker.apply(
                    obs(2, wool_inventory=10_003), parent, {"episodeSteps": 720}
                )
                self.assertIs(retry, parent)
                self.assertEqual(tracker.telemetry["reorders"], 0)

    def test_engine_unreachable_ninth_shop_fails_closed_and_clears_latch(self):
        tracker = b10.RivalSupplyOrder(enabled=True)
        empty = {"farmer": ["PASS"], "hands": [], "market": []}
        tracker.apply(obs(3), empty, dict(STANDARD_CONFIG))
        self.assertIn(0, tracker.players)

        parent = parent_action()
        bad = obs(4, shops=["YARN_STORE"] * 9)
        result = tracker.apply(bad, parent, dict(STANDARD_CONFIG))
        self.assertIs(result, parent)
        self.assertEqual(tracker.players, {})
        self.assertEqual(tracker.telemetry["reorders"], 0)

        control = b10._town_consumption(
            obs(4, shops=["YARN_STORE"] * 8), dict(STANDARD_CONFIG))
        self.assertEqual(control["WOOL"], 16)

    def test_fresh_impossible_shop_snapshot_cannot_seed_evidence(self):
        tracker = b10.RivalSupplyOrder(enabled=True)
        parent = parent_action()
        impossible = obs(4, shops=["YARN_STORE"] * 8)
        result = tracker.apply(impossible, parent, dict(STANDARD_CONFIG))
        self.assertIs(result, parent)
        self.assertEqual(tracker.players, {})

        valid = tracker.apply(
            obs(72, shops=["YARN_STORE"]),
            {"farmer": ["PASS"], "hands": [], "market": []},
            dict(STANDARD_CONFIG),
        )
        self.assertEqual(tracker.players[0]["shops"], ("YARN_STORE",))
        self.assertEqual(tracker.players[0]["step"], 72)
        self.assertEqual(valid["market"], [])

    def test_shop_history_is_append_only_and_schedule_exact(self):
        empty = {"farmer": ["PASS"], "hands": [], "market": []}
        parent = parent_action()

        tracker = b10.RivalSupplyOrder(enabled=True)
        tracker.apply(obs(71), empty, dict(STANDARD_CONFIG))
        result = tracker.apply(
            obs(72, wool_inventory=10_003, shops=["YARN_STORE"]),
            parent, dict(STANDARD_CONFIG),
        )
        self.assertIsNot(result, parent)
        self.assertEqual(result["market"][:2],
                         [["SELL", "WOOL", 1], ["SELL", "MILK", 1]])
        self.assertEqual(tracker.players[0]["shops"], ("YARN_STORE",))

        swapped = b10.RivalSupplyOrder(enabled=True)
        swapped.apply(obs(72, shops=["YARN_STORE"]), empty, dict(STANDARD_CONFIG))
        out = swapped.apply(
            obs(73, shops=["BAKERY"]), parent, dict(STANDARD_CONFIG)
        )
        self.assertIs(out, parent)
        self.assertEqual(swapped.players, {})

        mid = b10.RivalSupplyOrder(enabled=True)
        mid.apply(obs(72, shops=["YARN_STORE"]), empty, dict(STANDARD_CONFIG))
        out = mid.apply(
            obs(73, shops=["YARN_STORE", "BAKERY"]), parent, dict(STANDARD_CONFIG)
        )
        self.assertIs(out, parent)
        self.assertEqual(mid.players, {})

        jump = b10.RivalSupplyOrder(enabled=True)
        jump.apply(obs(71), empty, dict(STANDARD_CONFIG))
        out = jump.apply(
            obs(72, shops=["YARN_STORE", "BAKERY"]), parent, dict(STANDARD_CONFIG)
        )
        self.assertIs(out, parent)
        self.assertEqual(jump.players, {})

    def test_tuple_shop_vector_is_malformed_public_state(self):
        tracker = b10.RivalSupplyOrder(enabled=True)
        malformed = obs(1)
        malformed["town"]["unlocked_shops"] = ("YARN_STORE",)
        parent = parent_action()
        result = tracker.apply(malformed, parent, dict(STANDARD_CONFIG))
        self.assertIs(result, parent)
        self.assertEqual(tracker.players, {})

    def test_malformed_step_breaks_evidence_continuity(self):
        tracker = b10.RivalSupplyOrder(enabled=True)
        empty = {"farmer": ["PASS"], "hands": [], "market": []}
        tracker.apply(obs(1), empty)
        self.assertIn(0, tracker.players)

        malformed = obs(2, wool_inventory=10_003)
        malformed["step"] = "2"
        parent = parent_action()
        result = tracker.apply(malformed, parent)
        self.assertIs(result, parent)
        self.assertEqual(tracker.players, {})
        self.assertEqual(tracker.telemetry["reorders"], 0)

        result = tracker.apply(obs(2, wool_inventory=10_003), parent)
        self.assertIs(result, parent)
        self.assertEqual(tracker.telemetry["reorders"], 0)

    def test_unidentifiable_player_clears_all_evidence_latches(self):
        tracker = b10.RivalSupplyOrder(enabled=True)
        empty = {"farmer": ["PASS"], "hands": [], "market": []}
        tracker.apply(obs(1), empty)
        other = obs(1)
        other["player"] = 1
        tracker.apply(other, empty)
        self.assertEqual(set(tracker.players), {0, 1})

        malformed = obs(2)
        malformed["player"] = True
        parent = parent_action()
        result = tracker.apply(malformed, parent)
        self.assertIs(result, parent)
        self.assertEqual(tracker.players, {})
        self.assertEqual(tracker.telemetry["reorders"], 0)


if __name__ == "__main__":
    unittest.main()
