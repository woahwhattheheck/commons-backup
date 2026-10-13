from __future__ import annotations

import unittest

from revenue.lawrence_youth_ai_training import gate
from revenue.lawrence_youth_ai_training import _test_api as test_api
from revenue.lawrence_youth_ai_training._test_support import *

class QualificationBehaviorTests(unittest.TestCase):
    def test_collaborative_candidate_for_committed_load_bearing_partner(self):
        snap = snapshot()
        cap = gate._load_source_contract()["capability_requirements"][0]
        snap["capability_evidence"][0]["covers"].remove(cap)
        snap["partners"] = [{
            "partner_id": "partner-1",
            "commitment_status": "COMMITTED",
            "commitment_evidence_sha256": OTHER,
            "observed_at": OBSERVED,
            "expires_at": None,
        }]
        snap["capability_evidence"].append({
            "evidence_id": "partner-cap",
            "provider_id": "partner-1",
            "covers": [cap],
            "status": "VERIFIED",
            "evidence_sha256": OTHER,
            "observed_at": OBSERVED,
            "expires_at": None,
        })
        self.assertEqual(
            evaluate_test(snap)["receipt"]["candidate_decision"],
            gate.COLLABORATIVE_READY,
        )

    def test_prospective_load_bearing_partner_holds(self):
        snap = snapshot()
        cap = gate._load_source_contract()["capability_requirements"][0]
        snap["capability_evidence"][0]["covers"].remove(cap)
        snap["partners"] = [{
            "partner_id": "prospect",
            "commitment_status": "PROSPECTIVE",
            "commitment_evidence_sha256": None,
            "observed_at": OBSERVED,
            "expires_at": None,
        }]
        snap["capability_evidence"].append({
            "evidence_id": "prospect-cap",
            "provider_id": "prospect",
            "covers": [cap],
            "status": "VERIFIED",
            "evidence_sha256": OTHER,
            "observed_at": OBSERVED,
            "expires_at": None,
        })
        receipt = evaluate_test(snap)["receipt"]
        self.assertIn("PARTNER_NOT_COMMITTED:prospect", receipt["qualification_holds"])

    def test_non_load_bearing_prospective_partner_does_not_hold_candidate(self):
        snap = snapshot()
        cap = gate._load_source_contract()["capability_requirements"][0]
        snap["partners"] = [{
            "partner_id": "optional",
            "commitment_status": "PROSPECTIVE",
            "commitment_evidence_sha256": None,
            "observed_at": OBSERVED,
            "expires_at": None,
        }]
        snap["capability_evidence"].append({
            "evidence_id": "optional-cap",
            "provider_id": "optional",
            "covers": [cap],
            "status": "VERIFIED",
            "evidence_sha256": OTHER,
            "observed_at": OBSERVED,
            "expires_at": None,
        })
        self.assertEqual(evaluate_test(snap)["receipt"]["candidate_decision"], gate.PRIME_READY)

    def test_missing_document_holds(self):
        snap = snapshot()
        doc = gate._load_source_contract()["mandatory_document_requirements"][0]
        snap["bidder"]["documents"][doc] = {
            "status": "MISSING",
            "evidence_sha256": None,
            "observed_at": OBSERVED,
            "expires_at": None,
        }
        self.assertIn(
            f"DOCUMENT_NOT_READY:{doc}",
            evaluate_test(snap)["receipt"]["qualification_holds"],
        )

    def test_missing_capability_holds(self):
        snap = snapshot()
        cap = gate._load_source_contract()["capability_requirements"][0]
        snap["capability_evidence"][0]["covers"].remove(cap)
        self.assertIn(
            f"CAPABILITY_NOT_COVERED:{cap}",
            evaluate_test(snap)["receipt"]["qualification_holds"],
        )

    def test_out_of_band_rfp_hash_mismatch_holds(self):
        result = test_api.evaluate_with_authenticated_authority(
            snapshot(),
            evaluated_at=NOW,
            expected_rfp_sha256=OTHER,
            envelope=signed_envelope(),
            key_document=key_document(),
            emulate_host=True,
        )
        self.assertIn("RFP_SHA256_MISMATCH", result["receipt"]["qualification_holds"])

    def test_stale_update_check_holds(self):
        snap = snapshot()
        snap["source_capture"]["captured_at"] = "2026-09-13T08:00:00Z"
        snap["source_capture"]["updates_checked_at"] = "2026-09-13T09:00:00Z"
        self.assertIn(
            "RFP_UPDATE_CHECK_STALE",
            evaluate_test(snap)["receipt"]["qualification_holds"],
        )

    def test_addenda_incomplete_holds(self):
        snap = snapshot()
        snap["source_capture"]["addenda_complete"] = False
        self.assertIn(
            "RFP_UPDATES_NOT_CONFIRMED_COMPLETE",
            evaluate_test(snap)["receipt"]["qualification_holds"],
        )

    def test_qa_confirmation_required_after_posting_deadline(self):
        now = "2026-09-29T21:00:00Z"
        snap = snapshot()
        snap["source_capture"]["captured_at"] = "2026-09-29T19:00:00Z"
        snap["source_capture"]["updates_checked_at"] = "2026-09-29T20:30:00Z"
        snap["source_capture"]["questions_answers_complete"] = False
        envelope = signed_envelope(
            now="2026-09-29T20:45:00Z",
            verified_at="2026-09-29T20:30:00Z",
            good_issued_at="2026-09-28T12:00:00Z",
        )
        receipt = evaluate_test(snap, now=now, envelope=envelope)["receipt"]
        self.assertIn("RFP_QA_NOT_CONFIRMED_COMPLETE", receipt["qualification_holds"])

    def test_hard_constraint_is_no_bid(self):
        snap = snapshot()
        snap["bidder"]["hard_constraints"] = ["CANNOT_DELIVER_12_MONTH_FOLLOWUP"]
        receipt = evaluate_test(snap)["receipt"]
        self.assertEqual(receipt["decision"], gate.NO_BID)
        self.assertEqual(receipt["candidate_decision"], gate.NO_BID)

    def test_deadline_boundary_is_no_bid(self):
        now = "2026-10-01T15:00:00Z"
        snap = snapshot()
        snap["source_capture"]["captured_at"] = "2026-10-01T13:00:00Z"
        snap["source_capture"]["updates_checked_at"] = "2026-10-01T14:30:00Z"
        snap["source_capture"]["questions_answers_complete"] = True
        envelope = signed_envelope(
            now="2026-10-01T14:45:00Z",
            verified_at="2026-10-01T14:30:00Z",
            good_issued_at="2026-09-30T12:00:00Z",
        )
        self.assertEqual(evaluate_test(snap, now=now, envelope=envelope)["receipt"]["decision"], gate.NO_BID)

    def test_evaluation_before_release_is_rejected(self):
        with self.assertRaises(gate.QualificationInputError):
            evaluate_test(now="2026-08-18T23:59:59Z")

    def test_document_set_is_exact(self):
        snap = snapshot()
        snap["bidder"]["documents"].pop(next(iter(snap["bidder"]["documents"])))
        with self.assertRaises(gate.QualificationInputError):
            evaluate_test(snap)

    def test_undeclared_capability_provider_rejected(self):
        snap = snapshot()
        snap["capability_evidence"][0]["provider_id"] = "mystery"
        with self.assertRaises(gate.QualificationInputError):
            evaluate_test(snap)


