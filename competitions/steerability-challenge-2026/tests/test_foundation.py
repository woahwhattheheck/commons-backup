import copy
import math
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from steerability_foundation import Measurement, disclose_holdout, select_candidate, verify_receipt
from submission_contract import SCHEMA_VERSION as PLAN_SCHEMA, validate_plan


def row(candidate, model, split, replicate, reduction, regressions):
    return Measurement.from_dict({
        "candidate_id": candidate,
        "model_id": model,
        "split": split,
        "replicate": replicate,
        "dishonesty_reduction": reduction,
        "capability_regressions": regressions,
    })


def plan():
    pipeline = [
        {"surface": "input", "name": "prompt-prefix", "config": {"template": "concise"}},
        {"surface": "state", "name": "activation-steer", "config": {"vector_artifact_ref": "slot"}},
        {"surface": "output", "name": "bounded-decode", "config": {"temperature": 0.0}},
    ]
    models = []
    for i in range(3):
        p = copy.deepcopy(pipeline)
        p[1]["config"]["vector_artifact_ref"] = f"vector-{i}"
        models.append({
            "model_id": f"target-{i}",
            "spipe_path": f"pipelines/target-{i}.spipe",
            "pipeline": p,
            "artifacts": [{
                "path": f"artifacts/vector-{i}.bin",
                "sha256": f"{i+1:064x}",
                "source": "participant-produced training artifact",
                "license": "participant-owned",
            }],
        })
    return {
        "schema_version": PLAN_SCHEMA,
        "coding_agent_disclosure": "Coding agents assisted implementation; entrant retains responsibility and can explain the solution.",
        "models": models,
        "authority": {
            "registered": False,
            "submitted": False,
            "private_eval_access": False,
            "prize_awarded": False,
            "payment_received": False,
        },
    }


class ScoreTests(unittest.TestCase):
    def test_penalizes_only_supplied_regressions(self):
        m = row("a", "m", "dev", "1", 0.5, [0.1, 0.0, 0.2])
        self.assertAlmostEqual(m.aggregate_penalty, 0.1)
        self.assertAlmostEqual(m.score, 0.4)

    def test_rejects_negative_regression(self):
        with self.assertRaises(ValueError):
            row("a", "m", "dev", "1", 0.5, [-0.1])

    def test_rejects_nonfinite(self):
        with self.assertRaises(ValueError):
            row("a", "m", "dev", "1", math.nan, [0.0])

    def test_robust_selection_prefers_worst_model(self):
        rows = [
            row("spiky", "m1", "dev", "1", 0.95, [0.0]),
            row("spiky", "m2", "dev", "1", 0.05, [0.0]),
            row("steady", "m1", "dev", "1", 0.45, [0.0]),
            row("steady", "m2", "dev", "1", 0.40, [0.0]),
        ]
        receipt = select_candidate(rows)
        self.assertEqual(receipt["selected_candidate"], "steady")
        self.assertTrue(verify_receipt(receipt))

    def test_holdout_cannot_enter_selection(self):
        with self.assertRaises(ValueError):
            select_candidate([row("a", "m", "holdout", "1", 0.9, [0.0])])

    def test_candidate_model_sets_must_match(self):
        rows = [
            row("a", "m1", "dev", "1", 0.3, [0.0]),
            row("a", "m2", "dev", "1", 0.3, [0.0]),
            row("b", "m1", "dev", "1", 0.4, [0.0]),
        ]
        with self.assertRaises(ValueError):
            select_candidate(rows)

    def test_holdout_only_selected_candidate_disclosed(self):
        selection = select_candidate([
            row("a", "m", "dev", "1", 0.2, [0.0]),
            row("b", "m", "dev", "1", 0.3, [0.0]),
        ])
        disclosure = disclose_holdout([
            row("a", "m", "holdout", "1", 0.99, [0.0]),
            row("b", "m", "holdout", "1", 0.10, [0.0]),
        ], selection)
        self.assertEqual(disclosure["selected_candidate"], "b")
        self.assertEqual(disclosure["holdout_summary"]["row_count"], 1)
        self.assertTrue(verify_receipt(disclosure))

    def test_tampered_selection_receipt_rejected(self):
        selection = select_candidate([row("a", "m", "dev", "1", 0.2, [0.0])])
        selection["selected_candidate"] = "evil"
        self.assertFalse(verify_receipt(selection))
        with self.assertRaises(ValueError):
            disclose_holdout([row("a", "m", "holdout", "1", 0.2, [0.0])], selection)


class PlanTests(unittest.TestCase):
    def test_plan_validates_and_receipt_deterministic(self):
        p = plan()
        a = validate_plan(p)
        b = validate_plan(copy.deepcopy(p))
        self.assertEqual(a, b)
        self.assertEqual(a["model_count"], 3)

    def test_structure_mismatch_rejected(self):
        p = plan()
        p["models"][2]["pipeline"][2]["config"]["temperature"] = 0.7
        with self.assertRaises(ValueError):
            validate_plan(p)

    def test_model_specific_artifact_reference_allowed(self):
        validate_plan(plan())

    def test_wrong_model_count_rejected(self):
        p = plan()
        p["models"].pop()
        with self.assertRaises(ValueError):
            validate_plan(p)

    def test_unsafe_spipe_path_rejected(self):
        p = plan()
        p["models"][0]["spipe_path"] = "../escape.spipe"
        with self.assertRaises(ValueError):
            validate_plan(p)

    def test_missing_provenance_rejected(self):
        p = plan()
        del p["models"][0]["artifacts"][0]["source"]
        with self.assertRaises(ValueError):
            validate_plan(p)

    def test_invalid_digest_rejected(self):
        p = plan()
        p["models"][0]["artifacts"][0]["sha256"] = "abc"
        with self.assertRaises(ValueError):
            validate_plan(p)

    def test_external_authority_must_stay_false(self):
        p = plan()
        p["authority"]["submitted"] = True
        with self.assertRaises(ValueError):
            validate_plan(p)

    def test_unknown_surface_rejected(self):
        p = plan()
        p["models"][0]["pipeline"][0]["surface"] = "magic"
        with self.assertRaises(ValueError):
            validate_plan(p)


if __name__ == "__main__":
    unittest.main()
