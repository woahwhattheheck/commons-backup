from __future__ import annotations

from .test_support import (
    AT, D, PartnerLedgerTestCase, Path, base_packet, copy, handoff, hashlib,
    ledger, mock, os, reply, sent, subprocess, sys, tempfile, unittest,
)

class LedgerCoreTests(PartnerLedgerTestCase):
    def test_clean_initial_is_owner_review_only(self):
        report = self.compile(base_packet())
        self.assertEqual(self.state(report), "READY_FOR_OWNER_REVIEW")
        self.assertEqual(report["owner_review_queue"][0]["action"], "REVIEW_INITIAL_CONTACT")
        self.assertTrue(all(v is False for v in report["authority"].values()))

    def test_sent_waits_for_reply(self):
        p = base_packet()
        p["opportunities"][0]["candidates"][0]["events"] = [sent()]
        report = self.compile(p)
        self.assertEqual(self.state(report), "AWAITING_REPLY")
        self.assertEqual(report["owner_review_queue"], [])

    def test_positive_reply_requires_review(self):
        p = base_packet()
        p["opportunities"][0]["candidates"][0]["events"] = [sent(), reply()]
        report = self.compile(p)
        self.assertEqual(self.state(report), "REPLY_REVIEW_REQUIRED")
        self.assertEqual(report["owner_review_queue"][0]["action"], "REVIEW_REPLY")

    def test_handoff_requires_positive_reply(self):
        p = base_packet()
        c = p["opportunities"][0]["candidates"][0]
        c["events"] = [sent(), reply(reply_class="POSITIVE"), handoff()]
        report = self.compile(p)
        self.assertEqual(self.state(report), "HANDOFF_COMPLETE")

        p2 = base_packet()
        p2["opportunities"][0]["candidates"][0]["events"] = [sent(), reply(reply_class="NEGATIVE"), handoff()]
        report2 = self.compile(p2)
        self.assertEqual(self.state(report2), "HOLD")
        self.assertIn("HANDOFF_WITHOUT_POSITIVE_REPLY", self.reasons(report2))

    def test_terminal_no_fit(self):
        p = base_packet()
        p["opportunities"][0]["candidates"][0]["events"] = [{
            "event_id": "term-1", "type": "TERMINAL", "at": "2026-09-10T11:00:00Z",
            "evidence_digest": D("1"), "terminal_class": "NO_FIT"
        }]
        self.assertEqual(self.state(self.compile(p)), "TERMINAL")

    def test_declined_requires_negative_reply(self):
        p = base_packet()
        c = p["opportunities"][0]["candidates"][0]
        c["events"] = [sent(), {"event_id": "term-1", "type": "TERMINAL", "at": "2026-09-10T14:00:00Z", "evidence_digest": D("1"), "terminal_class": "DECLINED"}]
        r = self.compile(p)
        self.assertEqual(self.state(r), "HOLD")
        self.assertIn("DECLINED_WITHOUT_NEGATIVE_REPLY", self.reasons(r))

    def test_duplicate_send_without_exception_holds(self):
        p = base_packet()
        c = p["opportunities"][0]["candidates"][0]
        c["events"] = [sent(), sent("send-2", "2026-09-11T12:00:00Z", "msg-2", "thr-2")]
        r = self.compile(p)
        self.assertEqual(self.state(r), "HOLD")
        self.assertIn("DUPLICATE_SEND_WITHOUT_EXCEPTION", self.reasons(r))

    def test_followup_send_requires_exact_exception(self):
        p = base_packet()
        c = p["opportunities"][0]["candidates"][0]
        c["exceptions"] = [{
            "exception_id": "exc-1", "opportunity_id": "opp-1", "candidate_id": "cand-1",
            "prior_send_event_id": "send-1", "approved_at": "2026-09-11T11:00:00Z",
            "expires_at": "2026-09-12T00:00:00Z", "evidence_digest": D("9")
        }]
        c["events"] = [sent(), sent("send-2", "2026-09-11T12:00:00Z", "msg-2", "thr-2", "exc-1")]
        r = self.compile(p)
        self.assertEqual(self.state(r), "AWAITING_REPLY")
        self.assertEqual(r["opportunities"][0]["candidates"][0]["sent_count"], 2)

    def test_followup_exception_reuse_holds(self):
        p = base_packet()
        c = p["opportunities"][0]["candidates"][0]
        c["exceptions"] = [{
            "exception_id": "exc-1", "opportunity_id": "opp-1", "candidate_id": "cand-1",
            "prior_send_event_id": "send-1", "approved_at": "2026-09-11T11:00:00Z",
            "expires_at": "2026-09-14T00:00:00Z", "evidence_digest": D("9")
        }]
        c["events"] = [
            sent(),
            sent("send-2", "2026-09-11T12:00:00Z", "msg-2", "thr-2", "exc-1"),
            sent("send-3", "2026-09-12T12:00:00Z", "msg-3", "thr-3", "exc-1"),
        ]
        r = self.compile(p)
        self.assertEqual(self.state(r), "HOLD")
        self.assertIn("FOLLOWUP_EXCEPTION_REUSED", self.reasons(r))

    def test_reply_before_send_and_thread_mismatch_hold(self):
        p = base_packet()
        p["opportunities"][0]["candidates"][0]["events"] = [reply(at="2026-09-09T12:00:00Z"), sent(at="2026-09-10T12:00:00Z")]
        r = self.compile(p)
        self.assertIn("REPLY_BEFORE_SEND", self.reasons(r))

        p2 = base_packet()
        p2["opportunities"][0]["candidates"][0]["events"] = [sent(), reply(thread="thr-other")]
        r2 = self.compile(p2)
        self.assertIn("REPLY_THREAD_MISMATCH", self.reasons(r2))

    def test_handoff_before_reply_holds(self):
        p = base_packet()
        p["opportunities"][0]["candidates"][0]["events"] = [sent(), handoff()]
        r = self.compile(p)
        self.assertIn("HANDOFF_BEFORE_REPLY", self.reasons(r))

    def test_stale_and_future_qualification_hold(self):
        p = base_packet()
        p["opportunities"][0]["qualification"]["valid_until"] = "2026-09-14T00:00:00Z"
        self.assertIn("QUALIFICATION_STALE", self.reasons(self.compile(p)))

        p2 = base_packet()
        p2["opportunities"][0]["qualification"]["captured_at"] = "2026-09-16T00:00:00Z"
        p2["opportunities"][0]["qualification"]["valid_until"] = "2026-12-31T23:59:59Z"
        self.assertIn("QUALIFICATION_FROM_FUTURE", self.reasons(self.compile(p2)))

    def test_provider_message_and_thread_replay_cross_candidate_hold(self):
        p = base_packet(2)
        c1, c2 = p["opportunities"][0]["candidates"]
        c1["events"] = [sent(message="msg-shared", thread="thr-shared")]
        c2["events"] = [sent(message="msg-shared", thread="thr-shared")]
        r = self.compile(p)
        self.assertEqual(self.state(r, 1), "HOLD")
        self.assertIn("PROVIDER_MESSAGE_REPLAY", self.reasons(r, 1))
        self.assertIn("PROVIDER_THREAD_REPLAY", self.reasons(r, 1))

    def test_opaque_ref_and_unknown_body_fence(self):
        p = base_packet()
        p["opportunities"][0]["candidates"][0]["org_ref"] = "kathy@example.com"
        with self.assertRaises(ledger.LedgerError):
            self.compile(p)

        p2 = base_packet()
        p2["opportunities"][0]["candidates"][0]["email_body"] = "hello"
        with self.assertRaises(ledger.LedgerError):
            self.compile(p2)

    def test_duplicate_json_key_and_nonfinite_rejected(self):
        with self.assertRaises(ledger.LedgerError):
            ledger.loads_strict('{"a":1,"a":2}')
        with self.assertRaises(ledger.LedgerError):
            ledger.loads_strict('{"a":NaN}')
