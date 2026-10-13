from __future__ import annotations

from copy import deepcopy
import unittest

from revenue.travelers_agent_toolcall_evidence.bundle import (
    BUNDLE_SCHEMA,
    build_evidence_bundle,
    verify_evidence_bundle,
)
from revenue.travelers_agent_toolcall_evidence.fixtures import acceptance_envelopes
from revenue.travelers_agent_toolcall_evidence.gate import (
    build_ledger,
    daily_root_manifest,
    sha256_json,
)


def _rewrite_receipt_digest(receipt: dict) -> None:
    body = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    receipt["receipt_sha256"] = sha256_json(body)


def _rewrite_bundle(bundle: dict, envelopes: list[dict]) -> None:
    bundle["envelopes_sha256"] = sha256_json(envelopes)
    bundle["receipts_sha256"] = sha256_json(bundle["receipts"])
    bundle["ledger_sha256"] = sha256_json(bundle["ledger"])
    bundle["root_sha256"] = sha256_json(bundle["root"])
    body = {key: value for key, value in bundle.items() if key != "bundle_sha256"}
    bundle["bundle_sha256"] = sha256_json(body)


def _rebuild_structural_layers(bundle: dict, envelopes: list[dict]) -> None:
    bundle["ledger"] = build_ledger(bundle["receipts"])
    bundle["root"] = daily_root_manifest(bundle["ledger"], bundle["day"])
    _rewrite_bundle(bundle, envelopes)


class EvidenceBundleTest(unittest.TestCase):
    def setUp(self):
        self.envelopes = acceptance_envelopes()[:24]
        self.bundle = build_evidence_bundle(self.envelopes, "2026-09-17")

    def test_exact_bundle_verifies(self):
        self.assertEqual(self.bundle["schema"], BUNDLE_SCHEMA)
        self.assertTrue(verify_evidence_bundle(self.envelopes, self.bundle))

    def test_semantically_forged_decision_fails_even_after_every_hash_layer_is_rebuilt(self):
        forged = deepcopy(self.bundle)
        forged["receipts"][0]["decision"] = "HOLD"
        forged["receipts"][0]["reasons"] = ["FORGED_REASON"]
        _rewrite_receipt_digest(forged["receipts"][0])
        _rebuild_structural_layers(forged, self.envelopes)
        self.assertFalse(verify_evidence_bundle(self.envelopes, forged))

    def test_scope_widening_fails_even_after_every_hash_layer_is_rebuilt(self):
        forged = deepcopy(self.bundle)
        receipt = forged["receipts"][0]
        receipt["decision_scope"] = "PRODUCTION_EXECUTION_AUTHORIZED"
        receipt["evaluation_time_authority"] = "CURRENT_TRUSTED_CLOCK"
        receipt["current_execution_authority_claimed"] = True
        _rewrite_receipt_digest(receipt)
        _rebuild_structural_layers(forged, self.envelopes)
        self.assertFalse(verify_evidence_bundle(self.envelopes, forged))

    def test_valid_receipts_with_forged_chain_fail_even_after_bundle_digest_rewrite(self):
        forged = deepcopy(self.bundle)
        forged["ledger"][1]["previous_entry_sha256"] = "0" * 64
        entry = forged["ledger"][1]
        body = {key: value for key, value in entry.items() if key != "entry_sha256"}
        entry["entry_sha256"] = sha256_json(body)
        _rewrite_bundle(forged, self.envelopes)
        self.assertFalse(verify_evidence_bundle(self.envelopes, forged))

    def test_root_swap_fails_even_after_bundle_digest_rewrite(self):
        forged = deepcopy(self.bundle)
        forged["root"]["merkle_root_sha256"] = "0" * 64
        root_body = {key: value for key, value in forged["root"].items() if key != "manifest_sha256"}
        forged["root"]["manifest_sha256"] = sha256_json(root_body)
        _rewrite_bundle(forged, self.envelopes)
        self.assertFalse(verify_evidence_bundle(self.envelopes, forged))

    def test_envelope_change_breaks_existing_bundle(self):
        changed = deepcopy(self.envelopes)
        changed[0]["request"]["target_resource"] = "policy/P9999"
        self.assertFalse(verify_evidence_bundle(changed, self.bundle))

    def test_bundle_digest_tamper_rejected(self):
        forged = deepcopy(self.bundle)
        forged["bundle_sha256"] = "0" * 64
        self.assertFalse(verify_evidence_bundle(self.envelopes, forged))


if __name__ == "__main__":
    unittest.main()
