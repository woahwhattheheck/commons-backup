from __future__ import annotations

import copy
import hashlib
import json
import unittest
import urllib.parse

from revenue.commercial_opportunity_custody import custody as c


IDENTITY = {
    "schema": c.SCHEMA,
    "repo": "woahwhattheheck/commons",
    "buyer_scope": "utilitysafety.ca",
    "authority_scope": "utilitysafety.ca",
    "opportunity_id": "data-ai-rfp-2026",
}
SRC1 = "11" * 32
SRC2 = "22" * 32
EVIDENCE = "33" * 32
ANCHOR1 = "a" * 40
ANCHOR2 = "b" * 40
T1 = "2026-09-14T01:00:00Z"
T2 = "2026-09-14T01:01:00Z"
T3 = "2026-09-14T01:02:00Z"


class MemoryGitHub:
    def __init__(self):
        self.tags = {}
        self.refs = {}
        self.posts = []

    @staticmethod
    def _sha(payload):
        return hashlib.sha1(c.canon_json(payload)).hexdigest()

    def __call__(self, method, path, body):
        self.posts.append((method, path, copy.deepcopy(body)))
        if method == "POST" and path.endswith("/git/tags"):
            sha = self._sha(body)
            stored = copy.deepcopy(body)
            stored["sha"] = sha
            stored["object"] = {"sha": body["object"], "type": body["type"]}
            stored.pop("type", None)
            self.tags[sha] = stored
            return 201, {"sha": sha}
        if method == "POST" and path.endswith("/git/refs"):
            ref = body["ref"]
            if ref in self.refs:
                return 422, {"message": "Reference already exists"}
            self.refs[ref] = body["sha"]
            return 201, {"ref": ref, "object": {"type": "tag", "sha": body["sha"]}}
        marker = "/git/matching-refs/"
        if method == "GET" and marker in path:
            suffix = urllib.parse.unquote(path.split(marker, 1)[1])
            prefix = "refs/" + suffix
            rows = []
            for ref, sha in sorted(self.refs.items()):
                if ref.startswith(prefix):
                    rows.append({"ref": ref, "object": {"type": "tag", "sha": sha}})
            return 200, rows
        marker = "/git/ref/"
        if method == "GET" and marker in path:
            suffix = urllib.parse.unquote(path.split(marker, 1)[1])
            ref = "refs/" + suffix
            if ref not in self.refs:
                return 404, {"message": "Not Found"}
            sha = self.refs[ref]
            return 200, {"ref": ref, "object": {"type": "tag", "sha": sha}}
        marker = "/git/tags/"
        if method == "GET" and marker in path:
            sha = path.rsplit("/", 1)[-1]
            if sha not in self.tags:
                return 404, {"message": "Not Found"}
            return 200, copy.deepcopy(self.tags[sha])
        raise AssertionError((method, path, body))


class CustodyTests(unittest.TestCase):
    def acquire(self, git=None, owner="ZLF-B8R3", op="USP-DATA-AI-RFP-ZLFB8R3-20260913"):
        git = git or MemoryGitHub()
        receipt = c.acquire_whole(
            IDENTITY,
            actor_owner=owner,
            actor_operation=op,
            source_generation_sha256=SRC1,
            anchor_sha=ANCHOR1,
            observed_at=T1,
            transport=git,
        )
        self.assertTrue(receipt["event_appended"])
        self.assertTrue(c.verify_mutation_receipt(receipt))
        return git, receipt

    def test_identity_normalizes_case_but_ref_contains_no_domain(self):
        raw = dict(IDENTITY)
        raw["buyer_scope"] = "UtilitySafety.CA."
        raw["authority_scope"] = "UTILITYSAFETY.CA"
        raw["opportunity_id"] = "DATA-AI-RFP-2026"
        identity = c.Identity.parse(raw)
        self.assertEqual(identity.buyer_scope, "utilitysafety.ca")
        self.assertEqual(identity.authority_scope, "utilitysafety.ca")
        self.assertEqual(identity.opportunity_id, "data-ai-rfp-2026")
        self.assertNotIn("utilitysafety", identity.ref_prefix)

    def test_external_id_same_but_other_buyer_is_different_seam(self):
        one = c.Identity.parse(IDENTITY)
        other = dict(IDENTITY)
        other["buyer_scope"] = "example.com"
        two = c.Identity.parse(other)
        self.assertNotEqual(one.seam_sha256, two.seam_sha256)

    def test_acquire_live_readback_and_old_receipt_not_authority(self):
        git, receipt = self.acquire()
        state = c.read_live_state(IDENTITY, git)
        self.assertEqual(state.whole_owner, "ZLF-B8R3")
        self.assertEqual(state.generation, 1)
        check = c.authorize_internal_work(
            IDENTITY,
            actor_owner="ZLF-B8R3",
            actor_operation="USP-DATA-AI-RFP-ZLFB8R3-20260913",
            lane="proposal",
            transport=git,
        )
        self.assertTrue(check["internal_work_authorized"])
        self.assertEqual(check["basis"], "WHOLE")
        self.assertTrue(receipt["must_reread_live_authority_before_work"])
        self.assertFalse(receipt["external_send_authorized"])

    def test_sequential_second_whole_claim_holds_without_ref_write(self):
        git, _ = self.acquire()
        before_refs = dict(git.refs)
        loser = c.acquire_whole(
            IDENTITY,
            actor_owner="ZNQ-R6M3",
            actor_operation="UTILITY-SAFETY-DATA-AI-RFP-ZNQR6M3-20260913",
            source_generation_sha256=SRC1,
            anchor_sha=ANCHOR1,
            observed_at=T2,
            transport=git,
        )
        self.assertFalse(loser["event_appended"])
        self.assertIn("whole custody already active", loser["reason"])
        self.assertEqual(before_refs, git.refs)

    def test_exact_race_two_prepared_generation_one_events_only_one_wins(self):
        identity = c.Identity.parse(IDENTITY)
        empty = c.empty_state(identity)
        a = c._plan_event(
            empty, action="ACQUIRE_WHOLE", actor_owner="ZLF-B8R3",
            actor_operation="USP-DATA-AI-RFP-ZLFB8R3-20260913",
            target_owner="ZLF-B8R3", target_operation="USP-DATA-AI-RFP-ZLFB8R3-20260913",
            lane=None, source_generation_sha256=SRC1, anchor_sha=ANCHOR1,
            observed_at=T1, legacy_evidence_sha256=None,
        )
        b = c._plan_event(
            empty, action="ACQUIRE_WHOLE", actor_owner="ZNQ-R6M3",
            actor_operation="UTILITY-SAFETY-DATA-AI-RFP-ZNQR6M3-20260913",
            target_owner="ZNQ-R6M3", target_operation="UTILITY-SAFETY-DATA-AI-RFP-ZNQR6M3-20260913",
            lane=None, source_generation_sha256=SRC1, anchor_sha=ANCHOR1,
            observed_at=T1, legacy_evidence_sha256=None,
        )
        git = MemoryGitHub()
        ra = c._publish_planned_event(identity, a, git)
        rb = c._publish_planned_event(identity, b, git)
        self.assertTrue(ra["event_appended"])
        self.assertFalse(rb["event_appended"])
        self.assertEqual(rb["reason"], "GENERATION_HELD_BY_OTHER")
        self.assertEqual(c.read_live_state(IDENTITY, git).whole_owner, "ZLF-B8R3")

    def test_whole_owner_can_delegate_proposal_only(self):
        git, _ = self.acquire()
        receipt = c.set_delegate(
            IDENTITY,
            actor_owner="ZLF-B8R3", actor_operation="USP-DATA-AI-RFP-ZLFB8R3-20260913",
            lane="proposal", target_owner="ZTQ-K7M3", target_operation="USP-PROPOSAL-ZTQK7M3-20260913",
            source_generation_sha256=SRC1, anchor_sha=ANCHOR1, observed_at=T2, transport=git,
        )
        self.assertTrue(receipt["event_appended"])
        yes = c.authorize_internal_work(IDENTITY, actor_owner="ZTQ-K7M3", actor_operation="USP-PROPOSAL-ZTQK7M3-20260913", lane="proposal", transport=git)
        no = c.authorize_internal_work(IDENTITY, actor_owner="ZTQ-K7M3", actor_operation="USP-PROPOSAL-ZTQK7M3-20260913", lane="outreach", transport=git)
        self.assertTrue(yes["internal_work_authorized"])
        self.assertEqual(yes["basis"], "DELEGATE:proposal")
        self.assertFalse(no["internal_work_authorized"])

    def test_delegate_cannot_self_expand_or_transfer(self):
        git, _ = self.acquire()
        c.set_delegate(
            IDENTITY, actor_owner="ZLF-B8R3", actor_operation="USP-DATA-AI-RFP-ZLFB8R3-20260913",
            lane="proposal", target_owner="ZTQ-K7M3", target_operation="USP-PROPOSAL-ZTQK7M3-20260913",
            source_generation_sha256=SRC1, anchor_sha=ANCHOR1, observed_at=T2, transport=git,
        )
        denied = c.set_delegate(
            IDENTITY, actor_owner="ZTQ-K7M3", actor_operation="USP-PROPOSAL-ZTQK7M3-20260913",
            lane="outreach", target_owner="ZNQ-R6M3", target_operation="USP-OUTREACH-ZNQR6M3-20260913",
            source_generation_sha256=SRC1, anchor_sha=ANCHOR1, observed_at=T3, transport=git,
        )
        self.assertFalse(denied["event_appended"])
        self.assertIn("not current whole owner", denied["reason"])

    def test_transfer_clears_delegates_and_invalidates_old_owner_operation(self):
        git, _ = self.acquire()
        c.set_delegate(
            IDENTITY, actor_owner="ZLF-B8R3", actor_operation="USP-DATA-AI-RFP-ZLFB8R3-20260913",
            lane="proposal", target_owner="ZTQ-K7M3", target_operation="USP-PROPOSAL-ZTQK7M3-20260913",
            source_generation_sha256=SRC1, anchor_sha=ANCHOR1, observed_at=T2, transport=git,
        )
        moved = c.transfer_whole(
            IDENTITY, actor_owner="ZLF-B8R3", actor_operation="USP-DATA-AI-RFP-ZLFB8R3-20260913",
            target_owner="ZHB-Q8V5", target_operation="COMMERCIAL-OPPORTUNITY-CUSTODY-LEASE-ZHBQ8V5-20260913",
            source_generation_sha256=SRC1, anchor_sha=ANCHOR2, observed_at=T3, transport=git,
        )
        self.assertTrue(moved["event_appended"])
        state = c.read_live_state(IDENTITY, git)
        self.assertEqual(state.whole_owner, "ZHB-Q8V5")
        self.assertEqual(state.delegates, {})
        old = c.authorize_internal_work(IDENTITY, actor_owner="ZLF-B8R3", actor_operation="USP-DATA-AI-RFP-ZLFB8R3-20260913", lane="whole", transport=git)
        delegate = c.authorize_internal_work(IDENTITY, actor_owner="ZTQ-K7M3", actor_operation="USP-PROPOSAL-ZTQK7M3-20260913", lane="proposal", transport=git)
        self.assertFalse(old["internal_work_authorized"])
        self.assertFalse(delegate["internal_work_authorized"])

    def test_release_clears_delegate_and_allows_atomic_reacquire_only_with_same_source_generation(self):
        git, _ = self.acquire()
        released = c.release_whole(
            IDENTITY, actor_owner="ZLF-B8R3", actor_operation="USP-DATA-AI-RFP-ZLFB8R3-20260913",
            source_generation_sha256=SRC1, anchor_sha=ANCHOR1, observed_at=T2, transport=git,
        )
        self.assertTrue(released["event_appended"])
        state = c.read_live_state(IDENTITY, git)
        self.assertIsNone(state.whole_owner)
        bad = c.acquire_whole(
            IDENTITY, actor_owner="ZHB-Q8V5", actor_operation="COMMERCIAL-OPPORTUNITY-CUSTODY-LEASE-ZHBQ8V5-20260913",
            source_generation_sha256=SRC2, anchor_sha=ANCHOR2, observed_at=T3, transport=git,
        )
        self.assertFalse(bad["event_appended"])
        good = c.acquire_whole(
            IDENTITY, actor_owner="ZHB-Q8V5", actor_operation="COMMERCIAL-OPPORTUNITY-CUSTODY-LEASE-ZHBQ8V5-20260913",
            source_generation_sha256=SRC1, anchor_sha=ANCHOR2, observed_at=T3, transport=git,
        )
        self.assertTrue(good["event_appended"])

    def test_source_revision_updates_without_seam_split(self):
        git, _ = self.acquire()
        before = c.Identity.parse(IDENTITY).seam_sha256
        receipt = c.update_source(
            IDENTITY, actor_owner="ZLF-B8R3", actor_operation="USP-DATA-AI-RFP-ZLFB8R3-20260913",
            new_source_generation_sha256=SRC2, anchor_sha=ANCHOR2, observed_at=T2, transport=git,
        )
        self.assertTrue(receipt["event_appended"])
        state = c.read_live_state(IDENTITY, git)
        self.assertEqual(state.source_generation_sha256, SRC2)
        self.assertEqual(state.identity.seam_sha256, before)
        stale = c.set_delegate(
            IDENTITY, actor_owner="ZLF-B8R3", actor_operation="USP-DATA-AI-RFP-ZLFB8R3-20260913",
            lane="proposal", target_owner="ZTQ-K7M3", target_operation="USP-PROPOSAL-ZTQK7M3-20260913",
            source_generation_sha256=SRC1, anchor_sha=ANCHOR2, observed_at=T3, transport=git,
        )
        self.assertFalse(stale["event_appended"])
        self.assertIn("stale or rewritten source generation", stale["reason"])

    def test_stale_actor_operation_same_seat_cannot_mutate_after_transfer_back(self):
        git, _ = self.acquire()
        c.transfer_whole(
            IDENTITY, actor_owner="ZLF-B8R3", actor_operation="USP-DATA-AI-RFP-ZLFB8R3-20260913",
            target_owner="ZHB-Q8V5", target_operation="COMMERCIAL-OPPORTUNITY-CUSTODY-LEASE-ZHBQ8V5-20260913",
            source_generation_sha256=SRC1, anchor_sha=ANCHOR1, observed_at=T2, transport=git,
        )
        c.transfer_whole(
            IDENTITY, actor_owner="ZHB-Q8V5", actor_operation="COMMERCIAL-OPPORTUNITY-CUSTODY-LEASE-ZHBQ8V5-20260913",
            target_owner="ZLF-B8R3", target_operation="USP-RECOVERED-NEW-OP-20260913",
            source_generation_sha256=SRC1, anchor_sha=ANCHOR2, observed_at=T3, transport=git,
        )
        stale = c.release_whole(
            IDENTITY, actor_owner="ZLF-B8R3", actor_operation="USP-DATA-AI-RFP-ZLFB8R3-20260913",
            source_generation_sha256=SRC1, anchor_sha=ANCHOR2, observed_at="2026-09-14T01:03:00Z", transport=git,
        )
        self.assertFalse(stale["event_appended"])
        self.assertIn("not current whole owner", stale["reason"])

    def test_replaced_live_ref_breaks_authority_even_if_old_receipt_verifies(self):
        git, receipt = self.acquire()
        self.assertTrue(c.verify_mutation_receipt(receipt))
        ref = next(iter(git.refs))
        git.refs[ref] = "f" * 40
        with self.assertRaisesRegex(c.CustodyError, "LIVE_TAG_UNPROVEN"):
            c.read_live_state(IDENTITY, git)

    def test_generation_gap_fails_closed(self):
        git, _ = self.acquire()
        identity = c.Identity.parse(IDENTITY)
        git.refs[identity.generation_ref(3)] = next(iter(git.tags))
        with self.assertRaisesRegex(c.CustodyError, "generation gap"):
            c.read_live_state(IDENTITY, git)

    def test_tag_metadata_tamper_fails_closed(self):
        git, _ = self.acquire()
        sha = next(iter(git.tags))
        git.tags[sha]["message"] = git.tags[sha]["message"].replace("ACQUIRE_WHOLE", "RELEASE_WHOLE")
        with self.assertRaises(c.CustodyError):
            c.read_live_state(IDENTITY, git)

    def test_fabricated_receipt_digest_cannot_create_live_authority(self):
        git = MemoryGitHub()
        fake = c.compile_legacy_import(
            IDENTITY, prior_owner="ZLF-B8R3", prior_operation="USP-DATA-AI-RFP-ZLFB8R3-20260913",
            evidence_sha256=EVIDENCE, observed_at=T1,
        )
        self.assertFalse(fake["custody_authorized"])
        state = c.read_live_state(IDENTITY, git)
        self.assertIsNone(state.whole_owner)
        check = c.authorize_internal_work(IDENTITY, actor_owner="ZLF-B8R3", actor_operation="USP-DATA-AI-RFP-ZLFB8R3-20260913", lane="proposal", transport=git)
        self.assertFalse(check["internal_work_authorized"])

    def test_legacy_import_is_explicitly_non_authorizing(self):
        receipt = c.compile_legacy_import(
            IDENTITY, prior_owner="ZLF-B8R3", prior_operation="USP-DATA-AI-RFP-ZLFB8R3-20260913",
            evidence_sha256=EVIDENCE, observed_at=T1,
        )
        self.assertEqual(receipt["decision"], "LEGACY_CUSTODY_REQUIRES_CANONICAL_OWNER_SEED")
        self.assertFalse(receipt["custody_authorized"])
        self.assertFalse(receipt["external_send_authorized"])

    def test_release_invalidates_old_appended_receipt(self):
        git, acquire_receipt = self.acquire()
        c.release_whole(
            IDENTITY, actor_owner="ZLF-B8R3", actor_operation="USP-DATA-AI-RFP-ZLFB8R3-20260913",
            source_generation_sha256=SRC1, anchor_sha=ANCHOR1, observed_at=T2, transport=git,
        )
        self.assertTrue(c.verify_mutation_receipt(acquire_receipt))
        check = c.authorize_internal_work(IDENTITY, actor_owner="ZLF-B8R3", actor_operation="USP-DATA-AI-RFP-ZLFB8R3-20260913", lane="proposal", transport=git)
        self.assertFalse(check["internal_work_authorized"])

    def test_revoke_delegate(self):
        git, _ = self.acquire()
        c.set_delegate(
            IDENTITY, actor_owner="ZLF-B8R3", actor_operation="USP-DATA-AI-RFP-ZLFB8R3-20260913",
            lane="proposal", target_owner="ZTQ-K7M3", target_operation="USP-PROPOSAL-ZTQK7M3-20260913",
            source_generation_sha256=SRC1, anchor_sha=ANCHOR1, observed_at=T2, transport=git,
        )
        revoked = c.revoke_delegate(
            IDENTITY, actor_owner="ZLF-B8R3", actor_operation="USP-DATA-AI-RFP-ZLFB8R3-20260913",
            lane="proposal", source_generation_sha256=SRC1, anchor_sha=ANCHOR2, observed_at=T3, transport=git,
        )
        self.assertTrue(revoked["event_appended"])
        self.assertNotIn("proposal", c.read_live_state(IDENTITY, git).delegates)

    def test_unsupported_lane_and_delegate_noop_fail_without_git_mutation(self):
        git, _ = self.acquire()
        refs = dict(git.refs)
        bad = c.set_delegate(
            IDENTITY, actor_owner="ZLF-B8R3", actor_operation="USP-DATA-AI-RFP-ZLFB8R3-20260913",
            lane="root", target_owner="ZTQ-K7M3", target_operation="USP-PROPOSAL-ZTQK7M3-20260913",
            source_generation_sha256=SRC1, anchor_sha=ANCHOR1, observed_at=T2, transport=git,
        )
        self.assertFalse(bad["event_appended"])
        noop = c.set_delegate(
            IDENTITY, actor_owner="ZLF-B8R3", actor_operation="USP-DATA-AI-RFP-ZLFB8R3-20260913",
            lane="proposal", target_owner="ZLF-B8R3", target_operation="USP-DATA-AI-RFP-ZLFB8R3-20260913",
            source_generation_sha256=SRC1, anchor_sha=ANCHOR1, observed_at=T2, transport=git,
        )
        self.assertFalse(noop["event_appended"])
        self.assertEqual(refs, git.refs)

    def test_strict_duplicate_json_and_nonfinite_refused(self):
        with self.assertRaises(c.CustodyError):
            c.strict_json_loads('{"a":1,"a":2}')
        with self.assertRaises(c.CustodyError):
            c.strict_json_loads('{"a":NaN}')

    def test_receipt_tamper_detected(self):
        _, receipt = self.acquire()
        receipt = dict(receipt)
        receipt["reason"] = "forged"
        with self.assertRaisesRegex(c.CustodyError, "digest mismatch"):
            c.verify_mutation_receipt(receipt)

    def test_precondition_hold_receipt_is_verifiable_but_non_authorizing(self):
        git, _ = self.acquire()
        denied = c.acquire_whole(
            IDENTITY, actor_owner="ZNQ-R6M3", actor_operation="UTILITY-SAFETY-DATA-AI-RFP-ZNQR6M3-20260913",
            source_generation_sha256=SRC1, anchor_sha=ANCHOR1, observed_at=T2, transport=git,
        )
        self.assertFalse(denied["event_appended"])
        self.assertIsNone(denied["event_sha256"])
        self.assertTrue(c.verify_mutation_receipt(denied))
        self.assertFalse(denied["external_send_authorized"])

    def test_legacy_evidence_rejected_after_initial_generation(self):
        git, _ = self.acquire()
        identity = c.Identity.parse(IDENTITY)
        state = c.read_live_state(IDENTITY, git)
        with self.assertRaisesRegex(c.CustodyError, "legacy evidence allowed only"):
            c._plan_event(
                state, action="SET_DELEGATE", actor_owner="ZLF-B8R3",
                actor_operation="USP-DATA-AI-RFP-ZLFB8R3-20260913", target_owner="ZTQ-K7M3",
                target_operation="USP-PROPOSAL-ZTQK7M3-20260913", lane="proposal",
                source_generation_sha256=SRC1, anchor_sha=ANCHOR1, observed_at=T2,
                legacy_evidence_sha256=EVIDENCE,
            )
        self.assertEqual(identity.seam_sha256, state.identity.seam_sha256)

    def test_authority_ceiling_always_false(self):
        git, _ = self.acquire()
        auth = c.read_live_state(IDENTITY, git).authority
        self.assertFalse(auth["external_send_authorized"])
        self.assertFalse(auth["proposal_submission_authorized"])
        self.assertFalse(auth["buyer_acceptance_inferred"])
        self.assertFalse(auth["payment_or_revenue_inferred"])


if __name__ == "__main__":
    unittest.main()
