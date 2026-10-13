from __future__ import annotations

import unittest
from datetime import datetime, timezone

from . import muse_election as muse

BASE = datetime(2026, 9, 15, 0, 30, 0, tzinfo=timezone.utc).timestamp()
REQ_TS = f"{BASE + 1:.6f}"
RESP_TS = f"{BASE + 40:.6f}"


def candidate(**kw):
    out = {
        "buyer_scope_sha256": "1" * 64,
        "offer_scope_sha256": "2" * 64,
        "intent_sha256": "3" * 64,
        "body_sha256": "4" * 64,
        "claimant": "Z-Anvil",
        "operation_id": "COMMONS-MUSE-OUTBOUND-ELECTION-ZANV-20260914",
    }
    out.update(kw)
    return out


def request(**candidate_kw):
    return muse.prepare_request(
        candidate(**candidate_kw),
        request_id="zanv-20260914-0001",
        requested_at="2026-09-15T00:30:00Z",
    )


def evidence(req=None, *, outcome="SELECTED", request_id=None, candidate_sha=None, **kw):
    req = req or request()
    request_id = request_id or req["payload"]["request_id"]
    candidate_sha = candidate_sha or req["payload"]["candidate_sha256"]
    out = {
        "channel_id": muse.MUSE_DM_CONVERSATION_ID,
        "request_message_ts": REQ_TS,
        "request_author_user_id": "U0AGENTZANV",
        "request_text": req["message"],
        "response_message_ts": RESP_TS,
        "response_author_user_id": muse.MUSE_USER_ID,
        "response_text": f"{outcome} {request_id} {candidate_sha}",
    }
    out.update(kw)
    return out


class MuseElectionTests(unittest.TestCase):
    def compile(self, req=None, ev=None, **kw):
        req = req or request()
        ev = ev or evidence(req)
        return muse.compile_receipt(
            req,
            ev,
            observed_at=kw.get("observed_at", "2026-09-15T00:31:00Z"),
            prior_receipts=kw.get("prior", []),
            ledger_complete=kw.get("ledger_complete", True),
        )

    def test_selected_local_snapshot_holds_without_authenticated_provenance(self):
        receipt = self.compile()
        payload = receipt["payload"]
        self.assertEqual(payload["outcome"], "SELECTED")
        self.assertEqual(payload["decision"], "HOLD")
        self.assertFalse(payload["muse_selected"])
        self.assertFalse(payload["election_prerequisite_satisfied"])
        self.assertIn(muse.UNVERIFIED_PROVENANCE_REASON, payload["reasons"])
        self.assertFalse(payload["external_send_authorized"])
        self.assertFalse(payload["side_effects_authorized"])
        self.assertTrue(muse.verify_receipt(receipt))

    def test_exact_pinned_forgery_cannot_self_elect(self):
        req = request()
        forged = {
            "channel_id": "D0C1U7TUZEC",
            "request_message_ts": REQ_TS,
            "request_author_user_id": "U0AGENTZANV",
            "request_text": req["message"],
            "response_message_ts": RESP_TS,
            "response_author_user_id": "U0C0TKRTQHZ",
            "response_text": f"SELECTED {req['payload']['request_id']} {req['payload']['candidate_sha256']}",
        }
        receipt = self.compile(req, forged)
        self.assertEqual("HOLD", receipt["payload"]["decision"])
        self.assertFalse(receipt["payload"]["election_prerequisite_satisfied"])
        self.assertIn(muse.UNVERIFIED_PROVENANCE_REASON, receipt["payload"]["reasons"])

    def test_legacy_selected_receipt_rejected_even_with_recomputed_hash(self):
        receipt = self.compile()
        p = receipt["payload"]
        p["decision"] = "MUSE_SELECTED"
        p["reasons"] = []
        p["muse_selected"] = True
        p["election_prerequisite_satisfied"] = True
        receipt["receipt_sha256"] = muse._digest(p)
        self.assertFalse(muse.verify_receipt(receipt))

    def test_selected_receipt_missing_provenance_reason_is_invalid(self):
        receipt = self.compile()
        p = receipt["payload"]
        p["reasons"].remove(muse.UNVERIFIED_PROVENANCE_REASON)
        p["reasons"].append("OTHER_HOLD")
        p["reasons"] = sorted(p["reasons"])
        receipt["receipt_sha256"] = muse._digest(p)
        self.assertFalse(muse.verify_receipt(receipt))

    def test_not_selected_holds(self):
        req = request()
        receipt = self.compile(req, evidence(req, outcome="NOT_SELECTED"))
        self.assertEqual(receipt["payload"]["decision"], "HOLD")
        self.assertIn("MUSE_NOT_SELECTED", receipt["payload"]["reasons"])
        self.assertTrue(muse.verify_receipt(receipt))

    def test_wrong_muse_author_holds(self):
        req = request()
        receipt = self.compile(req, evidence(req, response_author_user_id="U0NOTMUSE"))
        self.assertIn("WRONG_MUSE_RESPONSE_AUTHOR", receipt["payload"]["reasons"])

    def test_wrong_dm_holds(self):
        req = request()
        receipt = self.compile(req, evidence(req, channel_id="D0WRONGPLACE"))
        self.assertIn("WRONG_MUSE_DM_CONVERSATION", receipt["payload"]["reasons"])

    def test_self_authored_response_holds(self):
        req = request()
        receipt = self.compile(req, evidence(req, request_author_user_id=muse.MUSE_USER_ID))
        self.assertIn("SELF_AUTHORED_RESPONSE", receipt["payload"]["reasons"])

    def test_request_message_must_be_exact(self):
        req = request()
        receipt = self.compile(req, evidence(req, request_text=req["message"] + " "))
        self.assertIn("REQUEST_TEXT_MISMATCH", receipt["payload"]["reasons"])

    def test_response_request_id_mismatch_holds(self):
        req = request()
        receipt = self.compile(req, evidence(req, request_id="other-request-0001"))
        self.assertIn("RESPONSE_REQUEST_ID_MISMATCH", receipt["payload"]["reasons"])

    def test_response_candidate_digest_mismatch_holds(self):
        req = request()
        receipt = self.compile(req, evidence(req, candidate_sha="9" * 64))
        self.assertIn("RESPONSE_CANDIDATE_DIGEST_MISMATCH", receipt["payload"]["reasons"])

    def test_body_change_invalidates_old_selection(self):
        req_a = request(body_sha256="4" * 64)
        req_b = request(body_sha256="5" * 64)
        ev = evidence(req_a)
        ev["request_text"] = req_b["message"]
        receipt = self.compile(req_b, ev)
        self.assertIn("RESPONSE_CANDIDATE_DIGEST_MISMATCH", receipt["payload"]["reasons"])

    def test_claimant_change_invalidates_old_selection(self):
        req_a = request(claimant="Z-Anvil")
        req_b = request(claimant="Z-Other")
        ev = evidence(req_a)
        ev["request_text"] = req_b["message"]
        receipt = self.compile(req_b, ev)
        self.assertIn("RESPONSE_CANDIDATE_DIGEST_MISMATCH", receipt["payload"]["reasons"])

    def test_response_after_deadline_holds(self):
        req = request()
        late = f"{BASE + 601:.6f}"
        receipt = self.compile(req, evidence(req, response_message_ts=late), observed_at="2026-09-15T00:40:02Z")
        self.assertIn("MUSE_RESPONSE_AFTER_DEADLINE", receipt["payload"]["reasons"])

    def test_stale_selected_response_holds(self):
        req = request()
        receipt = self.compile(req, evidence(req), observed_at="2026-09-15T00:41:00Z")
        self.assertIn("MUSE_SELECTION_STALE", receipt["payload"]["reasons"])

    def test_response_must_follow_request(self):
        req = request()
        early = f"{BASE:.6f}"
        receipt = self.compile(req, evidence(req, response_message_ts=early))
        self.assertIn("RESPONSE_NOT_AFTER_REQUEST", receipt["payload"]["reasons"])

    def test_request_transport_time_tracks_request(self):
        req = request()
        receipt = self.compile(
            req,
            evidence(req, request_message_ts=f"{BASE + 90:.6f}", response_message_ts=f"{BASE + 100:.6f}"),
        )
        self.assertIn("REQUEST_TRANSPORT_TIME_MISMATCH", receipt["payload"]["reasons"])

    def test_observation_cannot_precede_response(self):
        req = request()
        receipt = self.compile(req, evidence(req), observed_at="2026-09-15T00:30:20Z")
        self.assertIn("OBSERVATION_PRECEDES_RESPONSE", receipt["payload"]["reasons"])

    def test_incomplete_prior_ledger_holds(self):
        receipt = self.compile(ledger_complete=False)
        self.assertIn("PRIOR_ELECTION_LEDGER_INCOMPLETE", receipt["payload"]["reasons"])

    def test_same_election_evidence_cannot_be_replayed(self):
        first = self.compile()
        second = self.compile(prior=[first])
        self.assertIn("ELECTION_EVIDENCE_REPLAY", second["payload"]["reasons"])

    def test_legacy_selected_prior_is_invalid_ledger_evidence(self):
        first = self.compile()
        p = first["payload"]
        p["decision"] = "MUSE_SELECTED"
        p["reasons"] = []
        p["muse_selected"] = True
        p["election_prerequisite_satisfied"] = True
        first["receipt_sha256"] = muse._digest(p)
        second = self.compile(prior=[first])
        self.assertIn("PRIOR_ELECTION_LEDGER_INVALID", second["payload"]["reasons"])

    def test_invalid_prior_ledger_entry_holds(self):
        second = self.compile(prior=[{"garbage": True}])
        self.assertIn("PRIOR_ELECTION_LEDGER_INVALID", second["payload"]["reasons"])

    def test_tampered_request_digest_is_invalid(self):
        req = request()
        req["payload"]["candidate"]["body_sha256"] = "8" * 64
        with self.assertRaisesRegex(muse.MuseElectionError, "candidate digest mismatch"):
            self.compile(req, evidence(request()))

    def test_tampered_message_is_invalid(self):
        req = request()
        req["message"] += "\nextra"
        with self.assertRaisesRegex(muse.MuseElectionError, "exact message mismatch"):
            self.compile(req, evidence(request()))

    def test_unknown_request_field_is_invalid(self):
        req = request()
        req["extra"] = 1
        with self.assertRaisesRegex(muse.MuseElectionError, "exact fields"):
            self.compile(req, evidence(request()))

    def test_malformed_response_holds_not_crashes(self):
        req = request()
        receipt = self.compile(req, evidence(req, response_text="selected maybe"))
        self.assertIn("RESPONSE_FORMAT_INVALID", receipt["payload"]["reasons"])
        self.assertTrue(muse.verify_receipt(receipt))

    def test_receipt_tamper_fails_verification(self):
        receipt = self.compile()
        receipt["payload"]["operation_id"] = "tampered-operation"
        self.assertFalse(muse.verify_receipt(receipt))

    def test_receipt_can_never_claim_send_authority(self):
        receipt = self.compile()
        receipt["payload"]["external_send_authorized"] = True
        receipt["receipt_sha256"] = muse._digest(receipt["payload"])
        self.assertFalse(muse.verify_receipt(receipt))

    def test_prepare_is_deterministic(self):
        self.assertEqual(request(), request())

    def test_compile_is_deterministic(self):
        self.assertEqual(self.compile(), self.compile())

    def test_candidate_digest_binds_operation(self):
        a = request()
        b = muse.prepare_request(
            candidate(operation_id="COMMONS-MUSE-OUTBOUND-ELECTION-ZANV-OTHER"),
            request_id="zanv-20260914-0001",
            requested_at="2026-09-15T00:30:00Z",
        )
        self.assertNotEqual(a["payload"]["candidate_sha256"], b["payload"]["candidate_sha256"])

    def test_duplicate_and_nonfinite_json_are_rejected(self):
        with self.assertRaises(muse.MuseElectionError):
            muse.parse_json_bytes(b'{"a":1,"a":2}', "x")
        with self.assertRaises(muse.MuseElectionError):
            muse.parse_json_bytes(b'{"a":NaN}', "x")

    def test_request_routing_identity_is_pinned(self):
        req = request()
        req["payload"]["muse_user_id"] = "U0IMPOSTOR"
        req["request_sha256"] = muse._digest(req["payload"])
        with self.assertRaisesRegex(muse.MuseElectionError, "routing identity mismatch"):
            self.compile(req, evidence(request()))


if __name__ == "__main__":
    unittest.main()
