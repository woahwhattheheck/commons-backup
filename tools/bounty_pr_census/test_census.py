"""One focused, offline regression for PR collision admission.

No GitHub calls, environment variables, broad test runner, or local credentials.
"""
from datetime import datetime, timedelta, timezone
import unittest

from tools.bounty_pr_census.census import IncompleteSnapshot, evaluate

NOW = datetime(2026, 10, 8, 5, 14, tzinfo=timezone.utc)
REPO = "Stellar-PocketPay/pocketpay-mobile"


def pr(number, title, body="Closes #526", repo=REPO):
    return {
        "number": number,
        "state": "open",
        "title": title,
        "body": body,
        "html_url": f"https://github.com/{repo}/pull/{number}",
        "user": {"login": "woahwhattheheck"},
        "head": {"sha": "a" * 40},
    }


def snapshot(*rows, page_size=100, captured_at=None):
    return {
        "repository": REPO,
        "source": "github-rest-pulls-authenticated",
        "captured_at": (captured_at or NOW).isoformat(),
        "page_size": page_size,
        "pages": [{"page": 1, "pull_requests": list(rows)}],
    }


class SponsorPrCensusTests(unittest.TestCase):
    def test_original_author_pr_hidden_by_search_is_a_hold(self):
        report = evaluate(snapshot(pr(556, "feat(wallet): refresh state machine")), REPO, 526, NOW)
        self.assertEqual(report["status"], "HOLD_EXISTING")
        self.assertEqual(report["incumbents"][0]["number"], 556)
        self.assertEqual(report["incumbents"][0]["author"], "woahwhattheheck")
        self.assertEqual(report["incumbents"][0]["head_sha"], "a" * 40)

    def test_multiple_incumbents_trigger_conflict_and_no_duplicate_publication(self):
        rows = [pr(556, "feat: refresh (#526)"), pr(599, "fix #526")]
        report = evaluate(snapshot(*rows), REPO, 526, NOW)
        self.assertEqual(report["status"], "HOLD_COLLISION")
        self.assertEqual([x["number"] for x in report["incumbents"]], [556, 599])

    def test_no_reference_never_authorizes_go(self):
        row = pr(552, "Typed receipts", body=None)
        report = evaluate(snapshot(row), REPO, 526, NOW)
        self.assertEqual(report["status"], "REVIEW_NO_MATCH")
        self.assertEqual(report["unmapped_pr_numbers"], [552])
        self.assertIn("Manually review", report["next_action"])

    def test_cross_repo_link_is_not_false_positive(self):
        row = pr(552, "Other team's issue", body="Closes NotUs/AnotherRepo#526")
        report = evaluate(snapshot(row), REPO, 526, NOW)
        self.assertEqual(report["status"], "REVIEW_NO_MATCH")
        self.assertEqual(report["incumbents"], [])

    def test_incomplete_full_last_page_and_stale_capture_fail_closed(self):
        full = snapshot(pr(1, "first"), pr(2, "second"), page_size=2)
        with self.assertRaisesRegex(IncompleteSnapshot, "full final page"):
            evaluate(full, REPO, 526, NOW)
        old = snapshot(pr(556, "old"), captured_at=NOW - timedelta(hours=1))
        with self.assertRaisesRegex(IncompleteSnapshot, "stale"):
            evaluate(old, REPO, 526, NOW)

    def test_complete_pagination_and_wrong_repository_gate(self):
        data = snapshot(page_size=1)
        data["pages"] = [
            {"page": 1, "pull_requests": [pr(556, "Balance fix")]},
            {"page": 2, "pull_requests": []},
        ]
        self.assertEqual(evaluate(data, REPO, 526, NOW)["status"], "HOLD_EXISTING")
        data["repository"] = "Other/Repo"
        with self.assertRaisesRegex(IncompleteSnapshot, "repository mismatch"):
            evaluate(data, REPO, 526, NOW)


if __name__ == "__main__":
    unittest.main()
