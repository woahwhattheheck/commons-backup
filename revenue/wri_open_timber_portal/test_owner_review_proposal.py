from __future__ import annotations

import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parent
PROPOSAL = ROOT / "OWNER_REVIEW_PROPOSAL.md"
CHECKLIST = ROOT / "OWNER_REVIEW_CHECKLIST.json"

EXPECTED_BLOCKERS = {
    "submission_route",
    "deadline_time_and_timezone",
    "mandatory_qualifications",
    "required_forms_and_representations",
    "evaluation_method",
    "pricing_instructions",
    "role_title",
}

EXPECTED_WORKSTREAMS = {
    "reference_and_runtime_updates",
    "performance_and_security",
    "surface_fixes",
    "maintenance_and_bugs",
    "forward_improvement_list",
}


class OwnerReviewProposalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.proposal = PROPOSAL.read_text(encoding="utf-8")
        cls.checklist = json.loads(CHECKLIST.read_text(encoding="utf-8"))

    def test_all_controlling_blockers_remain_open(self) -> None:
        self.assertEqual(set(self.checklist["controlling_blockers"]), EXPECTED_BLOCKERS)
        self.assertEqual(
            self.checklist["artifact"]["submission_state"],
            "HOLD_CONTROLLING_SOURCE",
        )
        self.assertIsNone(self.checklist["artifact"]["exact_due_time_and_timezone"])

    def test_all_five_workstreams_are_present(self) -> None:
        self.assertEqual(set(self.checklist["workstreams"]), EXPECTED_WORKSTREAMS)
        for heading in (
            "Workstream 1 — Reference layers and runtime updates",
            "Workstream 2 — Performance and security",
            "Workstream 3 — Targeted platform fixes",
            "Workstream 4 — Maintenance and bug solving",
            "Workstream 5 — Forward improvement register",
        ):
            self.assertIn(heading, self.proposal)
        self.assertGreaterEqual(self.proposal.count("**Acceptance evidence.**"), 5)

    def test_buyer_repo_baseline_is_carried(self) -> None:
        for token in self.checklist["technical_baseline_tokens"]:
            self.assertIn(token, self.proposal)
        self.assertTrue(
            self.checklist["source_lineage"]["buyer_repo_binding"].startswith(
                "wri/fti_api@"
            )
        )

    def test_company_claims_remain_owner_evidence(self) -> None:
        self.assertEqual(
            set(self.checklist["owner_evidence_required"]),
            {
                "legal_vendor_eligibility",
                "named_staffing",
                "relevant_past_performance",
                "ruby_rails_delivery",
            },
        )
        self.assertIn("[OWNER EVIDENCE REQUIRED BEFORE SUBMISSION]", self.proposal)
        self.assertIn("does not invent biographies", self.proposal)

    def test_secondary_budget_is_not_promoted_to_offer(self) -> None:
        pricing = self.checklist["pricing"]
        self.assertIsNone(pricing["amount_minor"])
        self.assertEqual(pricing["status"], "OWNER_DECISION_REQUIRED")
        self.assertFalse(pricing["secondary_budget_authoritative"])
        self.assertNotIn("$9,900", self.proposal)
        self.assertIsNone(re.search(r"\$\s*\d", self.proposal))

    def test_role_title_conflict_stays_explicit(self) -> None:
        self.assertIn("formal WRI role title", self.proposal)
        self.assertIn("secondary indexes conflict", self.proposal)

    def test_external_authority_is_all_false(self) -> None:
        self.assertTrue(self.checklist["external_authority"])
        self.assertTrue(
            all(value is False for value in self.checklist["external_authority"].values())
        )
        self.assertIn("not authorized by this artifact", self.proposal)
        self.assertIn("not claimed", self.proposal)

    def test_artifact_is_substantial_not_stub(self) -> None:
        self.assertGreater(len(self.proposal.split()), 1000)
        required_sections = {
            "## Executive summary",
            "## Delivery principles",
            "## Technical baseline",
            "## Work plan",
            "## Six-month operating cadence",
            "## Quality, security, and release evidence",
            "## Coordination and handoff",
            "## Organization, staffing, and past performance",
            "## Commercial proposal",
            "## Submission blockers that must be resolved",
        }
        for section in required_sections:
            self.assertIn(section, self.proposal)


if __name__ == "__main__":
    unittest.main()
