"""Focused regression cases for claim, merge, award and cash boundaries."""
import unittest

from audit import audit

TIME = "2026-10-08T06:00:00Z"
PR = "https://github.com/example-org/test-project/pull/42"


def ev(kind, status, url="https://example.test/marketplace/claim", **kw):
    return dict(source_kind=kind, status=status, observed_at=TIME, source_url=url, **kw)


def record(id="BountyHub2994", pr=PR):
    return {
        "id": id, "pr_url": pr, "advertised_usd": 4999,
        "claim": ev("marketplace", "registered", pr_url=pr),
        "merge": ev("github", "open", "https://github.com/example-org/test-project/pull/42", pr_url=pr),
        "award": ev("marketplace", "unknown"),
        "payment_setup": ev("marketplace", "unverified"),
        "payment": ev("processor", "none", "https://example.test/processor/"),
    }


def report(*rows):
    return audit({"snapshot_at": TIME, "records": list(rows)})


class CashTruth(unittest.TestCase):
    def test_green_platform_but_payment_setup_false_is_not_paid(self):
        rec = report(record())["records"][0]
        self.assertEqual(rec["state"], "CLAIM_REGISTERED_NOT_MERGED")
        self.assertFalse(rec["payment_setup_verified"])
        self.assertFalse(rec["cash_receipt_recorded"])
        self.assertIn("payment_setup_not_verified", rec["warnings"])

    def test_merged_mova_unregistered_is_not_settled(self):
        r = record(id="Mova1190")
        r["advertised_usd"] = 1190
        r["merge"] = ev("github", "merged", "https://github.com/example-org/test-project/pull/42", pr_url=PR)
        r["claim"] = ev("marketplace", "unknown")
        out = report(r)
        self.assertEqual(out["records"][0]["next_action"], "request_eligibility_decision")
        self.assertEqual(out["cash_receipts_by_currency"], {})
        self.assertEqual(out["advertised_usd_not_receivables"], "1190")

    def test_merged_registered_marktext_award_outstanding(self):
        r = record(id="MarkText375")
        r["claim"] = ev("marketplace", "registered", pr_url=PR)
        r["merge"] = ev("github", "merged", "https://github.com/example-org/test-project/pull/42", pr_url=PR)
        result = report(r)["records"][0]
        self.assertEqual(result["state"], "MERGED_REGISTERED_NO_AWARD")
        self.assertEqual(result["next_action"], "request_award_decision")

    def test_unbacked_receipt_and_non_cash_credits_do_not_count(self):
        r = record()
        r["payment"] = ev("user", "received", amount=80, currency="RTC", receipt_id="internal-ledger")
        first = report(r)
        self.assertEqual(first["cash_receipts_by_currency"], {})
        self.assertIn("cash_receipt_evidence_insufficient", first["records"][0]["warnings"])

    def test_cash_receipt_has_authoritative_reference(self):
        r = record()
        r["payment"] = ev("processor", "received", "https://example.test/processor/receipt/fixture", amount="30.00", currency="USD", receipt_id="synthetic-receipt-fixture")
        result = report(r)
        self.assertEqual(result["records"][0]["state"], "CASH_RECEIPT_RECORDED")
        self.assertEqual(result["cash_receipts_by_currency"], {"USD": "30.00"})

    def test_claim_pr_mismatch_and_url_secret_fail_closed(self):
        r = record()
        r["claim"] = ev("marketplace", "registered", pr_url="https://github.com/other/repo/pull/8")
        r["payment"] = ev("processor", "received", "https://example.test/processor/payment?id=secret", amount=99, currency="USD", receipt_id="receipt")
        out = report(r)
        self.assertFalse(out["records"][0]["claim_verified"])
        self.assertEqual(out["cash_receipts_by_currency"], {})


if __name__ == "__main__":
    unittest.main()
