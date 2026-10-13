import copy
import unittest
from unittest.mock import patch

import qualification as q

NOTICE = {
    "rfp_id": q.RFP_ID,
    "merx_notice_id": q.MERX_ID,
    "buyer": q.BUYER,
    "title": q.TITLE,
    "reported_deadline": q.REPORTED_DEADLINE,
    "discovery_sources": [
        {"uri": "https://example.invalid/a", "source_type": "procurement-index"},
        {"uri": "https://example.invalid/b", "source_type": "procurement-index"},
    ],
}


def packet():
    return {"notice": copy.deepcopy(NOTICE), "requirements": [], "evidence": []}


def source(sid="sol", sha="a" * 64, **kw):
    out = {
        "source_id": sid,
        "sha256": sha,
        "authority": q.TRUSTED_AUTHORITY,
        "current": True,
        "scope_complete": True,
        "deadline_utc": "2026-09-25T22:00:00Z",
        "kind": "SOLICITATION",
        "official_locator": "https://umanitoba.ca/example",
        "supersedes": [],
    }
    out.update(kw)
    return out


def evidence(eid="e1", status="PROVEN", **kw):
    out = {"evidence_id": eid, "status": status}
    if status == "PROVEN":
        out.update({"artifact_ref": "repo:path", "artifact_sha256": "b" * 64})
    out.update(kw)
    return out


def requirement(rid="r1", eid="e1", source_id="sol", source_sha="a" * 64, classification="MANDATORY"):
    return {
        "requirement_id": rid,
        "source_id": source_id,
        "source_sha256": source_sha,
        "classification": classification,
        "locator": "Section 1",
        "text": "Source-bound requirement",
        "evidence_ids": [] if eid is None else [eid],
    }


class QualificationTests(unittest.TestCase):
    def future(self):
        return patch("qualification._utc_now", return_value=q.datetime(2026, 9, 13, tzinfo=q.timezone.utc))

    def expired(self):
        return patch("qualification._utc_now", return_value=q.datetime(2026, 9, 26, tzinfo=q.timezone.utc))

    def test_discovery_holds(self):
        self.assertEqual("HOLD_CONTROLLING_PACK_REQUIRED", q.evaluate_discovery(packet())["status"])

    def test_discovery_caller_minted_trust_ignored(self):
        p = packet(); p["trusted_sources"] = [source()]
        self.assertEqual("HOLD_CONTROLLING_PACK_REQUIRED", q.evaluate_discovery(p)["status"])

    def test_wrong_rfp_invalid(self):
        p = packet(); p["notice"]["rfp_id"] = "wrong"
        self.assertEqual("INVALID", q.evaluate_discovery(p)["status"])

    def test_wrong_merx_invalid(self):
        p = packet(); p["notice"]["merx_notice_id"] = "wrong"
        self.assertEqual("INVALID", q.evaluate_discovery(p)["status"])

    def test_duplicate_discovery_source_invalid(self):
        p = packet(); p["notice"]["discovery_sources"][1]["uri"] = p["notice"]["discovery_sources"][0]["uri"]
        self.assertEqual("INVALID", q.evaluate_discovery(p)["status"])

    def test_untrusted_authority_invalid(self):
        with self.future():
            self.assertEqual("INVALID", q.evaluate_with_trusted_sources(packet(), [source(authority="CALLER")])["status"])

    def test_bad_source_hash_invalid(self):
        with self.future():
            self.assertEqual("INVALID", q.evaluate_with_trusted_sources(packet(), [source(sha="BAD")])["status"])

    def test_non_boolean_current_invalid(self):
        s = source(); s["current"] = 1
        with self.future():
            self.assertEqual("INVALID", q.evaluate_with_trusted_sources(packet(), [s])["status"])

    def test_duplicate_source_id_invalid(self):
        with self.future():
            self.assertEqual("INVALID", q.evaluate_with_trusted_sources(packet(), [source(), source()])["status"])

    def test_two_complete_current_solicitations_invalid(self):
        with self.future():
            self.assertEqual("INVALID", q.evaluate_with_trusted_sources(packet(), [source("a"), source("b", sha="c" * 64)])["status"])

    def test_superseded_source_must_be_noncurrent(self):
        old = source("old", scope_complete=False)
        new = source("sol", supersedes=["old"])
        with self.future():
            self.assertEqual("INVALID", q.evaluate_with_trusted_sources(packet(), [old, new])["status"])

    def test_missing_superseded_source_invalid(self):
        s = source(supersedes=["missing"])
        with self.future():
            self.assertEqual("INVALID", q.evaluate_with_trusted_sources(packet(), [s])["status"])

    def test_expired_deadline_holds(self):
        with self.expired():
            self.assertEqual("HOLD_DEADLINE_REVERIFY", q.evaluate_with_trusted_sources(packet(), [source()])["status"])

    def test_official_pack_without_requirements_holds(self):
        with self.future():
            self.assertEqual("HOLD_REQUIREMENT_EXTRACTION_REQUIRED", q.evaluate_with_trusted_sources(packet(), [source()])["status"])

    def test_unknown_evidence_holds(self):
        p = packet(); p["evidence"] = [evidence(status="UNKNOWN")]; p["requirements"] = [requirement()]
        with self.future():
            self.assertEqual("HOLD_MANDATORY_GAPS", q.evaluate_with_trusted_sources(p, [source()])["status"])

    def test_missing_mandatory_evidence_holds(self):
        p = packet(); p["requirements"] = [requirement(eid=None)]
        with self.future():
            self.assertEqual("HOLD_MANDATORY_GAPS", q.evaluate_with_trusted_sources(p, [source()])["status"])

    def test_requirement_source_hash_must_match(self):
        p = packet(); p["evidence"] = [evidence()]; p["requirements"] = [requirement(source_sha="f" * 64)]
        with self.future():
            self.assertEqual("INVALID", q.evaluate_with_trusted_sources(p, [source()])["status"])

    def test_requirement_cannot_bind_superseded_source(self):
        old = source("old", current=False, scope_complete=False)
        new = source("sol", supersedes=["old"])
        p = packet(); p["evidence"] = [evidence()]; p["requirements"] = [requirement(source_id="old")]
        with self.future():
            self.assertEqual("INVALID", q.evaluate_with_trusted_sources(p, [old, new])["status"])

    def test_duplicate_requirement_invalid(self):
        p = packet(); p["evidence"] = [evidence()]; p["requirements"] = [requirement(), requirement()]
        with self.future():
            self.assertEqual("INVALID", q.evaluate_with_trusted_sources(p, [source()])["status"])

    def test_duplicate_evidence_invalid(self):
        p = packet(); p["evidence"] = [evidence(), evidence()]; p["requirements"] = [requirement()]
        with self.future():
            self.assertEqual("INVALID", q.evaluate_with_trusted_sources(p, [source()])["status"])

    def test_all_mandatory_proven_only_owner_review(self):
        p = packet(); p["evidence"] = [evidence()]; p["requirements"] = [requirement()]
        with self.future():
            receipt = q.evaluate_with_trusted_sources(p, [source()])
        self.assertEqual("READY_FOR_OWNER_REVIEW", receipt["status"])
        self.assertIs(receipt["submission_authorized"], False)
        self.assertIn("no buyer contact", receipt["authority"])

    def test_malformed_official_locator_invalid(self):
        with self.future():
            self.assertEqual("INVALID", q.evaluate_with_trusted_sources(packet(), [source(official_locator="not-a-url")])["status"])

    def test_deadline_requires_utc(self):
        with self.future():
            self.assertEqual("INVALID", q.evaluate_with_trusted_sources(packet(), [source(deadline_utc="2026-09-25T17:00:00")])["status"])


if __name__ == "__main__":
    unittest.main()
