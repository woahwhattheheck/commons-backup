"""Focused regression cases for the offline Slack TAKE collision advisory."""
import unittest

from audit import audit


def message(ts, action, op, pr, suffix="", user="agent"):
    return {
        "ts": str(ts),
        "user": user,
        "channel": "bug-bounty",
        "text": f"{action} · {op} · original sponsor PR "
                f"https://github.com/{pr} {suffix}",
    }


class CollisionAuditTests(unittest.TestCase):
    def test_three_workers_same_pr_and_path(self):
        rows = [
            message(1000, "TAKE", "GF-PPSDK445-R8", "owner/sdk/pull/461",
                    "HEAD a30d3421 src/config.ts", "one"),
            message(1010, "TAKE", "GF-PPSDK445-VAR17", "owner/sdk/pull/461",
                    "HEAD a30d3421 src/config.ts", "two"),
            message(1020, "TAKE", "GF-PPSDK445-R6", "owner/sdk/pull/461",
                    "HEAD a30d3421 src/config/index.ts", "three"),
        ]
        report = audit(rows)
        self.assertEqual(len(report["alerts"]), 1)
        alert = report["alerts"][0]
        self.assertEqual(alert["pr"], "owner/sdk#461")
        self.assertEqual(len(alert["operations"]), 3)
        self.assertEqual(alert["pairs"][0]["relation"], "overlapping-source-paths")
        self.assertTrue(alert["pairs"][0]["same_head"])

    def test_release_only_own_operation(self):
        rows = [
            message(1000, "TAKE", "OP-SOURCE-ONE", "owner/sdk/pull/461"),
            message(1001, "TAKE", "OP-SOURCE-TWO", "owner/sdk/pull/461"),
            message(1002, "RELEASE", "OP-SOURCE-ONE", "owner/sdk/pull/461"),
        ]
        report = audit(rows)
        self.assertEqual(report["active_takes"], 1)
        self.assertEqual(report["alerts"], [])

    def test_metadata_and_disjoint_scopes_are_advisory(self):
        rows = [
            message(1000, "TAKE", "OP-SOURCE-ONE", "org/repo/pull/7",
                    "HEAD abcdef123 src/main.py"),
            message(1001, "TAKE", "OP-SOURCE-TWO", "org/repo/pull/7",
                    "HEAD abcdef123 src/helpers.py"),
            message(1002, "TAKE", "OP-META-THREE", "org/repo/pull/7",
                    "metadata-only PR body text"),
        ]
        pairs = audit(rows)["alerts"][0]["pairs"]
        self.assertIn("disjoint-source-paths", [p["relation"] for p in pairs])
        self.assertIn("separate-metadata-scope", [p["relation"] for p in pairs])

    def test_old_and_other_pr_takes_do_not_alert(self):
        rows = [
            message(100, "TAKE", "OP-SOURCE-ONE", "org/repo/pull/7"),
            message(10000, "TAKE", "OP-SOURCE-TWO", "org/repo/pull/7"),
            message(10001, "TAKE", "OP-SOURCE-THREE", "org/repo/pull/8"),
        ]
        self.assertEqual(audit(rows, window_minutes=90)["alerts"], [])


if __name__ == "__main__":
    unittest.main()
