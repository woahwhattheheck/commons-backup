"""Focused full-interpreter tests for the corrected Gemini EGG timing frontier."""
import copy
import os
from pathlib import Path
import types
import unittest
from unittest.mock import patch

import gemini_egg_timing as gt
import sale_window as sw

REFERENCE = Path(os.environ.get("TITAN_REFERENCE", "checks/reference"))
PASS = {"farmer": ["PASS"], "hands": [], "market": []}


def action(*market):
    out = copy.deepcopy(PASS)
    out["market"] = list(market)
    return out


class ReceiptAttributionUnitTests(unittest.TestCase):
    class Env:
        configuration = {"maxMarketOrdersPerTurn": 10}

    @staticmethod
    def _tape(own):
        return [[a, action()] for a in own]

    @staticmethod
    def _report(
        *,
        source_sold=12,
        source_cash=120,
        target_sold=12,
        target_cash=120,
        own_delta=50,
    ):
        return {
            "baseline": {
                "reports": [
                    {"rows": [{
                        "seat": 0,
                        "row": 0,
                        "sold": source_sold,
                        "sale_cash": source_cash,
                    }]},
                    {"rows": []},
                ]
            },
            "candidate": {
                "reports": [
                    {"rows": []},
                    {"rows": [{
                        "seat": 0,
                        "row": 0,
                        "sold": target_sold,
                        "sale_cash": target_cash,
                    }]},
                ]
            },
            "window_cash_delta": [own_delta, 0],
            "window_margin_delta": own_delta,
            "terminal_margin_delta": None,
            "engagement": "SALE_FILL_CHANGED",
        }

    def _search(self, result):
        fake = types.SimpleNamespace(
            shift_sale=lambda tape, *args: copy.deepcopy(tape),
            compare=lambda *args: result,
        )
        tape = self._tape([action(["SELL", "EGG", 12]), action()])
        with patch.object(gt, "_load_sale_window", return_value=fake):
            return gt.search(
                None,
                None,
                self.Env(),
                tape,
                start_step=4,
                seat=0,
                source_turn=0,
                source_row_index=0,
                max_delay=1,
            )

    def test_net_cash_gain_without_sale_receipt_gain_is_not_positive(self):
        # Models the reviewed predecessor: delaying the sale can make an
        # intervening spend fail, leaving more terminal/window cash even when
        # the EGG receipt itself does not improve.
        report = self._search(
            self._report(source_cash=120, target_cash=120, own_delta=50)
        )
        row = report["candidates"][0]
        self.assertEqual(row["sale_cash_delta"], 0)
        self.assertEqual(row["own_cash_delta"], 50)
        self.assertIsNone(report["best_positive"])

    def test_sale_receipt_gain_is_positive_even_if_window_cash_is_negative(self):
        report = self._search(
            self._report(source_cash=120, target_cash=144, own_delta=-30)
        )
        row = report["best_positive"]
        self.assertIsNotNone(row)
        self.assertEqual(row["source_filled_units"], row["target_filled_units"])
        self.assertEqual(row["sale_cash_delta"], 24)
        self.assertEqual(row["own_cash_delta"], -30)

    def test_fewer_units_never_claims_sale_receipt_gain(self):
        report = self._search(
            self._report(
                source_sold=12,
                source_cash=120,
                target_sold=11,
                target_cash=220,
                own_delta=100,
            )
        )
        row = report["candidates"][0]
        self.assertFalse(row["realized_retiming"])
        self.assertEqual(row["sale_cash_delta"], 0)
        self.assertIsNone(report["best_positive"])

    def test_sale_cash_metric_fails_closed_on_non_plain_int(self):
        result = self._report()
        result["baseline"]["reports"][0]["rows"][0]["sale_cash"] = True
        self.assertIsNone(gt._sale_cash(result, "baseline", 0, 0, 0))

    def test_malformed_source_sale_cash_cannot_mint_positive(self):
        report = self._search(
            self._report(source_cash=True, target_cash=120, own_delta=120)
        )
        row = report["candidates"][0]
        self.assertTrue(row["realized_retiming"])
        self.assertFalse(row["receipt_evidence_valid"])
        self.assertEqual(row["sale_cash_delta"], 0)
        self.assertIsNone(report["best_positive"])

    def test_missing_source_sale_cash_cannot_mint_positive(self):
        result = self._report(source_cash=0, target_cash=120, own_delta=120)
        del result["baseline"]["reports"][0]["rows"][0]["sale_cash"]
        report = self._search(result)
        self.assertFalse(report["candidates"][0]["receipt_evidence_valid"])
        self.assertIsNone(report["best_positive"])

    def test_malformed_target_sale_cash_cannot_mint_positive(self):
        report = self._search(
            self._report(source_cash=0, target_cash=True, own_delta=120)
        )
        self.assertFalse(report["candidates"][0]["receipt_evidence_valid"])
        self.assertIsNone(report["best_positive"])

    def test_genuine_zero_source_receipt_remains_valid(self):
        report = self._search(
            self._report(source_cash=0, target_cash=120, own_delta=120)
        )
        row = report["best_positive"]
        self.assertIsNotNone(row)
        self.assertTrue(row["receipt_evidence_valid"])
        self.assertEqual(row["sale_cash_delta"], 120)

    def test_duplicate_matching_metric_rows_fail_closed(self):
        result = self._report(source_cash=0, target_cash=120, own_delta=120)
        source_row = result["baseline"]["reports"][0]["rows"][0]
        result["baseline"]["reports"][0]["rows"].append(copy.deepcopy(source_row))
        report = self._search(result)
        self.assertFalse(report["candidates"][0]["receipt_evidence_valid"])
        self.assertIsNone(report["best_positive"])


class GeminiEggTimingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine, cls.Struct = sw.load_engine(REFERENCE)

    def fixture(self, *, step=4, stock=12, rival_stock=0, inventory=10000,
                shops=("BAKERY",) * 8, cap=10):
        state, env = sw.initialize(self.engine, self.Struct, configuration={
            "weedSpawnChance": 0,
            "maxMarketOrdersPerTurn": cap,
        })
        for seat, s in enumerate(state):
            s.observation.step = step
            s.observation.day = step // 24
            s.observation.hour = step % 24
            s.observation.private["shed"]["EGG"] = stock if seat == 0 else rival_stock
            s.observation.farms[seat]["money"] = 0
        state[0].observation.market["inventory"]["EGG"] = inventory
        state[0].observation.town["unlocked_shops"] = list(shops)
        self.engine._refresh_prices(state[0].observation.market)
        return state, env

    @staticmethod
    def tape(own, rival=None):
        rival = rival or [action() for _ in own]
        return [[a, b] for a, b in zip(own, rival)]

    def test_town_egg_absorption_creates_profitable_later_window(self):
        state, env = self.fixture()
        own = [action(["SELL", "EGG", 12])] + [action() for _ in range(5)]
        report = gt.search(
            self.engine, state, env, self.tape(own), start_step=4, seat=0,
            source_turn=0, source_row_index=0, max_delay=5,
        )
        self.assertIsNotNone(report["best_positive"])
        self.assertGreater(report["best_positive"]["sale_cash_delta"], 0)
        self.assertTrue(report["best_positive"]["realized_retiming"])
        self.assertEqual(
            report["best_positive"]["target_filled_units"],
            report["best_positive"]["source_filled_units"],
        )
        # Step 8 consumes after market; step 9 is the first placement that can
        # capture both the step-4 and step-8 BAKERY depletion pulses.
        self.assertEqual(report["best_positive"]["target_step"], 9)
        self.assertFalse(report["policy_claim"])
        self.assertFalse(report["literal_direct_egg_short_squeeze_supported"])

    def test_fixed_rival_supply_can_destroy_waiting_edge(self):
        state, env = self.fixture(rival_stock=200)
        own = [action(["SELL", "EGG", 12])] + [action() for _ in range(2)]
        # Rival supply is quoted in the same source turn. The baseline receives
        # the precommit quote, while every delayed candidate faces that supply
        # after commit (net of town depletion), so waiting must not be blessed.
        rival = [action(["SELL", "EGG", 200]), action(), action()]
        report = gt.search(
            self.engine, state, env, self.tape(own, rival), start_step=4, seat=0,
            source_turn=0, source_row_index=0, max_delay=2,
        )
        self.assertIsNone(report["best_positive"])
        self.assertTrue(any(row["realized_retiming"] for row in report["candidates"]))

    def test_refuses_non_egg_or_nonpositive_source(self):
        state, env = self.fixture()
        for row in (["SELL", "MILK", 1], ["BUY_PRODUCT", "EGG", 1],
                    ["SELL", "EGG", 0], ["SELL", "EGG", -1]):
            tape = self.tape([action(row), action()])
            with self.assertRaises(ValueError):
                gt.search(
                    self.engine, state, env, tape, start_step=4, seat=0,
                    source_turn=0, source_row_index=0, max_delay=1,
                )

    def test_destination_never_displaces_live_economics(self):
        full = self.tape([
            action(["SELL", "EGG", 1]),
            action(*([["HIRE"]] * 10)),
            action(["PASS"], ["HIRE"]),
        ])
        self.assertEqual(
            gt.candidate_destinations(full, seat=0, source_turn=0, max_delay=2, cap=10),
            [(2, 0)],
        )

    def test_input_tape_is_immutable(self):
        state, env = self.fixture()
        tape = self.tape([action(["SELL", "EGG", 12]), action(), action()])
        before = sw.digest(tape)
        gt.search(
            self.engine, state, env, tape, start_step=4, seat=0,
            source_turn=0, source_row_index=0, max_delay=2,
        )
        self.assertEqual(before, sw.digest(tape))

    def test_zero_stock_is_not_a_realized_retiming(self):
        state, env = self.fixture(stock=0)
        tape = self.tape([action(["SELL", "EGG", 12]), action()])
        report = gt.search(
            self.engine, state, env, tape, start_step=4, seat=0,
            source_turn=0, source_row_index=0, max_delay=1,
        )
        self.assertIsNone(report["best_positive"])
        self.assertEqual(report["candidates"][0]["source_filled_units"], 0)
        self.assertFalse(report["candidates"][0]["realized_retiming"])


if __name__ == "__main__":
    unittest.main()
