from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
MODULE_PATH = HERE / "response_pack.py"
SPEC = importlib.util.spec_from_file_location("alcorn_response_pack", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load response_pack module")
rp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rp)


class ResponsePackTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        parent = Path(self.tmp.name) / "alcorn-rfp-5588"
        self.root = parent / "response_pack"
        shutil.copytree(HERE, self.root)
        for name in (
            "qualification_spec.json",
            "current_evidence.json",
            "current_result.json",
            "qualification.py",
            "qualification_guarded.py",
        ):
            shutil.copy2(HERE.parent / name, parent / name)

    def load(self, path: Path):
        return json.loads(path.read_text(encoding="utf-8"))

    def dump(self, path: Path, value) -> None:
        path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def result_path(self) -> Path:
        return self.root.parent / "current_result.json"

    def evidence_path(self) -> Path:
        return self.root.parent / "current_evidence.json"

    def test_current_pack_is_complete_but_authenticated_qualification_held(self) -> None:
        receipt = rp.compile_pack(self.root)
        self.assertEqual(receipt["state"], "HOLD_QUALIFICATION")
        self.assertEqual(receipt["reason"], "canonical_authenticated_qualification_not_ready")
        self.assertEqual(receipt["qualification_state"], "HOLD")
        self.assertTrue(receipt["qualification_blockers"])
        self.assertTrue(receipt["qualification_authenticated_replay"])
        self.assertFalse(receipt["source_buyer_artifacts_resolved"])
        self.assertFalse(receipt["owner_gates_ready"])
        self.assertTrue(receipt["response_artifacts_prepared"])
        self.assertTrue(all(value is False for value in receipt["authority"].values()))
        self.assertEqual(len(receipt["receipt_sha256"]), 64)
        self.assertEqual(
            set(receipt["source_missing_buyer_artifacts"]),
            rp.EXPECTED_MISSING_BUYER_ARTIFACTS,
        )

    def test_compile_is_deterministic(self) -> None:
        one = rp.compile_pack(self.root)
        two = rp.compile_pack(self.root)
        self.assertEqual(one, two)
        self.assertEqual(one["receipt_sha256"], two["receipt_sha256"])

    def test_receipt_verification_rejects_tamper(self) -> None:
        receipt = rp.compile_pack(self.root)
        path = self.root / "receipt.json"
        self.dump(path, receipt)
        self.assertEqual(rp.verify_receipt(path, self.root), receipt)
        receipt["state"] = "OWNER_READY_FOR_SUBMIT"
        self.dump(path, receipt)
        with self.assertRaises(rp.ContractError):
            rp.verify_receipt(path, self.root)

    def test_missing_artifact_fails_closed(self) -> None:
        (self.root / "technical_approach.md").unlink()
        with self.assertRaisesRegex(rp.ContractError, "required response artifact missing"):
            rp.compile_pack(self.root)

    def test_tiny_placeholder_artifact_fails_closed(self) -> None:
        (self.root / "technical_approach.md").write_text("draft\n", encoding="utf-8")
        with self.assertRaisesRegex(rp.ContractError, "too small"):
            rp.compile_pack(self.root)

    def test_required_anchor_removal_fails_closed(self) -> None:
        path = self.root / "risk_redline_questions.md"
        text = path.read_text(encoding="utf-8").replace("Closure rule", "Closing note")
        path.write_text(text, encoding="utf-8")
        with self.assertRaisesRegex(rp.ContractError, "lost required anchors"):
            rp.compile_pack(self.root)

    def test_customer_price_amount_cannot_be_published(self) -> None:
        path = self.root / "pricing_basis.json"
        pricing = self.load(path)
        pricing["customer_price_amount"] = 12345
        self.dump(path, pricing)
        with self.assertRaisesRegex(rp.ContractError, "may not contain a customer price amount"):
            rp.compile_pack(self.root)

    def test_price_release_cannot_be_self_authorized(self) -> None:
        path = self.root / "pricing_basis.json"
        pricing = self.load(path)
        pricing["customer_price_released"] = True
        self.dump(path, pricing)
        with self.assertRaisesRegex(rp.ContractError, "may not release"):
            rp.compile_pack(self.root)

    def test_pricing_approval_requires_source_bound_evidence_id(self) -> None:
        path = self.root / "pricing_basis.json"
        pricing = self.load(path)
        pricing["pricing_approved"] = True
        self.dump(path, pricing)
        with self.assertRaisesRegex(rp.ContractError, "requires a source-bound pricing approval evidence id"):
            rp.compile_pack(self.root)

    def test_approved_pricing_requires_buyer_cost_form(self) -> None:
        path = self.root / "pricing_basis.json"
        pricing = self.load(path)
        pricing["pricing_approved"] = True
        pricing["pricing_approval_evidence_id"] = "owner:pricing-approval:example"
        self.dump(path, pricing)
        with self.assertRaisesRegex(rp.ContractError, "requires the controlling buyer cost form"):
            rp.compile_pack(self.root)

    def test_unapproved_pricing_may_not_carry_approval_receipt(self) -> None:
        path = self.root / "pricing_basis.json"
        pricing = self.load(path)
        pricing["pricing_approval_evidence_id"] = "owner:pricing-approval:example"
        self.dump(path, pricing)
        with self.assertRaisesRegex(rp.ContractError, "unapproved pricing basis may not carry"):
            rp.compile_pack(self.root)

    def test_buyer_cost_form_claim_does_not_override_canonical_source_hold(self) -> None:
        path = self.root / "pricing_basis.json"
        pricing = self.load(path)
        pricing["buyer_cost_form_present"] = True
        self.dump(path, pricing)
        receipt = rp.compile_pack(self.root)
        self.assertEqual(receipt["state"], "HOLD_QUALIFICATION")
        self.assertFalse(receipt["source_buyer_artifacts_resolved"])
        self.assertIn("section_viii_cost_information", receipt["source_missing_buyer_artifacts"])

    def test_numeric_cost_bucket_value_fails_closed(self) -> None:
        path = self.root / "pricing_basis.json"
        pricing = self.load(path)
        pricing["cost_buckets"][0]["internal_estimate"] = 1
        self.dump(path, pricing)
        with self.assertRaisesRegex(rp.ContractError, "contains numeric value"):
            rp.compile_pack(self.root)

    def test_float_json_is_rejected_before_semantics(self) -> None:
        path = self.root / "pricing_basis.json"
        text = path.read_text(encoding="utf-8")
        text = text[:-2] + ',\n  "accidental_float": 1.5\n}\n'
        path.write_text(text, encoding="utf-8")
        with self.assertRaisesRegex(rp.ContractError, "floating-point"):
            rp.compile_pack(self.root)

    def test_plan_cannot_point_at_alternate_qualification_result(self) -> None:
        path = self.root / "response_plan.json"
        plan = self.load(path)
        plan["source_bindings"]["qualification_result"] = "shadow_result.json"
        self.dump(path, plan)
        with self.assertRaisesRegex(rp.ContractError, "canonical qualification result"):
            rp.compile_pack(self.root)

    def test_plan_cannot_grant_submission_authority(self) -> None:
        path = self.root / "response_plan.json"
        plan = self.load(path)
        plan["authority_ceiling"]["proposal_submission_authorized"] = True
        self.dump(path, plan)
        with self.assertRaisesRegex(rp.ContractError, "may not grant external authority"):
            rp.compile_pack(self.root)

    def test_plan_cannot_hide_required_artifact(self) -> None:
        path = self.root / "response_plan.json"
        plan = self.load(path)
        plan["artifacts"] = plan["artifacts"][:-1]
        self.dump(path, plan)
        with self.assertRaisesRegex(rp.ContractError, "artifact set drift"):
            rp.compile_pack(self.root)

    def test_plan_cannot_disable_declared_owner_gate(self) -> None:
        path = self.root / "response_plan.json"
        plan = self.load(path)
        plan["owner_gate_policy"]["pricing_must_be_owner_approved"] = False
        self.dump(path, plan)
        with self.assertRaisesRegex(rp.ContractError, "pricing_must_be_owner_approved must remain true"):
            rp.compile_pack(self.root)

    def test_plan_cannot_delete_declared_owner_gate(self) -> None:
        path = self.root / "response_plan.json"
        plan = self.load(path)
        del plan["owner_gate_policy"]["signature_officer_must_be_ready"]
        self.dump(path, plan)
        with self.assertRaisesRegex(rp.ContractError, "owner_gate_policy key drift"):
            rp.compile_pack(self.root)

    def test_unprepared_manifest_status_keeps_response_layer_unready(self) -> None:
        path = self.root / "response_plan.json"
        plan = self.load(path)
        plan["artifacts"][0]["status"] = "OWNER_INPUT_REQUIRED"
        self.dump(path, plan)
        receipt = rp.compile_pack(self.root)
        self.assertEqual(receipt["state"], "HOLD_QUALIFICATION")
        self.assertFalse(receipt["response_artifacts_prepared"])

    def test_spec_buyer_identity_drift_fails_closed(self) -> None:
        path = self.root.parent / "qualification_spec.json"
        spec = self.load(path)
        spec["opportunity"]["buyer"] = "Not Alcorn"
        self.dump(path, spec)
        with self.assertRaisesRegex(rp.ContractError, "buyer drift"):
            rp.compile_pack(self.root)

    def test_spec_packet_digest_drift_fails_closed(self) -> None:
        path = self.root.parent / "qualification_spec.json"
        spec = self.load(path)
        spec["source_packet"]["sha256"] = "0" * 64
        self.dump(path, spec)
        with self.assertRaisesRegex(rp.ContractError, "packet digest drift"):
            rp.compile_pack(self.root)

    def test_spec_addendum_semantic_drift_fails_closed(self) -> None:
        path = self.root.parent / "qualification_spec.json"
        spec = self.load(path)
        spec["buyer_addenda"][0]["normalized_effect"] = "PARTNER_AUTHORITY_GRANTED"
        self.dump(path, spec)
        with self.assertRaisesRegex(rp.ContractError, "semantic drift"):
            rp.compile_pack(self.root)

    def test_spec_cannot_hide_missing_buyer_form(self) -> None:
        path = self.root.parent / "qualification_spec.json"
        spec = self.load(path)
        spec["received_packet_structure"]["referenced_but_absent"] = spec["received_packet_structure"]["referenced_but_absent"][:-1]
        self.dump(path, spec)
        with self.assertRaisesRegex(rp.ContractError, "missing buyer-artifact set drift"):
            rp.compile_pack(self.root)

    def test_scoring_weight_drift_fails_closed(self) -> None:
        path = self.root.parent / "qualification_spec.json"
        spec = self.load(path)
        spec["scoring"]["lifecycle_cost"] = 34
        self.dump(path, spec)
        with self.assertRaisesRegex(rp.ContractError, "scoring model drift"):
            rp.compile_pack(self.root)

    def test_result_cannot_rewrite_addendum_as_oem_authority(self) -> None:
        path = self.result_path()
        result = self.load(path)
        result["source_findings"]["addendum_1"]["nvidia_oem_authority_granted"] = True
        self.dump(path, result)
        with self.assertRaisesRegex(rp.ContractError, "may not grant NVIDIA/OEM authority"):
            rp.compile_pack(self.root)

    def test_result_cannot_inherit_partner_credentials(self) -> None:
        path = self.result_path()
        result = self.load(path)
        result["source_findings"]["addendum_1"]["partner_credentials_inherited"] = True
        self.dump(path, result)
        with self.assertRaisesRegex(rp.ContractError, "may not inherit partner credentials"):
            rp.compile_pack(self.root)

    def test_result_authority_escalation_fails_closed(self) -> None:
        path = self.result_path()
        result = self.load(path)
        result["authority"]["buyer_contact_authorized"] = True
        self.dump(path, result)
        with self.assertRaisesRegex(rp.ContractError, "may not grant external authority"):
            rp.compile_pack(self.root)

    def test_ready_state_with_blockers_is_rejected(self) -> None:
        path = self.result_path()
        result = self.load(path)
        result["state"] = "TEAMING_READY"
        self.dump(path, result)
        with self.assertRaisesRegex(rp.ContractError, "may not retain missing buyer artifacts|may not retain blockers"):
            rp.compile_pack(self.root)

    def test_exact_stale_receipt_predecessor_state_and_blockers_fails_closed(self) -> None:
        path = self.result_path()
        result = self.load(path)
        result["state"] = "TEAMING_READY"
        result["blockers"] = []
        self.dump(path, result)
        with self.assertRaisesRegex(rp.ContractError, "may not retain missing buyer artifacts"):
            rp.compile_pack(self.root)

    def test_forged_resealed_result_cannot_replace_upstream_replay(self) -> None:
        path = self.result_path()
        result = self.load(path)
        result["reason"] = "forged_but_locally_resealed"
        unsigned = dict(result)
        unsigned.pop("receipt_sha256")
        result["receipt_sha256"] = rp.sha256_bytes(rp.canonical_json(unsigned).encode("ascii"))
        self.dump(path, result)
        with self.assertRaisesRegex(rp.ContractError, "not an authenticated replay of current evidence"):
            rp.compile_pack(self.root)

    def test_result_cannot_hide_known_missing_buyer_artifact(self) -> None:
        path = self.result_path()
        result = self.load(path)
        result["missing_buyer_artifacts"] = result["missing_buyer_artifacts"][:-1]
        self.dump(path, result)
        with self.assertRaisesRegex(rp.ContractError, "hides a known missing buyer artifact"):
            rp.compile_pack(self.root)

    def test_current_evidence_mutation_requires_regenerated_authenticated_result(self) -> None:
        path = self.evidence_path()
        evidence = self.load(path)
        evidence["current_time"] = "2026-09-16T17:40:09-04:00"
        self.dump(path, evidence)
        with self.assertRaisesRegex(rp.ContractError, "not an authenticated replay of current evidence"):
            rp.compile_pack(self.root)

    def test_owner_gate_status_is_explicitly_fail_closed_on_current_evidence(self) -> None:
        evidence = self.load(self.evidence_path())
        pricing = rp.validate_pricing_basis(self.load(self.root / "pricing_basis.json"))
        status = rp.owner_gate_status(evidence, pricing)
        self.assertEqual(set(status), rp.OWNER_GATE_STATUS_KEYS)
        self.assertTrue(all(value is False for value in status.values()))

    def test_local_pricing_approval_must_match_upstream_source_evidence(self) -> None:
        evidence = self.load(self.evidence_path())
        pricing = self.load(self.root / "pricing_basis.json")
        pricing["pricing_approved"] = True
        pricing["pricing_approval_evidence_id"] = "owner:pricing-approval:local-only"
        pricing["buyer_cost_form_present"] = True
        validated = rp.validate_pricing_basis(pricing)
        status = rp.owner_gate_status(evidence, validated)
        self.assertFalse(status["pricing_must_be_owner_approved"])

    def test_upstream_qualification_implementation_is_required(self) -> None:
        (self.root.parent / "qualification_guarded.py").unlink()
        with self.assertRaisesRegex(rp.ContractError, "canonical upstream qualification implementation is missing"):
            rp.compile_pack(self.root)

    def test_duplicate_json_key_is_rejected(self) -> None:
        path = self.root / "pricing_basis.json"
        text = path.read_text(encoding="utf-8")
        text = text.replace('"pricing_approved": false,', '"pricing_approved": false,\n  "pricing_approved": false,', 1)
        path.write_text(text, encoding="utf-8")
        with self.assertRaisesRegex(rp.ContractError, "duplicate JSON key"):
            rp.compile_pack(self.root)


if __name__ == "__main__":
    unittest.main()
