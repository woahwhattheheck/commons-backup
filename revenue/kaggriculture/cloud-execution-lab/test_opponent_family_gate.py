# SPDX-License-Identifier: Apache-2.0
"""Contracts for S10 identity-free opponent-family gating."""
import unittest

from opponent_family_gate import (
    FAMILIES,
    CentroidClassifier,
    CalibratedCentroidClassifier,
    LabeledPrefix,
    Prediction,
    PublicPrefix,
    UnsafePrefix,
    evaluate_classifier,
    evaluate_rules,
    evaluate_ungated,
    family_disjoint_folds,
    gate_prediction,
    rules_prediction,
)


def prefix(**changes):
    row = {
        "turns_observed": 6,
        "early_unlock_events": 0,
        "animal_events": 0,
        "hire_events": 0,
        "route_events": 0,
        "market_events": 0,
    }
    row.update(changes)
    return row


def labeled(family, *, loss=0, **features):
    return {"family": family, "prefix": prefix(**features), "goop_loss_bp": loss}


class OpponentFamilyGateTests(unittest.TestCase):
    def test_public_prefix_rejects_identity_and_future_leakage(self):
        base = prefix()
        for forbidden in (
            "opponent", "opponent_id", "name", "uuid", "submission",
            "submission_id", "future_action", "future_actions",
        ):
            bad = dict(base); bad[forbidden] = "leak"
            with self.subTest(forbidden=forbidden):
                with self.assertRaises(UnsafePrefix):
                    PublicPrefix.from_mapping(bad)

    def test_labeled_row_rejects_identity_extras(self):
        base = labeled("early_unlock", early_unlock_events=3)
        for forbidden in ("opponent", "name", "submission", "future_actions"):
            bad = dict(base); bad[forbidden] = "leak"
            with self.subTest(forbidden=forbidden):
                with self.assertRaises(UnsafePrefix):
                    LabeledPrefix.from_mapping(bad)

    def test_zero_prefix_is_unknown_and_falls_back(self):
        prediction = rules_prediction(prefix())
        self.assertEqual(prediction, Prediction(None, 0))
        decision = gate_prediction(prediction)
        self.assertFalse(decision.use_goop)
        self.assertEqual(decision.reason, "unknown_prefix")

    def test_rule_unique_strongest_family(self):
        prediction = rules_prediction(prefix(animal_events=4, route_events=1))
        self.assertEqual(prediction.family, "animal")
        self.assertEqual(prediction.confidence_ppm, 800_000)
        self.assertTrue(gate_prediction(prediction).use_goop)

    def test_rule_tie_is_unknown(self):
        prediction = rules_prediction(prefix(hire_events=2, route_events=2))
        self.assertIsNone(prediction.family)
        self.assertFalse(gate_prediction(prediction).use_goop)

    def test_centroid_tie_is_unknown_even_at_low_threshold(self):
        model = CentroidClassifier.fit([
            labeled("animal", animal_events=5),
            labeled("hire", hire_events=5),
        ])
        prediction = model.predict(prefix(animal_events=3, hire_events=3))
        self.assertIsNone(prediction.family)
        self.assertEqual(prediction.confidence_ppm, 500_000)
        decision = gate_prediction(prediction, threshold_ppm=1)
        self.assertFalse(decision.use_goop)
        self.assertEqual(decision.reason, "unknown_prefix")
        calibrated = CalibratedCentroidClassifier.fit(
            [
                labeled("animal", animal_events=5),
                labeled("hire", hire_events=5),
            ],
            [
                labeled("animal", animal_events=5),
                labeled("hire", hire_events=5),
            ],
        )
        calibrated_prediction = calibrated.predict(prefix(animal_events=3, hire_events=3))
        self.assertIsNone(calibrated_prediction.family)
        self.assertFalse(gate_prediction(calibrated_prediction, threshold_ppm=1).use_goop)

    def test_low_confidence_uses_canonical(self):
        decision = gate_prediction(Prediction("market", 599_999), threshold_ppm=600_000)
        self.assertFalse(decision.use_goop)
        self.assertEqual(decision.reason, "low_confidence")

    def test_classifier_fits_only_public_behavior(self):
        rows = [
            labeled("early_unlock", early_unlock_events=5),
            labeled("animal", animal_events=5),
            labeled("hire", hire_events=5),
            labeled("route", route_events=5),
            labeled("market", market_events=5),
        ]
        model = CentroidClassifier.fit(rows)
        for family, field in zip(FAMILIES, (
            "early_unlock_events", "animal_events", "hire_events", "route_events", "market_events"
        )):
            with self.subTest(family=family):
                prediction = model.predict(prefix(**{field: 4}))
                self.assertEqual(prediction.family, family)

    def test_classifier_is_repeatable(self):
        rows = [
            labeled("early_unlock", early_unlock_events=5, market_events=1),
            labeled("animal", animal_events=5, route_events=1),
            labeled("hire", hire_events=5, early_unlock_events=1),
            labeled("route", route_events=5, animal_events=1),
            labeled("market", market_events=5, hire_events=1),
        ]
        a = CentroidClassifier.fit(rows)
        b = CentroidClassifier.fit(rows)
        probe = prefix(route_events=4, animal_events=1)
        self.assertEqual(a, b)
        self.assertEqual(a.predict(probe), b.predict(probe))

    def test_family_disjoint_folds_withhold_exact_family(self):
        rows = [
            labeled("early_unlock", early_unlock_events=5),
            labeled("animal", animal_events=5),
            labeled("hire", hire_events=5),
        ]
        folds = family_disjoint_folds(rows)
        self.assertEqual([family for family, _, _ in folds], ["early_unlock", "animal", "hire"])
        for held_out, train, test in folds:
            self.assertTrue(test)
            self.assertTrue(all(row.family == held_out for row in test))
            self.assertTrue(all(row.family != held_out for row in train))

    def test_evaluation_reports_confusion_calibration_and_fallback(self):
        train = [
            labeled("early_unlock", early_unlock_events=6),
            labeled("animal", animal_events=6),
            labeled("hire", hire_events=6),
            labeled("route", route_events=6),
            labeled("market", market_events=6),
        ]
        eval_rows = [
            labeled("animal", loss=700, animal_events=5),
            labeled("route", loss=300, route_events=3, market_events=2),
            labeled("market", loss=900),
        ]
        model = CentroidClassifier.fit(train)
        report = evaluate_classifier(model, eval_rows, threshold_ppm=400_000)
        self.assertEqual(report["samples"], 3)
        self.assertIn("calibration_error_bp", report)
        self.assertEqual(report["fallback"], 1)
        self.assertEqual(report["confusion"]["market"]["unknown"], 1)

    def test_misclassification_loss_counts_only_wrong_confident_goop(self):
        row = LabeledPrefix.from_mapping(labeled("animal", loss=1200, animal_events=5))
        from opponent_family_gate import evaluate_predictions
        report = evaluate_predictions([row], [Prediction("route", 900_000)])
        self.assertEqual(report["goop_uses"], 1)
        self.assertEqual(report["gated_goop_loss_bp"], 1200)
        self.assertEqual(report["misclassification_loss_bp"], 1200)

    def test_fallback_avoids_goop_loss(self):
        row = LabeledPrefix.from_mapping(labeled("animal", loss=1200, animal_events=5))
        from opponent_family_gate import evaluate_predictions
        report = evaluate_predictions([row], [Prediction("route", 300_000)])
        self.assertEqual(report["fallback"], 1)
        self.assertEqual(report["gated_goop_loss_bp"], 0)
        self.assertEqual(report["misclassification_loss_bp"], 0)

    def test_ungated_uses_goop_on_every_row(self):
        rows = [
            labeled("animal", loss=100, animal_events=5),
            labeled("route", loss=250, route_events=5),
        ]
        report = evaluate_ungated(rows)
        self.assertEqual(report["goop_uses"], 2)
        self.assertEqual(report["fallback"], 0)
        self.assertEqual(report["gated_goop_loss_bp"], 350)

    def test_rules_can_reduce_loss_vs_ungated_by_falling_back(self):
        rows = [
            labeled("animal", loss=0, animal_events=6),
            labeled("route", loss=1500, route_events=1, market_events=1),
            labeled("market", loss=1800),
        ]
        rules = evaluate_rules(rows)
        ungated = evaluate_ungated(rows)
        self.assertLess(rules["gated_goop_loss_bp"], ungated["gated_goop_loss_bp"])
        self.assertGreater(rules["fallback"], 0)

    def test_missing_family_support_does_not_invent_centroid(self):
        model = CentroidClassifier.fit([
            labeled("animal", animal_events=4),
            labeled("route", route_events=4),
        ])
        self.assertEqual(model.support, (0, 1, 0, 1, 0))
        self.assertIsNone(model.centroids[0])
        self.assertIsNone(model.centroids[2])
        self.assertIsNone(model.centroids[4])

    def test_bool_negative_and_extra_fields_fail_closed(self):
        bad_prefixes = [
            prefix(turns_observed=True),
            prefix(animal_events=-1),
            prefix(market_events=True),
        ]
        for bad in bad_prefixes:
            with self.subTest(bad=bad):
                with self.assertRaises(UnsafePrefix):
                    PublicPrefix.from_mapping(bad)
        with self.assertRaises(UnsafePrefix):
            LabeledPrefix.from_mapping(labeled("animal", loss=10_001, animal_events=1))

    def test_calibration_confusion_are_deterministic(self):
        train = [
            labeled("early_unlock", early_unlock_events=7, market_events=1),
            labeled("animal", animal_events=7, route_events=1),
            labeled("hire", hire_events=7, early_unlock_events=1),
            labeled("route", route_events=7, animal_events=1),
            labeled("market", market_events=7, hire_events=1),
        ]
        eval_rows = [
            labeled("early_unlock", early_unlock_events=5, market_events=1),
            labeled("animal", animal_events=5, route_events=1),
            labeled("hire", hire_events=5, early_unlock_events=1),
            labeled("route", route_events=5, animal_events=1),
            labeled("market", market_events=5, hire_events=1),
        ]
        model = CentroidClassifier.fit(train)
        self.assertEqual(evaluate_classifier(model, eval_rows), evaluate_classifier(model, eval_rows))

    def test_empirical_calibration_can_only_lower_confidence(self):
        training = [
            labeled("animal", animal_events=5),
            labeled("route", route_events=5),
        ]
        calibration = [
            labeled("animal", animal_events=5),
            labeled("route", route_events=5),
            labeled("route", animal_events=5),
            labeled("animal", route_events=5),
        ]
        raw = CentroidClassifier.fit(training).predict(prefix(animal_events=5))
        calibrated = CalibratedCentroidClassifier.fit(training, calibration)
        prediction = calibrated.predict(prefix(animal_events=5))
        self.assertLessEqual(prediction.confidence_ppm, raw.confidence_ppm)
        self.assertEqual(calibrated.confidence_cap_ppm, 500_000)
        self.assertFalse(gate_prediction(prediction, threshold_ppm=600_000).use_goop)

    def test_empty_calibration_forces_canonical_fallback(self):
        calibrated = CalibratedCentroidClassifier.fit(
            [labeled("animal", animal_events=5)],
            [],
        )
        prediction = calibrated.predict(prefix(animal_events=5))
        self.assertEqual(prediction.confidence_ppm, 0)
        self.assertFalse(gate_prediction(prediction).use_goop)


if __name__ == "__main__":
    unittest.main()
