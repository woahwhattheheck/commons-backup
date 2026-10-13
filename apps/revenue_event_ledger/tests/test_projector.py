import copy
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

from apps.revenue_event_ledger.projector import (
    ACCEPTED,
    BOUNCE,
    DNR,
    HUMAN_ROUTED,
    MUSE_SELECTED,
    PAID,
    PROPOSAL_SENT,
    PROVIDER_SENT,
    RESEARCHED,
    SCOPE_REQUEST,
    ReceiptError,
    project,
)

ASOF = "2026-09-17T05:45:00Z"
BUYER = "example.com"
OFFER = "integration-25k"
PURPOSE = "prime-workshare"


def r(rid, source, kind, at, **extra):
    row = {
        "id": rid,
        "source": source,
        "kind": kind,
        "observed_at": at,
        "buyer_scope": BUYER,
        "offer_key": OFFER,
        "purpose_key": PURPOSE,
    }
    row.update(extra)
    return row


def base(rows=None):
    return {
        "schema": "revenue-event-receipts/v1",
        "as_of": ASOF,
        "buyer_scope": BUYER,
        "offer_key": OFFER,
        "purpose_key": PURPOSE,
        "receipts": rows or [],
    }


def path_to_sent():
    return [
        r("slack:research", "SLACK", "RESEARCHED", "2026-09-17T01:00:00Z"),
        r("slack:muse", "SLACK", "MUSE_SELECTED", "2026-09-17T01:05:00Z", seat="zvh", expires_at="2026-09-17T02:00:00Z"),
        r("gmail:sent", "GMAIL", "PROVIDER_SENT", "2026-09-17T01:10:00Z"),
    ]


def full_paid():
    return path_to_sent() + [
        r("gmail:routed", "GMAIL", "HUMAN_ROUTED", "2026-09-17T01:20:00Z", human=True),
        r("gmail:scope", "GMAIL", "SCOPE_REQUEST", "2026-09-17T01:30:00Z", human=True),
        r("gmail:proposal", "GMAIL", "PROPOSAL_SENT", "2026-09-17T01:40:00Z"),
        r("gmail:accepted", "GMAIL", "ACCEPTED", "2026-09-17T01:50:00Z", human=True),
        r("stripe:settled", "PAYMENT", "PAYMENT_SETTLED", "2026-09-17T02:00:00Z", verified=True, settlement_id="pi_123", amount_minor=2500000, currency="USD"),
    ]


class LifecycleTests(unittest.TestCase):
    def test_empty_is_start_and_silence_neutral(self):
        out = project(base())
        self.assertEqual(out["state"], "START")
        self.assertEqual(out["silence_assessment"], "NEUTRAL_NOT_EVIDENCE")
        self.assertFalse(out["cash_claim_authorized"])

    def test_researched_requires_explicit_receipt(self):
        out = project(base([r("s:r", "SLACK", "RESEARCHED", "2026-09-17T01:00:00Z")]))
        self.assertEqual(out["state"], RESEARCHED)
        self.assertEqual(out["state_receipt_id"], "s:r")

    def test_muse_selected_requires_research(self):
        rows = [r("s:m", "SLACK", "MUSE_SELECTED", "2026-09-17T01:00:00Z", seat="a", expires_at="2026-09-17T02:00:00Z")]
        out = project(base(rows))
        self.assertEqual(out["state"], "START")
        self.assertIn("MISSING_PREDECESSOR_RESEARCHED", [x["code"] for x in out["diagnostics"]])

    def test_provider_sent_requires_live_muse_selection_at_send(self):
        rows = [
            r("s:r", "SLACK", "RESEARCHED", "2026-09-17T00:30:00Z"),
            r("s:m", "SLACK", "MUSE_SELECTED", "2026-09-17T00:40:00Z", seat="a", expires_at="2026-09-17T00:50:00Z"),
            r("g:s", "GMAIL", "PROVIDER_SENT", "2026-09-17T01:00:00Z"),
        ]
        out = project(base(rows))
        self.assertEqual(out["state"], MUSE_SELECTED)
        self.assertIn("PROVIDER_SENT_WITHOUT_LIVE_MUSE_SELECTION", [x["code"] for x in out["diagnostics"]])

    def test_valid_provider_sent(self):
        self.assertEqual(project(base(path_to_sent()))["state"], PROVIDER_SENT)

    def test_auto_ack_is_side_event_only(self):
        rows = path_to_sent() + [r("g:ack", "GMAIL", "AUTO_ACK", "2026-09-17T01:15:00Z")]
        out = project(base(rows))
        self.assertEqual(out["state"], PROVIDER_SENT)
        self.assertEqual(out["side_events"]["AUTO_ACK"], ["g:ack"])

    def test_support_ticket_is_side_event_only(self):
        rows = path_to_sent() + [r("g:ticket", "GMAIL", "SUPPORT_TICKET", "2026-09-17T01:15:00Z")]
        out = project(base(rows))
        self.assertEqual(out["state"], PROVIDER_SENT)
        self.assertEqual(out["side_events"]["SUPPORT_TICKET"], ["g:ticket"])

    def test_human_routed_requires_human_true(self):
        rows = path_to_sent() + [r("g:h", "GMAIL", "HUMAN_ROUTED", "2026-09-17T01:20:00Z", human=False)]
        with self.assertRaises(ReceiptError): project(base(rows))

    def test_human_routed_advances(self):
        rows = path_to_sent() + [r("g:h", "GMAIL", "HUMAN_ROUTED", "2026-09-17T01:20:00Z", human=True)]
        self.assertEqual(project(base(rows))["state"], HUMAN_ROUTED)

    def test_scope_request_can_follow_provider_sent(self):
        rows = path_to_sent() + [r("g:q", "GMAIL", "SCOPE_REQUEST", "2026-09-17T01:20:00Z", human=True)]
        self.assertEqual(project(base(rows))["state"], SCOPE_REQUEST)

    def test_dnr_is_terminal_after_sent(self):
        rows = path_to_sent() + [
            r("g:dnr", "GMAIL", "DNR", "2026-09-17T01:20:00Z"),
            r("g:later", "GMAIL", "HUMAN_ROUTED", "2026-09-17T01:30:00Z", human=True),
        ]
        out = project(base(rows))
        self.assertEqual(out["state"], DNR)
        self.assertIn("POST_TERMINAL_RECEIPT_IGNORED", [x["code"] for x in out["diagnostics"]])

    def test_bounce_is_terminal_after_sent(self):
        rows = path_to_sent() + [r("g:b", "PROVIDER", "BOUNCE", "2026-09-17T01:20:00Z")]
        self.assertEqual(project(base(rows))["state"], BOUNCE)

    def test_dnr_without_send_does_not_create_state(self):
        rows = [r("s:r", "SLACK", "RESEARCHED", "2026-09-17T01:00:00Z"), r("s:d", "SLACK", "DNR", "2026-09-17T01:10:00Z")]
        out = project(base(rows))
        self.assertEqual(out["state"], RESEARCHED)
        self.assertIn("DNR_WITHOUT_PROVIDER_SENT", [x["code"] for x in out["diagnostics"]])

    def test_proposal_requires_human_event(self):
        rows = path_to_sent() + [r("g:p", "GMAIL", "PROPOSAL_SENT", "2026-09-17T01:20:00Z")]
        out = project(base(rows))
        self.assertEqual(out["state"], PROVIDER_SENT)
        self.assertIn("MISSING_PREDECESSOR_HUMAN_EVENT", [x["code"] for x in out["diagnostics"]])

    def test_proposal_after_scope(self):
        rows = path_to_sent() + [
            r("g:q", "GMAIL", "SCOPE_REQUEST", "2026-09-17T01:20:00Z", human=True),
            r("g:p", "GMAIL", "PROPOSAL_SENT", "2026-09-17T01:30:00Z"),
        ]
        self.assertEqual(project(base(rows))["state"], PROPOSAL_SENT)

    def test_accepted_requires_proposal(self):
        rows = path_to_sent() + [r("g:a", "GMAIL", "ACCEPTED", "2026-09-17T01:20:00Z", human=True)]
        out = project(base(rows))
        self.assertEqual(out["state"], PROVIDER_SENT)
        self.assertIn("MISSING_PREDECESSOR_PROPOSAL_SENT", [x["code"] for x in out["diagnostics"]])

    def test_full_chain_reaches_paid(self):
        out = project(base(full_paid()))
        self.assertEqual(out["state"], PAID)
        self.assertTrue(out["cash_claim_authorized"])
        self.assertEqual(out["money_evidence"], "VERIFIED_SETTLEMENT")
        self.assertEqual(out["settlement"]["settlement_id"], "pi_123")
        self.assertEqual(out["settlement"]["amount_minor"], 2500000)

    def test_unverified_settlement_cannot_pay(self):
        rows = full_paid()[:-1] + [r("pay:u", "PAYMENT", "PAYMENT_SETTLED", "2026-09-17T02:00:00Z", verified=False, settlement_id="pi_u", amount_minor=1, currency="USD")]
        out = project(base(rows))
        self.assertEqual(out["state"], ACCEPTED)
        self.assertFalse(out["cash_claim_authorized"])
        self.assertEqual(out["money_evidence"], "NOT_ESTABLISHED")
        self.assertIn("UNVERIFIED_SETTLEMENT_IGNORED", [x["code"] for x in out["diagnostics"]])

    def test_settlement_without_acceptance_cannot_pay(self):
        rows = path_to_sent() + [r("pay:x", "PAYMENT", "PAYMENT_SETTLED", "2026-09-17T02:00:00Z", verified=True, settlement_id="pi_x", amount_minor=100, currency="USD")]
        out = project(base(rows))
        self.assertEqual(out["state"], PROVIDER_SENT)
        self.assertFalse(out["cash_claim_authorized"])
        self.assertIn("SETTLEMENT_WITHOUT_ACCEPTED", [x["code"] for x in out["diagnostics"]])

    def test_payment_kind_requires_payment_source(self):
        rows = [r("x", "GMAIL", "PAYMENT_SETTLED", "2026-09-17T01:00:00Z", verified=True, settlement_id="x", amount_minor=1, currency="USD")]
        with self.assertRaises(ReceiptError): project(base(rows))

    def test_bool_not_amount(self):
        rows = [r("x", "PAYMENT", "PAYMENT_SETTLED", "2026-09-17T01:00:00Z", verified=True, settlement_id="x", amount_minor=True, currency="USD")]
        with self.assertRaises(ReceiptError): project(base(rows))

    def test_currency_must_be_three_letters(self):
        rows = [r("x", "PAYMENT", "PAYMENT_SETTLED", "2026-09-17T01:00:00Z", verified=True, settlement_id="x", amount_minor=1, currency="USDT")]
        with self.assertRaises(ReceiptError): project(base(rows))

    def test_duplicate_receipt_id_rejected(self):
        rows = [r("dup", "SLACK", "RESEARCHED", "2026-09-17T01:00:00Z"), r("dup", "SLACK", "RESEARCHED", "2026-09-17T01:01:00Z")]
        with self.assertRaises(ReceiptError): project(base(rows))

    def test_cross_buyer_receipt_rejected(self):
        row = r("x", "SLACK", "RESEARCHED", "2026-09-17T01:00:00Z"); row["buyer_scope"] = "other.com"
        with self.assertRaises(ReceiptError): project(base([row]))

    def test_future_receipt_rejected(self):
        with self.assertRaises(ReceiptError): project(base([r("x", "SLACK", "RESEARCHED", "2026-09-18T01:00:00Z")]))

    def test_naive_timestamp_rejected(self):
        with self.assertRaises(ReceiptError): project(base([r("x", "SLACK", "RESEARCHED", "2026-09-17T01:00:00")]))

    def test_active_multiple_muse_seats_collision(self):
        rows = [
            r("s:r", "SLACK", "RESEARCHED", "2026-09-17T01:00:00Z"),
            r("s:m1", "SLACK", "MUSE_SELECTED", "2026-09-17T01:05:00Z", seat="a", expires_at="2026-09-17T06:00:00Z"),
            r("s:m2", "SLACK", "MUSE_SELECTED", "2026-09-17T01:06:00Z", seat="b", expires_at="2026-09-17T06:00:00Z"),
        ]
        out = project(base(rows))
        self.assertTrue(out["collision"])
        self.assertIn("COLLISION_MULTIPLE_ACTIVE_MUSE_SELECTIONS", [x["code"] for x in out["diagnostics"]])

    def test_expired_unsent_muse_selection_stale_owner(self):
        rows = [
            r("s:r", "SLACK", "RESEARCHED", "2026-09-17T01:00:00Z"),
            r("s:m", "SLACK", "MUSE_SELECTED", "2026-09-17T01:05:00Z", seat="a", expires_at="2026-09-17T02:00:00Z"),
        ]
        out = project(base(rows))
        self.assertIn("STALE_OWNER_SELECTION", [x["code"] for x in out["diagnostics"]])

    def test_expired_selection_with_prior_valid_send_not_stale_owner(self):
        out = project(base(path_to_sent()))
        self.assertNotIn("STALE_OWNER_SELECTION", [x["code"] for x in out["diagnostics"]])

    def test_same_timestamp_mutations_diagnosed(self):
        rows = [
            r("a", "SLACK", "RESEARCHED", "2026-09-17T01:00:00Z"),
            r("b", "SLACK", "DNR", "2026-09-17T01:00:00Z"),
        ]
        out = project(base(rows))
        self.assertIn("AMBIGUOUS_SAME_TIMESTAMP_MUTATIONS", [x["code"] for x in out["diagnostics"]])

    def test_deterministic_output_and_digest(self):
        p = base(full_paid())
        a = project(copy.deepcopy(p)); b = project(copy.deepcopy(p))
        self.assertEqual(a, b)
        self.assertRegex(a["input_digest_sha256"], r"^[0-9a-f]{64}$")

    def test_provider_mutation_is_always_false(self):
        for rows in ([], path_to_sent(), full_paid()):
            self.assertIs(project(base(rows))["provider_mutation_performed"], False)


class CliTests(unittest.TestCase):
    def test_invalid_input_exits_two_without_projection(self):
        p = base([r("x", "GMAIL", "PAYMENT_SETTLED", "2026-09-17T01:00:00Z", verified=True, settlement_id="x", amount_minor=1, currency="USD")])
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "bad.json"
            path.write_text(json.dumps(p), encoding="utf-8")
            proc = subprocess.run([sys.executable, "-m", "apps.revenue_event_ledger.projector", str(path)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        self.assertIn("receipt-ledger-error:", proc.stderr)


if __name__ == "__main__":
    unittest.main()
