import copy
import unittest

from revenue.commercial_lifecycle_ledger.lifecycle import LedgerError, compile_ledger
from revenue.commercial_lifecycle_ledger.test_lifecycle import ev, full_payload


class EvidenceIdentityTests(unittest.TestCase):
    ASOF = "2026-09-13T11:00:00Z"

    def test_same_payment_proof_cannot_mint_two_installments(self):
        p = full_payload()
        p["events"] = p["events"][:7]
        shared = "a" * 64
        p["events"] += [
            ev(p, 8, "PAYMENT_SETTLED", "payment", "2026-09-13T10:07:00Z", amount=125000, currency="USD", evidence=shared),
            ev(p, 9, "PAYMENT_SETTLED", "payment", "2026-09-13T10:08:00Z", amount=125000, currency="USD", evidence=shared),
        ]
        with self.assertRaisesRegex(LedgerError, "evidence_sha256 reused by distinct event_id"):
            compile_ledger(p, trusted_as_of=self.ASOF)

    def test_buyer_proof_cannot_cross_acceptance_and_fulfillment(self):
        p = full_payload()
        p["events"][6]["evidence_sha256"] = p["events"][3]["evidence_sha256"]
        with self.assertRaisesRegex(LedgerError, "evidence_sha256 reused by distinct event_id"):
            compile_ledger(p, trusted_as_of=self.ASOF)

    def test_finance_proof_cannot_be_reused_as_refund_proof(self):
        p = full_payload()
        p["events"].append(
            ev(
                p,
                10,
                "REFUND_SETTLED",
                "payment",
                "2026-09-13T10:09:00Z",
                amount=50000,
                currency="USD",
                reversal="e08",
                evidence=p["events"][8]["evidence_sha256"],
            )
        )
        with self.assertRaisesRegex(LedgerError, "evidence_sha256 reused by distinct event_id"):
            compile_ledger(p, trusted_as_of=self.ASOF)

    def test_delayed_exact_retry_keeps_same_proof_idempotent(self):
        p = full_payload()
        p["events"].append(copy.deepcopy(p["events"][3]))
        r = compile_ledger(p, trusted_as_of=self.ASOF)
        self.assertEqual(r["unique_event_count"], 9)
        self.assertEqual(r["input_event_count"], 10)
        self.assertEqual(r["net_cash_evidenced_minor"], 250000)

    def test_distinct_payment_proofs_still_support_installments(self):
        p = full_payload()
        p["events"] = p["events"][:7]
        p["events"] += [
            ev(p, 8, "PAYMENT_SETTLED", "payment", "2026-09-13T10:07:00Z", amount=125000, currency="USD", evidence="a" * 64),
            ev(p, 9, "PAYMENT_SETTLED", "payment", "2026-09-13T10:08:00Z", amount=125000, currency="USD", evidence="b" * 64),
        ]
        r = compile_ledger(p, trusted_as_of=self.ASOF)
        self.assertEqual(r["state"], "PAYMENT_SETTLED_EVIDENCE_ONLY")
        self.assertEqual(r["settled_amount_minor"], 250000)


if __name__ == "__main__":
    unittest.main()
