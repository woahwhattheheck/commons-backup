# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import unittest

from causal_gate import EvidenceError, bind


OPERATION = "titan-v3-route-reference-echo-current-activation-20260910-01"
SOURCE_OPERATION = "titan-v3-route-reference-echo-20260909-sol-accrual-01"


def game(own, rival, hashes, evidence=None, seed=7):
    return {
        "opponent": "arlene",
        "seed": seed,
        "candidate_seat": 0,
        "status": "complete",
        "scores": [own, rival],
        "steps": len(hashes),
        "candidate_action_count": len(hashes),
        "candidate_action_step_sha256": hashes,
        "candidate_agent_evidence": list(evidence or []),
    }


def event(step=1):
    return {
        "step": step,
        "evidence": {
            "operation": OPERATION,
            "source_operation": SOURCE_OPERATION,
            "controller_route": 0,
            "runtime_status": "completed",
            "receipt_sha256": "a" * 64,
            "report": {
                "operation": SOURCE_OPERATION,
                "status": "NORMALIZED",
                "changed": True,
                "now": step,
                "item": "WHEAT",
                "removed_quantity": 2,
                "canonical_quantity": 4,
                "scheduler_owned_quantity": 2,
            },
        },
    }


def panel_row(activation_count, action_changed, first, own_delta=0.0, rival_delta=0.0):
    return {
        "opponent": "arlene",
        "seed": 7,
        "seat": 0,
        "activation_count": activation_count,
        "action_changed": action_changed,
        "first_action_divergence_step": first,
        "own_delta": own_delta,
        "rival_delta": rival_delta,
    }


def panel(row):
    return {
        "schema_version": 1,
        "operation": OPERATION,
        "cells": 1,
        "rows": [row],
    }


class CausalGateTests(unittest.TestCase):
    def test_normalization_at_divergence_binds_score_effect(self):
        control = {
            "games": [game(100, 50, ["1" * 64, "2" * 64])]
        }
        candidate = {
            "games": [
                game(
                    110,
                    50,
                    ["1" * 64, "3" * 64],
                    [event(step=1)],
                )
            ]
        }
        report = bind(
            control,
            candidate,
            panel(panel_row(1, True, 1, own_delta=10.0)),
        )
        self.assertEqual(report["verdict"], "CAUSAL_CHAIN_BOUND")
        self.assertEqual(report["activation_bound_action_cells"], 1)
        self.assertEqual(report["activation_bound_score_cells"], 1)

    def test_action_change_without_receipt_is_rejected(self):
        control = {
            "games": [game(100, 50, ["1" * 64, "2" * 64])]
        }
        candidate = {
            "games": [game(100, 50, ["1" * 64, "3" * 64])]
        }
        with self.assertRaises(EvidenceError):
            bind(control, candidate, panel(panel_row(0, True, 1)))

    def test_action_divergence_before_receipt_is_rejected(self):
        control = {
            "games": [
                game(100, 50, ["1" * 64, "2" * 64, "4" * 64])
            ]
        }
        candidate = {
            "games": [
                game(
                    100,
                    50,
                    ["1" * 64, "3" * 64, "4" * 64],
                    [event(step=2)],
                )
            ]
        }
        with self.assertRaises(EvidenceError):
            bind(control, candidate, panel(panel_row(1, True, 1)))

    def test_state_only_activation_is_valid_but_non_promoting(self):
        hashes = ["1" * 64, "2" * 64]
        control = {"games": [game(100, 50, hashes)]}
        candidate = {
            "games": [game(100, 50, hashes, [event(step=1)])]
        }
        report = bind(
            control,
            candidate,
            panel(panel_row(1, False, None)),
        )
        self.assertEqual(report["verdict"], "NO_ACTION_ACTIVATION")
        self.assertFalse(report["promotion_authorized"])

    def test_panel_tamper_is_rejected(self):
        hashes = ["1" * 64, "2" * 64]
        control = {"games": [game(100, 50, hashes)]}
        candidate = {"games": [game(100, 50, hashes)]}
        row = panel_row(0, False, None)
        row["own_delta"] = 1.0
        with self.assertRaises(EvidenceError):
            bind(control, candidate, panel(row))

    def test_activation_outside_action_range_is_rejected(self):
        hashes = ["1" * 64, "2" * 64]
        control = {"games": [game(100, 50, hashes)]}
        candidate = {
            "games": [game(100, 50, hashes, [event(step=2)])]
        }
        with self.assertRaises(EvidenceError):
            bind(
                control,
                candidate,
                panel(panel_row(1, False, None)),
            )


if __name__ == "__main__":
    unittest.main()
