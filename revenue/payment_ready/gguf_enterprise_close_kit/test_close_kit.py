from __future__ import annotations

import copy
import shutil
import tempfile
import unittest
from pathlib import Path

from close_kit import (
    ACCEPTANCE_IDS,
    AUTHORITY_FALSE,
    ContractError,
    PRODUCTION_MODE,
    SYNTHETIC_MODE,
    canonical_json,
    compile_close_packet,
    evaluate_acceptance,
    load_authority,
    sha256_hex,
    strict_load,
    strict_loads,
    validate_authority_docs,
    validate_intake,
    verify_close_packet,
)

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
INTAKE = HERE / "fixtures" / "synthetic_intake.json"
EVIDENCE = HERE / "fixtures" / "synthetic_delivery_evidence.json"
OPERATING = HERE / "operating_manifest.json"
PACK = REPO / "revenue" / "payment_ready" / "pack.json"
RECOVERY = REPO / "revenue" / "payment_ready" / "recovery.json"


def intake():
    return strict_load(INTAKE)


def evidence():
    return strict_load(EVIDENCE)


def authority():
    return load_authority(REPO)


def as_production(doc):
    out = copy.deepcopy(doc)
    out["mode"] = PRODUCTION_MODE
    return out


class AuthorityTests(unittest.TestCase):
    def test_current_offer_is_exact_source_bound(self):
        result = authority()
        self.assertEqual(result["offer_id"], "gguf-diagnostic-10d-12k")
        self.assertEqual(result["currency"], "USD")
        self.assertEqual(result["fixed_amount_usd"], 12000)
        self.assertEqual(result["term_calendar_days"], 10)
        self.assertEqual(result["m1_amount_usd"], 6000)
        self.assertEqual(result["m2_amount_usd"], 6000)
        self.assertEqual(result["m2_due"], "on AT1-AT6 acceptance")
        self.assertEqual(result["acceptance_ids"], list(ACCEPTANCE_IDS))
        self.assertEqual(result["public_surface_kind"], "PURCHASE_INTENT_ONLY")
        self.assertFalse(result["payment_collection_on_public_surface"])
        self.assertEqual(result["canonical_purchase_intent_stage"], "NEEDS_BUYER")
        self.assertEqual(result["canonical_delivery"], "NOT_LANDED")
        self.assertNotEqual(result["pack_text_sha256"], "NONE")
        for field in AUTHORITY_FALSE:
            self.assertFalse(result[field])

    def test_pack_currency_drift_fails_closed(self):
        pack = strict_load(PACK)
        recovery = strict_load(RECOVERY)
        pack["offer"]["currency"] = "EUR"
        with self.assertRaises(ContractError):
            validate_authority_docs(pack, recovery)

    def test_recovery_currency_drift_fails_closed(self):
        pack = strict_load(PACK)
        recovery = strict_load(RECOVERY)
        recovery["offer"]["currency"] = "EUR"
        with self.assertRaises(ContractError):
            validate_authority_docs(pack, recovery)

    def test_m2_due_drift_fails_closed(self):
        pack = strict_load(PACK)
        recovery = strict_load(RECOVERY)
        pack["offer"]["milestones"][1]["due"] = "whenever convenient"
        with self.assertRaises(ContractError):
            validate_authority_docs(pack, recovery)

    def test_terms_digest_drift_fails_closed(self):
        pack = strict_load(PACK)
        recovery = strict_load(RECOVERY)
        recovery["offer"]["terms_sha256"] = "0" * 64
        with self.assertRaises(ContractError):
            validate_authority_docs(pack, recovery)

    def test_exact_pack_source_whitespace_replay_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "revenue" / "payment_ready"
            target.mkdir(parents=True)
            target.joinpath("pack.json").write_text(PACK.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            shutil.copyfile(RECOVERY, target / "recovery.json")
            with self.assertRaises(ContractError):
                load_authority(root)

    def test_receipt_contract_cannot_drop_exact_byte_replay(self):
        pack = strict_load(PACK)
        recovery = strict_load(RECOVERY)
        recovery["receipt_contract"]["runtime_deterministic_replay_is_transition_authority"] = False
        with self.assertRaises(ContractError):
            validate_authority_docs(pack, recovery)


class IntakeTests(unittest.TestCase):
    def test_synthetic_intake_is_never_production_ready(self):
        result = validate_intake(intake())
        self.assertEqual(result["mode"], SYNTHETIC_MODE)
        self.assertEqual(result["qualification_state"], "SYNTHETIC_EVIDENCE_SHAPE_ONLY")
        self.assertFalse(result["recovery_runtime_replay_verified"])
        self.assertTrue(result["recovery_receipt_shape_present"])
        for field in AUTHORITY_FALSE:
            self.assertFalse(result[field])

    def test_all_hex_production_prerequisites_still_hold_for_replay(self):
        result = validate_intake(as_production(intake()))
        self.assertEqual(result["qualification_state"], "HOLD")
        self.assertIn("HOLD_RECOVERY_REPLAY_REQUIRED", result["holds"])
        self.assertFalse(result["nda_signed"])
        self.assertFalse(result["sow_signed"])
        self.assertFalse(result["m1_payment_received"])
        self.assertFalse(result["private_file_transfer_authorized"])

    def test_control_attestation_requires_real_bool(self):
        doc = intake()
        doc["gguf"]["control_attested"] = 1
        with self.assertRaises(ContractError):
            validate_intake(doc)

    def test_metric_lift_guarantee_is_term_conflict(self):
        doc = intake()
        doc["scope"]["metric_lift_guaranteed"] = True
        with self.assertRaises(ContractError):
            validate_intake(doc)

    def test_public_contact_query_is_rejected(self):
        doc = intake()
        doc["security"]["public_contact_url"] = "https://example.com/contact?email=private@example.com"
        with self.assertRaises(ContractError):
            validate_intake(doc)

    def test_retention_over_30_days_is_rejected(self):
        doc = intake()
        doc["security"]["retention_days"] = 31
        with self.assertRaises(ContractError):
            validate_intake(doc)

    def test_raw_sensitive_field_is_rejected(self):
        doc = intake()
        doc["password"] = "do-not-store-this"
        with self.assertRaises(ContractError):
            validate_intake(doc)

    def test_raw_model_public_allowed_false_is_a_valid_boundary_flag(self):
        doc = intake()
        self.assertFalse(doc["security"]["raw_model_public_allowed"])
        result = validate_intake(doc)
        self.assertEqual(result["qualification_state"], "SYNTHETIC_EVIDENCE_SHAPE_ONLY")
        self.assertFalse(result["private_file_transfer_authorized"])

    def test_raw_model_field_is_rejected_as_sensitive(self):
        doc = intake()
        doc["gguf"]["raw_model"] = "do-not-store-this"
        with self.assertRaises(ContractError):
            validate_intake(doc)


class AcceptanceTests(unittest.TestCase):
    def test_synthetic_evidence_is_complete_but_nonproduction(self):
        result = evaluate_acceptance(intake(), evidence())
        self.assertEqual(result["failed_tests"], [])
        self.assertTrue(all(result["tests"].values()))
        self.assertEqual(result["verdict"], "SYNTHETIC_AT1_AT6_COMPLETE_NON_PRODUCTION")
        self.assertFalse(result["payment_reference_proves_acceptance"])
        for field in AUTHORITY_FALSE:
            self.assertFalse(result[field])

    def test_restore_sha_mismatch_holds_at3(self):
        doc = evidence()
        doc["artifacts"]["restored"]["sha256"] = "7" * 64
        doc["harness_runs"]["restore"]["input_artifact_sha256"] = "7" * 64
        payload = dict(doc["harness_runs"]["restore"])
        payload.pop("receipt_sha256")
        doc["harness_runs"]["restore"]["receipt_sha256"] = sha256_hex(canonical_json(payload))
        doc["delivery_receipt"]["manifest"]["restored_sha256"] = "7" * 64
        doc["delivery_receipt"]["manifest"]["restore_run_receipt_sha256"] = doc["harness_runs"]["restore"]["receipt_sha256"]
        doc["delivery_receipt"]["receipt_sha256"] = sha256_hex(canonical_json(doc["delivery_receipt"]["manifest"]))
        result = evaluate_acceptance(intake(), doc)
        self.assertFalse(result["tests"]["AT3"])
        self.assertEqual(result["verdict"], "SYNTHETIC_HOLD_ACCEPTANCE_EVIDENCE")

    def test_arbitrary_distinct_run_hashes_fail_semantic_receipt(self):
        doc = evidence()
        doc["harness_runs"]["baseline"]["receipt_sha256"] = "7" * 64
        with self.assertRaises(ContractError):
            evaluate_acceptance(intake(), doc)

    def test_harness_generation_mismatch_fails_at4_contract(self):
        doc = evidence()
        doc["harness_runs"]["ablation"]["harness_command_sha256"] = "7" * 64
        payload = dict(doc["harness_runs"]["ablation"])
        payload.pop("receipt_sha256")
        doc["harness_runs"]["ablation"]["receipt_sha256"] = sha256_hex(canonical_json(payload))
        with self.assertRaises(ContractError):
            evaluate_acceptance(intake(), doc)

    def test_eval_generation_mismatch_fails_at4_contract(self):
        doc = evidence()
        doc["harness_runs"]["restore"]["eval_suite_sha256"] = "7" * 64
        payload = dict(doc["harness_runs"]["restore"])
        payload.pop("receipt_sha256")
        doc["harness_runs"]["restore"]["receipt_sha256"] = sha256_hex(canonical_json(payload))
        with self.assertRaises(ContractError):
            evaluate_acceptance(intake(), doc)

    def test_arbitrary_delivery_receipt_hash_fails(self):
        doc = evidence()
        doc["delivery_receipt"]["receipt_sha256"] = "7" * 64
        with self.assertRaises(ContractError):
            evaluate_acceptance(intake(), doc)

    def test_self_listed_delivery_manifest_cannot_hide_wrong_report(self):
        doc = evidence()
        doc["delivery_receipt"]["manifest"]["report_sha256"] = "7" * 64
        doc["delivery_receipt"]["receipt_sha256"] = sha256_hex(canonical_json(doc["delivery_receipt"]["manifest"]))
        with self.assertRaises(ContractError):
            evaluate_acceptance(intake(), doc)

    def test_cross_engagement_replay_fails(self):
        doc = evidence()
        doc["engagement_id"] = "other-engagement"
        with self.assertRaises(ContractError):
            evaluate_acceptance(intake(), doc)

    def test_payment_reference_never_accepts(self):
        doc = evidence()
        doc["payment_reference_sha256"] = "7" * 64
        result = evaluate_acceptance(intake(), doc)
        self.assertTrue(result["payment_reference_present"])
        self.assertFalse(result["payment_reference_proves_acceptance"])
        self.assertFalse(result["customer_acceptance_recorded"])


class ClosePacketTests(unittest.TestCase):
    def test_synthetic_packet_is_explicitly_nonproduction(self):
        packet = compile_close_packet(REPO, intake(), evidence())
        self.assertEqual(packet["state"], "SYNTHETIC_EVIDENCE_COMPLETE_NON_PRODUCTION")
        self.assertEqual(packet["canonical_blocker"], "HOLD_CANONICAL_NEEDS_BUYER")
        self.assertTrue(packet["recovery_runtime_replay_required_for_production"])
        self.assertTrue(packet["synthetic_mode_is_never_production_ready"])
        for field in AUTHORITY_FALSE:
            self.assertFalse(packet[field])
        self.assertTrue(verify_close_packet(packet, REPO, intake(), evidence()))

    def test_current_production_packet_cannot_leap_needs_buyer(self):
        prod_intake = as_production(intake())
        prod_evidence = as_production(evidence())
        packet = compile_close_packet(REPO, prod_intake, prod_evidence)
        self.assertEqual(packet["state"], "HOLD_CANONICAL_NEEDS_BUYER")
        self.assertFalse(packet["private_file_transfer_authorized"])
        self.assertFalse(packet["customer_acceptance_recorded"])

    def test_stale_recovery_generation_cannot_create_positive_state(self):
        prod_intake = as_production(intake())
        prod_evidence = as_production(evidence())
        prod_intake["recovery_authority"]["offer_source_sha256"] = "7" * 64
        prod_intake["recovery_authority"]["terms_sha256"] = "8" * 64
        packet = compile_close_packet(REPO, prod_intake, prod_evidence)
        self.assertTrue(packet["state"].startswith("HOLD_"))
        self.assertNotIn("READY", packet["state"])
        self.assertFalse(packet["private_file_transfer_authorized"])
        self.assertFalse(packet["customer_acceptance_recorded"])

    def test_packet_status_tamper_is_detected(self):
        packet = compile_close_packet(REPO, intake(), evidence())
        packet["state"] = "ACCEPTED"
        self.assertFalse(verify_close_packet(packet, REPO, intake(), evidence()))

    def test_compile_api_has_no_caller_authority_packet(self):
        with self.assertRaises((TypeError, ContractError, OSError)):
            compile_close_packet({"fixed_amount_usd": 1}, intake(), evidence())


class SerializationAndManifestTests(unittest.TestCase):
    def test_duplicate_json_key_is_rejected(self):
        with self.assertRaises(ContractError):
            strict_loads('{"a":1,"a":2}')

    def test_nonfinite_json_is_rejected(self):
        with self.assertRaises(ContractError):
            strict_loads('{"a":NaN}')

    def test_operating_manifest_keeps_10_day_authority_boundary(self):
        manifest = strict_load(OPERATING)
        self.assertEqual(manifest["offer_id"], "gguf-diagnostic-10d-12k")
        self.assertEqual(manifest["commercial_terms"]["fixed_amount_usd"], 12000)
        self.assertEqual(manifest["commercial_terms"]["term_calendar_days"], 10)
        self.assertEqual(len(manifest["days"]), 10)
        self.assertEqual([row["day"] for row in manifest["days"]], list(range(1, 11)))
        self.assertGreaterEqual(len(manifest["hard_stops"]), 8)
        for field in AUTHORITY_FALSE:
            self.assertFalse(manifest["authority"][field])


if __name__ == "__main__":
    unittest.main()
