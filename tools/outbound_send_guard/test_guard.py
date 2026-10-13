from __future__ import annotations

import json
import os
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from tools.outbound_send_guard._guard_core import GuardError, evaluate, main, parse_json_bytes


RECIPIENT = "matt@scientist.com"
OFFER = "scientist-clinical-lab-sow-result-evidence-reconciler-01"
NOW = "2026-09-13T07:20:00Z"


def intent(**overrides):
    value = {
        "schema_version": "outbound-send-intent/v1",
        "intent_id": "intent-scientist-1",
        "recipient": RECIPIENT,
        "offer_id": OFFER,
        "requested_at": NOW,
        "route_kind": "email",
    }
    value.update(overrides)
    return value


def evidence(*, mail=None, slack=None, mail_complete=True, slack_complete=True, generated_at="2026-09-13T07:19:30Z", policy=None):
    return {
        "schema_version": "outbound-send-evidence/v1",
        "generated_at": generated_at,
        "mailbox": {"complete": mail_complete, "query_id": "gmail:bidir:scientist", "messages": mail or []},
        "slack": {"complete": slack_complete, "query_id": "slack:scientist", "events": slack or []},
        "policy": policy or {"cross_offer_cooldown_days": 30, "max_evidence_age_seconds": 900, "max_future_skew_seconds": 300},
    }


def outbound(message_id="m1", at="2026-09-13T07:10:58Z", offer_id=None, counterparty=RECIPIENT):
    row = {"message_id": message_id, "direction": "outbound", "counterparty": counterparty, "observed_at": at, "offer_id": offer_id}
    return row


def inbound(message_id="in1", at="2026-09-13T07:15:00Z", offer_id=None, counterparty=RECIPIENT):
    return {"message_id": message_id, "direction": "inbound", "counterparty": counterparty, "observed_at": at, "offer_id": offer_id}


def slack_event(event_id="s1", kind="sent", at="2026-09-13T07:11:00Z", offer_id=OFFER, recipient=RECIPIENT, provider_message_id=None):
    return {"event_id": event_id, "kind": kind, "recipient": recipient, "observed_at": at, "offer_id": offer_id, "provider_message_id": provider_message_id}


class GuardTests(unittest.TestCase):
    def decision(self, ev, it=None):
        return evaluate(it or intent(), ev)["payload"]

    def test_clean_complete_evidence_allows_new(self):
        payload = self.decision(evidence())
        self.assertEqual(payload["decision"], "ALLOW_NEW")
        self.assertEqual(payload["authority"], "complete")
        self.assertFalse(payload["side_effects_authorized"])

    def test_real_incident_provider_sent_without_slack_receipt_holds(self):
        payload = self.decision(evidence(mail=[outbound(message_id="1a0999adcef566f2")]))
        self.assertEqual(payload["decision"], "HOLD")
        self.assertIn("cross-offer cooldown", " ".join(payload["reasons"]))
        self.assertIn("mail:1a0999adcef566f2", payload["evidence"]["matched_refs"])

    def test_provider_exact_offer_is_do_not_resend(self):
        payload = self.decision(evidence(mail=[outbound(offer_id=OFFER)]))
        self.assertEqual(payload["decision"], "DO_NOT_RESEND")

    def test_slack_exact_offer_is_do_not_resend_even_without_provider_row(self):
        payload = self.decision(evidence(slack=[slack_event()]))
        self.assertEqual(payload["decision"], "DO_NOT_RESEND")

    def test_newer_inbound_opens_reply_only_not_new_send(self):
        payload = self.decision(evidence(mail=[outbound(offer_id=OFFER), inbound()]))
        self.assertEqual(payload["decision"], "REPLY_ONLY")
        self.assertEqual(payload["reply_message_id"], "in1")

    def test_older_inbound_does_not_reopen(self):
        payload = self.decision(evidence(mail=[inbound(at="2026-09-13T07:00:00Z"), outbound(offer_id=OFFER)]))
        self.assertEqual(payload["decision"], "DO_NOT_RESEND")

    def test_hard_dnr_overrides_new_inbound(self):
        payload = self.decision(evidence(mail=[outbound(), inbound()], slack=[slack_event(kind="hard_dnr", offer_id=None)]))
        self.assertEqual(payload["decision"], "DO_NOT_RESEND")

    def test_old_cross_offer_send_can_age_out(self):
        old = outbound(at="2026-07-01T00:00:00Z", offer_id="different-offer")
        payload = self.decision(evidence(mail=[old]))
        self.assertEqual(payload["decision"], "ALLOW_NEW")

    def test_same_offer_never_ages_out_without_new_inbound(self):
        old = outbound(at="2025-01-01T00:00:00Z", offer_id=OFFER)
        payload = self.decision(evidence(mail=[old]))
        self.assertEqual(payload["decision"], "DO_NOT_RESEND")

    def test_incomplete_mailbox_fails_closed(self):
        payload = self.decision(evidence(mail_complete=False))
        self.assertEqual(payload["decision"], "HOLD")
        self.assertEqual(payload["authority"], "partial")

    def test_incomplete_slack_fails_closed(self):
        payload = self.decision(evidence(slack_complete=False))
        self.assertEqual(payload["decision"], "HOLD")
        self.assertEqual(payload["authority"], "partial")

    def test_stale_snapshot_fails_closed(self):
        payload = self.decision(evidence(generated_at="2026-09-13T06:00:00Z"))
        self.assertEqual(payload["decision"], "HOLD")
        self.assertIn("stale", " ".join(payload["reasons"]))

    def test_future_snapshot_fails_closed(self):
        payload = self.decision(evidence(generated_at="2026-09-13T08:00:00Z"))
        self.assertEqual(payload["decision"], "HOLD")
        self.assertEqual(payload["authority"], "unknown")

    def test_mail_row_after_snapshot_boundary_fails_closed(self):
        payload = self.decision(evidence(mail=[outbound(at="2026-09-13T07:19:31Z")]))
        self.assertEqual(payload["decision"], "HOLD")
        self.assertEqual(payload["authority"], "unknown")
        self.assertIn("after the snapshot boundary", " ".join(payload["reasons"]))

    def test_slack_row_after_snapshot_boundary_fails_closed(self):
        payload = self.decision(evidence(slack=[slack_event(at="2026-09-13T07:19:31Z")]))
        self.assertEqual(payload["decision"], "HOLD")
        self.assertEqual(payload["authority"], "unknown")
        self.assertIn("after the snapshot boundary", " ".join(payload["reasons"]))

    def test_conflicting_duplicate_provider_message_id_fails_closed(self):
        a = outbound(message_id="dup")
        b = inbound(message_id="dup")
        payload = self.decision(evidence(mail=[a, b]))
        self.assertEqual(payload["decision"], "HOLD")
        self.assertEqual(payload["authority"], "unknown")
        self.assertIn("conflicting", " ".join(payload["reasons"]))

    def test_exact_duplicate_provider_row_collapses(self):
        row = outbound(message_id="dup", offer_id=OFFER)
        payload = self.decision(evidence(mail=[row, deepcopy(row)]))
        self.assertEqual(payload["decision"], "DO_NOT_RESEND")
        self.assertEqual(payload["evidence"]["matched_refs"].count("mail:dup"), 1)

    def test_conflicting_duplicate_slack_event_fails_closed(self):
        a = slack_event(event_id="dup")
        b = deepcopy(a); b["kind"] = "lead"
        payload = self.decision(evidence(slack=[a, b]))
        self.assertEqual(payload["decision"], "HOLD")
        self.assertEqual(payload["authority"], "unknown")

    def test_email_identity_is_casefolded(self):
        payload = self.decision(evidence(mail=[outbound(counterparty="MATT@SCIENTIST.COM", offer_id=OFFER)]), intent(recipient="Matt@Scientist.com"))
        self.assertEqual(payload["decision"], "DO_NOT_RESEND")
        self.assertEqual(payload["intent"]["recipient"], RECIPIENT)

    def test_unknown_or_malformed_authority_fields_are_rejected(self):
        with self.assertRaises(GuardError):
            evaluate(intent(), evidence(mail_complete=1))
        broken = intent(); broken["extra"] = "surprise"
        with self.assertRaises(GuardError):
            evaluate(broken, evidence())

    def test_duplicate_json_key_is_rejected_before_materialization(self):
        raw = b'{"schema_version":"outbound-send-intent/v1","offer_id":"a","offer_id":"b"}'
        with self.assertRaises(GuardError):
            parse_json_bytes(raw, "intent")

    def test_receipt_is_deterministic_and_content_addressed(self):
        first = evaluate(intent(), evidence())
        second = evaluate(deepcopy(intent()), deepcopy(evidence()))
        self.assertEqual(first, second)
        self.assertEqual(len(first["receipt_sha256"]), 64)

    def test_cli_rejects_output_aliasing_input_without_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); ip = root / "intent.json"; ep = root / "evidence.json"
            ip.write_text(json.dumps(intent()), encoding="utf-8"); ep.write_text(json.dumps(evidence()), encoding="utf-8")
            before = ip.read_bytes()
            rc = main(["--intent", str(ip), "--evidence", str(ep), "--out", str(ip)])
            self.assertEqual(rc, 2); self.assertEqual(ip.read_bytes(), before)

    def test_cli_atomic_output_and_semantic_exit_codes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); ip = root / "intent.json"; ep = root / "evidence.json"; out = root / "receipt.json"
            ip.write_text(json.dumps(intent()), encoding="utf-8")
            ep.write_text(json.dumps(evidence(mail=[outbound(offer_id=OFFER)])), encoding="utf-8")
            rc = main(["--intent", str(ip), "--evidence", str(ep), "--out", str(out)])
            self.assertEqual(rc, 5)
            published = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(published["payload"]["decision"], "DO_NOT_RESEND")
            self.assertFalse(any(".stage-" in p.name for p in root.iterdir()))


if __name__ == "__main__":
    unittest.main()
