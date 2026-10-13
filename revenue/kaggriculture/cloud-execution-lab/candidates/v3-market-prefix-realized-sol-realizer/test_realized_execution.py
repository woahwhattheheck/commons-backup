# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import unittest

from realized_execution import compare_game_pair, digest, summarize_pairs


def receipt(step, *, pre, action, rival, post, event=False):
    return {
        "step": step,
        "pre_world_sha256": digest(pre),
        "tested_action_sha256": digest(action),
        "opponent_action_sha256": digest(rival),
        "post_world_sha256": digest(post),
        "syntactic_event": event,
        "diagnostic_sha256": digest({"event": step}) if event else None,
    }


def game(*, variant, rows, scores=(100, 90), opponent="arlene", seed=1, seat=0):
    return {
        "variant": variant,
        "opponent": opponent,
        "seed": seed,
        "candidate_seat": seat,
        "status": "complete",
        "episode_steps": len(rows) + 1,
        "steps": len(rows),
        "step_receipts": rows,
        "scores": list(scores),
    }


class RealizedExecutionTests(unittest.TestCase):
    def test_action_change_plus_post_state_change_is_realized(self):
        control = game(
            variant="control",
            rows=[receipt(0, pre={"x": 0}, action=["PASS"], rival=["PASS"], post={"x": 0})],
        )
        candidate = game(
            variant="candidate",
            rows=[receipt(0, pre={"x": 0}, action=["BUY"], rival=["PASS"], post={"x": 1}, event=True)],
            scores=(110, 90),
        )
        row = compare_game_pair(control, candidate)
        self.assertEqual(row["realized_events"], 1)
        self.assertEqual(row["first_realized_step"], 0)
        self.assertEqual(row["own_delta"], 10)

    def test_structural_crossing_can_be_inert(self):
        control = game(
            variant="control",
            rows=[receipt(0, pre={"x": 0}, action=["PASS"], rival=["PASS"], post={"x": 0})],
        )
        candidate = game(
            variant="candidate",
            rows=[receipt(0, pre={"x": 0}, action=["SELL"], rival=["PASS"], post={"x": 0}, event=True)],
        )
        row = compare_game_pair(control, candidate)
        self.assertEqual(row["inert_events"], 1)
        self.assertEqual(row["realized_events"], 0)
        summary = summarize_pairs([row, {**row, "candidate_seat": 1}])
        self.assertEqual(summary["verdict"], "NO_REALIZED_SIGNAL")

    def test_unattributed_action_divergence_is_rejected(self):
        control = game(
            variant="control",
            rows=[receipt(0, pre=0, action="a", rival="r", post=0)],
        )
        candidate = game(
            variant="candidate",
            rows=[receipt(0, pre=0, action="b", rival="r", post=1)],
        )
        with self.assertRaisesRegex(ValueError, "unattributed"):
            compare_game_pair(control, candidate)

    def test_rival_divergence_in_equal_prestate_is_rejected(self):
        control = game(
            variant="control",
            rows=[receipt(0, pre=0, action="a", rival="r0", post=0)],
        )
        candidate = game(
            variant="candidate",
            rows=[receipt(0, pre=0, action="b", rival="r1", post=1, event=True)],
        )
        with self.assertRaisesRegex(ValueError, "rival action diverged"):
            compare_game_pair(control, candidate)

    def test_equal_actions_cannot_diverge_engine_state(self):
        control = game(
            variant="control",
            rows=[receipt(0, pre=0, action="a", rival="r", post=0)],
        )
        candidate = game(
            variant="candidate",
            rows=[receipt(0, pre=0, action="a", rival="r", post=1)],
        )
        with self.assertRaisesRegex(ValueError, "engine state diverged"):
            compare_game_pair(control, candidate)

    def test_downstream_actions_are_not_misattributed(self):
        control = game(
            variant="control",
            rows=[
                receipt(0, pre=0, action="a", rival="r", post=0),
                receipt(1, pre=0, action="x", rival="q", post=0),
            ],
        )
        candidate = game(
            variant="candidate",
            rows=[
                receipt(0, pre=0, action="b", rival="r", post=1, event=True),
                receipt(1, pre=1, action="y", rival="z", post=2, event=True),
            ],
            scores=(101, 90),
        )
        row = compare_game_pair(control, candidate)
        self.assertEqual(row["realized_events"], 1)
        self.assertEqual(row["downstream_events"], 1)

    def test_score_change_without_realized_event_is_rejected(self):
        control = game(
            variant="control",
            rows=[receipt(0, pre=0, action="a", rival="r", post=0)],
        )
        candidate = game(
            variant="candidate",
            rows=[receipt(0, pre=0, action="b", rival="r", post=0, event=True)],
            scores=(101, 90),
        )
        with self.assertRaisesRegex(ValueError, "score changed without"):
            compare_game_pair(control, candidate)

    def test_negative_seat_stratum_blocks_upside(self):
        pairs = []
        for seat, delta in ((0, 10), (1, -1)):
            pairs.append(
                {
                    "schema": "x",
                    "opponent": "arlene",
                    "seed": 1,
                    "candidate_seat": seat,
                    "syntactic_events": 1,
                    "causal_events": 1,
                    "realized_events": 1,
                    "inert_events": 0,
                    "downstream_events": 0,
                    "action_divergence_steps": 1,
                    "state_divergence_steps": 1,
                    "first_action_divergence_step": 0,
                    "first_realized_step": 0,
                    "causal_event_details": [],
                    "control_scores": [0, 0],
                    "candidate_scores": [0, 0],
                    "own_delta": delta,
                    "rival_delta": -10,
                    "margin_delta": delta + 10,
                }
            )
        summary = summarize_pairs(pairs)
        self.assertEqual(summary["verdict"], "REALIZED_REGRESSION")
        self.assertIn("arlene/seat1", " ".join(summary["reasons"]))

    def test_boolean_seat_is_rejected(self):
        rows = [receipt(0, pre=0, action="a", rival="r", post=0)]
        control = game(variant="control", rows=rows, seat=True)
        candidate = game(variant="candidate", rows=rows, seat=True)
        with self.assertRaisesRegex(ValueError, "literal integer"):
            compare_game_pair(control, candidate)


if __name__ == "__main__":
    unittest.main()
