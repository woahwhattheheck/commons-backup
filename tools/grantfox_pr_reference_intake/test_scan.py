"""Focused offline GrantFox PR-reference collision regressions."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from tools.grantfox_pr_reference_intake.scan import (
    audit_issues, main, render_slack,
)


def issue(**overrides):
    value = {
        "repository": "LFGBanditLabs/Quipay",
        "number": 1078,
        "url": "https://github.com/LFGBanditLabs/Quipay/issues/1078",
        "issue_comments": [],
    }
    value.update(overrides)
    return value


class GrantFoxPrReferenceTests(unittest.TestCase):
    def test_incumbent_pr_from_verified_issue_comment(self):
        item = issue(issue_comments=[{
            "id": 4995986493,
            "user": {"login": "wilber123451-design"},
            "body": "I opened PR #1093: https://github.com/LFGBanditLabs/Quipay/pull/1093",
        }])
        output = audit_issues([item])
        row = output["issues"][0]
        self.assertEqual(row["status"], "PR_REFERENCE_REVIEW")
        self.assertEqual(len(row["pr_references"]), 1)
        reference = row["pr_references"][0]
        self.assertEqual(reference["pr_url"], "https://github.com/LFGBanditLabs/Quipay/pull/1093")
        self.assertFalse(reference["pr_open_verified"])
        self.assertEqual(reference["sources"][0]["comment_author"], "wilber123451-design")
        self.assertEqual(reference["sources"][0]["comment_id"], 4995986493)
        self.assertEqual(output["provider_queries_executed"], 0)

    def test_local_bare_pr_id_requires_explicit_pr_noun(self):
        row = issue(issue_comments=[{
            "id": 1, "body": "Fixes #1078; pull request #1093 is ready."
        }])
        self.assertEqual(len(audit_issues([row])["issues"][0]["pr_references"]), 1)

    def test_cross_repo_pr_link_does_not_invent_sponsor_incumbent(self):
        row = issue(issue_comments=[{
            "id": 2,
            "body": "See https://github.com/other/repo/pull/404 and issue #1078",
        }])
        self.assertEqual(
            audit_issues([row])["issues"][0]["status"],
            "NO_PR_LINKS_IN_SUPPLIED_CENSUS",
        )

    def test_missing_comment_census_is_not_clean(self):
        row = issue()
        del row["issue_comments"]
        missing, supplied = audit_issues([row, issue(number=1079)])["issues"]
        self.assertEqual(missing["status"], "COMMENT_CENSUS_MISSING")
        self.assertFalse(missing["comment_census_supplied"])
        self.assertEqual(supplied["status"], "NO_PR_LINKS_IN_SUPPLIED_CENSUS")
        self.assertTrue(supplied["comment_census_supplied"])

    def test_repeated_reference_deduplicates_but_keeps_evidence(self):
        row = issue(issue_comments=[
            {"id": 1, "body": "PR #1093", "user": {"login": "alice"}},
            {"id": 2, "body": "PR #1093", "user": {"login": "bob"}},
        ])
        result = audit_issues([row])["issues"][0]["pr_references"]
        self.assertEqual(len(result), 1)
        self.assertEqual([s["comment_id"] for s in result[0]["sources"]], [1, 2])
        self.assertTrue(result[0]["operation_id"].startswith("GFOX-PRREF-"))

    def test_reject_duplicate_issue_case_variation_and_malformed_comments(self):
        with self.assertRaisesRegex(ValueError, "duplicate sponsor issue"):
            audit_issues([issue(), issue(repository="lfgbanditlabs/quipay")])
        with self.assertRaisesRegex(ValueError, "comments require body"):
            audit_issues([issue(issue_comments=[{"id": 1}])])

    def test_jsonl_cli_output_contains_full_audit(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td, "sample.jsonl")
            src.write_text(json.dumps(issue(issue_comments=[
                {"id": 42, "body": "PR #1093"}
            ])) + "\n", encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(main([str(src), "--format", "json"]), 0)
            record = json.loads(output.getvalue())
            self.assertEqual(record["reference_review_issues"], 1)
            self.assertEqual(record["claims_created"], 0)

    def test_slack_output_is_bounded_and_disclaims_open_pr(self):
        cases = [
            issue(number=i + 1, issue_comments=[
                {"id": i + 1, "body": f"PR #{i + 15}"}
            ])
            for i in range(120)
        ]
        report = render_slack(audit_issues(cases), limit=120)
        self.assertLessEqual(len(report), 5000)
        self.assertIn("do NOT prove PR open", report)


if __name__ == "__main__":
    unittest.main()
