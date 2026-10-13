import unittest

from integrations.command_center.grantfox_execution_readiness import (
    APPLICATION_REQUIRED,
    CLOSED_OR_SATISFIED,
    IMPLEMENTATION_READY,
    NEEDS_REFRESH,
    OVERLAP_EXISTING_WORK,
    PROVIDER_ASSIGNED_OTHER,
    RESEARCH_ONLY,
    WAIT_PROVIDER_ASSIGNMENT,
    GrantFoxExecutionEvidence,
    classify_execution,
)
from integrations.command_center.grantfox_overlap_triage import (
    ISSUE_CLOSED,
    NEEDS_REFRESH as OVERLAP_NEEDS_REFRESH,
    OVERLAP_OPEN_PR,
    READY,
    SATISFIED_DEFAULT_BRANCH,
)


class GrantFoxExecutionReadinessTests(unittest.TestCase):
    def evidence(self, **changes):
        data = dict(
            repository="Example/Project",
            issue_number=17,
            issue_state="open",
            overlap_verdict=READY,
            grantfox_candidate_verified=True,
            application_state="not_submitted",
            assignment_state="unassigned",
            provider_state_observed=True,
        )
        data.update(changes)
        return GrantFoxExecutionEvidence(**data)

    def test_application_required_before_submission(self):
        result = classify_execution(self.evidence())
        self.assertEqual(result["verdict"], APPLICATION_REQUIRED)
        self.assertTrue(result["application_allowed"])
        self.assertFalse(result["implementation_allowed"])

    def test_submitted_application_waits_for_assignment(self):
        result = classify_execution(
            self.evidence(application_state="submitted", assignment_state="unassigned")
        )
        self.assertEqual(result["verdict"], WAIT_PROVIDER_ASSIGNMENT)
        self.assertFalse(result["implementation_allowed"])

    def test_pending_assignment_waits(self):
        result = classify_execution(
            self.evidence(application_state="submitted", assignment_state="pending")
        )
        self.assertEqual(result["verdict"], WAIT_PROVIDER_ASSIGNMENT)

    def test_assigned_current_contributor_allows_implementation(self):
        result = classify_execution(
            self.evidence(
                application_state="submitted",
                assignment_state="assigned_current_contributor",
            )
        )
        self.assertEqual(result["verdict"], IMPLEMENTATION_READY)
        self.assertTrue(result["implementation_allowed"])

    def test_assigned_other_is_explicit(self):
        result = classify_execution(
            self.evidence(application_state="submitted", assignment_state="assigned_other")
        )
        self.assertEqual(result["verdict"], PROVIDER_ASSIGNED_OTHER)
        self.assertFalse(result["implementation_allowed"])

    def test_assignment_without_application_is_contradictory(self):
        result = classify_execution(
            self.evidence(
                application_state="not_submitted",
                assignment_state="assigned_current_contributor",
            )
        )
        self.assertEqual(result["verdict"], NEEDS_REFRESH)

    def test_rejected_application_is_research_only(self):
        result = classify_execution(
            self.evidence(application_state="rejected", assignment_state="unassigned")
        )
        self.assertEqual(result["verdict"], RESEARCH_ONLY)
        self.assertTrue(result["research_allowed"])

    def test_rejected_application_with_assignment_needs_refresh(self):
        result = classify_execution(
            self.evidence(
                application_state="rejected",
                assignment_state="assigned_current_contributor",
            )
        )
        self.assertEqual(result["verdict"], NEEDS_REFRESH)

    def test_pending_assignment_without_application_needs_refresh(self):
        result = classify_execution(
            self.evidence(application_state="not_submitted", assignment_state="pending")
        )
        self.assertEqual(result["verdict"], NEEDS_REFRESH)

    def test_open_pr_overlap_wins_over_provider_state(self):
        result = classify_execution(
            self.evidence(
                overlap_verdict=OVERLAP_OPEN_PR,
                application_state="submitted",
                assignment_state="assigned_current_contributor",
            )
        )
        self.assertEqual(result["verdict"], OVERLAP_EXISTING_WORK)
        self.assertFalse(result["implementation_allowed"])

    def test_satisfied_default_branch_is_terminal(self):
        result = classify_execution(
            self.evidence(overlap_verdict=SATISFIED_DEFAULT_BRANCH)
        )
        self.assertEqual(result["verdict"], CLOSED_OR_SATISFIED)
        self.assertFalse(result["research_allowed"])

    def test_closed_issue_is_terminal(self):
        result = classify_execution(
            self.evidence(issue_state="closed", overlap_verdict=ISSUE_CLOSED)
        )
        self.assertEqual(result["verdict"], CLOSED_OR_SATISFIED)

    def test_unverified_candidate_needs_refresh(self):
        result = classify_execution(
            self.evidence(grantfox_candidate_verified=False)
        )
        self.assertEqual(result["verdict"], NEEDS_REFRESH)

    def test_unobserved_provider_state_needs_refresh(self):
        result = classify_execution(
            self.evidence(provider_state_observed=False)
        )
        self.assertEqual(result["verdict"], NEEDS_REFRESH)

    def test_unknown_provider_values_need_refresh(self):
        result = classify_execution(
            self.evidence(application_state="mystery", assignment_state="unassigned")
        )
        self.assertEqual(result["verdict"], NEEDS_REFRESH)

    def test_overlap_refresh_propagates(self):
        result = classify_execution(
            self.evidence(overlap_verdict=OVERLAP_NEEDS_REFRESH)
        )
        self.assertEqual(result["verdict"], NEEDS_REFRESH)


if __name__ == "__main__":
    unittest.main(verbosity=2)
