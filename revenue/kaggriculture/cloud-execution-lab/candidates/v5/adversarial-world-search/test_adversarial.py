#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
import importlib.util
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("f50", HERE / "adversarial.py")
f50 = importlib.util.module_from_spec(spec)
sys.modules["f50"] = f50
spec.loader.exec_module(f50)


def game(margin, seat=0, *, complete=True):
    if not complete:
        return {"status": "failed", "steps": 17, "scores": None}
    scores = [100 + margin, 100] if seat == 0 else [100, 100 + margin]
    return {"status": "complete", "steps": 719, "scores": scores}


def step(i, obs="same", cand="A", opp="O"):
    observation = {"step": i, "token": obs}
    return {
        "step": i,
        "candidate_observation_sha256": f50.sha256_bytes(f50.canonical(observation)),
        "candidate_observation": observation,
        "candidate_action_sha256": f50.sha256_bytes(f50.canonical({"x": cand})),
        "candidate_action": {"x": cand},
        "opponent_action_sha256": f50.sha256_bytes(f50.canonical({"x": opp})),
        "bank_before": [100.0, 100.0],
    }


class F50Tests(unittest.TestCase):
    def test_seed_plan_explicit_and_range(self):
        self.assertEqual(f50.seed_plan("4,9,12", None, None, 1), [4, 9, 12])
        self.assertEqual(f50.seed_plan(None, 10, 3, 7), [10, 17, 24])
        with self.assertRaises(ValueError):
            f50.seed_plan("1,1", None, None, 1)
        with self.assertRaises(ValueError):
            f50.seed_plan("1,2", 3, 2, 1)

    def test_classify_pair_regression_and_conversion(self):
        row = f50.classify_pair(game(12), game(-3), 0)
        self.assertEqual(row["margin_delta"], -15)
        self.assertTrue(row["regression"])
        self.assertEqual(row["conversion"], "win_to_loss")

    def test_classify_pair_fails_closed_on_incomplete(self):
        row = f50.classify_pair(game(5), game(0, complete=False), 0)
        self.assertEqual(row["status"], "invalid_pair")
        self.assertFalse(row["regression"])
        self.assertIsNone(row["margin_delta"])

    def test_first_divergence_is_same_state_candidate_action(self):
        control = [step(0), step(1, cand="C")]
        candidate = [step(0), step(1, cand="D")]
        found = f50.first_divergence(control, candidate)
        self.assertTrue(found["valid"])
        self.assertEqual(found["kind"], "candidate_action")
        self.assertEqual(found["step"], 1)
        self.assertEqual(found["public_observation"], {"step": 1, "token": "same"})

    def test_observation_drift_before_action_is_invalid(self):
        control = [step(0), step(1, obs="left")]
        candidate = [step(0), step(1, obs="right")]
        found = f50.first_divergence(control, candidate)
        self.assertFalse(found["valid"])
        self.assertEqual(found["kind"], "pre_action_state_divergence")

    def test_opponent_drift_before_candidate_action_is_invalid(self):
        control = [step(0), step(1, opp="L")]
        candidate = [step(0), step(1, opp="R")]
        found = f50.first_divergence(control, candidate)
        self.assertFalse(found["valid"])
        self.assertEqual(found["kind"], "pre_candidate_opponent_divergence")

    def test_identity_trace(self):
        trace = [step(0), step(1)]
        found = f50.first_divergence(trace, trace)
        self.assertTrue(found["valid"])
        self.assertEqual(found["kind"], "identity")

    def test_reducer_keeps_strongest_exact_signature(self):
        witness = f50.first_divergence([step(0, cand="A")], [step(0, cand="B")])
        rows = [
            {"regression": True, "first_divergence": witness, "margin_delta": -2,
             "seed": 9, "seat": 1, "opponent": "arlene_v14", "control_margin": 4,
             "candidate_margin": 2, "conversion": "none"},
            {"regression": True, "first_divergence": witness, "margin_delta": -8,
             "seed": 7, "seat": 0, "opponent": "arlene_v14", "control_margin": 4,
             "candidate_margin": -4, "conversion": "win_to_loss"},
        ]
        reduced = f50.reduce_witnesses(rows)
        self.assertEqual(len(reduced), 1)
        self.assertEqual(reduced[0]["seed"], 7)
        self.assertEqual(reduced[0]["margin_delta"], -8)
        self.assertEqual(reduced[0]["members"], 2)

    def test_signature_is_stable(self):
        witness = f50.first_divergence([step(0, cand="A")], [step(0, cand="B")])
        self.assertEqual(f50.signature(witness), f50.signature(dict(witness)))


if __name__ == "__main__":
    unittest.main()
