from __future__ import annotations

import unittest

from revenue.bidder_qualification_vault.v2.engine import RegistryError, compile_registry
from revenue.bidder_qualification_vault.v2.test_support import H, H2, evidence, payload, req


class CoreATests(unittest.TestCase):
    def state(self, p):
        return compile_registry(p)["requirements"][0]["state"]

    def test_candidate_verified_never_mints_bid_authority(self):
        out = compile_registry(payload())
        self.assertEqual(out["requirements"][0]["state"], "CANDIDATE_VERIFIED")
        self.assertTrue(out["candidate_requirements_satisfied"])
        self.assertFalse(out["ready_for_bid_consumption"])
        self.assertEqual(out["source_authentication"], "NOT_PERFORMED")
        self.assertEqual(out["as_of_authority"], "CALLER_SUPPLIED_NOT_CURRENT_AUTHORITY")
        self.assertTrue(all(v is False for v in out["authority"].values()))

    def test_expired_coi(self):
        ev = evidence("coi-1", "INSURANCE_COI", expires="2026-09-14T03:49:59Z")
        self.assertEqual(self.state(payload([ev], [req("r", "INSURANCE_COI")])), "EXPIRED")

    def test_exact_expiry_boundary_is_expired(self):
        ev = evidence("coi-1", "INSURANCE_COI", expires="2026-09-14T03:50:00Z")
        self.assertEqual(self.state(payload([ev], [req("r", "INSURANCE_COI")])), "EXPIRED")

    def test_superseded_w9(self):
        old = evidence("w9-old", "W9", sha=H)
        new = evidence("w9-new", "W9", sha=H2, supersedes="w9-old")
        out = compile_registry(payload([old, new], [req("r", "W9")]))
        self.assertEqual(out["requirements"][0]["state"], "CANDIDATE_VERIFIED")
        self.assertEqual(out["requirements"][0]["evidence_id"], "w9-new")
        self.assertFalse(out["ready_for_bid_consumption"])

    def test_revoked_registration_is_superseded(self):
        ev = evidence("reg-1", "REGISTRATION", revoked_at="2026-09-10T00:00:00Z")
        self.assertEqual(self.state(payload([ev], [req("r", "REGISTRATION")])), "SUPERSEDED")

    def test_pending_private_review_holds(self):
        ev = evidence("cv-1", "STAFF_CV", subject_id="staff-a", verification="PENDING_PRIVATE_REVIEW", verifier="HUMAN_OWNER")
        self.assertEqual(self.state(payload([ev], [req("r", "STAFF_CV", subject_id="staff-a")])), "HOLD_PRIVATE_REVIEW")

    def test_self_asserted_cannot_be_marked_verified(self):
        ev = evidence("x", "CERTIFICATION", source_class="SELF_ASSERTED", verification="VERIFIED")
        with self.assertRaisesRegex(RegistryError, "SELF_ASSERTED_CANNOT_BE_VERIFIED"):
            compile_registry(payload([ev], [req("r", "CERTIFICATION")]))

    def test_reference_permission_is_independent(self):
        perf = evidence("ref-perf", "REFERENCE_PERFORMANCE", subject_id="ref-a")
        reqs = [req("a", "REFERENCE_PERFORMANCE", subject_id="ref-a"), req("b", "REFERENCE_PERMISSION", subject_id="ref-a")]
        out = compile_registry(payload([perf], reqs))
        states = {r["requirement_id"]: r["state"] for r in out["requirements"]}
        self.assertEqual(states, {"a": "CANDIDATE_VERIFIED", "b": "MISSING"})
        self.assertFalse(out["candidate_requirements_satisfied"])
        self.assertFalse(out["ready_for_bid_consumption"])

    def test_reference_contactability_is_independent(self):
        perm = evidence("ref-perm", "REFERENCE_PERMISSION", subject_id="ref-a")
        reqs = [req("a", "REFERENCE_PERMISSION", subject_id="ref-a"), req("b", "REFERENCE_CONTACTABILITY", subject_id="ref-a")]
        out = compile_registry(payload([perm], reqs))
        self.assertEqual([r["state"] for r in out["requirements"]], ["CANDIDATE_VERIFIED", "MISSING"])
