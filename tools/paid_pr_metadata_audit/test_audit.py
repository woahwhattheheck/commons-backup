"""Only the four directly relevant regression boundaries for the offline audit."""
import copy
import unittest
from datetime import datetime, timezone

from audit import AuditError, audit, SCHEMA

NOW = datetime(2026, 10, 8, 5, 10, tzinfo=timezone.utc)


def case():
    return {
        "schema": SCHEMA,
        "actor": "ExampleContributor",
        "as_of": "2026-10-08T05:00:00Z",
        "records": [{
            "issue_url": "https://github.com/ExampleOrg/ExampleRepo/issues/42",
            "pr_url": "https://github.com/ExampleOrg/ExampleRepo/pull/100",
            "platform": "grantfox", "pr_author": "examplecontributor",
            "pr_state": "open", "issue_state": "open",
            "pr_head_sha": "1" * 40,
            "pr_body": "Closes #42\n\nThis fixes the issue with one scoped change.",
            "issue_labels": ["GrantFox OSS", "Maybe Rewarded", "Official Campaign"],
            "issue_comments": [{"author": "ExampleContributor", "body": "/claim #42"}],
            "comments_complete": True, "checked_at": "2026-10-08T05:00:00Z"
        }]
    }


class AuditFocused(unittest.TestCase):
    def test_existing_claim_but_missing_pr_request(self):
        result = audit(case(), now=NOW)["records"][0]
        self.assertEqual("MANUAL_METADATA_REVIEW", result["decision"])
        self.assertEqual(True, result["existing_issue_claim_by_actor"])
        self.assertIn("PR_COMPENSATION_REQUEST_NOT_FOUND", result["findings"])
        self.assertNotIn("ISSUE_CLAIM_NOT_FOUND", result["findings"])

    def test_affirmative_request_and_waiver_are_distinct(self):
        c = case()
        c["records"][0]["pr_body"] += "\nI request conditional GrantFox compensation for my contribution."
        r = audit(c, now=NOW)["records"][0]
        self.assertEqual("NO_METADATA_GAP_DETECTED", r["decision"])
        c["records"][0]["pr_body"] += "\nI am not claiming any reward."
        r = audit(c, now=NOW)["records"][0]
        self.assertIn("PR_WAIVER_LANGUAGE_REVIEW", r["findings"])

    def test_foreign_owner_is_preserved_even_with_pr_waiver(self):
        c = case()
        c["records"][0]["pr_author"] = "anothercontributor"
        c["records"][0]["pr_body"] += "\nI am not claiming any reward."
        r = audit(c, now=NOW)["records"][0]
        self.assertEqual("PRESERVE_FOREIGN_AUTHOR", r["decision"])

    def test_incomplete_comments_never_assert_missing_claim(self):
        c = case()
        c["records"][0]["issue_comments"] = []
        c["records"][0]["comments_complete"] = False
        r = audit(c, now=NOW)["records"][0]
        self.assertEqual("HOLD_INCOMPLETE_CLAIM_CENSUS", r["decision"])
        self.assertIsNone(r["existing_issue_claim_by_actor"])
        self.assertNotIn("ISSUE_CLAIM_NOT_FOUND", r["findings"])
        bad = copy.deepcopy(c)
        bad["records"][0]["pr_url"] = "https://github.com/AnotherOrg/ExampleRepo/pull/100"
        with self.assertRaises(AuditError):
            audit(bad, now=NOW)



    def test_nonclosing_sponsor_references_are_accepted(self):
        for reference in (
            "Refs #42",
            "References exampleorg/examplerepo#42",
            "Related to #42",
            "for #42",
            "https://github.com/EXAMPLEORG/ExampleRepo/issues/42",
        ):
            with self.subTest(reference=reference):
                snapshot = case()
                snapshot["records"][0]["pr_body"] = (
                    reference + "\nI request conditional GrantFox compensation for this work."
                )
                row = audit(snapshot, now=NOW)["records"][0]
                self.assertNotIn("SPONSOR_ISSUE_LINK_NOT_FOUND", row["findings"])
                self.assertEqual("NO_METADATA_GAP_DETECTED", row["decision"])

    def test_unrelated_repository_and_issue_number_are_rejected(self):
        for reference in (
            "Fixes OtherOrg/OtherRepo#42",
            "Refs OtherOrg/OtherRepo#42",
            "https://github.com/OtherOrg/OtherRepo/issues/42",
            "Refs #420",
        ):
            with self.subTest(reference=reference):
                snapshot = case()
                snapshot["records"][0]["pr_body"] = (
                    reference + "\nI request conditional GrantFox compensation for this work."
                )
                row = audit(snapshot, now=NOW)["records"][0]
                self.assertIn("SPONSOR_ISSUE_LINK_NOT_FOUND", row["findings"])

    def test_quoted_or_fenced_references_are_not_sponsor_links(self):
        snapshot = case()
        snapshot["records"][0]["pr_body"] = (
            "> Refs #42\n"
            "~~~markdown\n"
            "https://github.com/ExampleOrg/ExampleRepo/issues/42\n"
            "~~~\n"
            "I request conditional GrantFox compensation for this work."
        )
        row = audit(snapshot, now=NOW)["records"][0]
        self.assertIn("SPONSOR_ISSUE_LINK_NOT_FOUND", row["findings"])


    def test_indented_markdown_examples_do_not_count_as_claims_or_requests(self):
        snapshot = case()
        row = snapshot["records"][0]
        row["issue_comments"] = [{
            "author": "ExampleContributor",
            "body": "How to claim a bounty:\n\n    /claim #42",
        }]
        row["pr_body"] += (
            "\n\n"
            "    I request conditional compensation for sample work.\n"
            "    I am not claiming any reward.\n"
        )
        result = audit(snapshot, now=NOW)["records"][0]
        self.assertFalse(result["existing_issue_claim_by_actor"])
        self.assertFalse(result["affirmative_request_detected"])
        self.assertFalse(result["waiver_language_detected"])
        self.assertIn("ISSUE_CLAIM_NOT_FOUND", result["findings"])
        self.assertIn("PR_COMPENSATION_REQUEST_NOT_FOUND", result["findings"])
        self.assertNotIn("PR_WAIVER_LANGUAGE_REVIEW", result["findings"])

    def test_fences_require_matching_style_and_length_before_claim_is_real(self):
        snapshot = case()
        comment = snapshot["records"][0]["issue_comments"][0]
        comment["body"] = "````text\n/claim #42\n~~~\n/claim #42\n````"
        result = audit(snapshot, now=NOW)["records"][0]
        self.assertFalse(result["existing_issue_claim_by_actor"])
        comment["body"] += "\n/claim #42"
        result = audit(snapshot, now=NOW)["records"][0]
        self.assertTrue(result["existing_issue_claim_by_actor"])

if __name__ == "__main__":
    unittest.main()