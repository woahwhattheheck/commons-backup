"""Independent wire-contract regression; NOT a full compiler integration run.

The fixture vocabulary is read from the parent's actual constants source, never
from handoff_review.CELLS. Only the semantic verifier is explicitly stubbed here;
test_handoff_review.ParentCompilerIntegration exercises the real compiler.
"""
from __future__ import annotations

import ast
import copy
from pathlib import Path
import unittest
from unittest.mock import patch

import handoff_review as hr


PARENT = Path(__file__).resolve().parents[1] / "uiowa_rfq_18649_workshare"


def parent_literal(name: str) -> tuple[str, ...]:
    """Read the parent declaration without importing its runtime dependency graph."""
    tree = ast.parse((PARENT / "workshare_constants.py").read_text(encoding="utf-8"))
    matches = [node.value for node in tree.body if isinstance(node, ast.Assign)
               and any(isinstance(target, ast.Name) and target.id == name
                       for target in node.targets)]
    if len(matches) != 1:
        raise AssertionError(f"Expected one literal parent declaration: {name}")
    value = ast.literal_eval(matches[0])
    if not isinstance(value, tuple) or not value or any(not isinstance(x, str) for x in value):
        raise AssertionError(f"Parent {name} must remain a nonempty string tuple")
    if len(set(value)) != len(value):
        raise AssertionError(f"Parent {name} contains duplicates")
    return value


def wire_report() -> dict:
    return {
        "schema": "WIRE_CONTRACT_STUB_NOT_COMPILER_OUTPUT",
        "mode": "UNTRUSTED_INSPECTION",
        "receipt_sha256": "1" * 64,
        "aggregate_state": "HOLD_TRUSTED_AUTHORITY_REQUIRED",
        "trust": {"authority_root_supplied_out_of_band": False,
                  "current_evidence_review_authority": False},
        "assessment_matrix": [
            {"group": group, "dimension": dimension,
             "status": "HOLD_MISSING_EVIDENCE",
             "source_ids": [f"SYNTHETIC-{group}-{dimension}"],
             "source_record_sha256s": ["2" * 64],
             "reason_codes": ["WIRE_CONTRACT_FIXTURE"]}
            for group in parent_literal("GROUPS")
            for dimension in parent_literal("DIMENSIONS")
        ],
    }


def stub_integrity(report: dict) -> dict:
    return {"integrity_valid": True, "semantic_recompile_valid": True,
            "trusted_authority_root_verified": False,
            "current_authority_verified": False,
            "receipt_sha256": report["receipt_sha256"]}


class ParentVocabularyContract(unittest.TestCase):
    def setUp(self):
        self.report = wire_report()
        self.handoff = hr._blank_handoff(self.report)
        self.verifier = patch.object(hr, "_parent_integrity", side_effect=stub_integrity)
        self.verifier.start()
        self.addCleanup(self.verifier.stop)

    def test_vocabulary_matches_real_parent_not_ui_placeholder(self):
        expected = tuple((group, dimension) for group in parent_literal("GROUPS")
                         for dimension in parent_literal("DIMENSIONS"))
        self.assertEqual(hr.CELLS, expected)
        self.assertEqual(len(expected), 12)
        self.assertIn("software", parent_literal("DIMENSIONS"))
        self.assertNotIn("software_development", parent_literal("DIMENSIONS"))

    def test_parent_shaped_matrix_reconciles_without_identifier_translation(self):
        before = copy.deepcopy((self.report, self.handoff))
        result = hr.reconcile(self.report, [("wire-fixture", self.handoff)])
        self.assertEqual(result["reason_counts"], {"ALL_UNREVIEWED": 12})
        software = [cell for cell in result["assessment_cells"] if cell["dimension"] == "software"]
        self.assertEqual(len(software), 3)
        for cell in software:
            self.assertEqual(cell["source_ids"], [f"SYNTHETIC-{cell['group']}-software"])
            self.assertEqual(cell["source_record_sha256s"], ["2" * 64])
        self.assertEqual((self.report, self.handoff), before)

    def test_ui_placeholder_dimension_is_not_silently_aliased_in_report(self):
        for cell in self.report["assessment_matrix"]:
            if cell["dimension"] == "software":
                cell["dimension"] = "software_development"
        with self.assertRaisesRegex(hr.ReviewError, "unknown or duplicate report cell"):
            hr.reconcile(self.report, [("wire-fixture", self.handoff)])

    def test_ui_placeholder_dimension_is_not_silently_aliased_in_handoff(self):
        for cell in self.handoff["cell_notes"]:
            if cell["dimension"] == "software":
                cell["dimension"] = "software_development"
        with self.assertRaisesRegex(hr.ReviewError, "unknown or duplicate handoff cell"):
            hr.reconcile(self.report, [("wire-fixture", self.handoff)])

    def test_software_disagreement_and_exact_notes_survive(self):
        second = copy.deepcopy(self.handoff)
        first_cell = next(cell for cell in self.handoff["cell_notes"]
                          if (cell["group"], cell["dimension"]) == ("ESS", "software"))
        second_cell = next(cell for cell in second["cell_notes"]
                           if (cell["group"], cell["dimension"]) == ("ESS", "software"))
        note = "SYNTHETIC: scope is unresolved.\nRetain café and 🙂 exactly."
        first_cell.update(disposition="NEEDS_EVIDENCE", analyst_note=note)
        second_cell.update(disposition="DISCUSS_WITH_PRIME", analyst_note="SYNTHETIC: clarify window.")
        result = hr.reconcile(self.report, [("a", self.handoff), ("b", second)])
        cell = next(cell for cell in result["assessment_cells"]
                    if (cell["group"], cell["dimension"]) == ("ESS", "software"))
        self.assertIn("DISPOSITION_DISAGREEMENT", cell["review_reason_codes"])
        self.assertEqual(cell["entries"][0]["analyst_note"], note)
        self.assertTrue(all(value is False for value in result["authority"].values()))

    def test_correct_vocabulary_never_substitutes_for_semantic_verification(self):
        with patch.object(hr, "_parent_integrity", side_effect=hr.ReviewError("semantic failure")):
            with self.assertRaisesRegex(hr.ReviewError, "semantic failure"):
                hr.reconcile(self.report, [("wire-fixture", self.handoff)])

    def test_parent_source_is_required_not_guessed(self):
        with patch.object(Path, "read_text", side_effect=FileNotFoundError("missing parent source")):
            with self.assertRaises(FileNotFoundError):
                parent_literal("DIMENSIONS")


if __name__ == "__main__":
    unittest.main()
