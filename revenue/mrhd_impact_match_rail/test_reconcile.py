import copy
import json
import tempfile
import unittest
from pathlib import Path

from reconcile import LedgerError, main, reconcile, verify_receipt

H = "a" * 64


def passing_award(award_id="A-001"):
    return {
        "award_id": award_id,
        "base_award_cents": 10_000_00,
        "amendments": [],
        "contributions": [
            {"event_id": f"{award_id}-cash", "kind": "cash", "amount_cents": 150_000, "realized": True, "evidence_sha256": H},
            {"event_id": f"{award_id}-kind", "kind": "in_kind", "amount_cents": 100_000, "realized": True, "evidence_sha256": H},
        ],
        "expenses": [
            {"event_id": f"{award_id}-expense", "amount_cents": 1_250_000, "eligible": True, "evidence_sha256": H}
        ],
        "reimbursements": [
            {"event_id": f"{award_id}-reimb", "amount_cents": 1_000_000, "status": "paid", "evidence_sha256": H}
        ],
        "milestones": [
            {"milestone_id": f"{award_id}-close", "status": "complete", "evidence_sha256": H}
        ],
    }


def payload(*awards):
    return {
        "schema_version": 1,
        "cycle_id": "mrhd-2026-impact-match",
        "match_rate_bps": 2500,
        "in_kind_cap_bps_of_required_match": 5000,
        "awards": list(awards or [passing_award()]),
    }


class ReconcileTests(unittest.TestCase):
    def test_passing_award(self):
        out = reconcile(payload(passing_award()))
        self.assertEqual(out["summary"]["status"], "PASS")
        self.assertEqual(out["summary"]["required_match_cents"], 250_000)
        self.assertEqual(out["summary"]["counted_match_cents"], 250_000)
        self.assertTrue(verify_receipt(out))

    def test_in_kind_over_cap_is_held_and_only_cap_counts(self):
        award = passing_award()
        award["contributions"][0]["amount_cents"] = 125_000
        award["contributions"][1]["amount_cents"] = 150_000
        out = reconcile(payload(award))["awards"][0]
        self.assertIn("IN_KIND_OVER_CAP", out["holds"])
        self.assertEqual(out["counted_in_kind_match_cents"], 125_000)
        self.assertEqual(out["counted_match_cents"], 250_000)

    def test_commitment_does_not_satisfy_match(self):
        award = passing_award()
        award["contributions"][0]["realized"] = False
        out = reconcile(payload(award))["awards"][0]
        self.assertIn("MATCH_SHORTFALL", out["holds"])
        self.assertEqual(out["committed_not_realized_match_cents"], 150_000)

    def test_match_rounds_up_to_cent(self):
        award = passing_award()
        award["base_award_cents"] = 101
        award["contributions"][0]["amount_cents"] = 14
        award["contributions"][1]["amount_cents"] = 12
        award["expenses"][0]["amount_cents"] = 127
        award["reimbursements"][0]["amount_cents"] = 101
        out = reconcile(payload(award))["awards"][0]
        self.assertEqual(out["required_match_cents"], 26)
        self.assertEqual(out["in_kind_counting_cap_cents"], 13)
        self.assertEqual(out["counted_match_cents"], 26)
        self.assertEqual(out["status"], "PASS")

    def test_approved_amendment_changes_all_financial_thresholds(self):
        award = passing_award()
        award["amendments"] = [{"event_id": "am-1", "delta_cents": 200_000, "approved": True, "effective_at": "2026-11-01", "evidence_sha256": H}]
        award["contributions"][0]["amount_cents"] = 150_000
        award["contributions"][1]["amount_cents"] = 150_000
        award["expenses"][0]["amount_cents"] = 1_500_000
        award["reimbursements"][0]["amount_cents"] = 1_200_000
        out = reconcile(payload(award))["awards"][0]
        self.assertEqual(out["final_award_cents"], 1_200_000)
        self.assertEqual(out["required_match_cents"], 300_000)
        self.assertEqual(out["status"], "PASS")

    def test_unapproved_amendment_does_not_change_award_and_holds(self):
        award = passing_award()
        award["amendments"] = [{"event_id": "am-1", "delta_cents": 200_000, "approved": False, "effective_at": "2026-11-01", "evidence_sha256": H}]
        out = reconcile(payload(award))["awards"][0]
        self.assertEqual(out["final_award_cents"], 1_000_000)
        self.assertIn("UNAPPROVED_AMENDMENT_PRESENT", out["holds"])

    def test_project_spend_below_award_plus_match_holds(self):
        award = passing_award()
        award["expenses"][0]["amount_cents"] = 1_249_999
        out = reconcile(payload(award))["awards"][0]
        self.assertIn("PROJECT_SPEND_BELOW_AWARD_PLUS_MATCH", out["holds"])

    def test_reimbursement_over_award_holds(self):
        award = passing_award()
        award["reimbursements"][0]["amount_cents"] = 1_000_001
        out = reconcile(payload(award))["awards"][0]
        self.assertIn("REIMBURSEMENT_EXCEEDS_AWARD", out["holds"])

    def test_pending_milestone_holds(self):
        award = passing_award()
        award["milestones"][0]["status"] = "pending"
        out = reconcile(payload(award))["awards"][0]
        self.assertIn("MILESTONES_PENDING", out["holds"])

    def test_duplicate_award_fails_closed(self):
        with self.assertRaisesRegex(LedgerError, "duplicate award_id"):
            reconcile(payload(passing_award("X"), passing_award("X")))

    def test_event_id_collision_across_types_fails_closed(self):
        award = passing_award()
        award["expenses"][0]["event_id"] = award["contributions"][0]["event_id"]
        with self.assertRaisesRegex(LedgerError, "duplicate event_id"):
            reconcile(payload(award))

    def test_unknown_field_fails_closed(self):
        data = payload(passing_award())
        data["mystery"] = True
        with self.assertRaisesRegex(LedgerError, "unknown keys"):
            reconcile(data)

    def test_negative_money_fails_closed(self):
        award = passing_award()
        award["expenses"][0]["amount_cents"] = -1
        with self.assertRaisesRegex(LedgerError, "must be >= 0"):
            reconcile(payload(award))

    def test_bad_evidence_hash_fails_closed(self):
        award = passing_award()
        award["expenses"][0]["evidence_sha256"] = "not-a-hash"
        with self.assertRaisesRegex(LedgerError, "64-hex"):
            reconcile(payload(award))

    def test_order_invariance_and_byte_stable_receipt(self):
        a = passing_award("A")
        b = passing_award("B")
        data1 = payload(a, b)
        data2 = payload(copy.deepcopy(b), copy.deepcopy(a))
        data2["awards"][0]["contributions"].reverse()
        data2["awards"][1]["expenses"].reverse()
        out1 = reconcile(data1)
        out2 = reconcile(data2)
        self.assertEqual(out1, out2)
        self.assertEqual(json.dumps(out1, sort_keys=True), json.dumps(out2, sort_keys=True))

    def test_receipt_tamper_detection(self):
        out = reconcile(payload(passing_award()))
        tampered = copy.deepcopy(out)
        tampered["summary"]["final_award_cents"] += 1
        self.assertFalse(verify_receipt(tampered))

    def test_cli_require_pass_and_verify(self):
        award = passing_award()
        award["milestones"][0]["status"] = "pending"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inp = root / "in.json"
            out = root / "out.json"
            inp.write_text(json.dumps(payload(award)), encoding="utf-8")
            self.assertEqual(main([str(inp), "--output", str(out), "--require-pass"]), 3)
            self.assertTrue(out.exists())
            self.assertEqual(main(["--verify", str(out)]), 0)


if __name__ == "__main__":
    unittest.main()
