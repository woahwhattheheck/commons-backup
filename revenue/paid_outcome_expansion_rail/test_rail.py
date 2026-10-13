from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from revenue.paid_outcome_expansion_rail.acceptance import AS_OF, _ts, make_record, run_acceptance
from revenue.paid_outcome_expansion_rail.rail import catalog_row_digest, digest_json, evaluate, verify_receipt


class RailTests(unittest.TestCase):
    def setUp(self):
        self.record = make_record(1)

    def decision(self, record=None):
        return evaluate(self.record if record is None else record)

    def test_expansion_ready(self):
        r = self.decision()
        self.assertEqual(r["decision"], "EXPANSION_READY")
        self.assertEqual(r["hold_codes"], [])
        self.assertTrue(verify_receipt(r))
        self.assertEqual(r["event_log"], {"unique": 2, "exact_replays": 1, "conflicts": 0})
        self.assertTrue(all(v is False for v in r["authority"].values()))

    def test_renewal_ready(self):
        r = evaluate(make_record(2, "RENEWAL_REQUEST"))
        self.assertEqual(r["decision"], "RENEWAL_READY")
        self.assertEqual(r["selected_catalog"][0]["kind"], "RENEWAL")

    def test_pending_settlement_holds(self):
        self.record["settlement"]["status"] = "PENDING"
        self.assertIn("SETTLEMENT_NOT_FINAL", self.decision()["hold_codes"])

    def test_refund_holds(self):
        self.record["settlement"]["refunded_cents"] = 1
        self.assertIn("SETTLEMENT_REFUNDED", self.decision()["hold_codes"])

    def test_dispute_holds(self):
        self.record["settlement"]["disputed_cents"] = 1
        self.assertIn("SETTLEMENT_DISPUTED", self.decision()["hold_codes"])

    def test_short_settlement_holds(self):
        self.record["settlement"]["net_cents"] = 99
        self.assertIn("SETTLEMENT_AMOUNT_SHORT", self.decision()["hold_codes"])

    def test_currency_mismatch_holds(self):
        self.record["settlement"]["currency"] = "EUR"
        self.assertIn("SETTLEMENT_CURRENCY_MISMATCH", self.decision()["hold_codes"])

    def test_offer_identity_mismatch_holds(self):
        self.record["settlement"]["offer_version"] = "v0"
        self.assertIn("SETTLEMENT_OFFER_MISMATCH", self.decision()["hold_codes"])

    def test_acceptance_must_be_human(self):
        self.record["delivery_acceptance"]["accepted_by_class"] = "SYSTEM"
        self.assertIn("ACCEPTANCE_NOT_BUYER_HUMAN", self.decision()["hold_codes"])

    def test_acceptance_scope_mismatch_holds(self):
        self.record["delivery_acceptance"]["scope_digest"] = digest_json({"wrong": 1})
        self.assertIn("ACCEPTANCE_SCOPE_MISMATCH", self.decision()["hold_codes"])

    def test_signal_must_be_buyer_authored(self):
        self.record["buyer_signal"]["source_class"] = "SELLER_INFERRED"
        self.assertIn("BUYER_SIGNAL_NOT_BUYER_AUTHORED", self.decision()["hold_codes"])

    def test_stale_signal_holds(self):
        self.record["buyer_signal"]["observed_at"] = _ts(AS_OF - timedelta(days=46))
        self.assertIn("BUYER_SIGNAL_STALE", self.decision()["hold_codes"])

    def test_signal_before_acceptance_holds(self):
        self.record["buyer_signal"]["observed_at"] = _ts(AS_OF - timedelta(days=21))
        self.assertIn("BUYER_SIGNAL_PREDATES_ACCEPTANCE", self.decision()["hold_codes"])

    def test_owner_approval_required(self):
        self.record["owner_approval"]["approved_catalog_rows"] = []
        self.assertIn("CATALOG_NOT_OWNER_APPROVED", self.decision()["hold_codes"])

    def test_cross_account_relabel_holds_all_authority_evidence(self):
        self.record["account_id"] = "acct-other"
        codes = self.decision()["hold_codes"]
        self.assertIn("SETTLEMENT_ACCOUNT_MISMATCH", codes)
        self.assertIn("ACCEPTANCE_ACCOUNT_MISMATCH", codes)
        self.assertIn("BUYER_SIGNAL_ACCOUNT_MISMATCH", codes)
        self.assertIn("OWNER_APPROVAL_ACCOUNT_MISMATCH", codes)

    def test_settlement_cross_account_splice_holds(self):
        self.record["settlement"]["account_id"] = "acct-other"
        self.assertIn("SETTLEMENT_ACCOUNT_MISMATCH", self.decision()["hold_codes"])

    def test_acceptance_cross_account_splice_holds(self):
        self.record["delivery_acceptance"]["account_id"] = "acct-other"
        self.assertIn("ACCEPTANCE_ACCOUNT_MISMATCH", self.decision()["hold_codes"])

    def test_buyer_signal_cross_account_splice_holds(self):
        self.record["buyer_signal"]["account_id"] = "acct-other"
        self.assertIn("BUYER_SIGNAL_ACCOUNT_MISMATCH", self.decision()["hold_codes"])

    def test_owner_approval_cross_account_splice_holds(self):
        self.record["owner_approval"]["account_id"] = "acct-other"
        self.assertIn("OWNER_APPROVAL_ACCOUNT_MISMATCH", self.decision()["hold_codes"])

    def test_missing_catalog_holds(self):
        self.record["catalog"] = []
        self.assertIn("CATALOG_ITEM_MISSING", self.decision()["hold_codes"])

    def test_catalog_version_change_invalidates_old_approval(self):
        self.record["catalog"][0]["version"] = "v2"
        self.assertIn("CATALOG_APPROVAL_IDENTITY_MISMATCH", self.decision()["hold_codes"])

    def test_catalog_price_change_invalidates_old_approval(self):
        self.record["catalog"][0]["price_cents"] += 1
        self.assertIn("CATALOG_APPROVAL_IDENTITY_MISMATCH", self.decision()["hold_codes"])

    def test_catalog_scope_change_invalidates_old_approval(self):
        self.record["catalog"][0]["scope_digest"] = digest_json({"revision": "different-scope"})
        self.assertIn("CATALOG_APPROVAL_IDENTITY_MISMATCH", self.decision()["hold_codes"])

    def test_exact_revision_reapproval_restores_identity(self):
        self.record["catalog"][0]["version"] = "v2"
        self.record["catalog"][0]["price_cents"] += 2500
        binding = self.record["owner_approval"]["approved_catalog_rows"][0]
        binding["version"] = "v2"
        binding["row_digest"] = catalog_row_digest(self.record["catalog"][0])
        r = self.decision()
        self.assertEqual(r["decision"], "EXPANSION_READY")
        self.assertEqual(r["selected_catalog"][0]["version"], "v2")
        self.assertEqual(r["selected_catalog"][0]["row_digest"], binding["row_digest"])

    def test_duplicate_owner_approval_entry_holds(self):
        self.record["owner_approval"]["approved_catalog_rows"].append(
            copy.deepcopy(self.record["owner_approval"]["approved_catalog_rows"][0])
        )
        self.assertIn("OWNER_APPROVAL_ENTRY_DUPLICATE", self.decision()["hold_codes"])

    def test_conflicting_owner_approval_entry_holds(self):
        conflict = copy.deepcopy(self.record["owner_approval"]["approved_catalog_rows"][0])
        conflict["version"] = "v0"
        self.record["owner_approval"]["approved_catalog_rows"].append(conflict)
        self.assertIn("OWNER_APPROVAL_ENTRY_CONFLICT", self.decision()["hold_codes"])

    def test_buyer_signal_must_follow_revision_activation(self):
        self.record["catalog"][0]["active_from"] = _ts(AS_OF - timedelta(days=5))
        binding = self.record["owner_approval"]["approved_catalog_rows"][0]
        binding["row_digest"] = catalog_row_digest(self.record["catalog"][0])
        codes = self.decision()["hold_codes"]
        self.assertIn("BUYER_SIGNAL_PREDATES_CATALOG_REVISION", codes)
        self.assertIn("OWNER_APPROVAL_PREDATES_CATALOG_REVISION", codes)

    def test_owner_approval_must_follow_buyer_signal(self):
        self.record["owner_approval"]["approved_at"] = _ts(AS_OF - timedelta(days=11))
        self.assertIn("OWNER_APPROVAL_PREDATES_BUYER_SIGNAL", self.decision()["hold_codes"])

    def test_catalog_kind_matches_signal(self):
        self.record["catalog"][0]["kind"] = "RENEWAL"
        self.assertIn("CATALOG_SIGNAL_KIND_MISMATCH", self.decision()["hold_codes"])

    def test_catalog_currency_matches_offer(self):
        self.record["catalog"][0]["currency"] = "EUR"
        self.assertIn("CATALOG_CURRENCY_MISMATCH", self.decision()["hold_codes"])

    def test_catalog_must_be_active(self):
        self.record["catalog"][0]["active_until"] = _ts(AS_OF - timedelta(seconds=1))
        self.assertIn("CATALOG_NOT_ACTIVE", self.decision()["hold_codes"])

    def test_causal_claim_forbidden(self):
        self.record["outcomes"][0]["causal_claim"] = True
        self.assertIn("CAUSAL_OUTCOME_CLAIM_FORBIDDEN", self.decision()["hold_codes"])

    def test_claim_class_must_be_descriptive(self):
        self.record["outcomes"][0]["claim_class"] = "CAUSAL"
        self.assertIn("CAUSAL_OUTCOME_CLAIM_FORBIDDEN", self.decision()["hold_codes"])

    def test_outcome_evidence_required(self):
        self.record["outcomes"][0]["source_evidence_ids"] = []
        self.assertIn("OUTCOME_EVIDENCE_MISSING", self.decision()["hold_codes"])

    def test_outcome_windows_must_order(self):
        self.record["outcomes"][0]["observed_start"] = self.record["outcomes"][0]["baseline_start"]
        self.assertIn("OUTCOME_WINDOW_INVALID", self.decision()["hold_codes"])

    def test_nonfinite_metric_is_malformed(self):
        self.record["outcomes"][0]["observed_value"] = float("nan")
        r = self.decision()
        self.assertEqual(r["decision"], "HOLD")
        self.assertEqual(r["hold_codes"], ["MALFORMED_INPUT"])
        self.assertTrue(verify_receipt(r))

    def test_exact_event_replay_collapses(self):
        r = self.decision()
        self.assertEqual(r["event_log"]["exact_replays"], 1)
        self.assertNotIn("EVENT_ID_PAYLOAD_CONFLICT", r["hold_codes"])

    def test_changed_event_payload_conflicts(self):
        self.record["event_log"].append({
            "event_id": self.record["event_log"][0]["event_id"],
            "payload": {"status": "settled", "cents": 101},
        })
        r = self.decision()
        self.assertIn("EVENT_ID_PAYLOAD_CONFLICT", r["hold_codes"])
        self.assertEqual(r["event_log"]["conflicts"], 1)

    def test_receipt_tamper_detected(self):
        r = self.decision()
        tampered = copy.deepcopy(r)
        tampered["decision"] = "HOLD"
        self.assertFalse(verify_receipt(tampered))

    def test_hash_only_forgery_shape_rejected(self):
        forged = {"decision": "EXPANSION_READY"}
        forged["receipt_digest"] = digest_json(forged)
        self.assertFalse(verify_receipt(forged))

    def test_malformed_missing_fields_fail_closed(self):
        r = evaluate({"schema_version": "1", "account_id": "x"})
        self.assertEqual(r["decision"], "HOLD")
        self.assertEqual(r["hold_codes"], ["MALFORMED_INPUT"])
        self.assertTrue(verify_receipt(r))

    def test_boolean_cents_rejected(self):
        self.record["settlement"]["net_cents"] = True
        self.assertEqual(self.decision()["hold_codes"], ["MALFORMED_INPUT"])

    def test_acceptance_suite_exact_counts_and_order_invariant(self):
        result = run_acceptance()
        self.assertEqual(result["records"], 120)
        self.assertEqual(result["decisions"], {"EXPANSION_READY": 36, "HOLD": 48, "RENEWAL_READY": 36})
        self.assertTrue(result["order_invariant"])
        self.assertTrue(result["all_receipts_verified"])

    def test_cli_acceptance(self):
        proc = subprocess.run(
            [sys.executable, "-m", "revenue.paid_outcome_expansion_rail.cli", "acceptance"],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["records"], 120)

    def test_cli_evaluate_and_verify(self):
        with tempfile.TemporaryDirectory() as td_raw:
            td = Path(td_raw)
            packet = td / "packet.json"
            receipt = td / "receipt.json"
            packet.write_text(json.dumps(self.record), encoding="utf-8")
            evaluated = subprocess.run(
                [sys.executable, "-m", "revenue.paid_outcome_expansion_rail.cli", "evaluate", str(packet)],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(evaluated.returncode, 0, evaluated.stderr)
            receipt.write_text(evaluated.stdout, encoding="utf-8")
            verified = subprocess.run(
                [sys.executable, "-m", "revenue.paid_outcome_expansion_rail.cli", "verify", str(receipt)],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(verified.returncode, 0, verified.stderr)
            self.assertEqual(verified.stdout.strip(), "VALID")


if __name__ == "__main__":
    unittest.main()
