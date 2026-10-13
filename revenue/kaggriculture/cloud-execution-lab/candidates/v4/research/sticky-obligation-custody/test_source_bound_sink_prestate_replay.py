#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Prestate binding predecessor for source-bound STICKY sink evidence."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import sticky_obligation as sticky
import source_bound_sink as sink


class SourceBoundPrestateReplayTests(unittest.TestCase):
    def obligation(self):
        return sticky.issue_carry_consumption(
            actor="hand-1",
            item="WHEAT",
            quantity=1,
            created_step=0,
            due_end=10,
            capacity_pressure_units=1,
        )

    def test_consuming_capability_cannot_replay_onto_nonconsuming_prestate(self):
        consuming = sink.derive_sink_transition(
            actor="hand-1",
            step=1,
            op="FEED",
            tile={"kind": "PASTURE", "animal": "COW", "fed_today": False},
            inventory_units=1,
        )
        nonconsuming = sink.derive_sink_transition(
            actor="hand-1",
            step=1,
            op="FEED",
            tile={"kind": "PASTURE", "animal": "COW", "fed_today": True},
            inventory_units=4,
        )
        self.assertEqual(consuming.receipt()["consumed_units"], 1)
        self.assertEqual(nonconsuming.receipt()["consumed_units"], 0)
        self.assertNotEqual(
            consuming.receipt()["before_sha256"],
            nonconsuming.receipt()["before_sha256"],
        )

        # Upstream projection custody can authenticate a prestate digest, but the
        # consumer must actually bind that digest to the capability it counts.
        row = {
            "step": 1,
            "actor": "hand-1",
            "op": "FEED",
            "projected_prestate_sha256": nonconsuming.receipt()["before_sha256"],
            "sink_transition": consuming,
        }
        report = sink.prove_carry_consumption_source_bound(
            self.obligation(),
            [row],
            current_inventory_units=0,
        )
        self.assertFalse(report["proven"])
        self.assertEqual(report["sink_units"], 0)

    def test_missing_prestate_binding_cannot_contribute_positive_sink(self):
        consuming = sink.derive_sink_transition(
            actor="hand-1",
            step=1,
            op="FEED",
            tile={"kind": "PASTURE", "animal": "SHEEP", "fed_today": False},
            inventory_units=1,
        )
        report = sink.prove_carry_consumption_source_bound(
            self.obligation(),
            [{"step": 1, "actor": "hand-1", "op": "FEED", "sink_transition": consuming}],
            current_inventory_units=0,
        )
        self.assertFalse(report["proven"])
        self.assertEqual(report["sink_units"], 0)


if __name__ == "__main__":
    unittest.main()
