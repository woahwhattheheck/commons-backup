from __future__ import annotations

from copy import deepcopy
import unittest

from revenue.travelers_agent_toolcall_evidence.fixtures import acceptance_envelopes
from revenue.travelers_agent_toolcall_evidence.gate import (
    DECISION_SCOPE,
    EVALUATION_TIME_AUTHORITY,
    GateError,
    build_ledger,
    compile_batch,
    compile_one,
    daily_root_manifest,
    sha256_json,
    verify_batch,
    verify_root,
)


def _rewrite_receipt_digest(receipt: dict) -> None:
    body = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    receipt["receipt_sha256"] = sha256_json(body)


def _rewrite_entry_digest(entry: dict) -> None:
    body = {key: value for key, value in entry.items() if key != "entry_sha256"}
    entry["entry_sha256"] = sha256_json(body)


class DetachedReceiptScopeTest(unittest.TestCase):
    def test_receipt_binds_synthetic_replay_nonproduction_scope(self):
        receipt = compile_one(acceptance_envelopes()[0])
        self.assertEqual(receipt["decision_scope"], DECISION_SCOPE)
        self.assertEqual(receipt["evaluation_time_authority"], EVALUATION_TIME_AUTHORITY)
        self.assertFalse(receipt["current_execution_authority_claimed"])
        self.assertTrue(all(value is False for value in receipt["authority"].values()))

    def test_detached_scope_deletion_rejected_after_digest_rewrite(self):
        envelopes = acceptance_envelopes()[:4]
        receipts = compile_batch(envelopes)
        forged = deepcopy(receipts)
        forged[0].pop("decision_scope")
        _rewrite_receipt_digest(forged[0])
        self.assertFalse(verify_batch(envelopes, forged))

    def test_detached_scope_widening_rejected_after_digest_rewrite(self):
        envelopes = acceptance_envelopes()[:4]
        receipts = compile_batch(envelopes)
        forged = deepcopy(receipts)
        forged[0]["decision_scope"] = "PRODUCTION_EXECUTION_AUTHORIZED"
        forged[0]["current_execution_authority_claimed"] = True
        forged[0]["evaluation_time_authority"] = "CURRENT_TRUSTED_CLOCK"
        _rewrite_receipt_digest(forged[0])
        self.assertFalse(verify_batch(envelopes, forged))


class RootChainDependencyTest(unittest.TestCase):
    def setUp(self):
        self.receipts = compile_batch(acceptance_envelopes()[:8])
        self.ledger = build_ledger(self.receipts)

    def test_root_manifest_records_chain_verification(self):
        manifest = daily_root_manifest(self.ledger, "2026-09-17")
        self.assertEqual(manifest["schema"], "agent-toolcall-daily-root/v2")
        self.assertTrue(manifest["ledger_verified_before_root"])
        self.assertTrue(verify_root(manifest, self.ledger))

    def test_root_builder_rejects_invalid_chain_even_with_self_consistent_entry_digest(self):
        forged = deepcopy(self.ledger)
        forged[1]["previous_entry_sha256"] = "0" * 64
        _rewrite_entry_digest(forged[1])
        with self.assertRaises(GateError):
            daily_root_manifest(forged, "2026-09-17")

    def test_root_verifier_rejects_invalid_chain_even_if_manifest_is_rebuilt_from_entry_hashes(self):
        manifest = daily_root_manifest(self.ledger, "2026-09-17")
        forged_ledger = deepcopy(self.ledger)
        forged_ledger[1]["previous_entry_sha256"] = "0" * 64
        _rewrite_entry_digest(forged_ledger[1])
        self.assertFalse(verify_root(manifest, forged_ledger))


if __name__ == "__main__":
    unittest.main()
