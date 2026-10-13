#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import sticky_obligation as sticky
import source_bound_sink as sink


class SourceBoundSinkTests(unittest.TestCase):
    def wheat_obligation(self, *, quantity=1, created_step=0, due_end=10):
        return sticky.issue_carry_consumption(
            actor="hand-1",
            item="WHEAT",
            quantity=quantity,
            created_step=created_step,
            due_end=due_end,
            capacity_pressure_units=quantity,
        )

    def fert_obligation(self, *, quantity=1, created_step=0, due_end=10):
        return sticky.issue_carry_consumption(
            actor="hand-1",
            item="FERTILIZER",
            quantity=quantity,
            created_step=created_step,
            due_end=due_end,
            capacity_pressure_units=quantity,
        )

    def sink_row(self, *, step, op, evidence):
        return {
            "step": step,
            "actor": "hand-1",
            "op": op,
            "projected_prestate_sha256": evidence.receipt()["before_sha256"],
            "sink_transition": evidence,
        }

    def test_official_sources_are_exactly_authenticated(self):
        receipt = sink.source_authority_receipt()
        self.assertEqual(receipt["engine_git_blob"], sink.EXPECTED_ENGINE_BLOB)
        self.assertEqual(receipt["engine_spec_git_blob"], sink.EXPECTED_ENGINE_SPEC_BLOB)
        self.assertEqual(receipt["turns_per_day"], 24)

    def test_feed_positive_consumption_proves_reserved_sink(self):
        evidence = sink.derive_sink_transition(
            actor="hand-1", step=1, op="FEED",
            tile={"kind": "PASTURE", "animal": "COW", "fed_today": False},
            inventory_units=1,
        )
        self.assertEqual(evidence.receipt()["consumed_units"], 1)
        report = sink.prove_carry_consumption_source_bound(
            self.wheat_obligation(),
            [self.sink_row(step=1, op="FEED", evidence=evidence)],
            current_inventory_units=0,
        )
        self.assertTrue(report["proven"])
        self.assertEqual(
            report["sink_evidence_authority"],
            "source_bound_transition+projected_prestate",
        )
        self.assertEqual(report["sink_units"], 1)

    def test_second_same_animal_feed_is_source_real_noop(self):
        evidence = sink.derive_sink_transition(
            actor="hand-1", step=1, op="FEED",
            tile={"kind": "PASTURE", "animal": "COW", "fed_today": True},
            inventory_units=4,
        )
        self.assertEqual(evidence.receipt()["consumed_units"], 0)
        report = sink.prove_carry_consumption_source_bound(
            self.wheat_obligation(),
            [self.sink_row(step=1, op="FEED", evidence=evidence)],
            current_inventory_units=0,
        )
        self.assertFalse(report["proven"])
        self.assertEqual(report["sink_units"], 0)

    def test_feed_without_wheat_is_source_real_noop(self):
        evidence = sink.derive_sink_transition(
            actor="hand-1", step=1, op="FEED",
            tile={"kind": "COOP", "animal": "GOOSE", "fed_today": False},
            inventory_units=0,
        )
        self.assertEqual(evidence.receipt()["consumed_units"], 0)

    def test_fertilize_positive_consumption_proves_reserved_sink(self):
        evidence = sink.derive_sink_transition(
            actor="hand-1", step=25, op="FERTILIZE",
            tile={"kind": "PLANT", "crop": "MELON", "fertilized_until_day": -1},
            inventory_units=1,
        )
        receipt = evidence.receipt()
        self.assertEqual(receipt["item"], "FERTILIZER")
        self.assertEqual(receipt["consumed_units"], 1)
        report = sink.prove_carry_consumption_source_bound(
            self.fert_obligation(created_step=24, due_end=30),
            [self.sink_row(step=25, op="FERTILIZE", evidence=evidence)],
            current_inventory_units=0,
        )
        self.assertTrue(report["proven"])
        self.assertEqual(report["sink_units"], 1)

    def test_fertilize_nonplant_and_empty_inventory_are_noops(self):
        nonplant = sink.derive_sink_transition(
            actor="hand-1", step=1, op="FERTILIZE",
            tile={"kind": "PASTURE"}, inventory_units=2,
        )
        empty = sink.derive_sink_transition(
            actor="hand-1", step=1, op="FERTILIZE",
            tile={"kind": "PLANT", "crop": "MELON", "fertilized_until_day": 7},
            inventory_units=0,
        )
        self.assertEqual(nonplant.receipt()["consumed_units"], 0)
        self.assertEqual(empty.receipt()["consumed_units"], 0)

    def test_existing_fertilization_still_consumes_inventory(self):
        evidence = sink.derive_sink_transition(
            actor="hand-1", step=25, op="FERTILIZE",
            tile={"kind": "PLANT", "crop": "MELON", "fertilized_until_day": 99},
            inventory_units=1,
        )
        self.assertEqual(evidence.receipt()["consumed_units"], 1)

    def test_old_caller_authentication_bits_have_zero_authority(self):
        row = {
            "step": 1, "actor": "hand-1", "op": "FEED",
            "consumption_authenticated": True,
            "consumed_item": "WHEAT", "consumed_units": 1,
        }
        report = sink.prove_carry_consumption_source_bound(
            self.wheat_obligation(), [row], current_inventory_units=0
        )
        self.assertFalse(report["proven"])
        self.assertEqual(report["sink_units"], 0)

    def test_forged_mapping_cannot_impersonate_transition(self):
        forged = {
            "schema": "titan-v4-source-bound-sink/v1",
            "engine_git_blob": sink.EXPECTED_ENGINE_BLOB,
            "actor": "hand-1", "step": 1, "op": "FEED",
            "item": "WHEAT", "consumed_units": 1,
        }
        with self.assertRaises(sink.SourceBoundSinkError):
            sink.prove_carry_consumption_source_bound(
                self.wheat_obligation(),
                [{"step": 1, "actor": "hand-1", "op": "FEED", "sink_transition": forged}],
                current_inventory_units=0,
            )

    def test_transition_is_bound_to_exact_actor_step_op_and_item(self):
        evidence = sink.derive_sink_transition(
            actor="hand-1", step=1, op="FEED",
            tile={"animal": "SHEEP", "fed_today": False}, inventory_units=1,
        )
        row = self.sink_row(step=2, op="FEED", evidence=evidence)
        with self.assertRaises(sink.SourceBoundSinkError):
            sink.prove_carry_consumption_source_bound(
                self.wheat_obligation(), [row], current_inventory_units=0,
            )

    def test_existing_burden_still_consumes_sink_capacity_first(self):
        evidence = sink.derive_sink_transition(
            actor="hand-1", step=1, op="FEED",
            tile={"animal": "COW", "fed_today": False}, inventory_units=2,
        )
        report = sink.prove_carry_consumption_source_bound(
            self.wheat_obligation(),
            [self.sink_row(step=1, op="FEED", evidence=evidence)],
            current_inventory_units=1,
        )
        self.assertFalse(report["proven"])
        self.assertEqual(report["sink_units"], 1)
        self.assertEqual(report["competing_units"], 1)

    def test_drop_and_wheat_harvest_fail_closed_before_future_sink(self):
        evidence = sink.derive_sink_transition(
            actor="hand-1", step=3, op="FEED",
            tile={"animal": "COW", "fed_today": False}, inventory_units=1,
        )
        cases = {
            "DROP": "lossy_drop_before_reserved_sink",
            "HARVEST": "unknown_wheat_harvest_acquisition_before_sink",
        }
        for boundary, expected_reason in cases.items():
            with self.subTest(boundary=boundary):
                report = sink.prove_carry_consumption_source_bound(
                    self.wheat_obligation(),
                    [
                        {"step": 1, "actor": "hand-1", "op": boundary},
                        self.sink_row(step=3, op="FEED", evidence=evidence),
                    ],
                    current_inventory_units=0,
                )
                self.assertFalse(report["proven"])
                self.assertEqual(report["reason"], expected_reason)


if __name__ == "__main__":
    unittest.main()
