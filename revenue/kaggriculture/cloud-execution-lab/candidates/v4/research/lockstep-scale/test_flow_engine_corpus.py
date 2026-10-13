# SPDX-License-Identifier: MIT
"""Independent oracle acceptance. FLOW_ENGINE_DIR must point to pinned sources.

These are unittest assertions, so python -O does not remove the checks. The
reconstructed requested-flow formula is a negative control, NOT executed donor
bytes. Bounds-source acceptance is separate from this corpus-generator gate.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import flow_engine_corpus as corpus

ENGINE_DIR = Path(os.environ.get("FLOW_ENGINE_DIR", str(corpus.default_engine_dir())))


def requested_point(record, product):
    """Reproduce only the displayed donor premise, without claiming raw custody."""
    inp = record["input"]
    total = inp["current"]["market"]["inventory"][product] - inp["previous"]["market"]["inventory"][product]
    total -= record["oracle"]["town_inventory_delta"][product]
    for order in inp["submitted_action"].get("market", []) or []:
        if not order or len(order) < 3 or order[1] != product:
            continue
        try:
            q = max(0, int(order[2]))
        except (TypeError, ValueError, OverflowError):
            continue
        if order[0] == "SELL":
            total -= q
        elif order[0] == "BUY_PRODUCT":
            total += q
    return total


class FlowEngineCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = corpus.load_engine(ENGINE_DIR)
        cls.records = corpus.build_corpus(cls.engine)
        cls.index = {r["id"]: r for r in cls.records}

    def row(self, name, seat=0):
        return self.index[f"{name}/seat{seat}"]

    def test_panel_is_complete_and_reproducible(self):
        self.assertEqual(len(self.records), 236)
        self.assertEqual(len(self.index), 236)
        self.assertEqual(hashlib.sha256(corpus.corpus_bytes(self.records)).hexdigest(),
                         "24f50b86efffec1c38be32bd39fe4c3abbea497b2c7bb18e149abb6044f22639")
        second = corpus.build_corpus(self.engine, random_worlds=0)
        self.assertEqual(corpus.corpus_bytes(second), corpus.corpus_bytes(self.records[:44]))

    def test_every_audit_matches_pristine_and_balances_all_products(self):
        for r in self.records:
            with self.subTest(case=r["id"]):
                truth, inp = r["oracle"], r["input"]
                self.assertIs(truth["audit_matches_pristine"], True)
                for p in self.engine.PRODUCTS:
                    observed = inp["current"]["market"]["inventory"][p] - inp["previous"]["market"]["inventory"][p]
                    self.assertEqual(observed, truth["own_admitted_net"][p] +
                         truth["opponent_admitted_net"][p] + truth["town_inventory_delta"][p])

    def test_input_excludes_oracle_and_rival_private_and_seed(self):
        for r in self.records:
            inp = r["input"]
            self.assertEqual(set(inp), {"previous", "current", "submitted_action", "configuration"})
            self.assertNotIn("seed", inp["configuration"])
            for obs in (inp["previous"], inp["current"]):
                self.assertEqual(set(obs), {"player", "step", "day", "hour", "farms", "private", "market", "town"})
                self.assertEqual(len(obs["farms"]), 2)
                self.assertTrue(all("private" not in farm for farm in obs["farms"]))
                self.assertIsInstance(obs["private"], dict)
            self.assertNotIn("oracle", inp)
            self.assertNotIn("rival_action", inp)

    def test_zero_cash_alone_fabricates_two_hundred_unit_dump(self):
        for seat in (0, 1):
            r = self.row("cash_zero_false_dump", seat)
            self.assertEqual(r["oracle"]["own_admitted_net"]["WHEAT"], 0)
            self.assertEqual(r["oracle"]["opponent_admitted_net"]["WHEAT"], 0)
            self.assertEqual(requested_point(r, "WHEAT"), 200)

    def test_full_shed_alone_fabricates_dump(self):
        for seat in (0, 1):
            r = self.row("shed_full_false_dump", seat)
            self.assertEqual(r["oracle"]["own_admitted_net"]["WHEAT"], 0)
            self.assertEqual(requested_point(r, "WHEAT"), 200)

    def test_partial_fills_are_not_requests(self):
        for seat in (0, 1):
            for name, p in (("cash_partial", "WHEAT"), ("capacity_partial", "FERTILIZER")):
                r = self.row(name, seat)
                buy = r["oracle"]["own_physical_fills"]["BUY_PRODUCT"][p]
                self.assertGreater(buy, 0)
                self.assertLess(buy, 200)
                self.assertEqual(requested_point(r, p), 200-buy)
                self.assertEqual(r["oracle"]["opponent_admitted_net"][p], 0)

    def test_unsupported_product_cannot_be_bought(self):
        for seat in (0, 1):
            r = self.row("unsupported_buy", seat)
            self.assertEqual(r["oracle"]["own_physical_fills"]["BUY_PRODUCT"], {})
            self.assertEqual(requested_point(r, "MILK"), 200)

    def test_raw_dead_suffix_and_blank_slots_cannot_execute(self):
        for name in ("raw_dead_suffix", "blank_owns_slot", "normalized_zero_cap"):
            for seat in (0, 1):
                r = self.row(name, seat)
                self.assertEqual(r["oracle"]["own_admitted_net"]["WHEAT"], 0)
                self.assertEqual(requested_point(r, "WHEAT"), 200)
                self.assertEqual(r["input"]["submitted_action"]["market"][0], [])

    def test_partial_sell_can_hide_real_rival_flow(self):
        for seat in (0, 1):
            r = self.row("partial_sell_hides_rival", seat)
            self.assertEqual(r["oracle"]["own_physical_fills"]["SELL"]["WHEAT"], 3)
            self.assertEqual(r["oracle"]["opponent_admitted_net"]["WHEAT"], 20)
            self.assertEqual(requested_point(r, "WHEAT"), -177)

    def test_floor_sale_is_physical_but_not_inventory_flow(self):
        for seat in (0, 1):
            r = self.row("floor_sold_not_admitted", seat)
            self.assertEqual(r["oracle"]["own_physical_fills"]["SELL"]["MILK"], 50)
            self.assertEqual(r["oracle"]["own_admitted_net"]["MILK"], 0)
            self.assertEqual(requested_point(r, "MILK"), -50)

    def test_precommit_pair_can_admit_both_floor_crossing_units(self):
        for seat in (0, 1):
            r = self.row("paired_floor_crossing", seat)
            self.assertEqual(r["input"]["current"]["market"]["inventory"]["MILK"], 10077)
            self.assertEqual(r["oracle"]["own_admitted_net"]["MILK"], 1)
            self.assertEqual(r["oracle"]["opponent_admitted_net"]["MILK"], 1)
            self.assertEqual(r["oracle"]["own_physical_fills"]["SELL"]["MILK"], 2)

    def test_town_is_not_clipped_at_zero(self):
        r = self.row("town_crosses_zero")
        self.assertEqual(r["input"]["current"]["market"]["inventory"]["WHEAT"], -2)
        self.assertEqual(r["input"]["current"]["market"]["inventory"]["WOOL"], -5)
        self.assertEqual(r["oracle"]["town_inventory_delta"]["WOOL"], -5)
        self.assertTrue(all(x == 0 for x in r["oracle"]["opponent_admitted_net"].values()))

    def test_existing_negative_inventory_is_preserved(self):
        r = self.row("negative_market_inventory")
        self.assertEqual(r["input"]["previous"]["market"]["inventory"]["WHEAT"], -5)
        self.assertEqual(r["input"]["current"]["market"]["inventory"]["WHEAT"], -7)

    def test_eod_new_shop_is_not_previous_turn_consumption(self):
        r = self.row("eod_shop_chronology")
        self.assertEqual(len(r["input"]["previous"]["town"]["unlocked_shops"]), 1)
        self.assertEqual(len(r["input"]["current"]["town"]["unlocked_shops"]), 2)
        self.assertEqual({p: d for p, d in r["oracle"]["town_inventory_delta"].items() if d},
                         {"WHEAT": -1, "EGG": -1})
        self.assertEqual(r["input"]["current"]["step"], 72)

    def test_eod_deposits_are_separate_from_market_fills(self):
        r = self.row("eod_carry_is_not_market")
        self.assertEqual(r["oracle"]["own_admitted_net"]["WHEAT"], 5)
        self.assertEqual(r["input"]["current"]["private"]["shed"]["WHEAT"], 99)
        self.assertEqual(r["input"]["current"]["private"]["inventories"], [{}])

    def test_numeric_quantity_forms_follow_actual_parser(self):
        r = self.row("numeric_quantity_forms")
        fills = r["oracle"]["own_physical_fills"]
        self.assertEqual(fills["BUY_PRODUCT"], {"WHEAT": 3, "FERTILIZER": 1})
        self.assertEqual(fills["SELL"], {"WHEAT": 1})

    def test_audit_restores_hooks_on_engine_exception(self):
        commit, town = self.engine._commit_unit, self.engine._town_consume
        bad = dict(name="bad_fixture", seat=0, shops=["NOT_A_SHOP"], step=0)
        with self.assertRaises(KeyError):
            corpus.run_case(self.engine, bad)
        self.assertIs(self.engine._commit_unit, commit)
        self.assertIs(self.engine._town_consume, town)

    def test_each_source_dependency_is_authenticated(self):
        for name in corpus.ENGINE_PINS:
            with self.subTest(source=name), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                for filename in corpus.ENGINE_PINS:
                    (root / filename).write_bytes((ENGINE_DIR / filename).read_bytes())
                p = root / name
                p.write_bytes(p.read_bytes() + b"\n ")
                with self.assertRaisesRegex(ValueError, "source mismatch"):
                    corpus.load_engine(root)
                p.unlink()
                with self.assertRaises(OSError):
                    corpus.load_engine(root)

    def test_cli_never_overwrites_existing_output(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "existing.jsonl"
            out.write_text("preserve me\n")
            command = [sys.executable]
            if not __debug__:
                command.append("-O")
            command += [str(Path(corpus.__file__)), "--engine", str(ENGINE_DIR), "--output", str(out)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 2)
            self.assertIn("output already exists", result.stderr)
            self.assertEqual(out.read_text(), "preserve me\n")

    def test_all_named_controls_are_seat_symmetric(self):
        for spec in corpus.cases(0):
            if spec["seat"]:
                continue
            a, b = self.row(spec["name"], 0), self.row(spec["name"], 1)
            for key in ("own_admitted_net", "opponent_admitted_net", "town_inventory_delta",
                        "own_physical_fills", "opponent_physical_fills"):
                with self.subTest(name=spec["name"], key=key):
                    self.assertEqual(a["oracle"][key], b["oracle"][key])


if __name__ == "__main__":
    unittest.main(verbosity=2)
