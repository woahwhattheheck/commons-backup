"""Focused offline checks for exact-head paid validation receipt advice."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tools.paid_validation_receipts.audit import InputError, evaluate, load

NOW = datetime(2026, 10, 8, 2, 1, tzinfo=timezone(timedelta(hours=-4)))
HEAD = "a" * 40
PRIOR = "b" * 40
EVIDENCE = "https://github.com/woahwhattheheck/commons/actions/runs/123456"


def record(outcome="passed", head=HEAD, checked_at=None, with_url=True):
    receipt = {
        "check_id": "trustline-focus", "head": head, "outcome": outcome,
        "checked_at": (checked_at or NOW - timedelta(hours=1)).isoformat(),
    }
    if with_url:
        receipt["evidence_url"] = EVIDENCE
    return receipt


def snapshot(receipts):
    return {
        "repository": "woahwhattheheck/pocketpay-sdk", "pull_request": 21,
        "current_head": HEAD, "checks": [{"id": "trustline-focus"}], "receipts": receipts,
    }


class FocusedReceiptTests(unittest.TestCase):
    def decision(self, receipts, max_age_hours=168):
        return evaluate(snapshot(receipts), now=NOW, max_age_hours=max_age_hours)["advice"][0]["decision"]

    def test_same_head_executed_pass_is_reusable_advisory(self):
        result = evaluate(snapshot([record()]), now=NOW)
        self.assertEqual(result["advice"][0]["decision"], "REUSE_REPORTED_PASS")
        self.assertEqual(result["advice"][0]["evidence_url"], EVIDENCE)
        self.assertFalse(result["limits"]["external_evidence_authenticated"])

    def test_authored_not_run_never_counts_as_passed(self):
        self.assertEqual(self.decision([record("not_run", with_url=False)]), "PERFORM_FOCUSED")

    def test_old_head_not_reused_on_new_source(self):
        self.assertEqual(self.decision([record(head=PRIOR)]), "SOURCE_HEAD_CHANGED")

    def test_failed_latest_exact_head_overrules_earlier_pass(self):
        older = record(checked_at=NOW - timedelta(hours=4))
        newest = record(outcome="failed", checked_at=NOW - timedelta(minutes=10))
        self.assertEqual(self.decision([older, newest]), "FOCUSED_FIX_REQUIRED")

    def test_stale_same_head_requires_review_not_bulk_test(self):
        old = record(checked_at=NOW - timedelta(days=10))
        self.assertEqual(self.decision([old]), "REVIEW_OLD_RECEIPT")

    def test_equal_timestamp_conflict_needs_reconciliation(self):
        passed = record()
        failed = record(outcome="failed", checked_at=NOW - timedelta(hours=1))
        self.assertEqual(self.decision([passed, failed]), "RECONCILE_RECEIPTS")

    def test_fail_closed_on_fake_pass_without_log(self):
        with self.assertRaises(InputError):
            self.decision([record(with_url=False)])

    def test_fail_closed_on_future_and_fake_url(self):
        with self.assertRaises(InputError):
            self.decision([record(checked_at=NOW + timedelta(days=1))])
        r = record()
        r["evidence_url"] = "https://token:secret@example.com/passed"
        with self.assertRaises(InputError):
            self.decision([r])

    def test_loader_rejects_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "snapshot.json"
            path.write_text('{"repository":"one/a","repository":"two/b"}', encoding="utf-8")
            with self.assertRaises(InputError):
                load(path)

    def test_two_independent_checks_reconcile_separately(self):
        data = snapshot([record()])
        data["checks"].append({"id": "unused-focused-check"})
        result = evaluate(data, now=NOW)
        self.assertEqual([a["decision"] for a in result["advice"]], ["REUSE_REPORTED_PASS", "PERFORM_FOCUSED"])


if __name__ == "__main__":
    unittest.main()
