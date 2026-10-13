from __future__ import annotations

import copy
import unittest

from revenue.tate_lyle_cp_kelco_solution_proof_gate.codec import digest
from revenue.tate_lyle_cp_kelco_solution_proof_gate.fixture import make_acceptance_batch, make_acceptance_reference_set
from revenue.tate_lyle_cp_kelco_solution_proof_gate.gate import GateInputError, evaluate, reference_commitment, verify
from revenue.tate_lyle_cp_kelco_solution_proof_gate.rules import HOLD_LEGACY, HOLD_OWNER, HOLD_REGION, HOLD_SPEC, HOLD_STABILITY

EXPECTED_COUNTS = {
    HOLD_SPEC: 20,
    HOLD_REGION: 15,
    HOLD_LEGACY: 15,
    HOLD_STABILITY: 15,
    HOLD_OWNER: 10,
}


def inputs():
    batch = make_acceptance_batch()
    refs = make_acceptance_reference_set()
    return batch, refs, reference_commitment(refs)


class AcceptanceTests(unittest.TestCase):
    def test_acceptance_counts(self) -> None:
        batch, refs, pin = inputs()
        result = evaluate(batch, references=refs, expected_reference_sha256=pin)
        receipt = result["receipt"]
        self.assertEqual(receipt["record_count"], 120)
        self.assertEqual(receipt["pass_count"], 90)
        self.assertEqual(receipt["hold_count"], 30)
        self.assertEqual(receipt["seeded_defect_count"], 75)
        self.assertEqual(receipt["source_writes"], 0)
        self.assertEqual(receipt["network_writes"], 0)
        self.assertIs(receipt["external_authority"], False)
        self.assertIs(receipt["trusted_reference_provenance_authenticated_by_this_package"], False)
        self.assertTrue(verify(result, batch=batch, references=refs, expected_reference_sha256=pin))

    def test_defect_mix(self) -> None:
        batch, refs, pin = inputs()
        rows = evaluate(batch, references=refs, expected_reference_sha256=pin)["manifest"]["rows"]
        counts = {code: 0 for code in EXPECTED_COUNTS}
        for row in rows:
            for code in row["holds"]:
                counts[code] += 1
        self.assertEqual(counts, EXPECTED_COUNTS)

    def test_exact_30_seeded_rows_hold_and_90_clean_pass(self) -> None:
        batch, refs, pin = inputs()
        rows = evaluate(batch, references=refs, expected_reference_sha256=pin)["manifest"]["rows"]
        by_id = {row["record_id"]: row for row in rows}
        for i in range(1, 91):
            self.assertEqual(by_id[f"REC-{i:03d}"]["status"], "PASS")
        for i in range(91, 121):
            self.assertEqual(by_id[f"REC-{i:03d}"]["status"], "HOLD")

    def test_deterministic_replay(self) -> None:
        batch, refs, pin = inputs()
        a = evaluate(batch, references=refs, expected_reference_sha256=pin)
        b = evaluate(copy.deepcopy(batch), references=copy.deepcopy(refs), expected_reference_sha256=pin)
        self.assertEqual(digest(a), digest(b))

    def test_duplicate_identical_candidate_collapses(self) -> None:
        batch, refs, pin = inputs()
        batch["records"].append(dict(batch["records"][0]))
        result = evaluate(batch, references=refs, expected_reference_sha256=pin)
        self.assertEqual(result["receipt"]["record_count"], 120)

    def test_same_id_changed_candidate_refuses(self) -> None:
        batch, refs, pin = inputs()
        changed = dict(batch["records"][0]); changed["region"] = "APAC"
        batch["records"].append(changed)
        with self.assertRaises(GateInputError):
            evaluate(batch, references=refs, expected_reference_sha256=pin)

    def test_old_candidate_self_authority_fields_rejected(self) -> None:
        batch, refs, pin = inputs()
        batch["records"][0]["approved_spec_revision"] = batch["records"][0]["spec_revision"]
        with self.assertRaises(GateInputError):
            evaluate(batch, references=refs, expected_reference_sha256=pin)

    def test_coupled_spec_mutation_cannot_self_authorize(self) -> None:
        batch, refs, pin = inputs()
        batch["records"][0]["spec_revision"] = "SPEC-999"
        tampered_refs = copy.deepcopy(refs)
        tampered_refs["records"][0]["approved_spec_revision"] = "SPEC-999"
        with self.assertRaises(GateInputError):
            evaluate(batch, references=tampered_refs, expected_reference_sha256=pin)

    def test_arbitrary_legacy_remap_holds(self) -> None:
        batch, refs, pin = inputs()
        batch["records"][50]["legacy_code"] = "ATTACKER-SELECTED"
        result = evaluate(batch, references=refs, expected_reference_sha256=pin)
        row = next(r for r in result["manifest"]["rows"] if r["record_id"] == "REC-051")
        self.assertEqual(row["status"], "HOLD")
        self.assertIn(HOLD_LEGACY, row["holds"])

    def test_reference_generation_mutation_refuses_under_old_pin(self) -> None:
        batch, refs, pin = inputs()
        refs["generation"] = "ATTACKER-GENERATION"
        with self.assertRaises(GateInputError):
            evaluate(batch, references=refs, expected_reference_sha256=pin)

    def test_wrong_reference_pin_refuses(self) -> None:
        batch, refs, _ = inputs()
        with self.assertRaises(GateInputError):
            evaluate(batch, references=refs, expected_reference_sha256="0" * 64)

    def test_substituted_reference_authority_breaks_verify(self) -> None:
        batch, refs, pin = inputs()
        result = evaluate(batch, references=refs, expected_reference_sha256=pin)
        other = copy.deepcopy(refs); other["generation"] = "OTHER-GENERATION"
        other_pin = reference_commitment(other)
        self.assertFalse(verify(result, batch=batch, references=other, expected_reference_sha256=other_pin))

    def test_unused_reference_authority_refuses(self) -> None:
        batch, refs, pin = inputs()
        extra = copy.deepcopy(refs["records"][0]); extra["record_id"] = "REC-999"
        refs["records"].append(extra)
        new_pin = reference_commitment(refs)
        with self.assertRaises(GateInputError):
            evaluate(batch, references=refs, expected_reference_sha256=new_pin)

    def test_missing_reference_authority_refuses(self) -> None:
        batch, refs, _ = inputs()
        refs["records"].pop()
        pin = reference_commitment(refs)
        with self.assertRaises(GateInputError):
            evaluate(batch, references=refs, expected_reference_sha256=pin)

    def test_reference_identity_transplant_refuses(self) -> None:
        batch, refs, _ = inputs()
        refs["records"][0]["ingredient_id"] = "ING-ATTACKER"
        pin = reference_commitment(refs)
        with self.assertRaises(GateInputError):
            evaluate(batch, references=refs, expected_reference_sha256=pin)

    def test_result_tamper_rejected(self) -> None:
        batch, refs, pin = inputs()
        result = evaluate(batch, references=refs, expected_reference_sha256=pin)
        result["receipt"]["pass_count"] = 91
        self.assertFalse(verify(result, batch=batch, references=refs, expected_reference_sha256=pin))

    def test_order_invariant_candidate_and_reference_records(self) -> None:
        batch, refs, pin = inputs()
        result = evaluate(batch, references=refs, expected_reference_sha256=pin)
        batch["records"].reverse(); refs["records"].reverse()
        self.assertEqual(result, evaluate(batch, references=refs, expected_reference_sha256=pin))

    def test_reference_digest_bound_into_manifest_and_receipt(self) -> None:
        batch, refs, pin = inputs()
        result = evaluate(batch, references=refs, expected_reference_sha256=pin)
        self.assertEqual(result["receipt"]["reference_sha256"], pin)
        self.assertEqual(result["manifest"]["reference_sha256"], pin)
        self.assertEqual(result["receipt"]["reference_generation"], refs["generation"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
