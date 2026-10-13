import copy
import unittest

from revenue.commercial_lifecycle_ledger.lifecycle import (
    LedgerError, compile_ledger, load_json_strict, subject_commitment, verify_receipt,
)


def base():
    return {
        "version": "commons-commercial-lifecycle/v1",
        "deal_id": "deal-001",
        "opportunity_sha256": "1" * 64,
        "offer_sha256": "2" * 64,
        "scope_sha256": "3" * 64,
        "buyer_ref_sha256": "4" * 64,
        "currency": "USD",
        "contract_amount_minor": 250000,
        "offer_expires_at": "2026-10-01T00:00:00Z",
        "events": [],
    }


def ev(payload, n, kind, authority, when, *, amount=None, currency=None, reversal=None, evidence=None):
    return {
        "event_id": f"e{n:02d}",
        "kind": kind,
        "occurred_at": when,
        "authority": authority,
        "evidence_sha256": evidence or (f"{n:x}" * 64)[:64],
        "subject_sha256": subject_commitment(payload),
        "amount_minor": amount,
        "currency": currency,
        "reversal_of": reversal,
    }


def full_payload():
    p = base()
    p["events"] = [
        ev(p, 1, "OPPORTUNITY_QUALIFIED", "owner", "2026-09-13T10:00:00Z"),
        ev(p, 2, "OFFER_OWNER_APPROVED", "owner", "2026-09-13T10:01:00Z"),
        ev(p, 3, "OFFER_SENT", "transport", "2026-09-13T10:02:00Z"),
        ev(p, 4, "BUYER_ACCEPTED", "buyer", "2026-09-13T10:03:00Z"),
        ev(p, 5, "FUNDING_VERIFIED", "funding", "2026-09-13T10:04:00Z", amount=250000, currency="USD"),
        ev(p, 6, "EXECUTION_STARTED", "owner", "2026-09-13T10:05:00Z"),
        ev(p, 7, "FULFILLMENT_ACCEPTED", "buyer", "2026-09-13T10:06:00Z"),
        ev(p, 8, "PAYMENT_SETTLED", "payment", "2026-09-13T10:07:00Z", amount=250000, currency="USD"),
        ev(p, 9, "REVENUE_RECOGNIZED", "finance", "2026-09-13T10:08:00Z", amount=250000, currency="USD"),
    ]
    return p


class LifecycleTests(unittest.TestCase):
    ASOF = "2026-09-13T11:00:00Z"

    def test_full_lifecycle(self):
        p = full_payload()
        r = compile_ledger(p, trusted_as_of=self.ASOF)
        self.assertEqual(r["state"], "REVENUE_RECOGNITION_EVIDENCED")
        self.assertEqual(r["net_cash_evidenced_minor"], 250000)
        self.assertEqual(r["net_recognized_evidenced_minor"], 250000)
        self.assertTrue(verify_receipt(p, r, trusted_as_of=self.ASOF))
        self.assertTrue(all(v is False for v in r["authority"].values()))

    def test_partial_payments(self):
        p = full_payload()
        p["events"] = p["events"][:7]
        p["events"] += [
            ev(p, 8, "PAYMENT_SETTLED", "payment", "2026-09-13T10:07:00Z", amount=100000, currency="USD"),
            ev(p, 9, "PAYMENT_SETTLED", "payment", "2026-09-13T10:08:00Z", amount=150000, currency="USD"),
            ev(p, 10, "REVENUE_RECOGNIZED", "finance", "2026-09-13T10:09:00Z", amount=250000, currency="USD"),
        ]
        r = compile_ledger(p, trusted_as_of=self.ASOF)
        self.assertEqual(r["settled_amount_minor"], 250000)

    def test_partial_refund_and_reversal(self):
        p = full_payload()
        p["events"] += [
            ev(p, 10, "REFUND_SETTLED", "payment", "2026-09-13T10:09:00Z", amount=50000, currency="USD", reversal="e08"),
            ev(p, 11, "REVENUE_REVERSED", "finance", "2026-09-13T10:10:00Z", amount=50000, currency="USD", reversal="e10"),
        ]
        r = compile_ledger(p, trusted_as_of=self.ASOF)
        self.assertEqual(r["state"], "PARTIALLY_REVERSED_EVIDENCE_ONLY")
        self.assertEqual(r["net_cash_evidenced_minor"], 200000)
        self.assertEqual(r["net_recognized_evidenced_minor"], 200000)

    def test_full_refund_and_reversal(self):
        p = full_payload()
        p["events"] += [
            ev(p, 10, "REFUND_SETTLED", "payment", "2026-09-13T10:09:00Z", amount=250000, currency="USD", reversal="e08"),
            ev(p, 11, "REVENUE_REVERSED", "finance", "2026-09-13T10:10:00Z", amount=250000, currency="USD", reversal="e10"),
        ]
        r = compile_ledger(p, trusted_as_of=self.ASOF)
        self.assertEqual(r["state"], "FULLY_REVERSED_EVIDENCE_ONLY")
        self.assertEqual(r["net_cash_evidenced_minor"], 0)
        self.assertEqual(r["net_recognized_evidenced_minor"], 0)

    def test_cancel_terminal_except_reversals(self):
        p = base()
        p["events"] = [
            ev(p, 1, "OPPORTUNITY_QUALIFIED", "owner", "2026-09-13T10:00:00Z"),
            ev(p, 2, "CANCELLED", "owner", "2026-09-13T10:01:00Z"),
        ]
        r = compile_ledger(p, trusted_as_of=self.ASOF)
        self.assertEqual(r["state"], "CANCELLED_EVIDENCE_ONLY")
        p["events"].append(ev(p, 3, "OFFER_OWNER_APPROVED", "owner", "2026-09-13T10:02:00Z"))
        with self.assertRaises(LedgerError):
            compile_ledger(p, trusted_as_of=self.ASOF)

    def test_duplicate_identical_is_idempotent(self):
        p = full_payload()
        p["events"].append(copy.deepcopy(p["events"][-1]))
        r = compile_ledger(p, trusted_as_of=self.ASOF)
        self.assertEqual(r["unique_event_count"], 9)
        self.assertEqual(r["input_event_count"], 10)

    def test_conflicting_duplicate_fails(self):
        p = full_payload()
        dup = copy.deepcopy(p["events"][-1])
        dup["evidence_sha256"] = "f" * 64
        p["events"].append(dup)
        with self.assertRaises(LedgerError):
            compile_ledger(p, trusted_as_of=self.ASOF)

    def test_cross_deal_replay_fails(self):
        p = full_payload()
        p["buyer_ref_sha256"] = "9" * 64
        with self.assertRaises(LedgerError):
            compile_ledger(p, trusted_as_of=self.ASOF)

    def test_wrong_authority_fails(self):
        p = full_payload()
        p["events"][3]["authority"] = "owner"
        with self.assertRaises(LedgerError):
            compile_ledger(p, trusted_as_of=self.ASOF)

    def test_stage_skip_fails(self):
        p = base()
        p["events"] = [ev(p, 1, "OFFER_SENT", "transport", "2026-09-13T10:00:00Z")]
        with self.assertRaises(LedgerError):
            compile_ledger(p, trusted_as_of=self.ASOF)

    def test_repeat_stage_fails(self):
        p = base()
        e = ev(p, 1, "OPPORTUNITY_QUALIFIED", "owner", "2026-09-13T10:00:00Z")
        e2 = copy.deepcopy(e)
        e2["event_id"] = "e02"
        e2["evidence_sha256"] = "2" * 64
        p["events"] = [e, e2]
        with self.assertRaises(LedgerError):
            compile_ledger(p, trusted_as_of=self.ASOF)

    def test_future_event_fails(self):
        p = full_payload()
        with self.assertRaises(LedgerError):
            compile_ledger(p, trusted_as_of="2026-09-13T10:07:59Z")

    def test_out_of_order_time_fails(self):
        p = full_payload()
        p["events"][4]["occurred_at"] = "2026-09-13T09:00:00Z"
        with self.assertRaises(LedgerError):
            compile_ledger(p, trusted_as_of=self.ASOF)

    def test_offer_send_after_expiry_fails(self):
        p = full_payload()
        p["offer_expires_at"] = "2026-09-13T10:01:30Z"
        s = subject_commitment(p)
        for e in p["events"]:
            e["subject_sha256"] = s
        with self.assertRaisesRegex(LedgerError, "OFFER_SENT occurred after offer expiry"):
            compile_ledger(p, trusted_as_of=self.ASOF)

    def test_buyer_acceptance_after_expiry_fails(self):
        p = full_payload()
        p["offer_expires_at"] = "2026-09-13T10:02:30Z"
        s = subject_commitment(p)
        for e in p["events"]:
            e["subject_sha256"] = s
        with self.assertRaisesRegex(LedgerError, "BUYER_ACCEPTED occurred after offer expiry"):
            compile_ledger(p, trusted_as_of=self.ASOF)

    def test_funding_below_contract_fails(self):
        p = full_payload()
        p["events"][4]["amount_minor"] = 249999
        with self.assertRaises(LedgerError):
            compile_ledger(p, trusted_as_of=self.ASOF)

    def test_wrong_currency_fails(self):
        p = full_payload()
        p["events"][7]["currency"] = "EUR"
        with self.assertRaises(LedgerError):
            compile_ledger(p, trusted_as_of=self.ASOF)

    def test_bool_money_fails(self):
        p = full_payload()
        p["events"][7]["amount_minor"] = True
        with self.assertRaises(LedgerError):
            compile_ledger(p, trusted_as_of=self.ASOF)

    def test_float_money_fails(self):
        p = full_payload()
        p["events"][7]["amount_minor"] = 250000.0
        with self.assertRaises(LedgerError):
            compile_ledger(p, trusted_as_of=self.ASOF)

    def test_payment_before_fulfillment_fails(self):
        p = full_payload()
        del p["events"][6]
        with self.assertRaises(LedgerError):
            compile_ledger(p, trusted_as_of=self.ASOF)

    def test_overpayment_fails(self):
        p = full_payload()
        p["events"].insert(8, ev(p, 10, "PAYMENT_SETTLED", "payment", "2026-09-13T10:07:30Z", amount=1, currency="USD"))
        with self.assertRaises(LedgerError):
            compile_ledger(p, trusted_as_of=self.ASOF)

    def test_recognition_over_net_cash_fails(self):
        p = full_payload()
        p["events"] = p["events"][:8]
        p["events"].append(ev(p, 9, "REVENUE_RECOGNIZED", "finance", "2026-09-13T10:08:00Z", amount=250001, currency="USD"))
        with self.assertRaises(LedgerError):
            compile_ledger(p, trusted_as_of=self.ASOF)

    def test_refund_wrong_reference_fails(self):
        p = full_payload()
        p["events"].append(ev(p, 10, "REFUND_SETTLED", "payment", "2026-09-13T10:09:00Z", amount=1, currency="USD", reversal="e07"))
        with self.assertRaises(LedgerError):
            compile_ledger(p, trusted_as_of=self.ASOF)

    def test_refund_over_payment_fails(self):
        p = full_payload()
        p["events"].append(ev(p, 10, "REFUND_SETTLED", "payment", "2026-09-13T10:09:00Z", amount=250001, currency="USD", reversal="e08"))
        with self.assertRaises(LedgerError):
            compile_ledger(p, trusted_as_of=self.ASOF)

    def test_reversal_without_refund_fails(self):
        p = full_payload()
        p["events"].append(ev(p, 10, "REVENUE_REVERSED", "finance", "2026-09-13T10:09:00Z", amount=1, currency="USD", reversal="e08"))
        with self.assertRaises(LedgerError):
            compile_ledger(p, trusted_as_of=self.ASOF)

    def test_reversal_over_refund_fails(self):
        p = full_payload()
        p["events"] += [
            ev(p, 10, "REFUND_SETTLED", "payment", "2026-09-13T10:09:00Z", amount=100, currency="USD", reversal="e08"),
            ev(p, 11, "REVENUE_REVERSED", "finance", "2026-09-13T10:10:00Z", amount=101, currency="USD", reversal="e10"),
        ]
        with self.assertRaises(LedgerError):
            compile_ledger(p, trusted_as_of=self.ASOF)

    def test_unknown_root_field_fails(self):
        p = full_payload()
        p["send_authorized"] = True
        with self.assertRaises(LedgerError):
            compile_ledger(p, trusted_as_of=self.ASOF)

    def test_unknown_event_field_fails(self):
        p = full_payload()
        p["events"][0]["approved"] = True
        with self.assertRaises(LedgerError):
            compile_ledger(p, trusted_as_of=self.ASOF)

    def test_duplicate_json_key_fails(self):
        with self.assertRaises(LedgerError):
            load_json_strict('{"a":1,"a":2}')

    def test_nonfinite_json_fails(self):
        with self.assertRaises(LedgerError):
            load_json_strict('{"a":NaN}')

    def test_bad_digest_fails(self):
        p = full_payload()
        p["offer_sha256"] = "ABC"
        with self.assertRaises(LedgerError):
            compile_ledger(p, trusted_as_of=self.ASOF)

    def test_bad_currency_fails(self):
        p = full_payload()
        p["currency"] = "usd"
        with self.assertRaises(LedgerError):
            compile_ledger(p, trusted_as_of=self.ASOF)

    def test_bool_contract_amount_fails(self):
        p = full_payload()
        p["contract_amount_minor"] = True
        with self.assertRaises(LedgerError):
            compile_ledger(p, trusted_as_of=self.ASOF)

    def test_tampered_receipt_fails_verification(self):
        p = full_payload()
        r = compile_ledger(p, trusted_as_of=self.ASOF)
        r["net_cash_evidenced_minor"] = 1
        self.assertFalse(verify_receipt(p, r, trusted_as_of=self.ASOF))

    def test_wrong_asof_fails_verification(self):
        p = full_payload()
        r = compile_ledger(p, trusted_as_of=self.ASOF)
        self.assertFalse(verify_receipt(p, r, trusted_as_of="2026-09-13T12:00:00Z"))

    def test_moneyless_event_cannot_smuggle_amount(self):
        p = full_payload()
        p["events"][0]["amount_minor"] = 1
        p["events"][0]["currency"] = "USD"
        with self.assertRaises(LedgerError):
            compile_ledger(p, trusted_as_of=self.ASOF)

    def test_refund_cannot_smuggle_other_currency(self):
        p = full_payload()
        p["events"].append(ev(p, 10, "REFUND_SETTLED", "payment", "2026-09-13T10:09:00Z", amount=1, currency="EUR", reversal="e08"))
        with self.assertRaises(LedgerError):
            compile_ledger(p, trusted_as_of=self.ASOF)


if __name__ == "__main__":
    unittest.main()
