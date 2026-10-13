from __future__ import annotations

import copy
import json
import unittest
from datetime import datetime, timezone
from email.message import EmailMessage
from email import policy

from tools.outbound_send_guard import dsn_normalizer as dsn

ORIGINAL = "<CAJdSjCyD9wL-WSjiT=r2w1qiyp=uvtzB9Jtoxt9+zYmYHm4_dw@mail.gmail.com>"
RECIPIENT = "MBudz@atlab.com"
PROVIDER_ID = "1a09a16f419172cb"
SOURCE_ID = "1a09a16fee44277b"


def binding(**updates):
    value = {
        "schema_version": dsn.SCHEMA,
        "source_id": SOURCE_ID,
        "provider_message_id": PROVIDER_ID,
        "original_rfc822_message_id": ORIGINAL,
        "recipient": RECIPIENT,
        "sent_at": "2026-09-13T09:26:31Z",
        "captured_at": "2026-09-13T09:27:00Z",
    }
    value.update(updates)
    return value


def raw_dsn(
    *,
    recipient=RECIPIENT,
    action="failed",
    status="5.4.1",
    diagnostic="smtp; 550 5.4.1 Recipient address rejected: Access denied.",
    outer_date="Sun, 13 Sep 2026 02:26:33 -0700",
    x_original=ORIGINAL,
    in_reply=ORIGINAL,
    extra_recipient=None,
    duplicate_target=False,
    report_type="delivery-status",
    content_type="multipart/report",
):
    boundary = "BOUNDARY-OUTER"
    lines = [
        f'Content-Type: {content_type}; boundary="{boundary}"; report-type={report_type}',
        "From: Mail Delivery Subsystem <mailer-daemon@googlemail.com>",
        "To: tokenjunkielabs@gmail.com",
        f"Date: {outer_date}",
        "Subject: Delivery Status Notification (Failure)",
    ]
    if in_reply is not None:
        lines.append(f"In-Reply-To: {in_reply}")
    lines.extend(["", f"--{boundary}", "Content-Type: text/plain; charset=UTF-8", "", "Delivery failed.", f"--{boundary}", "Content-Type: message/delivery-status", ""])
    lines.extend([
        "Reporting-MTA: dns; googlemail.com",
        "Arrival-Date: Sun, 13 Sep 2026 02:26:31 -0700",
    ])
    if x_original is not None:
        lines.append(f"X-Original-Message-ID: {x_original}")
    lines.append("")
    def recipient_block(addr):
        return [
            f"Final-Recipient: rfc822; {addr}",
            f"Action: {action}",
            f"Status: {status}",
            f"Diagnostic-Code: {diagnostic}",
            "",
        ]
    lines.extend(recipient_block(recipient))
    if extra_recipient is not None:
        lines.extend(recipient_block(extra_recipient))
    if duplicate_target:
        lines.extend(recipient_block(recipient))
    lines.extend([f"--{boundary}--", ""])
    return "\r\n".join(lines).encode("ascii")


class DsnNormalizerTests(unittest.TestCase):
    def test_live_google_shape_normalizes(self):
        out = dsn.normalize(raw_dsn(), binding())
        event = out["event"]
        self.assertEqual(event["kind"], "dsn")
        self.assertEqual(event["recipient"], RECIPIENT.casefold())
        self.assertEqual(event["provider_message_id"], PROVIDER_ID)
        self.assertEqual(event["smtp_code"], 550)
        self.assertEqual(event["enhanced_status"], "5.4.1")
        self.assertEqual(event["observed_at"], "2026-09-13T09:26:33Z")
        self.assertEqual(
            out["original_message_binding_sources"],
            ["X-Original-Message-ID", "In-Reply-To"],
        )
        self.assertFalse(out["side_effects_authorized"])
        self.assertTrue(dsn.verify_receipt(out))

    def test_unrelated_second_recipient_is_allowed_but_only_target_event_emitted(self):
        out = dsn.normalize(raw_dsn(extra_recipient="other@example.com"), binding())
        self.assertEqual(out["recipient_block_count"], 2)
        self.assertEqual(out["matched_recipient_block_count"], 1)
        self.assertEqual(out["event"]["recipient"], RECIPIENT.casefold())

    def test_duplicate_target_blocks_are_ambiguous(self):
        with self.assertRaisesRegex(dsn.DsnError, "matched 2"):
            dsn.normalize(raw_dsn(duplicate_target=True), binding())

    def test_missing_target_block_is_ambiguous(self):
        with self.assertRaisesRegex(dsn.DsnError, "matched 0"):
            dsn.normalize(raw_dsn(recipient="other@example.com"), binding())

    def test_only_x_original_can_bind(self):
        out = dsn.normalize(raw_dsn(in_reply=None), binding())
        self.assertEqual(out["original_message_binding_sources"], ["X-Original-Message-ID"])

    def test_only_in_reply_to_can_bind(self):
        out = dsn.normalize(raw_dsn(x_original=None), binding())
        self.assertEqual(out["original_message_binding_sources"], ["In-Reply-To"])

    def test_missing_original_binding_holds(self):
        with self.assertRaisesRegex(dsn.DsnError, "no supported original-message binding"):
            dsn.normalize(raw_dsn(x_original=None, in_reply=None), binding())

    def test_wrong_x_original_holds_even_when_in_reply_matches(self):
        with self.assertRaisesRegex(dsn.DsnError, "X-Original-Message-ID"):
            dsn.normalize(raw_dsn(x_original="<wrong@example.com>"), binding())

    def test_wrong_in_reply_holds(self):
        with self.assertRaisesRegex(dsn.DsnError, "In-Reply-To"):
            dsn.normalize(raw_dsn(in_reply="<wrong@example.com>"), binding())

    def test_delayed_4xx_normalizes(self):
        out = dsn.normalize(
            raw_dsn(action="delayed", status="4.2.0", diagnostic="smtp; 450 4.2.0 Mailbox temporarily unavailable"),
            binding(),
        )
        self.assertEqual(out["event"]["smtp_code"], 450)
        self.assertEqual(out["event"]["enhanced_status"], "4.2.0")

    def test_failed_requires_5xx_status(self):
        with self.assertRaisesRegex(dsn.DsnError, "Action failed"):
            dsn.normalize(
                raw_dsn(action="failed", status="4.2.0", diagnostic="smtp; 450 4.2.0 temp"),
                binding(),
            )

    def test_delayed_requires_4xx_status(self):
        with self.assertRaisesRegex(dsn.DsnError, "Action delayed"):
            dsn.normalize(raw_dsn(action="delayed"), binding())

    def test_unsupported_action_holds(self):
        with self.assertRaisesRegex(dsn.DsnError, "only failed or delayed"):
            dsn.normalize(raw_dsn(action="delivered", status="2.0.0", diagnostic="smtp; 250 2.0.0 ok"), binding())

    def test_diagnostic_class_must_match_status(self):
        with self.assertRaisesRegex(dsn.DsnError, "classes disagree"):
            dsn.normalize(raw_dsn(status="5.4.1", diagnostic="smtp; 450 4.2.0 temp"), binding())

    def test_multiple_smtp_codes_are_ambiguous(self):
        with self.assertRaisesRegex(dsn.DsnError, "multiple SMTP failure codes"):
            dsn.normalize(raw_dsn(diagnostic="smtp; upstream 550 then downstream 551"), binding())

    def test_non_smtp_diagnostic_holds(self):
        with self.assertRaisesRegex(dsn.DsnError, "only smtp"):
            dsn.normalize(raw_dsn(diagnostic="x-unix; 550 nope"), binding())

    def test_missing_diagnostic_holds(self):
        raw = raw_dsn().replace(b"Diagnostic-Code: smtp; 550 5.4.1 Recipient address rejected: Access denied.\r\n", b"")
        with self.assertRaisesRegex(dsn.DsnError, "Diagnostic-Code"):
            dsn.normalize(raw, binding())

    def test_outer_date_before_send_holds(self):
        with self.assertRaisesRegex(dsn.DsnError, "predates original send"):
            dsn.normalize(raw_dsn(outer_date="Sun, 13 Sep 2026 02:26:30 -0700"), binding())

    def test_outer_date_after_capture_holds(self):
        with self.assertRaisesRegex(dsn.DsnError, "after capture boundary"):
            dsn.normalize(raw_dsn(outer_date="Sun, 13 Sep 2026 02:27:01 -0700"), binding())

    def test_wrong_report_type_holds(self):
        with self.assertRaisesRegex(dsn.DsnError, "report-type"):
            dsn.normalize(raw_dsn(report_type="disposition-notification"), binding())

    def test_wrong_outer_content_type_holds(self):
        raw = raw_dsn().replace(b"Content-Type: multipart/report;", b"Content-Type: multipart/mixed;", 1)
        with self.assertRaisesRegex(dsn.DsnError, "multipart/report"):
            dsn.normalize(raw, binding())

    def test_unknown_binding_field_holds(self):
        value = binding()
        value["extra"] = True
        with self.assertRaisesRegex(dsn.DsnError, "unexpected fields"):
            dsn.normalize(raw_dsn(), value)

    def test_recipient_comparison_is_case_insensitive(self):
        out = dsn.normalize(raw_dsn(recipient="mbUDZ@ATLAB.COM"), binding())
        self.assertEqual(out["event"]["recipient"], RECIPIENT.casefold())

    def test_event_identity_is_stable(self):
        a = dsn.normalize(raw_dsn(), binding())
        b = dsn.normalize(raw_dsn(), copy.deepcopy(binding()))
        self.assertEqual(a, b)

    def test_raw_source_change_changes_source_and_receipt_digest(self):
        a = dsn.normalize(raw_dsn(), binding())
        raw = raw_dsn().replace(b"Delivery failed.", b"Delivery has failed.")
        b = dsn.normalize(raw, binding())
        self.assertNotEqual(a["source_sha256"], b["source_sha256"])
        self.assertNotEqual(a["receipt_sha256"], b["receipt_sha256"])

    def test_receipt_tamper_holds(self):
        out = dsn.normalize(raw_dsn(), binding())
        out["event"]["smtp_code"] = 551
        with self.assertRaisesRegex(dsn.DsnError, "event digest mismatch"):
            dsn.verify_receipt(out)

    def test_receipt_cannot_authorize_side_effects(self):
        out = dsn.normalize(raw_dsn(), binding())
        out["side_effects_authorized"] = True
        material = dict(out)
        material.pop("receipt_sha256")
        out["receipt_sha256"] = dsn.sha256_json(material)
        with self.assertRaisesRegex(dsn.DsnError, "never authorize"):
            dsn.verify_receipt(out)

    def test_binding_message_id_must_be_bracketed(self):
        with self.assertRaisesRegex(dsn.DsnError, "RFC Message-ID"):
            dsn.normalize(raw_dsn(), binding(original_rfc822_message_id="not-bracketed"))

    def test_non_rfc822_final_recipient_holds(self):
        raw = raw_dsn().replace(b"Final-Recipient: rfc822;", b"Final-Recipient: x400;", 1)
        with self.assertRaisesRegex(dsn.DsnError, "only rfc822"):
            dsn.normalize(raw, binding())

    def test_raw_size_bound(self):
        with self.assertRaisesRegex(dsn.DsnError, "1.."):
            dsn.normalize(b"", binding())


if __name__ == "__main__":
    unittest.main()
