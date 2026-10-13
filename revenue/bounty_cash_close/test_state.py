from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path

from .cli import _load_json, compile_command
from .engine import CloseBoardError, INPUT_SCHEMA, ZERO_SHA256, canonical_bounty_key, compile_board, mint_receipt, validate_input, verify_bundle
from .test_support import *  # test fixture helpers

class StateTests(unittest.TestCase):
    def test_empty_chain_requests_submit(self):
        row = row_for([])
        self.assertEqual(row["state"], "READY_TO_SUBMIT")
        self.assertEqual(row["next_action"], "SUBMIT")

    def test_failed_transport_is_not_delivery(self):
        chain = add([], "SUBMISSION_ATTEMPT_FAILED", "2026-09-14T10:00:00Z")
        row = row_for(chain)
        self.assertEqual(row["state"], "SUBMISSION_BLOCKED")
        self.assertEqual(row["next_action"], "UNBLOCK_EXTERNAL_GATE")
        self.assertFalse(row["technical_acceptance_observed"])

    def test_failed_then_fallback_delivered_keeps_identity(self):
        chain = add([], "SUBMISSION_ATTEMPT_FAILED", "2026-09-14T10:00:00Z")
        chain = add(chain, "SUBMISSION_DELIVERED", "2026-09-14T10:05:00Z", pclass="EMAIL")
        bounty = make_bounty(chain)
        key_before = canonical_bounty_key(make_bounty([]))
        out, _, _ = compile_board(make_doc([bounty]), AS_OF)
        self.assertEqual(out["rows"][0]["canonical_bounty_key"], key_before)
        self.assertEqual(out["rows"][0]["state"], "SUBMITTED_PENDING_ACCEPTANCE")

    def test_delivery_only_waits(self):
        row = row_for(add([], "SUBMISSION_DELIVERED", "2026-09-14T10:00:00Z"))
        self.assertEqual(row["next_action"], "WAIT_DNR")

    def test_technical_acceptance_asks_compensation(self):
        chain = add([], "SUBMISSION_DELIVERED", "2026-09-14T10:00:00Z")
        chain = add(chain, "TECHNICAL_ACCEPTED", "2026-09-14T11:00:00Z", pclass="SPONSOR")
        row = row_for(chain)
        self.assertEqual(row["state"], "ACCEPTED_COMPENSATION_UNASKED")
        self.assertEqual(row["next_action"], "ASK_COMPENSATION")
        self.assertFalse(row["settlement_observed"])

    def test_recent_compensation_ask_waits(self):
        chain = add([], "SUBMISSION_DELIVERED", "2026-09-14T10:00:00Z")
        chain = add(chain, "TECHNICAL_ACCEPTED", "2026-09-14T11:00:00Z", pclass="SPONSOR")
        chain = add(chain, "COMPENSATION_ASK_SENT", "2026-09-14T19:00:00Z", pclass="EMAIL")
        row = row_for(chain)
        self.assertEqual(row["next_action"], "WAIT_DNR")
        self.assertEqual(row["next_action_eligible_at_utc"], "2026-09-14T21:00:00Z")

    def test_aged_compensation_ask_allows_one_followup(self):
        chain = add([], "SUBMISSION_DELIVERED", "2026-09-14T10:00:00Z")
        chain = add(chain, "TECHNICAL_ACCEPTED", "2026-09-14T11:00:00Z", pclass="SPONSOR")
        chain = add(chain, "COMPENSATION_ASK_SENT", "2026-09-14T12:00:00Z", pclass="EMAIL")
        self.assertEqual(row_for(chain)["next_action"], "FOLLOW_UP_COMPENSATION")
        chain = add(chain, "COMPENSATION_FOLLOWUP_SENT", "2026-09-14T15:00:00Z", pclass="EMAIL")
        self.assertEqual(row_for(chain)["next_action"], "WAIT_DNR")

    def test_sponsor_paid_ack_is_not_settlement(self):
        chain = add([], "SUBMISSION_DELIVERED", "2026-09-14T10:00:00Z")
        chain = add(chain, "TECHNICAL_ACCEPTED", "2026-09-14T11:00:00Z", pclass="SPONSOR")
        chain = add(chain, "COMPENSATION_ASK_SENT", "2026-09-14T12:00:00Z", pclass="EMAIL")
        chain = add(chain, "PAYOUT_ACKNOWLEDGED", "2026-09-14T13:00:00Z", pclass="SPONSOR")
        row = row_for(chain)
        self.assertEqual(row["state"], "PAYOUT_ACK_SETTLEMENT_PENDING")
        self.assertEqual(row["next_action"], "RECONCILE_SETTLEMENT")
        self.assertFalse(row["settlement_observed"])

    def test_independent_rail_receipt_settles(self):
        chain = add([], "SUBMISSION_DELIVERED", "2026-09-14T10:00:00Z")
        chain = add(chain, "TECHNICAL_ACCEPTED", "2026-09-14T11:00:00Z", pclass="SPONSOR")
        chain = add(chain, "COMPENSATION_ASK_SENT", "2026-09-14T12:00:00Z", pclass="EMAIL")
        chain = add(chain, "PAYOUT_ACKNOWLEDGED", "2026-09-14T13:00:00Z", pclass="SPONSOR")
        chain = add(chain, "SETTLEMENT_OBSERVED", "2026-09-14T14:00:00Z", pclass="PROCESSOR")
        row = row_for(chain)
        self.assertEqual(row["state"], "SETTLED")
        self.assertEqual(row["next_action"], "CLOSE_SETTLED")
        self.assertTrue(row["settlement_observed"])

    def test_payment_link_never_settles(self):
        chain = add([], "SUBMISSION_DELIVERED", "2026-09-14T10:00:00Z")
        chain = add(chain, "TECHNICAL_ACCEPTED", "2026-09-14T11:00:00Z", pclass="SPONSOR")
        chain = add(chain, "PAYMENT_LINK_CREATED", "2026-09-14T12:00:00Z", pclass="PROCESSOR")
        row = row_for(chain)
        self.assertEqual(row["next_action"], "ASK_COMPENSATION")
        self.assertFalse(row["settlement_observed"])

    def test_gate_wait_and_single_followup(self):
        chain = add([], "SUBMISSION_DELIVERED", "2026-09-14T10:00:00Z")
        chain = add(chain, "GATE_BLOCKED", "2026-09-14T19:30:00Z")
        row = row_for(chain)
        self.assertEqual(row["next_action"], "WAIT_DNR")
        self.assertEqual(row["next_action_eligible_at_utc"], "2026-09-14T20:30:00Z")
        self.assertEqual(row_for(chain, as_of="2026-09-14T21:00:00Z")["next_action"], "UNBLOCK_EXTERNAL_GATE")
        chain = add(chain, "GATE_FOLLOWUP_SENT", "2026-09-14T21:05:00Z", pclass="EMAIL")
        self.assertEqual(row_for(chain, as_of="2026-09-14T22:00:00Z")["next_action"], "WAIT_DNR")

    def test_cleared_gate_returns_acceptance_wait(self):
        chain = add([], "SUBMISSION_DELIVERED", "2026-09-14T10:00:00Z")
        chain = add(chain, "GATE_BLOCKED", "2026-09-14T11:00:00Z")
        chain = add(chain, "GATE_CLEARED", "2026-09-14T12:00:00Z")
        self.assertEqual(row_for(chain)["state"], "SUBMITTED_PENDING_ACCEPTANCE")

    def test_terminal_nonpay_is_terminal(self):
        chain = add([], "TERMINAL_NONPAY", "2026-09-14T10:00:00Z", pclass="SPONSOR")
        row = row_for(chain)
        self.assertEqual(row["state"], "TERMINAL_NONPAY")
        self.assertEqual(row["next_action"], "WAIT_DNR")
