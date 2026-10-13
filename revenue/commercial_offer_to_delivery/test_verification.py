from __future__ import annotations

import copy
import unittest

from . import BridgeError, create_operator_verification, load_json_strict, verify_operator_verification
from .fixtures import (
    NOW, OWNER_KEY, VERIFY_KEY, ZERO, catalog, contract, contract_verifier,
    scope_acceptance, service_window, verification,
)


class VerificationTests(unittest.TestCase):
    def bad(self, fn, *args, **kwargs):
        with self.assertRaises(BridgeError):
            fn(*args, **kwargs)

    def verify_receipt(self, c, receipt, cat=None):
        return verify_operator_verification(
            c, receipt, OWNER_KEY, VERIFY_KEY, catalog=cat or catalog(), trusted_now=NOW,
            contract_verifier=contract_verifier,
        )

    def test_happy_verification(self):
        c = contract(); receipt = verification(c)
        verified, readback = self.verify_receipt(c, receipt)
        self.assertEqual(verified["offer_sha256"], c["offer_sha256"])
        self.assertEqual(readback, receipt)
        self.assertEqual(receipt["schema_version"], 2)
        self.assertEqual(receipt["scope_terms_acceptance"]["terms_digest"], scope_acceptance(c)["terms_digest"])

    def test_exact_scope_terms_digest_required(self):
        c = contract(); accepted = scope_acceptance(c); accepted["terms_digest"] = ZERO
        self.bad(verification, c, accepted)

    def test_service_window_drift_after_buyer_acceptance_fails(self):
        c = contract(); accepted = scope_acceptance(c); window = service_window(); window["end"] = "2026-09-19T21:00:00Z"
        self.bad(verification, c, accepted, window)

    def test_catalog_price_drift_after_buyer_acceptance_fails(self):
        c = contract(); accepted = scope_acceptance(c); self.bad(verification, c, accepted, cat=catalog("14999.99"))

    def test_scope_acceptance_cannot_predate_offer(self):
        c = contract(); accepted = scope_acceptance(c, accepted_at="2026-09-13T10:02:30Z")
        self.bad(verification, c, accepted)

    def test_service_cannot_start_before_exact_terms_acceptance(self):
        c = contract(); window = service_window(); window["start"] = "2026-09-13T10:04:00Z"; window["end"] = "2026-09-14T10:00:00Z"
        accepted = scope_acceptance(c, window=window, accepted_at="2026-09-13T10:05:00Z")
        self.bad(verification, c, accepted, window)

    def test_service_window_must_advance(self):
        c = contract(); window = service_window(); window["end"] = window["start"]
        self.bad(scope_acceptance, c, catalog(), window)

    def test_scope_acceptance_not_future(self):
        c = contract(); accepted = scope_acceptance(c, accepted_at="2026-09-13T10:11:00Z")
        self.bad(verification, c, accepted)

    def test_operator_verification_time_bounds(self):
        for stamp in ("2026-09-13T10:04:30Z", "2026-09-13T10:11:00Z"):
            self.bad(verification, verified_at=stamp)

    def test_exact_money_types(self):
        for value in (True, 1500000.0):
            c = contract(); c["offer"]["total_amount_minor"] = value
            self.bad(verification, c)

    def test_only_usd(self):
        c = contract(); c["offer"]["currency"] = "EUR"; self.bad(verification, c)

    def test_requires_captured_state(self):
        c = contract(); c["state"] = "READY_FOR_EXPLICIT_SEND"; self.bad(verification, c)

    def test_rejects_authority_escalation(self):
        for field in ("fulfillment_authorized", "payment_collected", "revenue_recognized", "buyer_acceptance_verified"):
            c = contract(); c["authority"][field] = True; self.bad(verification, c)

    def test_offer_acceptance_binding(self):
        c = contract(); c["buyer_acceptance"]["offer_sha256"] = ZERO; self.bad(verification, c)

    def test_offer_buyer_binding(self):
        c = contract(); c["buyer_acceptance"]["buyer_ref"] = "otherbuyer_001"; self.bad(verification, c)

    def test_offer_acceptance_time_bounds(self):
        for stamp in ("2026-09-13T10:01:00Z", "2026-09-13T10:11:00Z"):
            c = contract(); c["buyer_acceptance"]["accepted_at"] = stamp; self.bad(verification, c)

    def test_public_ref_allowlist(self):
        self.bad(verification, public_ref="mailto:someone.invalid")

    def test_wrong_owner_key(self):
        c = contract(); cat = catalog(); window = service_window(); accepted = scope_acceptance(c, cat, window)
        self.bad(
            create_operator_verification, c, b"X" * 32, VERIFY_KEY,
            verifier_id="operator-001", key_id="acceptance-key-v2", verified_at="2026-09-13T10:06:00Z",
            public_ref="p/accepted-scope-terms.md", catalog=cat, service_window=window,
            scope_terms_acceptance=accepted, trusted_now=NOW, contract_verifier=contract_verifier,
        )

    def test_wrong_verification_key(self):
        c = contract(); receipt = verification(c)
        with self.assertRaises(BridgeError):
            verify_operator_verification(
                c, receipt, OWNER_KEY, b"Y" * 32, catalog=catalog(), trusted_now=NOW,
                contract_verifier=contract_verifier,
            )

    def test_offer_evidence_binding_tamper(self):
        c = contract(); receipt = verification(c); receipt["offer_acceptance_evidence_sha256"] = ZERO
        self.bad(self.verify_receipt, c, receipt)

    def test_exact_scope_digest_tamper_breaks_hmac(self):
        c = contract(); receipt = verification(c); receipt["scope_terms_acceptance"]["terms_digest"] = ZERO
        self.bad(self.verify_receipt, c, receipt)

    def test_service_window_tamper_breaks_terms_binding(self):
        c = contract(); receipt = verification(c); receipt["service_window"]["end"] = "2026-09-19T21:00:00Z"
        self.bad(self.verify_receipt, c, receipt)

    def test_unknown_verification_field(self):
        c = contract(); receipt = verification(c); receipt["surprise"] = True
        self.bad(self.verify_receipt, c, receipt)

    def test_legacy_v1_receipt_fails_closed(self):
        c = contract(); receipt = verification(c); receipt["schema_version"] = 1
        self.bad(self.verify_receipt, c, receipt)

    def test_empty_exclusions_fail_closed(self):
        c = contract(); c["offer"]["exclusions"] = []; self.bad(verification, c)

    def test_strict_json(self):
        for raw in ('{"a":1,"a":2}', '{"a":1.5}', '{"a":NaN}'):
            self.bad(load_json_strict, raw)
        self.assertEqual(load_json_strict('{"a":1,"b":"x"}'), {"a": 1, "b": "x"})


if __name__ == "__main__":
    unittest.main()
