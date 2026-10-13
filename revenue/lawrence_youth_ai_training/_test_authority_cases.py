from __future__ import annotations

import copy
import inspect
import unittest
from datetime import datetime, timezone
from unittest import mock

from revenue.lawrence_youth_ai_training import gate
from revenue.lawrence_youth_ai_training import _test_api as test_api
from revenue.lawrence_youth_ai_training._test_support import *

class LawrenceAuthorityTests(unittest.TestCase):
    def test_source_contract_digest_is_pinned(self):
        contract = gate._load_source_contract()
        self.assertEqual(gate.digest(contract), gate.EXPECTED_SOURCE_CONTRACT_SHA256)

    def test_current_api_has_no_clock_override(self):
        self.assertEqual(
            list(inspect.signature(gate.evaluate_current).parameters),
            ["snapshot", "expected_rfp_sha256"],
        )
        self.assertEqual(
            list(inspect.signature(gate.verify_current).parameters),
            ["result", "snapshot", "expected_rfp_sha256"],
        )

    def test_supported_package_does_not_export_test_authority_helpers(self):
        import revenue.lawrence_youth_ai_training as package

        self.assertNotIn("_test_sign_envelope", package.__all__)
        self.assertNotIn("_test_evaluate_with_authenticated_authority", package.__all__)

    def test_authenticated_semantics_can_support_candidate_prime_but_test_clock_cannot_authorize(self):
        receipt = evaluate_test()["receipt"]
        self.assertEqual(receipt["candidate_decision"], gate.PRIME_READY)
        self.assertEqual(receipt["decision"], gate.HOLD)
        self.assertFalse(receipt["current_authority"])
        self.assertIn("NON_PROCESS_CLOCK_AUTHORITY", receipt["holds"])
        self.assertEqual(
            receipt["document_semantic_states"][gate.GOOD_STANDING_DOCUMENT],
            "VERIFIED_CURRENT",
        )
        self.assertEqual(
            receipt["document_semantic_states"][gate.AUDIT_DOCUMENT],
            "VERIFIED_MOST_RECENT",
        )

    def test_current_api_can_green_only_from_host_mode_and_process_clock(self):
        snap = snapshot()
        context = authority_context()
        with (
            mock.patch.object(gate, "_load_host_authority", return_value=context),
            mock.patch.object(
                gate,
                "_utc_now",
                return_value=datetime(2026, 9, 15, 22, 0, tzinfo=timezone.utc),
            ),
        ):
            receipt = gate.evaluate_current(snap, expected_rfp_sha256=SHA)["receipt"]
        self.assertEqual(receipt["decision"], gate.PRIME_READY)
        self.assertTrue(receipt["current_authority"])
        self.assertEqual(receipt["semantic_authority_mode"], "HOST_HMAC")

    def test_missing_host_root_fails_closed(self):
        with (
            mock.patch.object(
                gate,
                "_load_host_authority",
                side_effect=gate.SemanticAuthorityUnavailable("missing"),
            ),
            mock.patch.object(
                gate,
                "_utc_now",
                return_value=datetime(2026, 9, 15, 22, 0, tzinfo=timezone.utc),
            ),
        ):
            receipt = gate.evaluate_current(snapshot(), expected_rfp_sha256=SHA)["receipt"]
        self.assertEqual(receipt["decision"], gate.HOLD)
        self.assertFalse(receipt["current_authority"])
        self.assertIn("NON_PRODUCTION_SEMANTIC_AUTHORITY", receipt["holds"])
        self.assertIn(
            f"DOCUMENT_SEMANTICS_UNVERIFIED:{gate.GOOD_STANDING_DOCUMENT}",
            receipt["holds"],
        )

    def test_caller_authored_semantic_authority_is_schema_rejected(self):
        snap = snapshot()
        snap["bidder"]["documents"][gate.GOOD_STANDING_DOCUMENT]["semantic_authority"] = {
            "verification_evidence_sha256": "c" * 64
        }
        with self.assertRaises(gate.QualificationInputError):
            evaluate_test(snap)

    def test_arbitrary_hash_shaped_proof_cannot_green(self):
        snap = snapshot()
        snap["bidder"]["documents"][gate.AUDIT_DOCUMENT]["semantic_authority"] = {
            "semantic_kind": "MOST_RECENT_FINANCIAL_ASSURANCE",
            "verification_evidence_sha256": "c" * 64,
            "most_recent": True,
        }
        with self.assertRaises(gate.QualificationInputError):
            evaluate_test(snap)

    def test_wrong_hmac_is_rejected(self):
        envelope = signed_envelope()
        envelope["hmac_sha256"] = "0" * 64
        with self.assertRaises(gate.QualificationInputError):
            evaluate_test(envelope=envelope)

    def test_attestation_document_hash_must_match(self):
        receipt = evaluate_test(envelope=signed_envelope(document_sha=OTHER))["receipt"]
        self.assertEqual(receipt["candidate_decision"], gate.HOLD)
        self.assertIn(
            f"DOCUMENT_SEMANTICS_UNVERIFIED:{gate.GOOD_STANDING_DOCUMENT}",
            receipt["qualification_holds"],
        )

    def test_good_standing_wrong_issuer_holds(self):
        envelope = signed_envelope(good_issuer="Not Massachusetts DOR")
        receipt = evaluate_test(envelope=envelope)["receipt"]
        self.assertIn(
            f"DOCUMENT_ISSUER_MISMATCH:{gate.GOOD_STANDING_DOCUMENT}",
            receipt["qualification_holds"],
        )

    def test_good_standing_stale_issuance_holds(self):
        envelope = signed_envelope(good_issued_at="2025-01-01T00:00:00Z")
        receipt = evaluate_test(envelope=envelope)["receipt"]
        self.assertIn(
            f"DOCUMENT_NOT_CURRENT:{gate.GOOD_STANDING_DOCUMENT}",
            receipt["qualification_holds"],
        )

    def test_audit_not_most_recent_holds(self):
        envelope = signed_envelope(audit_most_recent=False)
        receipt = evaluate_test(envelope=envelope)["receipt"]
        self.assertIn(
            f"DOCUMENT_NOT_MOST_RECENT:{gate.AUDIT_DOCUMENT}",
            receipt["qualification_holds"],
        )

    def test_semantic_verification_stale_holds(self):
        envelope = signed_envelope(
            verified_at="2026-09-14T10:00:00Z",
            good_issued_at="2026-09-13T12:00:00Z",
        )
        receipt = evaluate_test(envelope=envelope)["receipt"]
        self.assertIn(
            f"DOCUMENT_SEMANTIC_VERIFICATION_STALE:{gate.AUDIT_DOCUMENT}",
            receipt["qualification_holds"],
        )

    def test_stale_authority_generation_holds(self):
        envelope = signed_envelope(
            now="2026-09-14T10:00:00Z",
            verified_at="2026-09-14T09:00:00Z",
            good_issued_at="2026-09-13T12:00:00Z",
        )
        receipt = evaluate_test(envelope=envelope)["receipt"]
        self.assertIn("SEMANTIC_AUTHORITY_GENERATION_STALE", receipt["qualification_holds"])

    def test_historical_replay_is_never_current_authority(self):
        receipt = gate.evaluate_historical(
            snapshot(),
            evaluated_at=NOW,
            expected_rfp_sha256=SHA,
        )["receipt"]
        self.assertEqual(receipt["decision"], gate.HOLD)
        self.assertFalse(receipt["current_authority"])
        self.assertEqual(receipt["clock_authority"], "CALLER_SUPPLIED_HISTORICAL")
        self.assertIn("NON_PROCESS_CLOCK_AUTHORITY", receipt["holds"])

    def test_backdating_does_not_create_current_ready_receipt(self):
        receipt = gate.evaluate_historical(
            snapshot(),
            evaluated_at=NOW,
            expected_rfp_sha256=SHA,
        )["receipt"]
        self.assertNotIn(receipt["decision"], {gate.PRIME_READY, gate.COLLABORATIVE_READY})
        self.assertFalse(
            gate.verify_current(
                {"receipt": receipt},
                snapshot=snapshot(),
                expected_rfp_sha256=SHA,
            )
        )

    def test_current_receipt_verifies_under_same_host_generation(self):
        snap = snapshot()
        context = authority_context()
        eval_now = datetime(2026, 9, 15, 22, 0, tzinfo=timezone.utc)
        with (
            mock.patch.object(gate, "_load_host_authority", return_value=context),
            mock.patch.object(gate, "_utc_now", return_value=eval_now),
        ):
            result = gate.evaluate_current(snap, expected_rfp_sha256=SHA)
        with (
            mock.patch.object(gate, "_load_host_authority", return_value=context),
            mock.patch.object(gate, "_utc_now", return_value=VERIFY_NOW),
        ):
            self.assertTrue(
                gate.verify_current(result, snapshot=snap, expected_rfp_sha256=SHA)
            )

    def test_current_verifier_rejects_authority_generation_change(self):
        snap = snapshot()
        first = authority_context()
        eval_now = datetime(2026, 9, 15, 22, 0, tzinfo=timezone.utc)
        with (
            mock.patch.object(gate, "_load_host_authority", return_value=first),
            mock.patch.object(gate, "_utc_now", return_value=eval_now),
        ):
            result = gate.evaluate_current(snap, expected_rfp_sha256=SHA)
        changed_unsigned = unsigned_envelope()
        changed_unsigned["generation_id"] = "lawrence-semantic-generation-2"
        changed = gate._authenticate_envelope(
            test_api.sign_envelope(changed_unsigned, key_document()),
            key_document(),
        )
        with (
            mock.patch.object(gate, "_load_host_authority", return_value=changed),
            mock.patch.object(gate, "_utc_now", return_value=VERIFY_NOW),
        ):
            self.assertFalse(
                gate.verify_current(result, snapshot=snap, expected_rfp_sha256=SHA)
            )

    def test_receipt_tamper_fails(self):
        snap = snapshot()
        context = authority_context()
        with (
            mock.patch.object(gate, "_load_host_authority", return_value=context),
            mock.patch.object(
                gate,
                "_utc_now",
                return_value=datetime(2026, 9, 15, 22, 0, tzinfo=timezone.utc),
            ),
        ):
            result = gate.evaluate_current(snap, expected_rfp_sha256=SHA)
        result["receipt"]["decision"] = gate.COLLABORATIVE_READY
        with (
            mock.patch.object(gate, "_load_host_authority", return_value=context),
            mock.patch.object(gate, "_utc_now", return_value=VERIFY_NOW),
        ):
            self.assertFalse(
                gate.verify_current(result, snapshot=snap, expected_rfp_sha256=SHA)
            )

    def test_snapshot_mutation_fails_verifier(self):
        snap = snapshot()
        context = authority_context()
        with (
            mock.patch.object(gate, "_load_host_authority", return_value=context),
            mock.patch.object(
                gate,
                "_utc_now",
                return_value=datetime(2026, 9, 15, 22, 0, tzinfo=timezone.utc),
            ),
        ):
            result = gate.evaluate_current(snap, expected_rfp_sha256=SHA)
        changed = copy.deepcopy(snap)
        changed["bidder"]["organization_type"] = "NON_CORPORATE"
        with (
            mock.patch.object(gate, "_load_host_authority", return_value=context),
            mock.patch.object(gate, "_utc_now", return_value=VERIFY_NOW),
        ):
            self.assertFalse(
                gate.verify_current(result, snapshot=changed, expected_rfp_sha256=SHA)
            )

    def test_external_authority_fields_are_false(self):
        receipt = evaluate_test()["receipt"]
        for field in gate._AUTHORITY_FALSE_FIELDS:
            self.assertIs(receipt[field], False)


