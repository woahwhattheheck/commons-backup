"""Behavioral tests execute the complete pinned interpreter, including EOD."""
import copy
import json
import os
from pathlib import Path
import unittest

import sale_window as sw

REFERENCE = Path(os.environ.get("TITAN_REFERENCE", "checks/reference"))
PASS = {"farmer": ["PASS"], "hands": [], "market": []}


def action(*market):
    out = copy.deepcopy(PASS)
    out["market"] = list(market)
    return out


class SaleWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine, cls.Struct = sw.load_engine(REFERENCE)

    def fixture(self, step=4, seat=0, stock=12, rival_stock=0, inventory=10030,
                item="MILK", cap=10, terminal=720, shops=()):
        e = self.engine
        state, env = sw.initialize(e, self.Struct, configuration={
            "weedSpawnChance": 0, "maxMarketOrdersPerTurn": cap, "episodeSteps": terminal})
        for i, s in enumerate(state):
            s.observation.step = step
            s.observation.day = step // 24
            s.observation.hour = step % 24
            s.observation.private["shed"][item] = stock if i == seat else rival_stock
            s.observation.farms[i]["money"] = 0
        state[0].observation.market["inventory"][item] = inventory
        state[0].observation.town["unlocked_shops"] = list(shops)
        e._refresh_prices(state[0].observation.market)
        return state, env

    def tape(self, seat, own, rival=None):
        rival = rival or [action() for _ in own]
        return [[a, b] if seat == 0 else [b, a] for a, b in zip(own, rival)]

    def test_no_change_control_and_input_immutability(self):
        state, env = self.fixture()
        tape = self.tape(0, [action(["SELL", "MILK", 12]), action()])
        before = sw.digest([state, env, tape])
        result = sw.compare(self.engine, state, env, tape, tape, 4, 0)
        self.assertEqual(result["engagement"], "UNCHANGED_RETURN")
        self.assertEqual(result["baseline"], result["candidate"])
        self.assertEqual(result["window_cash_delta"], [0, 0])
        self.assertEqual(before, sw.digest([state, env, tape]))
        self.assertIsNone(result["terminal_margin_delta"])

    def test_town_absorption_rewards_waiting_both_seats(self):
        for seat in (0, 1):
            state, env = self.fixture(seat=seat, shops=["SMOOTHIE_SHOP"] * 4)
            now = self.tape(seat, [action(["SELL", "MILK", 12]), action()])
            later = sw.shift_sale(now, seat, 0, 0, 1, 0)
            result = sw.compare(self.engine, state, env, now, later, 4, seat)
            self.assertEqual(result["engagement"], "SALE_FILL_CHANGED")
            self.assertGreater(result["window_cash_delta"][seat], 0)
            self.assertEqual(result["candidate"]["reports"][0]["rows"][0]["raw"], ["PASS"])

    def test_rival_supply_reverses_waiting_advantage(self):
        for seat in (0, 1):
            state, env = self.fixture(seat=seat, rival_stock=24, shops=["SMOOTHIE_SHOP"] * 4)
            now = self.tape(seat, [action(["SELL", "MILK", 12]), action()],
                            [action(["SELL", "MILK", 24]), action()])
            later = sw.shift_sale(now, seat, 0, 0, 1, 0)
            result = sw.compare(self.engine, state, env, now, later, 4, seat)
            self.assertLess(result["window_cash_delta"][seat], 0)

    def test_floor_sales_are_fills_without_supply_growth(self):
        state, env = self.fixture(stock=4, inventory=10076)
        report = sw.observed_step(self.engine, state, env, [action(["SELL", "MILK", 4]), action()], 4)
        self.assertEqual(report["rows"][0]["sold"], 4)
        self.assertEqual(report["rows"][0]["sale_cash"], 4)
        self.assertEqual(state[0].observation.market["inventory"]["MILK"], 10076)

    def test_capped_changes_not_mistaken_for_filled_sales(self):
        state, env = self.fixture(cap=1)
        tape = self.tape(0, [action(["PASS"], ["SELL", "MILK", 12]), action(["PASS"])])
        moved = sw.shift_sale(tape, 0, 0, 1, 1, 1)
        result = sw.compare(self.engine, state, env, tape, moved, 4, 0)
        self.assertEqual(result["engagement"], "CHANGED_WITHOUT_SALE_FILL_DELTA")
        self.assertEqual(result["window_cash_delta"], [0, 0])
        self.assertEqual(result["baseline"]["outcome_sha256"], result["candidate"]["outcome_sha256"])
        self.assertNotEqual(result["baseline"]["state_sha256"], result["candidate"]["state_sha256"])

    def test_minimum_one_cap_is_engine_contract(self):
        state, env = self.fixture(cap=0, stock=1)
        report = sw.observed_step(self.engine, state, env, [action(["SELL", "MILK", 1]), action()], 4)
        self.assertEqual(report["rows"][0]["sold"], 1)

    def test_empty_shed_requested_sales_are_not_fills(self):
        state, env = self.fixture(stock=0)
        tape = self.tape(0, [action(["SELL", "MILK", 12]), action()])
        result = sw.compare(self.engine, state, env, tape, sw.shift_sale(tape, 0, 0, 0, 1, 0), 4, 0)
        self.assertEqual(result["engagement"], "CHANGED_WITHOUT_SALE_FILL_DELTA")
        self.assertEqual(sum(r["sold"] for t in result["baseline"]["reports"] for r in t["rows"]), 0)

    def test_eod_delivery_not_available_to_same_turn_market(self):
        state, env = self.fixture(step=23, stock=0)
        state[0].observation.private["inventories"] = [{"MILK": 12}]
        tape = self.tape(0, [action(), action(["SELL", "MILK", 12])])
        earlier = sw.shift_sale(tape, 0, 1, 0, 0, 0)
        result = sw.compare(self.engine, state, env, tape, earlier, 23, 0)
        self.assertEqual(result["candidate"]["reports"][0]["market_entry_shed" ][0]["MILK"], 0)
        self.assertEqual(result["candidate"]["reports"][0]["rows"][0]["sold"], 0)
        self.assertGreater(result["baseline"]["reports"][1]["rows"][0]["sold"], 0)
        self.assertLess(result["window_cash_delta"][0], 0)

    def test_unit_drop_is_available_before_market(self):
        state, env = self.fixture(stock=0)
        state[0].observation.private["inventories"] = [{"MILK": 3}]
        a = action(["SELL", "MILK", 3])
        a["farmer"] = ["DROP"]
        report = sw.observed_step(self.engine, state, env, [a, action()], 4)
        self.assertEqual(report["market_entry_shed"][0]["MILK"], 3)
        self.assertEqual(report["rows"][0]["sold"], 3)

    def test_partial_and_duplicate_sales_share_actual_stock(self):
        state, env = self.fixture(stock=5)
        report = sw.observed_step(self.engine, state, env,
                                 [action(["SELL", "MILK", 4], ["SELL", "MILK", 4]), action()], 4)
        self.assertEqual([r["sold"] for r in report["rows"]], [4, 1])

    def test_source_slot_placeholder_preserves_atomic_funding_order(self):
        state, env = self.fixture(stock=2, rival_stock=2, inventory=10000)
        tape = self.tape(0, [action(["SELL", "MILK", 1], ["HIRE"]), action()],
                            [action(["SELL", "MILK", 1], ["HIRE"]), action()])
        moved = sw.shift_sale(tape, 0, 0, 0, 1, 0)
        self.assertEqual(moved[0][0]["market"], [["PASS"], ["HIRE"]])
        result = sw.compare(self.engine, state, env, tape, moved, 4, 0)
        self.assertNotEqual(result["baseline"]["state_sha256"], result["candidate"]["state_sha256"])

    def test_terminal_margin_accounts_for_rival_cash(self):
        state, env = self.fixture(step=717, stock=12, rival_stock=24, terminal=720)
        tape = self.tape(0, [action(["SELL", "MILK", 12]), action()],
                            [action(["SELL", "MILK", 24]), action()])
        result = sw.compare(self.engine, state, env, tape, sw.shift_sale(tape, 0, 0, 0, 1, 0), 717, 0)
        d = result["window_cash_delta"]
        self.assertNotEqual(d[1], 0)
        self.assertEqual(result["terminal_margin_delta"], d[0] - d[1])
        self.assertEqual(result["candidate"]["rewards"], result["candidate"]["money"])

    def test_no_terminal_claim_for_nonterminal_window(self):
        state, env = self.fixture()
        tape = self.tape(0, [action(["SELL", "MILK", 12])])
        r = sw.compare(self.engine, state, env, tape, tape, 4, 0)
        self.assertFalse(r["baseline"]["terminal"])
        self.assertIsNone(r["terminal_margin_delta"])

    def test_source_and_destination_validation(self):
        tape = self.tape(0, [action(["SELL", "MILK", 1]), action(["HIRE"])])
        for args in [(0, 0, 0, 1, 0), (0, 0, 0, 0, 0), (0, 0, 0, 2, 0),
                     (0, 0, 1, 1, 0), (0, 0, 0, 1, 2), (True, 0, 0, 1, 0)]:
            with self.assertRaises(ValueError): sw.shift_sale(tape, *args)
        for quantity in (True, -1, 0, "4", 1.5):
            bad = self.tape(0, [action(["SELL", "MILK", quantity]), action()])
            with self.assertRaises(ValueError): sw.shift_sale(bad, 0, 0, 0, 1, 0)

    def test_cross_turn_alias_does_not_change_unrelated_actions(self):
        a = action(["SELL", "MILK", 1])
        tape = [[a, PASS], [PASS, PASS], [a, PASS]]
        before = sw.digest(tape)
        moved = sw.shift_sale(tape, 0, 0, 0, 1, 0)
        self.assertEqual(moved[2], tape[2])
        self.assertEqual(moved[0][0]["market"], [["PASS"]])
        self.assertEqual(before, sw.digest(tape))

    def test_reject_opponent_or_unit_action_drift(self):
        state, env = self.fixture()
        tape = self.tape(0, [action()])
        for seat, key, value in [(1, "market", [["HIRE"]]), (0, "farmer", ["NORTH"])]:
            bad = copy.deepcopy(tape)
            bad[0][seat][key] = value
            with self.assertRaises(ValueError): sw.compare(self.engine, state, env, tape, bad, 4, 0)

    def test_snapshot_step_and_post_done_rejection(self):
        state, env = self.fixture(step=718)
        tape = self.tape(0, [action(), action()])
        with self.assertRaises(ValueError): sw.replay(self.engine, state, env, tape, 717)
        with self.assertRaises(ValueError): sw.replay(self.engine, state, env, tape, 718)

    def test_hooks_restore_after_numeric_error(self):
        state, env = self.fixture()
        e = self.engine
        before = e._parse_order, e._commit_unit, e._process_market
        with self.assertRaises(OverflowError):
            sw.observed_step(e, state, env, [action(["SELL", "MILK", float("inf")]), action()], 4)
        self.assertEqual(before, (e._parse_order, e._commit_unit, e._process_market))

    def test_native_census_uses_official_parsed_type(self):
        import run_native
        state, env = sw.initialize(self.engine, self.Struct)
        state[0].observation.private["shed"]["MILK"] = 3
        tape = self.tape(0, [action(["SELL", "MILK", 9])])
        result, census, outcomes = run_native.audit(self.engine, (state, env), tape, 0)
        self.assertEqual(census, {"exposed_sell_rows": 1, "filled_sell_rows": 1, "filled_units": 3})
        self.assertEqual(len(outcomes), 4)
        self.assertTrue(all(r["status"] == "NO_FILLED_SOURCE_IN_WINDOW" for r in outcomes))
        self.assertFalse(result["terminal"])

    def test_native_witness_rejects_false_earlier_fill(self):
        import run_native
        state, env = self.fixture(step=23, stock=0)
        state[0].observation.private["inventories"] = [{"MILK": 12}]
        tape = self.tape(0, [action(), action(["SELL", "MILK", 12])])
        result = sw.compare(self.engine, state, env, tape,
                            sw.shift_sale(tape, 0, 1, 0, 0, 0), 23, 0)
        witness = run_native.timing_witness(result, 0, 24, 0, 23, 0)
        self.assertEqual(witness["source_filled_units"], 12)
        self.assertEqual(witness["destination_filled_units"], 0)
        self.assertEqual(witness["classification"], "SUPPRESSED_SALE_NOT_RETIMED")

    def test_native_witness_recognizes_fully_filled_retiming(self):
        import run_native
        state, env = self.fixture(stock=12)
        tape = self.tape(0, [action(["SELL", "MILK", 12]), action()])
        result = sw.compare(self.engine, state, env, tape,
                            sw.shift_sale(tape, 0, 0, 0, 1, 0), 4, 0)
        witness = run_native.timing_witness(result, 0, 4, 0, 5, 0)
        self.assertEqual(witness["source_filled_units"], 12)
        self.assertEqual(witness["destination_filled_units"], 12)
        self.assertEqual(witness["classification"], "REALIZED_RETIMING")

    def test_native_manifest_rejects_unauthenticated_input(self):
        import run_native
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_text("{}")
            with self.assertRaisesRegex(ValueError, "manifest identity mismatch"):
                run_native.authenticate(Path(tmp), path)

    def test_observer_complete_state_parity_corpus(self):
        rows = [[], [["PASS"]], [None, ["SELL", "MILK", 3]], [["SELL", "MILK", 99]],
                [["SELL", "MILK", 2], ["HIRE"]], [["HIRE"], ["SELL", "MILK", 2]],
                [["BUY_PRODUCT", "WHEAT", 3]], [["SELL", "MILK", "bad"]]]
        for seat in (0, 1):
            for cap in (0, 1, 3):
                for i, row in enumerate(rows):
                    state, env = self.fixture(step=23, seat=seat, stock=i, rival_stock=3,
                                              cap=cap, inventory=10070+i)
                    state[seat].observation.private["inventories"] = [{"MILK": 2}]
                    acts = self.tape(seat, [action(*row)], [action(["SELL", "MILK", 2])])[0]
                    plain, pe = copy.deepcopy((state, env))
                    for n in (0, 1): plain[n].action = copy.deepcopy(acts[n])
                    self.engine.interpreter(plain, pe)
                    sw.observed_step(self.engine, state, env, acts, 23)
                    self.assertEqual(plain, state)
                    self.assertEqual(pe, env)


if __name__ == "__main__":
    unittest.main()
