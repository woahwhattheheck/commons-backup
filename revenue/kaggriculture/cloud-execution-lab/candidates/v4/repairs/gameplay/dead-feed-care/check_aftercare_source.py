# SPDX-License-Identifier: Apache-2.0
"""Execute SECONDHELP's authenticated W2 helper against AFTERCARE's engine oracle.

AFTERCARE_LANE and AFTERCARE_LANE_BLOB are mandatory. This checks physical
semantics and records synthetic economics; it does NOT promote the policy.
"""
from __future__ import annotations
import copy
import os
from pathlib import Path
import unittest
import aftercare_engine as a


class AftercareSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.oracle = a.Oracle(Path(os.environ["AFTERCARE_REFERENCE"]))
        cls.function = staticmethod(a.load_lane(Path(os.environ["AFTERCARE_LANE"]), os.environ["AFTERCARE_LANE_BLOB"]))
        cls.rows = {case.name: cls.oracle.pair(case, cls.function) for case in a.corpus()}

    def test_entry_and_ordered_source_really_activate_and_sell(self):
        for species, cash in (("GOOSE", 50), ("COW", 169), ("SHEEP", 209)):
            for seat in (0, 1):
                for kind in ("entry-fed", "ordered-feed"):
                    row = self.rows[f"{species}:{seat}:{kind}"]
                    with self.subTest(case=row["case"]["name"]):
                        self.assertTrue(row["action_changed"])
                        self.assertEqual(row["product_sold"], [2, 3])
                        self.assertEqual(row["delta_own"], cash)
                        self.assertEqual(row["delta_rival"], 0)

    def test_only_executed_dead_feed_changes_to_care(self):
        for row in self.rows.values():
            before = [row["parent_action"]["farmer"], *row["parent_action"]["hands"]]
            after = [row["candidate_action"]["farmer"], *row["candidate_action"]["hands"]]
            self.assertEqual(len(before), len(after))
            events = {event["actor"]: event for event in row["first_unit_events"][0]
                      if event["seat"] == row["case"]["seat"]}
            for actor, (old, new) in enumerate(zip(before, after)):
                if old != new:
                    self.assertEqual((old, new), (["FEED"], ["CARE"]))
                    self.assertIs(events[actor]["tile_before"]["fed_today"], True)
                    self.assertEqual(events[actor]["tile_before"], events[actor]["tile_after"])
                    self.assertEqual(events[actor]["private_before"], events[actor]["private_after"])

    def test_no_wheat_spend_or_market_reordering_added(self):
        for row in self.rows.values():
            self.assertEqual(row["parent_action"]["market"], row["candidate_action"]["market"])
            self.assertEqual(row["wheat_consumed"][0], row["wheat_consumed"][1])
            self.assertEqual(row["wheat_bought"], [0, 0])

    def test_neutral_continuations_are_not_misreported_as_positive(self):
        for species in self.oracle.engine.ANIMALS:
            for seat in (0, 1):
                for kind in ("held-clipping", "later-care", "unfed-followup", "late-season"):
                    self.assertEqual(self.rows[f"{species}:{seat}:{kind}"]["delta_margin"], 0)

    def test_collateral_economics_remains_explicit_not_a_pass_for_promotion(self):
        for species, margin in (("GOOSE", -124), ("COW", -4), ("SHEEP", 36)):
            for seat in (0, 1):
                row = self.rows[f"{species}:{seat}:collateral-drop"]
                # Conservative future source guards may decline this case. Never
                # report a negative manual witness as an executed source witness.
                self.assertEqual(row["delta_margin"], margin if row["action_changed"] else 0)
                if row["action_changed"]:
                    self.assertEqual(row["melon_sold"][1]-row["melon_sold"][0], -1)

    def test_disabled_is_exact_parent_identity(self):
        for case in a.corpus():
            world = self.oracle.world(case)
            parent = self.oracle.parent(case)
            self.assertIs(self.function(parent, world.state[case.seat].observation,
                                        world.env.configuration, enabled=False), parent)

    def test_failed_prior_feed_cannot_certify_redundancy(self):
        for seat in (0, 1):
            case = a.Case("unfunded-prior-feed", seat=seat, ordered=True, first_feed_wheat=0)
            world = self.oracle.world(case)
            parent = self.oracle.parent(case)
            self.assertIs(self.function(parent, world.state[seat].observation,
                                        world.env.configuration, enabled=True), parent)

    def test_inputs_are_not_mutated(self):
        for case in a.corpus():
            world = self.oracle.world(case)
            parent = self.oracle.parent(case)
            pristine = copy.deepcopy(parent)
            fingerprint = world.fingerprint()
            self.function(parent, world.state[case.seat].observation, world.env.configuration, enabled=True)
            self.assertEqual(parent, pristine)
            self.assertEqual(world.fingerprint(), fingerprint)

    def test_source_identity_fails_closed(self):
        path = Path(os.environ["AFTERCARE_LANE"])
        with self.assertRaisesRegex(ValueError, "blob mismatch"):
            a.load_lane(path, "0"*40)

    def test_both_terminal_seats_and_margin_are_real(self):
        for row in self.rows.values():
            self.assertEqual(row["terminal_status"], [["DONE", "DONE"]]*2)
            self.assertEqual(row["delta_margin"], row["delta_own"]-row["delta_rival"])
            self.assertEqual(row["source_mode"], "bound_source")


if __name__ == "__main__":
    unittest.main(verbosity=2)
