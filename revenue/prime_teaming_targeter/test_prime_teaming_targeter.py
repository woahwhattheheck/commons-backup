from __future__ import annotations

import copy
import unittest
from datetime import datetime, timezone

from revenue.prime_teaming_targeter.targeter import TargeterError, compile_targeter, render_markdown, verify_receipt

NOW = datetime(2026, 9, 13, 16, 0, tzinfo=timezone.utc)
H = "a" * 64
H2 = "b" * 64
H3 = "c" * 64
H4 = "d" * 64


def fixture():
    return {
        "schema": "prime-teaming-targeter/input/v1",
        "opportunity": {
            "opportunity_id": "opp-14113",
            "title": "Synthetic modernization study",
            "source_ref": "public-notice:14113",
            "source_sha256": H,
            "observed_at": "2026-09-12T12:00:00Z",
            "deadline_at": "2026-09-25T21:00:00Z",
            "requirements": [
                {"requirement_id": "health", "label": "health-domain prime experience", "weight_bps": 4000, "mandatory": True},
                {"requirement_id": "legacy", "label": "legacy modernization", "weight_bps": 3500, "mandatory": True},
                {"requirement_id": "cloud", "label": "cloud roadmap", "weight_bps": 2500, "mandatory": False},
            ],
        },
        "evidence_authority": [
            {"evidence_id": "e-a-health", "opportunity_id": "opp-14113", "candidate_id": "prime-a", "requirement_id": "health", "source_kind": "CANDIDATE_PUBLIC", "source_ref": "prime-a:health", "source_sha256": H2, "observed_at": "2026-09-10T12:00:00Z", "status": "MEETS", "note": "Public program history"},
            {"evidence_id": "e-a-legacy", "opportunity_id": "opp-14113", "candidate_id": "prime-a", "requirement_id": "legacy", "source_kind": "CANDIDATE_PUBLIC", "source_ref": "prime-a:legacy", "source_sha256": H3, "observed_at": "2026-09-10T12:00:00Z", "status": "MEETS", "note": "Public modernization history"},
            {"evidence_id": "e-a-cloud", "opportunity_id": "opp-14113", "candidate_id": "prime-a", "requirement_id": "cloud", "source_kind": "CANDIDATE_PUBLIC", "source_ref": "prime-a:cloud", "source_sha256": H4, "observed_at": "2026-09-10T12:00:00Z", "status": "PARTIAL", "note": "Public cloud roadmap evidence"},
            {"evidence_id": "e-b-health", "opportunity_id": "opp-14113", "candidate_id": "prime-b", "requirement_id": "health", "source_kind": "CANDIDATE_PUBLIC", "source_ref": "prime-b:health", "source_sha256": H2, "observed_at": "2026-09-10T12:00:00Z", "status": "MEETS", "note": "Public health evidence"},
            {"evidence_id": "e-b-legacy", "opportunity_id": "opp-14113", "candidate_id": "prime-b", "requirement_id": "legacy", "source_kind": "CANDIDATE_PUBLIC", "source_ref": "prime-b:legacy", "source_sha256": H3, "observed_at": "2026-09-10T12:00:00Z", "status": "PARTIAL", "note": "Partial legacy evidence"},
        ],
        "candidates": [
            {"candidate_id": "prime-a", "name": "Prime A", "evidence_ids": ["e-a-health", "e-a-legacy", "e-a-cloud"], "paid_scope": {"title": "Evidence work package", "amount_minor": 1850000, "currency": "USD", "deliverables": ["architecture contradiction ledger", "migration evidence matrix"], "acceptance_criteria": ["all claims map to retained evidence", "prime reviews final scope"]}},
            {"candidate_id": "prime-b", "name": "Prime B", "evidence_ids": ["e-b-health", "e-b-legacy"], "paid_scope": {"title": "Evidence work package", "amount_minor": 1500000, "currency": "USD", "deliverables": ["legacy dependency map"], "acceptance_criteria": ["prime reviews final scope"]}},
        ],
    }


class TargeterTests(unittest.TestCase):
    def test_ranks_only_evidence_complete_prime(self):
        receipt = compile_targeter(fixture(), trusted_now=NOW)
        self.assertEqual(receipt["decision"], "READY_FOR_OWNER_TARGET_REVIEW")
        self.assertEqual(receipt["selected_candidate_id"], "prime-a")
        self.assertEqual(receipt["ranked_candidates"][0]["score_bps"], 8750)
        self.assertEqual(receipt["ranked_candidates"][0]["paid_scope"]["status"], "PROPOSED_NOT_ACCEPTED")
        self.assertFalse(receipt["ranked_candidates"][0]["outreach_authorized"])
        self.assertFalse(any(receipt["authority_ceiling"].values()))

    def test_partial_mandatory_holds_candidate(self):
        receipt = compile_targeter(fixture(), trusted_now=NOW)
        b = next(row for row in receipt["ranked_candidates"] if row["candidate_id"] == "prime-b")
        self.assertEqual(b["state"], "HOLD_NEEDS_EVIDENCE")
        self.assertIn("legacy", b["mandatory_not_met_ids"])

    def test_missing_mandatory_holds_all(self):
        data = fixture()
        data["candidates"] = [data["candidates"][1]]
        receipt = compile_targeter(data, trusted_now=NOW)
        self.assertEqual(receipt["decision"], "HOLD_NO_EVIDENCE_COMPLETE_TARGET")
        self.assertIsNone(receipt["selected_candidate_id"])

    def test_stale_evidence_holds(self):
        data = fixture()
        for record in data["evidence_authority"]:
            if record["candidate_id"] == "prime-a" and record["requirement_id"] == "legacy":
                record["observed_at"] = "2026-01-01T00:00:00Z"
        receipt = compile_targeter(data, trusted_now=NOW)
        a = next(row for row in receipt["ranked_candidates"] if row["candidate_id"] == "prime-a")
        self.assertIn("HOLD_STALE_EVIDENCE", a["hold_reasons"])
        self.assertIn("legacy", a["mandatory_not_met_ids"])

    def test_future_evidence_holds(self):
        data = fixture()
        data["evidence_authority"][0]["observed_at"] = "2026-09-14T00:00:00Z"
        receipt = compile_targeter(data, trusted_now=NOW)
        a = next(row for row in receipt["ranked_candidates"] if row["candidate_id"] == "prime-a")
        self.assertIn("HOLD_FUTURE_EVIDENCE", a["hold_reasons"])

    def test_deadline_passed_is_global_hold(self):
        receipt = compile_targeter(fixture(), trusted_now=datetime(2026, 9, 26, tzinfo=timezone.utc))
        self.assertEqual(receipt["decision"], "HOLD_NO_EVIDENCE_COMPLETE_TARGET")
        self.assertTrue(all("HOLD_DEADLINE_PASSED" in row["hold_reasons"] for row in receipt["ranked_candidates"]))

    def test_cross_candidate_evidence_transplant_rejected(self):
        data = fixture()
        data["candidates"][1]["evidence_ids"].append("e-a-cloud")
        with self.assertRaisesRegex(TargeterError, "transplanted across candidates"):
            compile_targeter(data, trusted_now=NOW)

    def test_cross_opportunity_evidence_transplant_rejected(self):
        data = fixture()
        data["evidence_authority"][0]["opportunity_id"] = "other"
        with self.assertRaisesRegex(TargeterError, "another opportunity"):
            compile_targeter(data, trusted_now=NOW)

    def test_duplicate_evidence_id_rejected(self):
        data = fixture()
        data["evidence_authority"].append(copy.deepcopy(data["evidence_authority"][0]))
        with self.assertRaisesRegex(TargeterError, "duplicate evidence_id"):
            compile_targeter(data, trusted_now=NOW)

    def test_weights_must_sum_exactly(self):
        data = fixture()
        data["opportunity"]["requirements"][0]["weight_bps"] = 3999
        with self.assertRaisesRegex(TargeterError, "sum to 10000"):
            compile_targeter(data, trusted_now=NOW)

    def test_bool_is_not_amount(self):
        data = fixture()
        data["candidates"][0]["paid_scope"]["amount_minor"] = True
        with self.assertRaisesRegex(TargeterError, "must be integer"):
            compile_targeter(data, trusted_now=NOW)

    def test_currency_is_explicit_uppercase(self):
        data = fixture()
        data["candidates"][0]["paid_scope"]["currency"] = "usd"
        with self.assertRaisesRegex(TargeterError, "uppercase"):
            compile_targeter(data, trusted_now=NOW)

    def test_receipt_recompiles_and_currently_revalidates(self):
        receipt = compile_targeter(fixture(), trusted_now=NOW)
        result = verify_receipt(fixture(), receipt, trusted_now=NOW)
        self.assertTrue(result["integrity_valid"])
        self.assertEqual(result["historical_decision"], "READY_FOR_OWNER_TARGET_REVIEW")
        self.assertEqual(result["current_decision"], "READY_FOR_OWNER_TARGET_REVIEW")

    def test_receipt_tamper_rejected(self):
        receipt = compile_targeter(fixture(), trusted_now=NOW)
        receipt["selected_candidate_id"] = "prime-b"
        result = verify_receipt(fixture(), receipt, trusted_now=NOW)
        self.assertFalse(result["integrity_valid"])
        self.assertEqual(result["reason"], "RECEIPT_DIGEST_MISMATCH")

    def test_markdown_is_explicitly_non_authorizing(self):
        receipt = compile_targeter(fixture(), trusted_now=NOW)
        rendered = render_markdown(receipt)
        self.assertIn("Prime / Teaming Target Brief", rendered)
        self.assertIn("PROPOSED_NOT_ACCEPTED", rendered)
        self.assertIn("External outreach authorized: **NO**", rendered)
        self.assertIn(receipt["receipt_sha256"], rendered)

    def test_historical_integrity_does_not_preserve_stale_current_authority(self):
        receipt = compile_targeter(fixture(), trusted_now=NOW)
        result = verify_receipt(fixture(), receipt, trusted_now=datetime(2026, 11, 1, tzinfo=timezone.utc))
        self.assertTrue(result["integrity_valid"])
        self.assertEqual(result["current_decision"], "HOLD_NO_EVIDENCE_COMPLETE_TARGET")


if __name__ == "__main__":
    unittest.main()
