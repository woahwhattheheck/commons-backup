from __future__ import annotations

import copy
import unittest
from pathlib import Path

import matrix


HERE = Path(__file__).resolve().parent
BASELINE = matrix.load_matrix(HERE / "requirements.json")


class ReviewedSourceBindingTests(unittest.TestCase):
    def fresh(self) -> dict:
        return copy.deepcopy(BASELINE)

    @staticmethod
    def requirement(value: dict, requirement_id: str) -> dict:
        return next(item for item in value["requirements"] if item["id"] == requirement_id)

    def test_caller_cannot_promote_unknown_to_pass_with_self_consistent_support(self) -> None:
        value = self.fresh()
        target = self.requirement(value, "fips-140-3")
        target["status"] = "PASS"
        target["public_evidence"][0]["relationship"] = "direct_support"
        target["rationale"] = (
            "Caller-edited rationale that is structurally long enough and internally "
            "consistent but was not authorized by the reviewed source generation."
        )
        with self.assertRaisesRegex(matrix.MatrixError, "classification differs from reviewed source"):
            matrix.build_receipt(value)

    def test_caller_cannot_promote_unknown_to_red_with_self_consistent_contradiction(self) -> None:
        value = self.fresh()
        target = self.requirement(value, "prompt-injection-defenses")
        target["status"] = "RED"
        target["public_evidence"][0]["relationship"] = "direct_contradiction"
        target["rationale"] = (
            "Caller-edited contradiction that is structurally valid but was not "
            "authorized by the reviewed source generation."
        )
        with self.assertRaisesRegex(matrix.MatrixError, "classification differs from reviewed source"):
            matrix.build_receipt(value)

    def test_same_status_semantic_substitution_cannot_retain_reviewed_authority(self) -> None:
        value = self.fresh()
        target = self.requirement(value, "fips-140-3")
        self.assertEqual(target["status"], "UNKNOWN")
        target["county_requirement"] = (
            "Caller-substituted County requirement text that remains structurally valid "
            "but is not part of the reviewed source generation."
        )
        target["public_evidence"][0]["claim"] = (
            "Caller-substituted adjacent evidence claim that does not alter status or "
            "relationship but must not inherit reviewed-source authority."
        )
        target["rationale"] = (
            "Caller-substituted rationale that preserves UNKNOWN while changing the "
            "semantic assessment and therefore must fail closed."
        )
        target["closure_artifact"] = (
            "Caller-substituted closure artifact request that was never reviewed."
        )
        with self.assertRaisesRegex(matrix.MatrixError, "matrix differs from reviewed source generation"):
            matrix.build_receipt(value)

    def test_receipt_names_the_reviewed_source_generation(self) -> None:
        receipt = matrix.build_receipt(self.fresh())
        self.assertEqual(
            receipt["reviewed_source_matrix_sha256"],
            matrix.REVIEWED_SOURCE_MATRIX_SHA256,
        )
        self.assertEqual(
            matrix.REVIEWED_SOURCE_MATRIX_SHA256,
            "e6e857e1df33a6b6d486252fd1e0f1f243fdf0818b48ebfe6a80525e5dc19f42",
        )


if __name__ == "__main__":
    unittest.main()
