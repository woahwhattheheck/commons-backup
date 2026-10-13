# SPDX-License-Identifier: Apache-2.0
"""Independent full-engine lifecycle and instrumentation acceptance for W2.

Run with AFTERCARE_REFERENCE pointing at the authenticated checks/reference tree.
No candidate helper is substituted or required by this oracle-only suite.
"""
from __future__ import annotations

import copy
import os
from pathlib import Path
import tempfile
import unittest

import aftercare_engine as a

REFERENCE = Path(os.environ.get("AFTERCARE_REFERENCE", "checks/reference"))


class AftercareEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.oracle = a.Oracle(REFERENCE)
        cls.rows = {case.name: cls.oracle.pair(case) for case in a.corpus()}

    def row(self, species="GOOSE", seat=0, kind="entry-fed"):
        return self.rows[f"{species}:{seat}:{kind}"]

    def test_complete_frozen_corpus(self):
        self.assertEqual(len(self.rows), 60)
        self.assertEqual(len({r["initial_hash"] for r in self.rows.values()}), 48)
        self.assertEqual(sum(r["transitions"] for r in self.rows.values()), 60600)
        self.assertTrue(all(r["synthetic"] for r in self.rows.values()))
        self.assertTrue(all(r["source_mode"] == "manual_intervention" for r in self.rows.values()))

    def test_real_terminal_status_and_seat_reward_arithmetic(self):
        for row in self.rows.values():
            with self.subTest(case=row["case"]["name"]):
                seat = row["case"]["seat"]
                cash = row["terminal_cash"]
                self.assertEqual(row["terminal_status"], [["DONE", "DONE"]]*2)
                self.assertEqual(row["delta_own"], cash[1][seat] - cash[0][seat])
                self.assertEqual(row["delta_rival"], cash[1][1-seat] - cash[0][1-seat])
                self.assertEqual(row["delta_margin"], row["delta_own"] - row["delta_rival"])

    def test_care_banked_after_not_before_same_night_production(self):
        for species in self.oracle.engine.ANIMALS:
            for seat in (0, 1):
                row = self.row(species, seat)
                base, candidate = [x[0]["tile"] for x in row["eod_milestones"]]
                self.assertEqual(base["yield_units"], 1)
                self.assertEqual(candidate["yield_units"], 1)
                self.assertEqual(base["pending_care_bonus"], 0)
                self.assertEqual(candidate["pending_care_bonus"], 1)

    def test_bonus_survives_to_species_production_event(self):
        for species in self.oracle.engine.ANIMALS:
            for seat in (0, 1):
                row = self.row(species, seat)
                base, candidate = [x[-1]["tile"] for x in row["eod_milestones"]]
                self.assertEqual(candidate["yield_units"]-base["yield_units"], 1)
                self.assertEqual(candidate["pending_care_bonus"], 0)
                self.assertEqual(row["production_day"],
                                 self.oracle.engine.ANIMALS[species]["first_yield_day"]+
                                 self.oracle.engine.ANIMALS[species]["interval"])

    def test_one_extra_unit_physically_sold_and_no_extra_wheat(self):
        expected = {"GOOSE": 50, "COW": 169, "SHEEP": 209}
        for species, cash in expected.items():
            for seat in (0, 1):
                row = self.row(species, seat)
                self.assertEqual(row["product_sold"], [2, 3])
                self.assertEqual(row["wheat_consumed"][0], row["wheat_consumed"][1])
                self.assertEqual(row["wheat_bought"], [0, 0])
                self.assertEqual(row["delta_own"], cash)
                self.assertEqual(row["delta_rival"], 0)

    def test_within_turn_redundancy_not_visible_at_entry(self):
        for species in self.oracle.engine.ANIMALS:
            for seat in (0, 1):
                row = self.row(species, seat, "ordered-feed")
                events = [x for x in row["first_unit_events"][0] if x["seat"] == seat]
                self.assertEqual([e["row"] for e in events], [["FEED"], ["FEED"]])
                self.assertIs(events[0]["tile_before"]["fed_today"], False)
                self.assertIs(events[0]["tile_after"]["fed_today"], True)
                self.assertIs(events[1]["tile_before"]["fed_today"], True)
                self.assertEqual(events[1]["private_before"], events[1]["private_after"])
                self.assertEqual(row["product_sold"], [2, 3])
                self.assertEqual(row["wheat_consumed"][0], row["wheat_consumed"][1])

    def test_later_care_subsumes_the_intervention(self):
        for species in self.oracle.engine.ANIMALS:
            for seat in (0, 1):
                row = self.row(species, seat, "later-care")
                self.assertEqual(row["product_sold"], [3, 3])
                self.assertEqual(row["delta_margin"], 0)
                self.assertEqual(row["terminal_hashes"][0], row["terminal_hashes"][1])

    def test_full_held_yield_erases_extra_production(self):
        for species in self.oracle.engine.ANIMALS:
            for seat in (0, 1):
                row = self.row(species, seat, "held-clipping")
                held = self.oracle.engine.ANIMALS[species]["max_held"]
                self.assertEqual(row["product_sold"], [held, held])
                self.assertEqual(row["delta_margin"], 0)

    def test_unfed_future_production_cannot_realize_care(self):
        for species in self.oracle.engine.ANIMALS:
            for seat in (0, 1):
                row = self.row(species, seat, "unfed-followup")
                self.assertEqual(row["product_sold"][0], row["product_sold"][1])
                self.assertEqual(row["delta_margin"], 0)
                self.assertEqual(row["wheat_consumed"], [0, 0])

    def test_day28_care_has_no_later_production_before_terminal(self):
        for species in self.oracle.engine.ANIMALS:
            for seat in (0, 1):
                row = self.row(species, seat, "late-season")
                self.assertIsNone(row["production_day"])
                self.assertEqual(len(row["eod_milestones"][1]), 1)
                self.assertEqual(row["eod_milestones"][1][0]["tile"]["pending_care_bonus"], 1)
                self.assertEqual(row["product_sold"], [0, 0])
                self.assertEqual(row["delta_margin"], 0)

    def test_shed_room_is_not_tile_yield(self):
        for species, sold in (("GOOSE", [1, 1]), ("COW", [2, 2]), ("SHEEP", [2, 3])):
            for seat in (0, 1):
                row = self.row(species, seat, "storage-full")
                self.assertEqual(row["product_sold"], sold)
                if species != "SHEEP":
                    self.assertEqual(row["delta_margin"], 0)

    def test_rival_cash_is_accounted_not_assumed_unchanged(self):
        for species in self.oracle.engine.ANIMALS:
            for seat in (0, 1):
                row = self.row(species, seat, "rival-sale")
                self.assertLess(row["delta_rival"], 0)
                self.assertNotEqual(row["delta_own"], row["delta_margin"])
                self.assertGreater(row["delta_margin"], 0)

    def test_extra_product_can_displace_more_valuable_later_crop(self):
        for species, margin in (("GOOSE", -124), ("COW", -4), ("SHEEP", 36)):
            for seat in (0, 1):
                row = self.row(species, seat, "collateral-drop")
                self.assertEqual(row["product_sold"][1]-row["product_sold"][0], 1)
                self.assertEqual(row["melon_sold"][1]-row["melon_sold"][0], -1)
                self.assertEqual(row["delta_margin"], margin)
                self.assertEqual(row["wheat_consumed"][0], row["wheat_consumed"][1])
                # Both arms physically harvest the same crop; only admission differs.
                crop = [[e for e in arm if e["row"] == ["HARVEST"] and e["site"] == [3, 4]][0]
                        for arm in row["delivery_events"]]
                self.assertEqual(crop[0]["tile_before"], crop[1]["tile_before"])
                self.assertEqual(crop[0]["private_after"], crop[1]["private_after"] | {
                    "shed": crop[0]["private_after"]["shed"]})

    def test_floor_price_still_realizes_cash(self):
        for species in self.oracle.engine.ANIMALS:
            for seat in (0, 1):
                row = self.row(species, seat, "floor-sale")
                self.assertEqual(row["product_sold"], [2, 3])
                self.assertEqual(row["delta_own"], 1)

    def test_raw_market_rows_and_units_preserved_except_care(self):
        for row in self.rows.values():
            parent, candidate = row["parent_action"], row["candidate_action"]
            self.assertEqual(parent["market"], candidate["market"])
            before = [parent["farmer"], *parent["hands"]]
            after = [candidate["farmer"], *candidate["hands"]]
            self.assertEqual(len(before), len(after))
            changes = [(b, c) for b, c in zip(before, after) if b != c]
            self.assertEqual(changes, [(["FEED"], ["CARE"])])

    def test_trace_is_exact_pristine_full_interpreter_equivalence(self):
        for species in self.oracle.engine.ANIMALS:
            for seat in (0, 1):
                for hour in (0, 22, 23):
                    for ordered in (False, True):
                        case = a.Case("trace", species, seat, hour=hour, ordered=ordered)
                        world = self.oracle.world(case)
                        left, right = world.clone(), world.clone()
                        own = self.oracle.parent(case)
                        other = a.action(market=[["HIRE"], ["BUY_SEED", "WHEAT", 1]])
                        actions = [own, other] if seat == 0 else [other, own]
                        self.oracle.tick(left, actions, trace=True)
                        self.oracle.tick(right, actions, trace=False)
                        self.assertEqual(left.fingerprint(), right.fingerprint())
                        self.assertIs(left.state[0].observation.farms, left.state[1].observation.farms)

    def test_observed_feed_vs_failed_feed_order(self):
        for seat in (0, 1):
            for wheat in (0, 1):
                case = a.Case("feed-fill", seat=seat, ordered=True, first_feed_wheat=wheat)
                world = self.oracle.world(case)
                rows = [self.oracle.parent(case), a.action()]
                if seat == 1:
                    rows.reverse()
                result = self.oracle.tick(world, rows, trace=True)
                events = [e for e in result["units"] if e["seat"] == seat]
                self.assertIs(events[1]["tile_before"]["fed_today"], bool(wheat))

    def test_wrappers_restored_even_on_real_engine_exception(self):
        world = self.oracle.world(a.Case("exception"))
        unit, commit = self.oracle.engine._apply_unit_action, self.oracle.engine._commit_unit
        with self.assertRaises(OverflowError):
            self.oracle.tick(world, [a.action(market=[["SELL", "WOOL", float("inf")]]), a.action()], trace=True)
        self.assertIs(self.oracle.engine._apply_unit_action, unit)
        self.assertIs(self.oracle.engine._commit_unit, commit)

    def test_missing_or_altered_reference_fails_before_import(self):
        for target in a.REFERENCE_BLOBS:
            for alter in (False, True):
                with self.subTest(target=target, alter=alter), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    for name in a.REFERENCE_BLOBS:
                        path = root / name
                        path.parent.mkdir(parents=True, exist_ok=True)
                        if name == target and not alter:
                            continue
                        path.write_bytes((REFERENCE / name).read_bytes() + (b"\n" if name == target else b""))
                    with self.assertRaisesRegex(ValueError, "custody failure"):
                        a.load_reference(root)

    def test_initial_pair_copy_is_detached_and_preserves_aliases(self):
        original = self.oracle.world(a.Case("copy"))
        fingerprint = original.fingerprint()
        new = original.clone()
        self.assertIs(new.state[0].observation.farms, new.state[1].observation.farms)
        self.assertIsNot(new.state[0].observation.farms, original.state[0].observation.farms)
        new.state[0].observation.farms[0]["money"] -= 1
        self.assertEqual(original.fingerprint(), fingerprint)

    def test_terminal_refuses_further_ticks(self):
        world = self.oracle.world(a.Case("terminal", day=29, hour=22))
        self.oracle.tick(world, [a.action(), a.action()])
        self.assertTrue(world.env.done)
        with self.assertRaisesRegex(ValueError, "after terminal"):
            self.oracle.tick(world, [a.action(), a.action()])

    def test_real_care_does_not_consume_wheat_or_change_market(self):
        for seat in (0, 1):
            case = a.Case("care", seat=seat)
            world = self.oracle.world(case)
            left, right = world.clone(), world.clone()
            parent = self.oracle.parent(case)
            candidate = self.oracle.manual_intervention(parent, case)
            for w, act in ((left, parent), (right, candidate)):
                self.oracle.tick(w, [act, a.action()] if seat == 0 else [a.action(), act])
            self.assertEqual(left.state[seat].observation.private, right.state[seat].observation.private)
            self.assertEqual(left.state[0].observation.market, right.state[0].observation.market)
            before = copy.deepcopy(left.state[0].observation.farms)
            after = copy.deepcopy(right.state[0].observation.farms)
            before[seat]["tiles"][4][4]["cared_today"] = True
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main(verbosity=2)
