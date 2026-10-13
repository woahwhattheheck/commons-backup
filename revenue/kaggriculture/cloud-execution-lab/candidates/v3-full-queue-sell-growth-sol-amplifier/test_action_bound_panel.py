# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

# run_contracts.py executes this module explicitly; importing the supplemental
# class makes its predecessor-killing cases part of the same authoritative suite.
from test_verify_panel import SupplementalPanelGateTests


class ActionBoundEvidenceTests(unittest.TestCase):
    @staticmethod
    def _grid(own_delta=1.0, margin_delta=1.0, changed=True):
        import run_panel

        baseline = {}
        candidate = {}
        rows = []
        for opponent in run_panel.EXPECTED_OPPONENTS:
            for seed in run_panel.EXPECTED_SEEDS:
                for seat in run_panel.EXPECTED_SEATS:
                    key = (opponent, seed, seat)
                    base_digest = hashlib.sha256(f"base:{key}".encode()).hexdigest()
                    cand_digest = (
                        hashlib.sha256(f"candidate:{key}".encode()).hexdigest()
                        if changed
                        else base_digest
                    )
                    common = {
                        "opponent": opponent,
                        "seed": seed,
                        "candidate_seat": seat,
                        "status": "complete",
                        "failure": None,
                        "episode_steps": run_panel.EXPECTED_EPISODE_STEPS,
                        "steps": run_panel.EXPECTED_ACTION_COUNT,
                        "candidate_action_count": run_panel.EXPECTED_ACTION_COUNT,
                    }
                    baseline[key] = {**common, "candidate_action_sha256": base_digest}
                    candidate[key] = {**common, "candidate_action_sha256": cand_digest}
                    rows.append(
                        {
                            "opponent": opponent,
                            "seed": seed,
                            "candidate_seat": seat,
                            "own_delta": float(own_delta),
                            "margin_delta": float(margin_delta),
                            "trace_changed": bool(changed),
                        }
                    )
        return rows, baseline, candidate

    @staticmethod
    def _summaries(rows):
        import run_panel

        own = [float(row["own_delta"]) for row in rows]
        margin = [float(row["margin_delta"]) for row in rows]
        summary = run_panel.add_action_summary(
            {
                "cells": len(rows),
                "mean_own_delta": sum(own) / len(own),
                "mean_margin_delta": sum(margin) / len(margin),
            },
            rows,
        )
        per_opponent = {}
        for name in run_panel.EXPECTED_OPPONENTS:
            values = [float(row["own_delta"]) for row in rows if row["opponent"] == name]
            per_opponent[name] = {"mean_own_delta": sum(values) / len(values)}
        return summary, per_opponent

    def test_literal_grid_and_candidate_action_receipts_advance_clean_gain(self):
        import run_panel

        rows, baseline, candidate = self._grid()
        bound = run_panel.bind_candidate_actions(rows, baseline, candidate)
        summary, per_opponent = self._summaries(bound)
        verdict = run_panel.strict_verdict(summary, per_opponent, bound)
        self.assertEqual(verdict["decision"], "ADVANCE")
        self.assertTrue(all(verdict["checks"].values()))
        self.assertEqual(summary["candidate_action_changed_cells"], 32)

    def test_same_candidate_actions_cannot_claim_score_gain(self):
        import run_panel

        rows, baseline, candidate = self._grid(changed=False)
        bound = run_panel.bind_candidate_actions(rows, baseline, candidate)
        summary, per_opponent = self._summaries(bound)
        verdict = run_panel.strict_verdict(summary, per_opponent, bound)
        self.assertEqual(verdict["decision"], "REJECT")
        self.assertFalse(verdict["checks"]["candidate_actions_activated"])
        self.assertFalse(verdict["checks"]["every_score_change_action_bound"])

    def test_positive_global_gain_cannot_mask_seat_regression(self):
        import run_panel

        rows, baseline, candidate = self._grid()
        for row in rows:
            row["own_delta"] = 10.0 if row["candidate_seat"] == 0 else -1.0
            row["margin_delta"] = row["own_delta"]
        bound = run_panel.bind_candidate_actions(rows, baseline, candidate)
        summary, per_opponent = self._summaries(bound)
        verdict = run_panel.strict_verdict(summary, per_opponent, bound)
        self.assertGreater(summary["mean_own_delta"], 0)
        self.assertEqual(verdict["decision"], "REJECT")
        self.assertFalse(verdict["checks"]["no_seat_mean_own_regression"])

    def test_positive_global_gain_cannot_mask_opponent_regression(self):
        import run_panel

        rows, baseline, candidate = self._grid()
        for row in rows:
            row["own_delta"] = -1.0 if row["opponent"] == "arlene" else 2.0
            row["margin_delta"] = row["own_delta"]
        bound = run_panel.bind_candidate_actions(rows, baseline, candidate)
        summary, per_opponent = self._summaries(bound)
        verdict = run_panel.strict_verdict(summary, per_opponent, bound)
        self.assertGreater(summary["mean_own_delta"], 0)
        self.assertEqual(verdict["decision"], "REJECT")
        self.assertFalse(verdict["checks"]["no_opponent_mean_own_regression"])

    def test_bool_seat_and_wrong_action_count_fail_closed(self):
        import run_panel

        rows, baseline, candidate = self._grid()
        key = (run_panel.EXPECTED_OPPONENTS[0], run_panel.EXPECTED_SEEDS[0], 1)
        baseline[key]["candidate_seat"] = True
        with self.assertRaisesRegex(ValueError, "literal seat"):
            run_panel.bind_candidate_actions(rows, baseline, candidate)
        baseline[key]["candidate_seat"] = 1
        candidate[key]["candidate_action_count"] -= 1
        with self.assertRaisesRegex(ValueError, "action count"):
            run_panel.bind_candidate_actions(rows, baseline, candidate)

    def test_evaluator_instrumentation_is_exact_and_idempotence_fails_closed(self):
        import run_panel

        source = '''actors, trace = [], hashlib.sha256()
result = {"failure": None, "steps": 0, "episode_steps": cfg.episodeSteps, "daily_bank": []}
                actions.append(response["action"])
            for seat in range(2):
        else:
            result["trace_sha256"] = trace.hexdigest()
        if finalization_errors:
'''
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evaluate.py"
            path.write_text(source, encoding="utf-8")
            run_panel.instrument_candidate_actions(path)
            patched = path.read_text(encoding="utf-8")
            self.assertIn('candidate_actions.update(encoded({"step": step', patched)
            self.assertIn('result["candidate_action_sha256"] = candidate_actions.hexdigest()', patched)
            with self.assertRaisesRegex(RuntimeError, "seam changed"):
                run_panel.instrument_candidate_actions(path)


if __name__ == "__main__":
    unittest.main()
