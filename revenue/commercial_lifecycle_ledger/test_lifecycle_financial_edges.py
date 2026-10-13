import unittest

from revenue.commercial_lifecycle_ledger.lifecycle import LedgerError, compile_ledger
from revenue.commercial_lifecycle_ledger.test_lifecycle import ev, full_payload


class FinancialEdgeTests(unittest.TestCase):
    ASOF = "2026-09-13T11:00:00Z"

    def test_funding_above_contract_fails(self):
        p = full_payload()
        p["events"][4]["amount_minor"] = 250001
        with self.assertRaises(LedgerError):
            compile_ledger(p, trusted_as_of=self.ASOF)

    def test_prepaid_cash_after_funding_is_supported(self):
        p = full_payload()
        p["events"] = p["events"][:5]
        p["events"].append(
            ev(p, 8, "PAYMENT_SETTLED", "payment", "2026-09-13T10:04:30Z", amount=250000, currency="USD")
        )
        r = compile_ledger(p, trusted_as_of=self.ASOF)
        self.assertEqual(r["state"], "PREPAID_CASH_EVIDENCE_ONLY")
        self.assertEqual(r["net_cash_evidenced_minor"], 250000)
        self.assertEqual(r["reported_recognized_amount_minor"], 0)

    def test_payment_before_funding_fails(self):
        p = full_payload()
        p["events"] = p["events"][:4]
        p["events"].append(
            ev(p, 8, "PAYMENT_SETTLED", "payment", "2026-09-13T10:03:30Z", amount=250000, currency="USD")
        )
        with self.assertRaises(LedgerError):
            compile_ledger(p, trusted_as_of=self.ASOF)

    def test_refund_can_precede_finance_reversal(self):
        p = full_payload()
        p["events"].append(
            ev(p, 10, "REFUND_SETTLED", "payment", "2026-09-13T10:09:00Z", amount=50000, currency="USD", reversal="e08")
        )
        r = compile_ledger(p, trusted_as_of=self.ASOF)
        self.assertEqual(r["state"], "RECOGNITION_REVERSAL_REQUIRED_EVIDENCE_ONLY")
        self.assertEqual(r["recognition_reversal_pending_minor"], 50000)
        self.assertEqual(r["net_cash_evidenced_minor"], 200000)
        self.assertEqual(r["net_recognized_evidenced_minor"], 250000)


if __name__ == "__main__":
    unittest.main()
