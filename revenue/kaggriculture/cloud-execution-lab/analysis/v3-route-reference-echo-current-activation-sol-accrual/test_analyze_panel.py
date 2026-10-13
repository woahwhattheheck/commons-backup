# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import unittest

from analyze_panel import EvidenceError, analyze


def game(*, own, rival, hashes, evidence=None, seat=0, seed=7, opponent="arlene"):
    scores = [own, rival] if seat == 0 else [rival, own]
    return {
        "opponent": opponent,
        "seed": seed,
        "candidate_seat": seat,
        "status": "complete",
        "scores": scores,
        "steps": len(hashes),
        "candidate_action_count": len(hashes),
        "candidate_action_step_sha256": hashes,
        "candidate_agent_evidence": list(evidence or []),
    }


def event(step=1, removed=2):
    return {
        "step": step,
        "evidence": {
            "schema_version": 1,
            "operation": "titan-v3-route-reference-echo-current-activation-20260910-01",
            "source_operation": "titan-v3-route-reference-echo-20260909-sol-accrual-01",
            "controller_route": 0,
            "runtime_status": "completed",
            "receipt_sha256": "a" * 64,
            "report": {
                "operation": "titan-v3-route-reference-echo-20260909-sol-accrual-01",
                "status": "NORMALIZED",
                "changed": True,
                "now": step,
                "item": "WHEAT",
                "removed_quantity": removed,
                "canonical_quantity": 4,
                "scheduler_owned_quantity": 2,
            },
        },
    }


class AnalyzePanelTests(unittest.TestCase):
    def test_advance_requires_natural_and_action_activation(self):
        control = {"games": [game(own=100, rival=50, hashes=["1" * 64, "2" * 64])]}
        candidate = {"games": [game(own=110, rival=50, hashes=["1" * 64, "3" * 64], evidence=[event()])]}
        report = analyze(control, candidate)
        self.assertEqual(report["verdict"], "ADVANCE")
        self.assertEqual(report["activation"]["events"], 1)
        self.assertEqual(report["rows"][0]["first_action_divergence_step"], 1)

    def test_score_delta_without_action_delta_is_rejected(self):
        hashes = ["1" * 64, "2" * 64]
        with self.assertRaises(EvidenceError):
            analyze(
                {"games": [game(own=100, rival=50, hashes=hashes)]},
                {"games": [game(own=101, rival=50, hashes=hashes, evidence=[event()])]},
            )

    def test_no_activation_is_not_mislabeled(self):
        hashes = ["1" * 64]
        report = analyze(
            {"games": [game(own=100, rival=50, hashes=hashes)]},
            {"games": [game(own=100, rival=50, hashes=hashes)]},
        )
        self.assertEqual(report["verdict"], "NO_NATURAL_ACTIVATION")

    def test_control_evidence_is_rejected(self):
        hashes = ["1" * 64, "2" * 64]
        with self.assertRaises(EvidenceError):
            analyze(
                {"games": [game(own=100, rival=50, hashes=hashes, evidence=[event()])]},
                {"games": [game(own=110, rival=50, hashes=["1" * 64, "3" * 64], evidence=[event()])]},
            )

    def test_mismatched_schedule_is_rejected(self):
        hashes = ["1" * 64]
        with self.assertRaises(EvidenceError):
            analyze(
                {"games": [game(own=1, rival=0, hashes=hashes, seed=1)]},
                {"games": [game(own=1, rival=0, hashes=hashes, seed=2)]},
            )


if __name__ == "__main__":
    unittest.main()
