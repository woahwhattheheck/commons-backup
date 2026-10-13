from __future__ import annotations

import copy
import unittest

from revenue.proof_to_paid_work.core import (
    KitError, compile_kit, render_private_json, render_public_json, render_public_markdown,
    strict_json_loads, validate_no_real_claims,
)


def base_record():
    return {
        "schema": "proof-to-paid-work-input/v1",
        "work_id": "bounty-001",
        "sponsor_label": "Example Sponsor",
        "task": {"public_url": "https://example.invalid/task/1",
                 "advertised_award": {"amount_minor": 9000, "currency": "USD", "decimals": 2}},
        "work": {"public_url": "https://example.invalid/pull/2", "state": "MERGED",
                 "acceptance_evidence_refs": ["public:merge:2"]},
        "settlement": {"state": "UNPAID", "amount": None, "settled_at": None, "provider_evidence_refs": []},
        "private_evidence_refs": ["private:digest:abc"],
    }


class ProofToPaidWorkTests(unittest.TestCase):
    def test_unpaid_merged_work_yields_direct_advertised_request(self):
        req = compile_kit(base_record()).private["payment_request"]
        self.assertEqual(req["state"], "REQUEST_READY_INTERNAL_DRAFT")
        self.assertIn("$90.00 USD", req["markdown"])
        self.assertIn("https://example.invalid/pull/2", req["markdown"])
        self.assertNotIn("eligible", req["markdown"].lower())

    def test_settled_work_suppresses_payment_request(self):
        row = base_record()
        row["settlement"] = {"state": "SETTLED", "amount": {"amount_minor": 9000, "currency": "USD", "decimals": 2},
                             "settled_at": "2026-09-16T12:00:00Z", "provider_evidence_refs": ["provider:receipt:opaque"]}
        compiled = compile_kit(row)
        self.assertEqual(compiled.private["payment_request"]["state"], "HOLD_ALREADY_SETTLED")
        truth = compiled.private["financial_truth"]
        self.assertIsNone(truth["cash_usd_minor"])
        self.assertFalse(truth["booked_revenue"])
        self.assertFalse(truth["recognized_revenue"])

    def test_native_token_settlement_never_converts_to_usd(self):
        row = base_record()
        row["task"]["advertised_award"] = {"amount_minor": 25, "currency": "RTC", "decimals": 0}
        row["settlement"] = {"state": "SETTLED", "amount": {"amount_minor": 25, "currency": "RTC", "decimals": 0},
                             "settled_at": "2026-09-16T12:00:00+00:00", "provider_evidence_refs": ["provider:token-settlement:opaque"]}
        compiled = compile_kit(row)
        truth = compiled.private["financial_truth"]
        self.assertEqual(truth["native_currency_only"], "25 RTC")
        self.assertEqual(truth["conversion_state"], "NO_USD_CONVERSION")
        self.assertIsNone(truth["usd_conversion"])
        self.assertIsNone(truth["cash_usd_minor"])
        public = render_public_json(compiled)
        self.assertNotIn("RTC", public)
        self.assertNotIn('"25"', public)

    def test_currency_conversion_is_refused(self):
        row = base_record()
        row["task"]["advertised_award"] = {"amount_minor": 25, "currency": "RTC", "decimals": 0}
        row["settlement"] = {"state": "SETTLED", "amount": {"amount_minor": 100, "currency": "USD", "decimals": 2},
                             "settled_at": "2026-09-16T12:00:00Z", "provider_evidence_refs": ["provider:receipt:opaque"]}
        with self.assertRaisesRegex(KitError, "refuses settlement currency"):
            compile_kit(row)

    def test_settled_requires_provider_reference(self):
        row = base_record()
        row["settlement"] = {"state": "SETTLED", "amount": {"amount_minor": 9000, "currency": "USD", "decimals": 2},
                             "settled_at": "2026-09-16T12:00:00Z", "provider_evidence_refs": []}
        with self.assertRaisesRegex(KitError, "requires provider evidence"):
            compile_kit(row)

    def test_accepted_requires_acceptance_reference(self):
        row = base_record(); row["work"]["state"] = "ACCEPTED"; row["work"]["acceptance_evidence_refs"] = []
        with self.assertRaisesRegex(KitError, "ACCEPTED requires"):
            compile_kit(row)

    def test_open_work_cannot_request_payment(self):
        row = base_record(); row["work"]["state"] = "OPEN"; row["work"]["acceptance_evidence_refs"] = []
        self.assertEqual(compile_kit(row).private["payment_request"]["state"], "HOLD_WORK_NOT_ACCEPTED_OR_MERGED")

    def test_bool_is_not_integer(self):
        row = base_record(); row["task"]["advertised_award"]["amount_minor"] = True
        with self.assertRaisesRegex(KitError, "must be an integer"):
            compile_kit(row)

    def test_float_json_is_rejected(self):
        with self.assertRaisesRegex(KitError, "floats are not allowed"):
            strict_json_loads('{"x":1.5}')

    def test_duplicate_json_key_is_rejected(self):
        with self.assertRaisesRegex(KitError, "duplicate key"):
            strict_json_loads('{"x":1,"x":2}')

    def test_timezone_is_required_for_settlement(self):
        row = base_record()
        row["settlement"] = {"state": "SETTLED", "amount": {"amount_minor": 9000, "currency": "USD", "decimals": 2},
                             "settled_at": "2026-09-16T12:00:00", "provider_evidence_refs": ["provider:r"]}
        with self.assertRaisesRegex(KitError, "timezone"):
            compile_kit(row)

    def test_public_projection_redacts_real_record(self):
        row = base_record(); row["sponsor_label"] = "Private Sponsor"; row["private_evidence_refs"] = ["gmail:private-message-id"]
        public = render_public_json(compile_kit(row))
        for secret in ("Private Sponsor", "bounty-001", "https://example.invalid/task/1", "https://example.invalid/pull/2", "gmail:private-message-id", "$90.00"):
            self.assertNotIn(secret, public)
        self.assertIn("GENERIC_TEMPLATE_ONLY", public)

    def test_public_markdown_is_generic_and_hard_false(self):
        md = render_public_markdown(compile_kit(base_record()))
        self.assertIn("GENERIC TEMPLATE ONLY", md)
        self.assertIn("PROPOSED_NOT_ACCEPTED", md)
        self.assertNotIn("Example Sponsor", md)
        self.assertNotIn("example.invalid", md)
        self.assertIn("Do not ask whether you are eligible", md)

    def test_receipt_is_deterministic(self):
        a, b = compile_kit(base_record()), compile_kit(copy.deepcopy(base_record()))
        self.assertEqual(a.receipt_sha256, b.receipt_sha256)
        self.assertEqual(render_private_json(a), render_private_json(b))

    def test_changed_private_record_changes_receipt_but_not_public(self):
        a = compile_kit(base_record()); row = base_record(); row["work_id"] = "bounty-002"; b = compile_kit(row)
        self.assertNotEqual(a.receipt_sha256, b.receipt_sha256)
        self.assertEqual(render_public_json(a), render_public_json(b))

    def test_https_url_credentials_are_rejected(self):
        row = base_record(); row["task"]["public_url"] = "https://u:p@example.invalid/task/1"
        with self.assertRaisesRegex(KitError, "without credentials"):
            compile_kit(row)

    def test_fragments_are_rejected(self):
        row = base_record(); row["work"]["public_url"] = "https://example.invalid/pull/2#private"
        with self.assertRaisesRegex(KitError, "fragment"):
            compile_kit(row)

    def test_extra_keys_are_rejected(self):
        row = base_record(); row["claimed_revenue"] = 9000
        with self.assertRaisesRegex(KitError, "keys mismatch"):
            compile_kit(row)

    def test_unsupported_claim_validator(self):
        for phrase in ("We were paid yesterday.", "Cash received.", "Recognized revenue is $1.", "Buyer accepted.", "Converted to USD."):
            with self.subTest(phrase=phrase):
                with self.assertRaises(KitError):
                    validate_no_real_claims(phrase)

    def test_generic_claim_validator_accepts_truth_boundary(self):
        validate_no_real_claims("This is a generic template. A merge is not settlement and does not authorize a payment claim.")


if __name__ == "__main__":
    unittest.main()
