import unittest

from integrations.command_center.grantfox_overlap_triage import (
    ISSUE_CLOSED,
    NEEDS_REFRESH,
    OVERLAP_OPEN_PR,
    READY,
    SATISFIED_DEFAULT_BRANCH,
    CandidateEvidence,
    PullRequestEvidence,
    classify,
)


class GrantFoxOverlapTriageTests(unittest.TestCase):
    def candidate(self, **changes):
        data = dict(
            repository="Flux-DeFi/LiquidFlow",
            issue_number=182,
            issue_state="open",
            default_branch_sha="c0cb1753a96ca900d3a3bb01791023da5a5148c1",
            default_branch_satisfied=False,
            pull_requests=(),
        )
        data.update(changes)
        return CandidateEvidence(**data)

    def test_ready_without_overlap(self):
        self.assertEqual(classify(self.candidate())["verdict"], READY)

    def test_liquidflow_182_pr_222_is_overlap(self):
        pr = PullRequestEvidence(
            222,
            "open",
            title="feat: loading/error/data states (Closes #182)",
        )
        result = classify(self.candidate(pull_requests=(pr,)))
        self.assertEqual(result["verdict"], OVERLAP_OPEN_PR)
        self.assertEqual(result["overlapping_prs"], [222])

    def test_draft_is_still_active_overlap(self):
        pr = PullRequestEvidence(9, "OPEN", title="Fixes: #182", draft=True)
        self.assertEqual(
            classify(self.candidate(pull_requests=(pr,)))["verdict"],
            OVERLAP_OPEN_PR,
        )

    def test_bare_mention_is_not_enough(self):
        pr = PullRequestEvidence(8, "open", body="Related to #182 only")
        self.assertEqual(classify(self.candidate(pull_requests=(pr,)))["verdict"], READY)

    def test_issue_url_is_explicit_overlap(self):
        pr = PullRequestEvidence(
            7,
            "open",
            body="Implements https://github.com/Flux-DeFi/LiquidFlow/issues/182",
        )
        self.assertEqual(
            classify(self.candidate(pull_requests=(pr,)))["verdict"],
            OVERLAP_OPEN_PR,
        )

    def test_closed_and_merged_prs_do_not_overlap(self):
        prs = (
            PullRequestEvidence(5, "closed", title="Closes #182"),
            PullRequestEvidence(6, "open", title="Closes #182", merged=True),
        )
        self.assertEqual(classify(self.candidate(pull_requests=prs))["verdict"], READY)

    def test_default_branch_satisfied(self):
        self.assertEqual(
            classify(self.candidate(default_branch_satisfied=True))["verdict"],
            SATISFIED_DEFAULT_BRANCH,
        )

    def test_closed_issue(self):
        self.assertEqual(classify(self.candidate(issue_state="closed"))["verdict"], ISSUE_CLOSED)

    def test_missing_default_branch_check_requires_refresh(self):
        self.assertEqual(
            classify(self.candidate(default_branch_satisfied=None))["verdict"],
            NEEDS_REFRESH,
        )

    def test_overlaps_are_sorted(self):
        prs = (
            PullRequestEvidence(30, "open", title="Resolve #182"),
            PullRequestEvidence(12, "open", body="Fixes #182"),
        )
        self.assertEqual(
            classify(self.candidate(pull_requests=prs))["overlapping_prs"],
            [12, 30],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
