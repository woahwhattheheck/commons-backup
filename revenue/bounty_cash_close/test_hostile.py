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

class HostileTests(unittest.TestCase):
    def test_acceptance_requires_delivery(self):
        chain = add([], "TECHNICAL_ACCEPTED", "2026-09-14T10:00:00Z", pclass="SPONSOR")
        with self.assertRaises(CloseBoardError):
            validate_input(make_doc([make_bounty(chain)]))

    def test_settlement_requires_payout(self):
        chain = add([], "SETTLEMENT_OBSERVED", "2026-09-14T10:00:00Z", pclass="BANK")
        with self.assertRaises(CloseBoardError):
            validate_input(make_doc([make_bounty(chain)]))

    def test_settlement_requires_independent_rail(self):
        chain = add([], "SUBMISSION_DELIVERED", "2026-09-14T09:00:00Z")
        chain = add(chain, "TECHNICAL_ACCEPTED", "2026-09-14T10:00:00Z", pclass="SPONSOR")
        chain = add(chain, "COMPENSATION_ASK_SENT", "2026-09-14T11:00:00Z", pclass="EMAIL")
        chain = add(chain, "PAYOUT_ACKNOWLEDGED", "2026-09-14T12:00:00Z", pclass="SPONSOR")
        previous = chain[-1]["receipt_sha256"]
        bad = mint_receipt({
            "event_id": "event:settle",
            "kind": "SETTLEMENT_OBSERVED",
            "observed_at_utc": "2026-09-14T13:00:00Z",
            "provider_class": "SPONSOR",
            "provider_ref": "provider:sponsor",
            "external_ref": "external:settle",
            "evidence_sha256": h("settle"),
            "previous_receipt_sha256": previous,
        })
        with self.assertRaises(CloseBoardError):
            validate_input(make_doc([make_bounty([*chain, bad])]))

    def test_payout_ack_requires_sponsor_provider(self):
        chain = add([], "SUBMISSION_DELIVERED", "2026-09-14T09:00:00Z")
        chain = add(chain, "TECHNICAL_ACCEPTED", "2026-09-14T10:00:00Z", pclass="SPONSOR")
        chain = add(chain, "COMPENSATION_ASK_SENT", "2026-09-14T11:00:00Z", pclass="EMAIL")
        previous = chain[-1]["receipt_sha256"]
        bad = mint_receipt({
            "event_id": "event:payout",
            "kind": "PAYOUT_ACKNOWLEDGED",
            "observed_at_utc": "2026-09-14T12:00:00Z",
            "provider_class": "EMAIL",
            "provider_ref": "provider:email",
            "external_ref": "external:payout",
            "evidence_sha256": h("payout"),
            "previous_receipt_sha256": previous,
        })
        with self.assertRaises(CloseBoardError):
            validate_input(make_doc([make_bounty([*chain, bad])]))

    def test_receipt_tamper_rejected(self):
        chain = add([], "SUBMISSION_DELIVERED", "2026-09-14T10:00:00Z")
        chain[0]["external_ref"] = "external:tampered"
        with self.assertRaises(CloseBoardError):
            validate_input(make_doc([make_bounty(chain)]))

    def test_reordered_receipt_input_is_deterministic(self):
        chain = add([], "SUBMISSION_DELIVERED", "2026-09-14T10:00:00Z")
        chain = add(chain, "GATE_BLOCKED", "2026-09-14T11:00:00Z")
        chain = add(chain, "GATE_CLEARED", "2026-09-14T12:00:00Z")
        doc1 = make_doc([make_bounty(chain)])
        doc2 = make_doc([make_bounty(list(reversed(chain)))])
        self.assertEqual(compile_board(doc1, AS_OF), compile_board(doc2, AS_OF))

    def test_fork_rejected(self):
        root = add([], "CLAIMED", "2026-09-14T09:00:00Z")
        a = add(root, "BUILD_COMPLETE", "2026-09-14T10:00:00Z")[-1]
        b_core = {
            "event_id": "event:fork",
            "kind": "SUBMISSION_ATTEMPT_FAILED",
            "observed_at_utc": "2026-09-14T10:05:00Z",
            "provider_class": "GITHUB",
            "provider_ref": "provider:github",
            "external_ref": "external:fork",
            "evidence_sha256": h("fork"),
            "previous_receipt_sha256": root[-1]["receipt_sha256"],
        }
        b = mint_receipt(b_core)
        with self.assertRaises(CloseBoardError):
            validate_input(make_doc([make_bounty([root[0], a, b])]))

    def test_duplicate_canonical_bounty_rejected(self):
        bounty = make_bounty([])
        with self.assertRaises(CloseBoardError):
            validate_input(make_doc([bounty, copy.deepcopy(bounty)]))

    def test_bool_amount_rejected(self):
        bounty = make_bounty([])
        bounty["advertised_value"]["amount_minor"] = True
        with self.assertRaises(CloseBoardError):
            validate_input(make_doc([bounty]))

    def test_bad_currency_rejected(self):
        bounty = make_bounty([])
        bounty["advertised_value"]["currency"] = "usd"
        with self.assertRaises(CloseBoardError):
            validate_input(make_doc([bounty]))

    def test_future_receipt_rejected_by_compile(self):
        chain = add([], "CLAIMED", "2026-09-15T00:00:00Z")
        with self.assertRaises(CloseBoardError):
            compile_board(make_doc([make_bounty(chain)]), AS_OF)

    def test_terminal_must_be_last(self):
        chain = add([], "TERMINAL_NONPAY", "2026-09-14T09:00:00Z", pclass="SPONSOR")
        chain = add(chain, "PAYMENT_LINK_CREATED", "2026-09-14T10:00:00Z", pclass="PROCESSOR")
        with self.assertRaises(CloseBoardError):
            validate_input(make_doc([make_bounty(chain)]))

    def test_output_markdown_receipt_tamper_rejected(self):
        doc = make_doc([make_bounty([])])
        out, md, receipt = compile_board(doc, AS_OF)
        verify_bundle(doc, out, md, receipt)
        bad_out = copy.deepcopy(out); bad_out["counts"]["total"] = 99
        with self.assertRaises(CloseBoardError): verify_bundle(doc, bad_out, md, receipt)
        with self.assertRaises(CloseBoardError): verify_bundle(doc, out, md + "x", receipt)
        bad_receipt = copy.deepcopy(receipt); bad_receipt["output_sha256"] = h("wrong")
        with self.assertRaises(CloseBoardError): verify_bundle(doc, out, md, bad_receipt)

    def test_input_order_invariance(self):
        a = make_bounty([], suffix="a")
        b = make_bounty([], suffix="b")
        self.assertEqual(compile_board(make_doc([a, b]), AS_OF), compile_board(make_doc([b, a]), AS_OF))

    def test_unpriced_is_explicit(self):
        bounty = make_bounty([])
        bounty["advertised_value"] = {"state":"UNPRICED", "source_ref":"issue:unknown", "evidence_sha256":h("unknown")}
        row = compile_board(make_doc([bounty]), AS_OF)[0]["rows"][0]
        self.assertEqual(row["advertised_value"]["state"], "UNPRICED")
