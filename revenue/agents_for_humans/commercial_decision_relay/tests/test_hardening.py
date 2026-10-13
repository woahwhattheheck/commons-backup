from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest

from decision_relay import DecisionRelayError, RelayEngine, canonical_digest, reconcile, verify_current_receipt, verify_receipt
from decision_relay.core import normalize_batch
from decision_relay.cli import _dump, main


def offer_batch(*, snapshot="2026-09-13T12:00:00Z", expires="2026-09-20T09:00:00Z", amount=1):
    return {
        "schema_version": 1,
        "snapshot_at": snapshot,
        "events": [
            {
                "event_id": "o1",
                "kind": "offer",
                "series_id": "s1",
                "offer_version": 1,
                "counterparty_id": "cp",
                "thread_id": "thread",
                "currency": "USD",
                "amount_minor": amount,
                "terms_digest": "a" * 64,
                "issued_at": "2026-09-13T09:00:00Z",
                "expires_at": expires,
            }
        ],
    }


def resign(receipt):
    body = deepcopy(receipt)
    body.pop("receipt_sha256", None)
    receipt["receipt_sha256"] = canonical_digest(body)
    return receipt


class TrustBoundaryTests(unittest.TestCase):
    def test_batch_schema_bool_is_not_integer_one(self):
        raw = offer_batch()
        raw["schema_version"] = True
        with self.assertRaises(DecisionRelayError) as ctx:
            normalize_batch(raw)
        self.assertEqual(ctx.exception.code, "unsupported_schema")

    def test_historical_verifier_is_explicitly_separate_from_current_verifier(self):
        raw = offer_batch()
        receipt = reconcile(raw, evaluated_at="2026-09-13T12:00:00Z")
        self.assertTrue(verify_receipt(receipt, receipt["receipt_sha256"], raw))
        self.assertTrue(
            verify_current_receipt(
                receipt,
                receipt["receipt_sha256"],
                raw,
                evaluated_at="2026-09-13T12:00:00Z",
            )
        )

    def test_preexpiry_receipt_fails_at_postexpiry_trusted_time(self):
        raw = offer_batch()
        receipt = reconcile(raw, evaluated_at="2026-09-19T12:00:00Z")
        self.assertEqual(receipt["series"][0]["status"], "AWAITING_RESPONSE")
        self.assertFalse(
            verify_current_receipt(
                receipt,
                receipt["receipt_sha256"],
                raw,
                evaluated_at="2026-09-21T12:00:00Z",
            )
        )
        current = reconcile(raw, evaluated_at="2026-09-21T12:00:00Z")
        self.assertEqual(current["series"][0]["status"], "REISSUE_REQUIRED")

    def test_authority_numeric_zero_cannot_impersonate_false(self):
        raw = offer_batch()
        for forged_value in (0, 0.0):
            with self.subTest(forged_value=forged_value):
                receipt = reconcile(raw, evaluated_at="2026-09-13T12:00:00Z")
                receipt["authority"]["payment_or_charge"] = forged_value
                resign(receipt)
                self.assertFalse(
                    verify_receipt(
                        receipt,
                        receipt["receipt_sha256"],
                        raw,
                        evaluated_at="2026-09-13T12:00:00Z",
                    )
                )

    def test_schema_true_cannot_impersonate_one(self):
        raw = offer_batch()
        receipt = reconcile(raw, evaluated_at="2026-09-13T12:00:00Z")
        receipt["schema_version"] = True
        resign(receipt)
        self.assertFalse(
            verify_receipt(
                receipt,
                receipt["receipt_sha256"],
                raw,
                evaluated_at="2026-09-13T12:00:00Z",
            )
        )

    def test_nested_true_cannot_impersonate_integer_one(self):
        raw = offer_batch(amount=1)
        receipt = reconcile(raw, evaluated_at="2026-09-13T12:00:00Z")
        receipt["series"][0]["amount_minor"] = True
        resign(receipt)
        self.assertFalse(
            verify_receipt(
                receipt,
                receipt["receipt_sha256"],
                raw,
                evaluated_at="2026-09-13T12:00:00Z",
            )
        )

    def test_engine_requires_trusted_time(self):
        raw = offer_batch()
        engine = RelayEngine()
        engine.ingest(raw)
        receipt = engine.reconcile(evaluated_at="2026-09-13T12:00:00Z")
        with self.assertRaises(DecisionRelayError) as ctx:
            engine.verify(receipt["receipt_sha256"])
        self.assertEqual(ctx.exception.code, "trusted_time_required")
        self.assertTrue(
            engine.verify(
                receipt["receipt_sha256"],
                evaluated_at="2026-09-13T12:00:00Z",
            )
        )


class DurableReceiptTests(unittest.TestCase):
    def test_dump_is_create_exclusive(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            _dump({"first": True}, str(path))
            before = path.read_bytes()
            with self.assertRaises(DecisionRelayError) as ctx:
                _dump({"second": True}, str(path))
            self.assertEqual(ctx.exception.code, "output_exists")
            self.assertEqual(path.read_bytes(), before)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support required")
    def test_dump_refuses_existing_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            real = directory / "real.json"
            real.write_text("sentinel\n", encoding="utf-8")
            link = directory / "receipt.json"
            try:
                link.symlink_to(real)
            except OSError:
                self.skipTest("symlink creation unavailable")
            with self.assertRaises(DecisionRelayError):
                _dump({"forged": True}, str(link))
            self.assertEqual(real.read_text(encoding="utf-8"), "sentinel\n")

    def test_cli_verify_requires_evaluated_at(self):
        with self.assertRaises(SystemExit) as ctx:
            main([
                "verify",
                "--receipt", "missing.json",
                "--batch", "missing.json",
                "--expected-receipt-sha256", "0" * 64,
            ])
        self.assertEqual(ctx.exception.code, 2)

    def test_cli_agent_requires_batch_and_evaluated_at(self):
        with self.assertRaises(SystemExit) as ctx:
            main(["agent"])
        self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
