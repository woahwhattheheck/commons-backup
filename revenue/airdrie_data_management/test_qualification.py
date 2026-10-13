import copy
import os
import unittest
from unittest.mock import patch

import qualification as q


NOTICE = {
    "solicitation_id": "AB-2026-06233",
    "buyer": "City of Airdrie",
    "title": "Data Management Consultant",
    "reported_deadline_local": "2026-10-06 20:00 (timezone unverified)",
    "discovery_sources": [
        {"uri": "https://example.invalid/a", "source_type": "procurement-index"},
        {"uri": "https://example.invalid/b", "source_type": "procurement-index"},
    ],
}
HOST_KEY = bytes(range(32))
ATTACKER_KEY = bytes(range(1, 33))
ISSUED_AT = "2026-09-12T23:00:00Z"


def packet():
    return {"notice": copy.deepcopy(NOTICE), "requirements": [], "evidence": []}


def source(sid="sol", sha="a" * 64, **kw):
    out = {
        "source_id": sid,
        "sha256": sha,
        "authority": q.TRUSTED_AUTHORITY,
        "current": True,
        "scope_complete": True,
        "deadline_utc": "2026-10-07T02:00:00Z",
        "kind": "SOLICITATION",
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
        "text": "Demonstrated requirement",
        "evidence_ids": [] if eid is None else [eid],
    }


def host_env(key=HOST_KEY):
    return patch.dict(os.environ, {q.AUTHORITY_KEY_ENV: key.hex()}, clear=False)


def authority(sources, issued_at=ISSUED_AT, key=HOST_KEY):
    with host_env(key), patch(
        "qualification._utc_now",
        return_value=q.datetime(2026, 9, 13, tzinfo=q.timezone.utc),
    ):
        return q.issue_host_authority_set(copy.deepcopy(sources), issued_at=issued_at)


def trusted_eval(p, sources, authority_set=None, key=HOST_KEY):
    if authority_set is None:
        try:
            authority_set = authority(sources, key=key)
        except q.QualificationError:
            authority_set = authority([source()], key=key)
    with host_env(key):
        return q.evaluate_with_trusted_sources(p, sources, authority_set)


class QualificationTests(unittest.TestCase):
    def future(self):
        return patch("qualification._utc_now", return_value=q.datetime(2026, 9, 13, tzinfo=q.timezone.utc))

    def expired(self):
        return patch("qualification._utc_now", return_value=q.datetime(2026, 10, 7, tzinfo=q.timezone.utc))

    def test_discovery_can_only_hold(self):
        with self.future():
            self.assertEqual("HOLD_CONTROLLING_PACK_REQUIRED", q.evaluate_discovery(packet())["status"])

    def test_discovery_stays_hold_even_after_reported_date(self):
        with self.expired():
            self.assertEqual("HOLD_CONTROLLING_PACK_REQUIRED", q.evaluate_discovery(packet())["status"])

    def test_trusted_deadline_reverify(self):
        s = source(deadline_utc="2026-10-06T20:00:00Z")
        a = authority([s])
        with self.expired(), host_env():
            self.assertEqual("HOLD_DEADLINE_REVERIFY", q.evaluate_with_trusted_sources(packet(), [s], a)["status"])

    def test_notice_identity_drift_is_invalid(self):
        p = packet(); p["notice"]["buyer"] = "Someone Else"
        with self.future():
            self.assertEqual("INVALID", q.evaluate_discovery(p)["status"])

    def test_duplicate_discovery_source_invalid(self):
        p = packet(); p["notice"]["discovery_sources"][1]["uri"] = p["notice"]["discovery_sources"][0]["uri"]
        with self.future():
            self.assertEqual("INVALID", q.evaluate_discovery(p)["status"])

    def test_trusted_pack_without_extraction_holds(self):
        with self.future():
            self.assertEqual(
                "HOLD_REQUIREMENT_EXTRACTION_REQUIRED",
                trusted_eval(packet(), [source()])["status"],
            )

    def test_untrusted_authority_invalid(self):
        with self.future():
            self.assertEqual(
                "INVALID",
                trusted_eval(packet(), [source(authority="CALLER")])["status"],
            )

    def test_source_hash_shape_invalid(self):
        with self.future():
            self.assertEqual("INVALID", trusted_eval(packet(), [source(sha="AA")])["status"])

    def test_two_current_complete_solicitations_invalid(self):
        with self.future():
            self.assertEqual(
                "INVALID",
                trusted_eval(packet(), [source("s1"), source("s2", sha="c" * 64)])["status"],
            )

    def test_supersession_requires_old_noncurrent(self):
        old = source("old", scope_complete=False)
        new = source("new", sha="c" * 64, supersedes=["old"])
        with self.future():
            self.assertEqual("INVALID", trusted_eval(packet(), [old, new])["status"])

    def test_requirement_cannot_bind_superseded_source(self):
        old = source("old", current=False, scope_complete=False)
        new = source("sol", supersedes=["old"])
        p = packet(); p["evidence"] = [evidence()]; p["requirements"] = [requirement(source_id="old")]
        with self.future():
            self.assertEqual("INVALID", trusted_eval(p, [old, new])["status"])

    def test_requirement_source_sha_must_match(self):
        p = packet(); p["evidence"] = [evidence()]; p["requirements"] = [requirement(source_sha="f" * 64)]
        with self.future():
            self.assertEqual("INVALID", trusted_eval(p, [source()])["status"])

    def test_missing_mandatory_evidence_holds(self):
        p = packet(); p["requirements"] = [requirement(eid=None)]
        with self.future():
            receipt = trusted_eval(p, [source()])
        self.assertEqual("HOLD_MANDATORY_GAPS", receipt["status"])
        self.assertFalse(receipt.get("submission_authorized", False))

    def test_unknown_mandatory_evidence_holds(self):
        p = packet(); p["evidence"] = [evidence(status="UNKNOWN")]; p["requirements"] = [requirement()]
        with self.future():
            self.assertEqual("HOLD_MANDATORY_GAPS", trusted_eval(p, [source()])["status"])

    def test_all_mandatory_proven_only_ready_for_owner_review(self):
        p = packet(); p["evidence"] = [evidence()]; p["requirements"] = [requirement()]
        with self.future():
            receipt = trusted_eval(p, [source()])
        self.assertEqual("READY_FOR_OWNER_REVIEW", receipt["status"])
        self.assertIs(receipt["submission_authorized"], False)
        self.assertIn("no buyer contact", receipt["authority"])
        self.assertEqual(q.AUTHORITY_KEY_ID, receipt["trusted_authority_key_id"])
        self.assertRegex(receipt["trusted_authority_sha256"], r"^[0-9a-f]{64}$")

    def test_duplicate_requirement_invalid(self):
        p = packet(); p["evidence"] = [evidence()]; p["requirements"] = [requirement(), requirement()]
        with self.future():
            self.assertEqual("INVALID", trusted_eval(p, [source()])["status"])

    def test_duplicate_evidence_invalid(self):
        p = packet(); p["evidence"] = [evidence(), evidence()]; p["requirements"] = [requirement()]
        with self.future():
            self.assertEqual("INVALID", trusted_eval(p, [source()])["status"])

    def test_bool_not_accepted_as_current(self):
        s = source(); s["current"] = 1
        with self.future():
            self.assertEqual("INVALID", trusted_eval(packet(), [s])["status"])

    def test_cli_surface_has_no_trusted_source_argument(self):
        p = packet()
        p["trusted_sources"] = [source()]
        p["authority_set"] = authority([source()])
        with self.future():
            self.assertEqual("HOLD_CONTROLLING_PACK_REQUIRED", q.evaluate_discovery(p)["status"])

    def test_caller_minted_self_consistent_authority_with_wrong_capability_is_invalid(self):
        s = source()
        p = packet(); p["evidence"] = [evidence()]; p["requirements"] = [requirement()]
        forged = authority([s], key=ATTACKER_KEY)
        with self.future():
            receipt = trusted_eval(p, [s], forged, key=HOST_KEY)
        self.assertEqual("INVALID", receipt["status"])
        self.assertIn("MAC verification failed", receipt["errors"][0])

    def test_missing_host_capability_is_invalid(self):
        s = source(); a = authority([s])
        with patch.dict(os.environ, {}, clear=True), self.future():
            receipt = q.evaluate_with_trusted_sources(packet(), [s], a)
        self.assertEqual("INVALID", receipt["status"])
        self.assertIn("not provisioned", receipt["errors"][0])

    def test_short_host_capability_is_invalid(self):
        s = source(); a = authority([s])
        with patch.dict(os.environ, {q.AUTHORITY_KEY_ENV: "00" * 16}, clear=True), self.future():
            receipt = q.evaluate_with_trusted_sources(packet(), [s], a)
        self.assertEqual("INVALID", receipt["status"])
        self.assertIn("at least 32 bytes", receipt["errors"][0])

    def test_wrong_authority_key_id_is_invalid_even_with_valid_mac(self):
        s = source(); a = authority([s]); a["key_id"] = "caller-key"
        with self.future():
            self.assertEqual("INVALID", trusted_eval(packet(), [s], a)["status"])

    def test_source_digest_mutation_after_authority_issue_is_invalid(self):
        original = source(); a = authority([original]); mutated = copy.deepcopy(original); mutated["sha256"] = "c" * 64
        with self.future():
            self.assertEqual("INVALID", trusted_eval(packet(), [mutated], a)["status"])

    def test_deadline_mutation_after_authority_issue_is_invalid(self):
        original = source(); a = authority([original]); mutated = copy.deepcopy(original); mutated["deadline_utc"] = "2026-10-08T02:00:00Z"
        with self.future():
            self.assertEqual("INVALID", trusted_eval(packet(), [mutated], a)["status"])

    def test_supersession_mutation_after_authority_issue_is_invalid(self):
        old = source("old", sha="d" * 64, current=False, scope_complete=False)
        new = source("sol", supersedes=["old"])
        a = authority([old, new])
        mutated_new = copy.deepcopy(new); mutated_new["supersedes"] = []
        with self.future():
            self.assertEqual("INVALID", trusted_eval(packet(), [old, mutated_new], a)["status"])

    def test_cross_solicitation_authority_transplant_is_invalid(self):
        s = source(); a = authority([s]); a["solicitation_id"] = "OTHER-2026-1"
        with self.future():
            self.assertEqual("INVALID", trusted_eval(packet(), [s], a)["status"])

    def test_unused_trusted_source_added_after_authority_issue_is_invalid(self):
        s = source(); a = authority([s])
        extra = source("old", sha="d" * 64, current=False, scope_complete=False)
        with self.future():
            self.assertEqual("INVALID", trusted_eval(packet(), [s, extra], a)["status"])

    def test_future_authority_generation_is_invalid(self):
        s = source(); a = authority([s]); a["issued_at"] = "2026-09-14T00:00:00Z"
        with self.future():
            self.assertEqual("INVALID", trusted_eval(packet(), [s], a)["status"])

    def test_source_order_does_not_change_authenticated_generation(self):
        old = source("old", sha="d" * 64, current=False, scope_complete=False)
        new = source("sol", supersedes=["old"])
        a = authority([old, new])
        with self.future():
            r1 = trusted_eval(packet(), [old, new], a)
            r2 = trusted_eval(packet(), [new, old], a)
        self.assertEqual("HOLD_REQUIREMENT_EXTRACTION_REQUIRED", r1["status"])
        self.assertEqual(r1["trusted_authority_sha256"], r2["trusted_authority_sha256"])

    def test_legacy_two_argument_trusted_call_is_not_available(self):
        with self.assertRaises(TypeError):
            q.evaluate_with_trusted_sources(packet(), [source()])


if __name__ == "__main__":
    unittest.main()
