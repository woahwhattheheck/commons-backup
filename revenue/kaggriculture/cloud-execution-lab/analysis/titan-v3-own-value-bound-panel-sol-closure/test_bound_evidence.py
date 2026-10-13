# SPDX-License-Identifier: Apache-2.0
"""Adversarial contracts for the action-bound own-value evidence gate."""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

import action_admission as admission
import materialize_evaluator as evaluator


HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
SOURCE_EVALUATOR = LAB.parent / "cloud-eval" / "evaluate.py"
PATCHED_SHA = "1" * 64


def evaluator_receipt() -> dict:
    return {
        "schema_version": 1,
        "operation": "titan-v3-own-value-bound-gameplay-screen-20260910-01",
        "source": {
            "git_blob_sha1": evaluator.EXPECTED_EVALUATOR_BLOB,
            "sha256": "2" * 64,
        },
        "patched": {
            "sha256": PATCHED_SHA,
            "capture_phase": "after both returned actions, before interpreter",
            "candidate_action_field": "candidate_action_sha256",
            "candidate_action_count_field": "candidate_action_count",
        },
    }


def reports(*, own_delta: float = 2.0, activate: bool = True) -> tuple[dict, dict, dict]:
    control_games = []
    candidate_games = []
    paired_rows = []
    for opponent in admission.OPPONENTS:
        for seed in admission.SEEDS:
            for seat in (0, 1):
                control_scores = [90.0, 90.0]
                control_scores[seat] = 100.0
                candidate_scores = list(control_scores)
                candidate_scores[seat] += own_delta
                token = f"{opponent}:{seed}:{seat}".encode("utf-8")
                base_action = hashlib.sha256(b"control-action:" + token).hexdigest()
                arm_action = (
                    hashlib.sha256(b"candidate-action:" + token).hexdigest()
                    if activate
                    else base_action
                )
                base_trace = hashlib.sha256(b"control-trace:" + token).hexdigest()
                arm_trace = (
                    hashlib.sha256(b"candidate-trace:" + token).hexdigest()
                    if activate
                    else base_trace
                )
                common = {
                    "opponent": opponent,
                    "seed": seed,
                    "candidate_seat": seat,
                    "status": "complete",
                    "failure": None,
                    "steps": 719,
                    "episode_steps": 720,
                    "candidate_action_count": 719,
                }
                control_games.append(
                    {
                        **common,
                        "scores": control_scores,
                        "bank_snapshot": list(control_scores),
                        "candidate_action_sha256": base_action,
                        "trace_sha256": base_trace,
                    }
                )
                candidate_games.append(
                    {
                        **common,
                        "scores": candidate_scores,
                        "bank_snapshot": list(candidate_scores),
                        "candidate_action_sha256": arm_action,
                        "trace_sha256": arm_trace,
                    }
                )
                control_own = control_scores[seat]
                candidate_own = candidate_scores[seat]
                control_rival = control_scores[1 - seat]
                candidate_rival = candidate_scores[1 - seat]
                paired_rows.append(
                    {
                        "opponent": opponent,
                        "seed": seed,
                        "candidate_seat": seat,
                        "control_own_cash": control_own,
                        "candidate_own_cash": candidate_own,
                        "own_cash_delta": candidate_own - control_own,
                        "control_margin": control_own - control_rival,
                        "candidate_margin": candidate_own - candidate_rival,
                        "margin_delta": (candidate_own - candidate_rival)
                        - (control_own - control_rival),
                        "control_trace_sha256": base_trace,
                        "candidate_trace_sha256": arm_trace,
                        "trace_changed": base_trace != arm_trace,
                    }
                )

    report_common = {
        "evaluator_sha256": PATCHED_SHA,
        "seeds": list(admission.SEEDS),
        "opponents": {name: {"entry": name} for name in admission.OPPONENTS},
        "progress": {
            "state": "complete",
            "planned_games": len(control_games),
            "recorded_games": len(control_games),
        },
    }
    control = {**copy.deepcopy(report_common), "games": control_games}
    candidate = {**copy.deepcopy(report_common), "games": candidate_games}
    paired = {
        "schema_version": 1,
        "experiment": "titan-v3-own-value-objective",
        "git_head": "a" * 40,
        "verdict": "UPSIDE_SCREEN" if own_delta > 0 else "NO_ACTION_CHANGE",
        "cells": paired_rows,
    }
    return control, candidate, paired


class EvaluatorMaterializationTests(unittest.TestCase):
    def test_real_evaluator_patch_is_exact_and_source_stays_unchanged(self) -> None:
        original = SOURCE_EVALUATOR.read_bytes()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "evaluate.py"
            receipt = evaluator.materialize_evaluator(SOURCE_EVALUATOR, output)
            self.assertTrue(output.is_file())
            self.assertNotEqual(output.read_bytes(), original)
            self.assertEqual(
                receipt["source"]["git_blob_sha1"],
                evaluator.EXPECTED_EVALUATOR_BLOB,
            )
            self.assertEqual(
                receipt["patched"]["capture_phase"],
                "after both returned actions, before interpreter",
            )
            self.assertEqual(len(receipt["patched"]["patches"]), 3)
            self.assertTrue(
                all(row["old_occurrences_after"] == 0 for row in receipt["patched"]["patches"])
            )
            compile(output.read_text(encoding="utf-8"), str(output), "exec")
        self.assertEqual(SOURCE_EVALUATOR.read_bytes(), original)

    def test_source_drift_fails_before_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "evaluate.py"
            source.write_bytes(SOURCE_EVALUATOR.read_bytes() + b"\n# drift\n")
            output = root / "patched.py"
            with self.assertRaisesRegex(
                evaluator.EvaluatorMaterializeError,
                "evaluator blob mismatch",
            ):
                evaluator.materialize_evaluator(source, output)
            self.assertFalse(output.exists())


class ActionAdmissionTests(unittest.TestCase):
    def test_positive_complete_panel_is_admitted(self) -> None:
        control, candidate, paired = reports()
        result = admission.assess(control, candidate, paired, evaluator_receipt())
        self.assertEqual(result["verdict"], "ADMIT")
        self.assertEqual(result["overall"]["action_changed_cells"], 32)
        self.assertEqual(result["overall"]["negative_cells"], 0)
        self.assertTrue(all(result["gates"].values()))

    def test_no_candidate_action_activation_is_inactive(self) -> None:
        control, candidate, paired = reports(own_delta=0.0, activate=False)
        result = admission.assess(control, candidate, paired, evaluator_receipt())
        self.assertEqual(result["verdict"], "INACTIVE")
        self.assertFalse(result["gates"]["candidate_action_activation"])

    def test_negative_opponent_seat_stratum_is_rejected(self) -> None:
        control, candidate, paired = reports(own_delta=3.0)
        for game in candidate["games"]:
            if game["opponent"] == "arlene" and game["candidate_seat"] == 0:
                game["scores"][0] = 99.0
                game["bank_snapshot"][0] = 99.0
        for row in paired["cells"]:
            if row["opponent"] == "arlene" and row["candidate_seat"] == 0:
                row["candidate_own_cash"] = 99.0
                row["own_cash_delta"] = -1.0
                row["candidate_margin"] = 9.0
                row["margin_delta"] = -1.0
        result = admission.assess(control, candidate, paired, evaluator_receipt())
        self.assertEqual(result["verdict"], "REJECT")
        self.assertFalse(
            result["gates"]["all_opponent_seat_strata_nonnegative"]
        )

    def test_trace_or_score_change_without_candidate_action_fails(self) -> None:
        control, candidate, paired = reports()
        candidate["games"][0]["candidate_action_sha256"] = control["games"][0][
            "candidate_action_sha256"
        ]
        with self.assertRaisesRegex(
            admission.EvidenceError,
            "complete trace changed without candidate action activation",
        ):
            admission.assess(control, candidate, paired, evaluator_receipt())

    def test_wrong_evaluator_binding_fails(self) -> None:
        control, candidate, paired = reports()
        candidate["evaluator_sha256"] = "f" * 64
        with self.assertRaisesRegex(
            admission.EvidenceError,
            "candidate report is not bound to patched evaluator",
        ):
            admission.assess(control, candidate, paired, evaluator_receipt())

    def test_duplicate_cell_fails_closed(self) -> None:
        control, candidate, paired = reports()
        candidate["games"][-1] = copy.deepcopy(candidate["games"][0])
        with self.assertRaisesRegex(admission.EvidenceError, "duplicate paired cell"):
            admission.assess(control, candidate, paired, evaluator_receipt())

    def test_detached_paired_score_fails_closed(self) -> None:
        control, candidate, paired = reports()
        paired["cells"][0]["own_cash_delta"] = 999.0
        with self.assertRaisesRegex(admission.EvidenceError, "is detached"):
            admission.assess(control, candidate, paired, evaluator_receipt())

    def test_incomplete_action_lifecycle_fails_closed(self) -> None:
        control, candidate, paired = reports()
        candidate["games"][0]["candidate_action_count"] = 718
        with self.assertRaisesRegex(
            admission.EvidenceError,
            "action count differs from steps",
        ):
            admission.assess(control, candidate, paired, evaluator_receipt())


if __name__ == "__main__":
    unittest.main(verbosity=2)
