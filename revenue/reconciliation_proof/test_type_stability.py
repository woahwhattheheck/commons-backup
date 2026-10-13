from __future__ import annotations

import unittest

from .proof import build_proof

AS_OF = "2026-09-13T09:15:00Z"
EVIDENCE = "0" * 64
SPEC = {
    "schema": "reconciliation-proof/v1",
    "profile": "type-stability",
    "required_fields": ["value"],
    "ignored_fields": [],
    "require_evidence_identity": True,
    "require_version_identity": True,
    "max_records_per_side": 10,
}


def rec(value):
    return {
        "record_id": "r1",
        "version": 1,
        "observed_at": "2026-09-13T09:00:00Z",
        "fields": {"value": value},
        "evidence_sha256": EVIDENCE,
    }


class ReconciliationTypeStabilityTests(unittest.TestCase):
    def assert_type_mismatch_holds(self, left_value, right_value):
        receipt = build_proof(SPEC, [rec(left_value)], [rec(right_value)], as_of=AS_OF)
        self.assertEqual(receipt["status"], "HOLD")
        self.assertEqual(receipt["counts"]["matched"], 0)
        self.assertIn("FIELD_MISMATCH", receipt["outcomes"][0]["reasons"])
        self.assertEqual(receipt["outcomes"][0]["mismatch_fields"], ["value"])

    def test_boolean_and_integer_are_not_equal(self):
        self.assert_type_mismatch_holds(True, 1)

    def test_integer_and_float_are_not_equal(self):
        self.assert_type_mismatch_holds(1, 1.0)

    def test_nested_boolean_and_integer_are_not_equal(self):
        self.assert_type_mismatch_holds({"nested": [True]}, {"nested": [1]})

    def test_positive_and_negative_zero_are_not_equal(self):
        self.assert_type_mismatch_holds(0.0, -0.0)


if __name__ == "__main__":
    unittest.main()
