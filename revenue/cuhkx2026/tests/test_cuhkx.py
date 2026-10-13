import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cuhkx import (
    ContractError,
    HierarchicalPrior,
    Prediction,
    ensemble_predictions,
    evaluate,
    grouped_subject_folds,
    normalize_prediction,
    read_prediction_csv,
    validate_rows,
    write_submission,
)
from readiness_gate import check


def row(qa, user, category="single", answer="A", d="four", question="What action 12 happens?"):
    return {
        "qa_id": str(qa), "source": "HARn", "path": f"HARn/a/user{user}/trial",
        "category": category, "question": question,
        "A": "one", "B": "two", "C": "three", "D": d, "answer": answer,
    }


def authorization(scope="conditional_after_registration_and_rule_acceptance"):
    return {
        "received": True,
        "received_date": "2026-09-14",
        "source": "CUHK-X Challenge Organizing Committee",
        "scope": scope,
        "official_mirrors_only": True,
        "noncommercial_competition_use_only": True,
    }


def ready_state(artifact: Path):
    return {
        "written_dataset_authorization": authorization(),
        "official_registration_complete": True,
        "kaggle_rules_accepted": True,
        "dataset_terms_accepted": True,
        "submission_authorized": True,
        "validation": {"subject_disjoint": True, "exact_accuracy": 0.9},
        "submission": {
            "path": str(artifact),
            "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        },
    }


class ContractTests(unittest.TestCase):
    def test_prediction_canonicalizes_multiselect(self):
        self.assertEqual(normalize_prediction("c, a"), "AC")

    def test_prediction_rejects_duplicates(self):
        with self.assertRaises(ContractError):
            normalize_prediction("AA")

    def test_absent_option_is_rejected(self):
        r = row(1, 1, d="")
        validate_rows([r], training=True)
        with self.assertRaises(ContractError):
            normalize_prediction("D", "ABC")

    def test_duplicate_id_rejected(self):
        with self.assertRaises(ContractError):
            validate_rows([row(1, 1), row(1, 2)], training=True)

    def test_unknown_category_rejected(self):
        bad = row(1, 1); bad["category"] = "mystery"
        with self.assertRaises(ContractError):
            validate_rows([bad], training=True)

    def test_non_multi_cannot_have_multiple_answers(self):
        bad = row(1, 1, answer="AB")
        with self.assertRaises(ContractError):
            validate_rows([bad], training=True)

    def test_multi_can_have_multiple_answers(self):
        validate_rows([row(1, 1, category="multi", answer="CA")], training=True)

    def test_subject_folds_are_disjoint_and_complete(self):
        rows = [row(i, i) for i in range(1, 11)]
        folds = grouped_subject_folds(rows, 5)
        seen_val = set()
        for train, val in folds:
            self.assertTrue(set(train).isdisjoint(val))
            self.assertTrue(train and val)
            seen_val.update(val)
        self.assertEqual(seen_val, set(range(10)))

    def test_prior_falls_back_without_validation_leakage(self):
        train = [row(1, 1, answer="B"), row(2, 2, answer="B"), row(3, 3, answer="A")]
        probe = row(4, 4, answer="A", question="Never seen prompt")
        model = HierarchicalPrior(min_signature_support=3).fit(train)
        pred = model.predict([probe])[0]
        self.assertEqual(pred.prediction, "B")
        self.assertEqual(pred.model_id, "prior:category")

    def test_exact_signature_prior_requires_support(self):
        train = [row(1, 1, answer="C"), row(2, 2, answer="C"), row(3, 3, answer="A")]
        probe = row(4, 4, answer="B")
        pred = HierarchicalPrior(2).fit(train).predict([probe])[0]
        self.assertEqual((pred.prediction, pred.model_id), ("C", "prior:signature"))

    def test_ensemble_requires_exact_coverage(self):
        test = [row(1, 1), row(2, 2)]
        with self.assertRaises(ContractError):
            ensemble_predictions(test, [[Prediction("1", "A", .9, "m")]])

    def test_ensemble_confidence_weighting(self):
        test = [row(1, 1)]
        a = [Prediction("1", "A", .4, "a")]
        b = [Prediction("1", "B", .9, "b")]
        pred = ensemble_predictions(test, [a, b], [1, 2])[0]
        self.assertEqual(pred.prediction, "B")
        self.assertGreater(pred.confidence, .8)

    def test_evaluate_category_slices(self):
        rows = [row(1, 1, answer="A"), row(2, 2, category="emotion", answer="B")]
        report = evaluate(rows, [Prediction("1", "A", 1, "m"), Prediction("2", "A", 1, "m")])
        self.assertEqual(report["exact_accuracy"], .5)
        self.assertEqual(report["by_category"]["emotion"]["exact_accuracy"], 0)

    def test_submission_order_and_digest(self):
        test = [row(2, 2), row(1, 1)]
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "submission.csv"
            meta = write_submission(test, [Prediction("1", "B", 1, "m"), Prediction("2", "A", 1, "m")], out)
            lines = out.read_text().splitlines()
            self.assertEqual(lines[1:], ["2,A", "1,B"])
            self.assertEqual(len(meta["sha256"]), 64)

    def test_prediction_csv_rejects_nonfinite_confidence(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "p.csv"
            p.write_text("qa_id,prediction,confidence\n1,A,nan\n")
            with self.assertRaises(ContractError):
                read_prediction_csv(p)

    def test_readiness_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "readiness.json"
            p.write_text(json.dumps({
                "written_dataset_authorization": authorization(),
                "official_registration_complete": False,
                "kaggle_rules_accepted": False,
                "dataset_terms_accepted": False,
                "submission_authorized": False,
                "validation": {"subject_disjoint": False, "exact_accuracy": None},
                "submission": {"path": "", "sha256": ""},
            }))
            ready, reasons = check(p)
            self.assertFalse(ready)
            self.assertGreaterEqual(len(reasons), 6)

    def test_readiness_rejects_missing_written_authorization(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            artifact = td / "submission.csv"
            artifact.write_text("qa_id,prediction\n1,A\n")
            state_data = ready_state(artifact)
            state_data.pop("written_dataset_authorization")
            state = td / "state.json"
            state.write_text(json.dumps(state_data))
            ready, reasons = check(state)
            self.assertFalse(ready)
            self.assertIn("written dataset authorization missing", reasons)

    def test_readiness_rejects_broadened_authorization_scope(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            artifact = td / "submission.csv"
            artifact.write_text("qa_id,prediction\n1,A\n")
            state_data = ready_state(artifact)
            state_data["written_dataset_authorization"] = authorization(scope="unconditional")
            state = td / "state.json"
            state.write_text(json.dumps(state_data))
            ready, reasons = check(state)
            self.assertFalse(ready)
            self.assertIn("written dataset authorization scope missing/invalid", reasons)

    def test_readiness_accepts_exact_hashed_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            artifact = td / "submission.csv"
            artifact.write_text("qa_id,prediction\n1,A\n")
            state = td / "state.json"
            state.write_text(json.dumps(ready_state(artifact)))
            ready, reasons = check(state)
            self.assertTrue(ready)
            self.assertEqual(reasons, [])


if __name__ == "__main__":
    unittest.main()
