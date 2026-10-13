#!/usr/bin/env python3
"""Hostile pins for the conversion attribution compiler."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import conversion_attribution_ledger as cal


def _sha(n: str) -> str:
    return (n * 64)[:64]


def _commit(n: str) -> str:
    return (n * 40)[:40]


def packet() -> dict:
    offer = {
        "id": "offer-cycle-count",
        "source_ref": "commons://offer/cycle-count",
        "source_sha256": _sha("a"),
        "commercial_state": "READY",
        "currency": "USD",
        "created_at": "2026-09-01T00:00:00Z",
    }
    lead = {
        "id": "lead-alpha",
        "identity_sha256": _sha("b"),
        "stage": "QUALIFIED",
        "created_at": "2026-09-02T00:00:00Z",
        "source_ref": "internal://lead/alpha",
    }
    unpaid = {
        "id": "lead-beta",
        "identity_sha256": _sha("c"),
        "stage": "QUALIFIED",
        "created_at": "2026-09-03T00:00:00Z",
        "source_ref": "internal://lead/beta",
    }
    payment = {
        "id": "pay-1",
        "provider_event_id": "evt_1",
        "offer_id": "offer-cycle-count",
        "lead_id": "lead-alpha",
        "amount_minor": 500000,
        "currency": "USD",
        "occurred_at": "2026-09-10T12:00:00Z",
        "status": "SETTLED",
        "source_sha256": _sha("d"),
    }
    fulfillment = {
        "offer_id": "offer-cycle-count",
        "generation": 1,
        "source_commit": _commit("e"),
        "readiness": "READY",
        "evidence_ref": "git://fulfillment/1",
        "captured_at": "2026-09-09T00:00:00Z",
    }
    return {
        "schema_version": 1,
        "portfolio": {"name": "Synthetic conversion desk"},
        "offers": [offer],
        "leads": [lead, unpaid],
        "payments": [payment],
        "fulfillment": [fulfillment],
    }


class TestConversionAttributionLedger(unittest.TestCase):
    def test_happy_path_paid_ready_and_unpaid_pipeline(self) -> None:
        ledger = cal.compile_ledger(packet())
        states = {row["row_id"]: row["state"] for row in ledger["rows"]}
        self.assertEqual(states["pay:pay-1"], "PAID_ATTRIBUTED_READY")
        self.assertEqual(states["lead:lead-beta"], "UNPAID_PIPELINE")
        self.assertEqual(ledger["summary"]["currency_buckets"]["USD"]["settled_payment_minor"], 500000)
        self.assertIs(ledger["summary"]["cash_collected"], False)
        self.assertIs(ledger["summary"]["revenue_recognized"], False)
        self.assertNotIn("cash_collected", str(ledger["rows"]))
        self.assertTrue(ledger["authority_boundary"]["cash_collected_never_asserted"])
        self.assertTrue(ledger["authority_boundary"]["revenue_recognized_never_asserted"])

    def test_order_shuffle_keeps_receipt_stable(self) -> None:
        first = packet()
        second = packet()
        second["leads"] = list(reversed(second["leads"]))
        second["payments"] = list(reversed(second["payments"]))
        second["offers"] = list(reversed(second["offers"]))
        self.assertEqual(cal.compile_ledger(first)["ledger_sha256"], cal.compile_ledger(second)["ledger_sha256"])
        self.assertEqual(cal.compile_ledger(first), cal.compile_ledger(second))

    def test_missing_lead_binding_is_review_and_excluded_from_totals(self) -> None:
        p = packet()
        p["payments"][0]["lead_id"] = ""
        ledger = cal.compile_ledger(p)
        row = next(item for item in ledger["rows"] if item["payment_id"] == "pay-1")
        self.assertEqual(row["state"], "ATTRIBUTION_REVIEW")
        self.assertEqual(row["settled_payment_minor"], 0)
        self.assertEqual(ledger["summary"]["currency_buckets"], {})
        self.assertEqual(ledger["summary"]["state_counts"]["UNPAID_PIPELINE"], 2)

    def test_source_red_offer_is_paid_but_blocked(self) -> None:
        p = packet()
        p["offers"][0]["commercial_state"] = "SOURCE_RED"
        ledger = cal.compile_ledger(p)
        row = next(item for item in ledger["rows"] if item["payment_id"] == "pay-1")
        self.assertEqual(row["state"], "PAID_FULFILLMENT_BLOCKED")
        self.assertEqual(row["settled_payment_minor"], 500000)
        self.assertIn("OFFER_SOURCE_RED", row["reasons"])

    def test_not_ready_offer_is_paid_but_blocked(self) -> None:
        p = packet()
        p["offers"][0]["commercial_state"] = "NOT_READY"
        row = next(item for item in cal.compile_ledger(p)["rows"] if item["payment_id"] == "pay-1")
        self.assertEqual(row["state"], "PAID_FULFILLMENT_BLOCKED")
        self.assertIn("OFFER_NOT_READY", row["reasons"])

    def test_stale_and_unknown_fulfillment_block_readiness(self) -> None:
        for readiness in ("STALE", "UNKNOWN", "BLOCKED"):
            with self.subTest(readiness=readiness):
                p = packet()
                p["fulfillment"][0]["readiness"] = readiness
                row = next(item for item in cal.compile_ledger(p)["rows"] if item["payment_id"] == "pay-1")
                self.assertEqual(row["state"], "PAID_FULFILLMENT_BLOCKED")
                self.assertIn(f"FULFILLMENT_{readiness}", row["reasons"])

    def test_latest_generation_wins(self) -> None:
        p = packet()
        p["fulfillment"].append(
            {
                "offer_id": "offer-cycle-count",
                "generation": 2,
                "source_commit": _commit("f"),
                "readiness": "READY",
                "evidence_ref": "git://fulfillment/2",
                "captured_at": "2026-09-11T00:00:00Z",
            }
        )
        row = next(item for item in cal.compile_ledger(p)["rows"] if item["payment_id"] == "pay-1")
        self.assertEqual(row["fulfillment_generation"], 2)
        self.assertEqual(row["state"], "PAID_ATTRIBUTED_READY")

    def test_duplicate_economic_provider_event_fails_closed(self) -> None:
        p = packet()
        clone = copy.deepcopy(p["payments"][0])
        clone["id"] = "pay-2"
        p["payments"].append(clone)
        with self.assertRaisesRegex(ValueError, "duplicate economic payment event"):
            cal.compile_ledger(p)

    def test_same_id_changed_replay_fails_closed(self) -> None:
        p = packet()
        clone = copy.deepcopy(p["payments"][0])
        clone["amount_minor"] = 1
        p["payments"].append(clone)
        with self.assertRaisesRegex(ValueError, "duplicate payment id"):
            cal.compile_ledger(p)

    def test_currency_mismatch_fails_closed(self) -> None:
        p = packet()
        p["payments"][0]["currency"] = "EUR"
        with self.assertRaisesRegex(ValueError, "currency mismatch"):
            cal.compile_ledger(p)

    def test_bool_and_float_amounts_fail_closed(self) -> None:
        for amount in (True, 500000.0):
            with self.subTest(amount=amount):
                p = packet()
                p["payments"][0]["amount_minor"] = amount
                with self.assertRaisesRegex(ValueError, "integer minor-unit"):
                    cal.compile_ledger(p)

    def test_unknown_field_and_bad_timestamp_fail_closed(self) -> None:
        p = packet()
        p["offers"][0]["extra"] = "nope"
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            cal.compile_ledger(p)
        p = packet()
        p["payments"][0]["occurred_at"] = "2026-09-10"
        with self.assertRaisesRegex(ValueError, "invalid format"):
            cal.compile_ledger(p)

    def test_pending_payment_does_not_count_or_leave_pipeline(self) -> None:
        p = packet()
        p["payments"][0]["status"] = "PENDING"
        ledger = cal.compile_ledger(p)
        self.assertTrue(all(row["state"] == "UNPAID_PIPELINE" for row in ledger["rows"]))
        self.assertEqual(ledger["summary"]["currency_buckets"], {})

    def test_verify_and_cli_roundtrip(self) -> None:
        p = packet()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "in.json"
            out = root / "ledger.json"
            md = root / "ledger.md"
            src.write_text(json.dumps(p), encoding="utf-8")
            self.assertEqual(cal.main(["compile", "--input", str(src), "--json-out", str(out), "--markdown-out", str(md)]), 0)
            self.assertEqual(cal.main(["verify", "--input", str(src), "--ledger", str(out)]), 0)
            self.assertIn("settled_payment_minor", md.read_text(encoding="utf-8"))
            self.assertNotIn("cash collected", md.read_text(encoding="utf-8").lower().split("not ")[0][-20:])

    def test_strict_json_rejects_duplicate_keys_and_nonfinite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dup = root / "dup.json"
            inf = root / "inf.json"
            dup.write_text('{"schema_version": 1, "schema_version": 2}', encoding="utf-8")
            inf.write_text('{"schema_version": Infinity}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                cal._load_json_strict(str(dup))
            with self.assertRaisesRegex(ValueError, "invalid JSON constant"):
                cal._load_json_strict(str(inf))


if __name__ == "__main__":
    unittest.main()
