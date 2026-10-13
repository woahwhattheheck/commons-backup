from __future__ import annotations

import unittest

from revenue.bidder_qualification_vault.v2.engine import RegistryError, compile_registry
from revenue.bidder_qualification_vault.v2.test_support import H, H2, evidence, payload, req


class CoreBTests(unittest.TestCase):
    def state(self, p):
        return compile_registry(p)["requirements"][0]["state"]

    def test_financial_class_mismatch_is_missing_not_substituted(self):
        ev = evidence("fin-reviewed", "FINANCIAL_STATEMENT", metadata={"financial_class": "REVIEWED"})
        p = payload([ev], [req("r", "FINANCIAL_STATEMENT", financial="AUDITED")])
        self.assertEqual(self.state(p), "MISSING")

    def test_financial_exact_class_is_candidate_only(self):
        ev = evidence("fin-reviewed", "FINANCIAL_STATEMENT", metadata={"financial_class": "REVIEWED"})
        p = payload([ev], [req("r", "FINANCIAL_STATEMENT", financial="REVIEWED")])
        out = compile_registry(p)
        self.assertEqual(out["requirements"][0]["state"], "CANDIDATE_VERIFIED")
        self.assertFalse(out["ready_for_bid_consumption"])

    def test_entity_transplant_cannot_green(self):
        ev = evidence("w9-other", "W9", entity_id="other-company")
        self.assertEqual(self.state(payload([ev], [req("r", "W9")])), "MISSING")

    def test_subject_scoped_evidence_cannot_satisfy_unscoped_requirement(self):
        ev = evidence("cert-person-a", "CERTIFICATION", subject_id="person-a")
        self.assertEqual(self.state(payload([ev], [req("r", "CERTIFICATION")])), "MISSING")

    def test_v1_subject_relabel_regression_same_evidence_digest_cannot_green(self):
        ev = evidence("w9-company-a", "W9", entity_id="company-a", sha=H)
        p = payload([ev], [req("r", "W9")])
        p["entity_id"] = "company-b"
        self.assertEqual(self.state(p), "MISSING")

    def test_opportunity_only_not_reused_globally(self):
        ev = evidence("w9-op", "W9", reuse_scope="OPPORTUNITY_ONLY", opportunity_ids=["usac-it-26-139"])
        self.assertEqual(self.state(payload([ev], [req("r", "W9", opportunity="wrf-5417")])), "MISSING")

    def test_opportunity_only_exact_scope_is_candidate_only(self):
        ev = evidence("w9-op", "W9", reuse_scope="OPPORTUNITY_ONLY", opportunity_ids=["usac-it-26-139"])
        out = compile_registry(payload([ev], [req("r", "W9", opportunity="usac-it-26-139")]))
        self.assertEqual(out["requirements"][0]["state"], "CANDIDATE_VERIFIED")
        self.assertFalse(out["ready_for_bid_consumption"])

    def test_submission_award_stage_separation(self):
        ev = evidence("coi-award", "INSURANCE_COI", stages=["AWARD"])
        p = payload([ev], [req("r", "INSURANCE_COI", stage="SUBMISSION")])
        self.assertEqual(self.state(p), "MISSING")

    def test_award_requirement_can_consume_award_candidate(self):
        ev = evidence("coi-award", "INSURANCE_COI", stages=["AWARD"])
        p = payload([ev], [req("r", "INSURANCE_COI", stage="AWARD")])
        out = compile_registry(p)
        self.assertEqual(out["requirements"][0]["state"], "CANDIDATE_VERIFIED")
        self.assertFalse(out["ready_for_bid_consumption"])
